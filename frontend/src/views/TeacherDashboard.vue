<!--
  @模块：TeacherDashboard.vue — 教师统计看板
  @页面用途：教师视角的学习统计看板，包含4个概览卡片、ECharts时长分布直方图、学生详情表格，
            以及发送提醒/每日报告/导出Excel等操作按钮
  @数据流：
    1. 组件挂载 → 调用 GET /courses?status=active 获取课程列表，默认选中第一门课
    2. 选择/切换课程 → 调用 GET /stats/class-overview?course_id=X 获取班级统计数据
    3. 后端返回概览数据+学生列表 → 渲染卡片、图表、表格
    4. 操作按钮：
       - 发送学习提醒 → POST /notify/study-reminder
       - 发送每日报告 → POST /notify/daily-report
       - 导出Excel → GET /notify/export（blob 下载）
  @后端API：
    - GET /courses?status=active：获取有效课程列表
    - GET /stats/class-overview?course_id=X：获取指定课程的班级统计概览
    - POST /notify/study-reminder：向未完成学生发送钉钉学习提醒
    - POST /notify/daily-report：发送每日学习报告到钉钉群
    - GET /notify/export?course_id=X：导出学生进度Excel文件（blob）
  @依赖：
    - echarts：ECharts 图表库，渲染学习时长分布直方图
    - utils/api：封装了 axios 的请求工具
-->
<template>
  <div class="dashboard">
    <h2 class="page-title">学习统计看板</h2>

    <!-- API Key 区域：供智能体调用系统接口 -->
    <div class="api-key-section" v-if="isTeacherOrAdmin">
      <div class="api-key-header">
        <span class="api-key-label">智能体接入密钥</span>
        <button class="btn-sm" @click="generateApiKey" :disabled="generatingKey">
          {{ generatingKey ? '生成中...' : (apiKeyInfo.has_key ? '重新生成' : '生成密钥') }}
        </button>
      </div>
      <div class="api-key-hint" v-if="!apiKeyInfo.has_key">生成 API Key 后，可委托智能体（如 TeleClaw）自动查看统计、发送提醒等</div>
      <div class="api-key-display" v-else>
        <code v-if="apiKeyNewlyGenerated">{{ apiKeyFull }}</code>
        <code v-else>{{ apiKeyInfo.masked }}</code>
        <button class="btn-sm" @click="copyApiKey" v-if="apiKeyNewlyGenerated">复制</button>
        <span class="api-key-note" v-if="apiKeyNewlyGenerated">请立即复制保存，关闭页面后将无法查看完整密钥</span>
      </div>
    </div>

    <!-- 新建课程按钮 + 管理后台入口 + 编辑/删除课程 -->
    <div class="top-actions">
      <router-link to="/course-edit/0" class="btn primary">+ 新建课程</router-link>
      <router-link to="/" class="btn">预览课程</router-link>
      <router-link to="/admin" class="btn">管理后台</router-link>
      <router-link v-if="isOpsOrAdmin" to="/ops" class="btn info">运维面板</router-link>
      <template v-if="selectedCourseId">
        <router-link :to="`/course-edit/${selectedCourseId}`" class="btn">编辑课程</router-link>
        <router-link :to="`/homework/${selectedCourseId}`" class="btn success">作业管理</router-link>
        <router-link :to="`/feedback-overview/${selectedCourseId}`" class="btn">课程评价</router-link>
        <router-link :to="`/leaderboard/${selectedCourseId}`" class="btn">排行榜</router-link>
        <button v-if="isAdmin" class="btn danger" @click="deleteCourse">删除课程</button>
      </template>
      <!-- v4.0: 全局功能入口 -->
      <router-link to="/announcements" class="btn">公告管理</router-link>
      <router-link to="/grading-overview" class="btn">批改概览</router-link>
      <router-link to="/study-report" class="btn">学习报告</router-link>
      <button v-if="isTeacherOrAdmin" type="button" class="btn info agent-toggle" @click="toggleAgentDrawer">
        <span>智能体联通</span>
        <span class="btn-chevron">{{ agentDrawerOpen ? '▴' : '▾' }}</span>
      </button>
    </div>

    <!-- 智能体联通抽屉：教师/管理员可见 -->
    <div v-if="isTeacherOrAdmin" id="agent-connectivity" class="agent-drawer-shell" :class="{ open: agentDrawerOpen }">
      <div class="agent-drawer-panel">
        <div class="agent-header">
          <div>
            <div class="agent-title-row">
              <span class="agent-title">智能体联通</span>
              <span class="agent-pill" :class="agentToneClass(agentInfo.status)">{{ agentStatusLabel(agentInfo.status) }}</span>
            </div>
            <div class="agent-hint">查看批改智能体的联通状态和最近一次检测结果。</div>
          </div>
          <div class="agent-header-actions">
            <button class="btn-sm primary" @click="checkAgentConnectivity" :disabled="agentLoading">
              {{ agentLoading ? '检测中...' : '重新检测' }}
            </button>
            <button class="agent-close" type="button" @click="toggleAgentDrawer" aria-label="收起智能体联通">
              ▴
            </button>
          </div>
        </div>
        <div class="agent-card" :class="agentToneClass(agentInfo.status)">
          <div class="agent-row">
            <div class="agent-kv">
              接口
              <strong>{{ agentInfo.endpoint || '-' }}</strong>
            </div>
            <div class="agent-kv">
              响应
              <strong>{{ formatAgentStatusCode(agentInfo.status_code) }}</strong>
            </div>
            <div class="agent-kv">
              耗时
              <strong>{{ formatAgentLatency(agentInfo.latency_ms) }}</strong>
            </div>
          </div>
          <div class="agent-row agent-row-bottom">
            <div class="agent-kv">
              最近检测
              <strong>{{ formatAgentCheckedAt(agentInfo.checked_at) }}</strong>
            </div>
            <div class="agent-kv agent-kv-grow">
              提示
              <strong>{{ agentInfo.message || '-' }}</strong>
            </div>
          </div>
          <div v-if="agentInfo.error" class="agent-error">{{ agentInfo.error }}</div>
        </div>
      </div>
    </div>

    <!-- 课程选择下拉框：切换课程后触发 loadData 重新获取统计数据 -->
    <div class="selector">
      <select v-model="selectedCourseId" @change="loadData">
        <option value="">请选择课程</option>
        <!-- v-for 遍历课程列表生成下拉选项 -->
        <option v-for="c in courses" :key="c.id" :value="c.id">{{ c.title }}</option>
      </select>
    </div>

    <!-- 未选择课程时的提示 -->
    <div v-if="!selectedCourseId" class="empty">请选择一门课程查看统计</div>

    <!-- 已选择课程时显示统计内容 -->
    <template v-else>
      <!-- ==================== 概览卡片：5格网格 ==================== -->
      <div class="overview-cards">
        <div class="card">
          <div class="card-num">{{ overview.total_students }}</div>
          <div class="card-label">全班人数</div>
        </div>
        <div class="card">
          <!-- 已完成人数：绿色高亮 -->
          <div class="card-num done">{{ overview.completed_students }}</div>
          <div class="card-label">已完成</div>
        </div>
        <div class="card">
          <!-- 未完成人数：红色警告 -->
          <div class="card-num warn">{{ overview.total_students - overview.completed_students }}</div>
          <div class="card-label">未完成</div>
        </div>
        <div class="card">
          <!-- 完成率：蓝色主题色，保留1位小数 -->
          <div class="card-num primary">{{ overview.completed_students }}/{{ overview.total_students }}</div>
          <div class="card-label">完成率</div>
        </div>
        <div class="card">
          <!-- 小节数量 -->
          <div class="card-num">{{ overview.section_count || 0 }}</div>
          <div class="card-label">课程小节</div>
        </div>
      </div>

      <!-- ==================== 今日学习概况 ==================== -->
      <div class="today-section" v-if="todayData">
        <h3>今日学习概况</h3>
        <div class="today-cards">
          <div class="today-item">
            <span class="today-num">{{ todayData.active_students }}</span>
            <span class="today-label">今日学习人数</span>
          </div>
          <div class="today-item">
            <span class="today-num">{{ todayData.total_effective_minutes }}</span>
            <span class="today-label">总有效时长(分)</span>
          </div>
          <div class="today-item">
            <span class="today-num">{{ todayData.avg_effective_minutes }}</span>
            <span class="today-label">人均(分)</span>
          </div>
        </div>
      </div>

      <!-- ==================== ECharts 图表区域 ==================== -->
      <div class="chart-section">
        <h3>完成进度分布</h3>
        <!-- 图表挂载容器，由 renderChart() 初始化 ECharts 实例 -->
        <div ref="chartRef" class="chart-container"></div>
      </div>

      <!-- ==================== 学生详情表格 ==================== -->
      <div class="student-section">
        <div class="section-header">
          <h3>学生详情</h3>
          <div class="table-controls">
            <select v-model="selectedClass" class="class-select" @change="onFilterChange">
              <option value="">全部班级</option>
              <option v-for="cls in classList" :key="cls" :value="cls">{{ cls }}</option>
            </select>
            <input v-model="studentSearch" placeholder="搜索姓名..." class="search-input" @keyup.enter="onFilterChange" />
            <button class="btn-sm primary" @click="onFilterChange">搜索</button>
            <select v-model="sortBy" class="sort-select" @change="onFilterChange">
              <option value="name">按姓名</option>
              <option value="completion_desc">完成率 高→低</option>
              <option value="completion_asc">完成率 低→高</option>
              <option value="minutes_desc">有效时长 多→少</option>
            </select>
          </div>
        </div>
        <div class="table-wrapper">
          <table>
            <thead>
              <tr>
                <th style="width:32px"></th>
                <th>姓名</th>
                <th>班级</th>
                <th>有效时长(分)</th>
                <th>总时长(分)</th>
                <th>完成进度</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="s in students" :key="s.user_id">
                <tr :class="{ incomplete: !s.is_completed, clickable: true }" @click="toggleExpand(s)">
                  <td class="expand-cell">{{ expandedRow === s.user_id ? '▾' : '▸' }}</td>
                  <td>{{ s.name }}</td>
                  <td>{{ s.class_name || '-' }}</td>
                  <td>{{ s.effective_minutes }}</td>
                  <td>{{ s.require_minutes || '-' }}</td>
                  <td>{{ s.completed_sections }}/{{ s.total_sections }}</td>
                  <td>
                    <span class="tag" :class="s.is_completed ? 'done' : 'warn'">
                      {{ s.is_completed ? '已完成' : (s.completed_sections > 0 ? '未完成' : '未开始') }}
                    </span>
                  </td>
                </tr>
                <!-- 展开行：小节级进度 -->
                <tr v-if="expandedRow === s.user_id" class="expand-row">
                  <td :colspan="7">
                    <div v-if="loadingSections" class="loading-cell">加载中...</div>
                    <div v-else-if="sectionData.length > 0" class="section-detail-list">
                      <div v-for="sec in sectionData" :key="sec.section_id" class="section-detail-item">
                        <span class="sec-title">{{ sec.title }}</span>
                        <div class="sec-progress-bar">
                          <div class="sec-progress-fill" :class="{ completed: sec.is_completed }" :style="{ width: secPct(sec) + '%' }"></div>
                        </div>
                        <span class="sec-status-text">
                          {{ sec.is_completed ? '✓' : Math.round(secPct(sec)) + '%' }}
                        </span>
                      </div>
                    </div>
                    <div v-else class="loading-cell">暂无小节数据</div>
                  </td>
                </tr>
              </template>
              <!-- 无数据提示 -->
              <tr v-if="students.length === 0">
                <td colspan="7" class="empty-cell">暂无学生数据</td>
              </tr>
            </tbody>
          </table>
        </div>
        <!-- 分页控件 -->
        <div class="pagination" v-if="pagination.total > 0">
          <div class="page-info">第 {{ pagination.page }}/{{ pagination.total_pages }} 页，共 {{ pagination.total }} 人</div>
          <div class="page-controls">
            <button class="btn-sm" :disabled="pagination.page <= 1" @click="goPage(1)">首页</button>
            <button class="btn-sm" :disabled="pagination.page <= 1" @click="goPage(pagination.page - 1)">上一页</button>
            <button class="btn-sm" :disabled="pagination.page >= pagination.total_pages" @click="goPage(pagination.page + 1)">下一页</button>
            <button class="btn-sm" :disabled="pagination.page >= pagination.total_pages" @click="goPage(pagination.total_pages)">末页</button>
            <select v-model.number="pageSize" class="page-size-select" @change="onFilterChange">
              <option :value="10">10条/页</option>
              <option :value="20">20条/页</option>
              <option :value="50">50条/页</option>
            </select>
          </div>
        </div>
      </div>

      <!-- ==================== 操作按钮区域 ==================== -->
      <div class="actions">
        <!-- 发送学习提醒：发送中时禁用按钮防止重复提交 -->
        <button class="btn primary" @click="sendReminder" :disabled="sending">
          {{ sending ? '发送中...' : '发送学习提醒' }}
        </button>
        <!-- 发送每日报告：同样防重复提交 -->
        <button class="btn" @click="sendDailyReport" :disabled="sending">
          {{ sending ? '发送中...' : '发送每日报告' }}
        </button>
        <!-- 查看进度慢的学生 -->
        <button class="btn primary" @click="showSlowStudents" :disabled="slowLoading">
          {{ slowLoading ? '加载中...' : '查看进度慢的学生' }}
        </button>
        <!-- 导出Excel：浏览器端 blob 下载 -->
        <button class="btn" @click="exportExcel">导出 Excel</button>
      </div>

      <!-- ==================== 进度慢的学生弹窗 ==================== -->
      <div v-if="showSlowModal" class="modal-overlay" @click.self="showSlowModal = false">
        <div class="modal-content">
          <div class="modal-header">
            <h3>进度慢的学生</h3>
            <button class="modal-close" @click="showSlowModal = false">✕</button>
          </div>
          <div class="modal-body">
            <div class="slow-summary">
              已开播 <strong>{{ slowData.open_sections }}</strong> / {{ slowData.total_sections }} 个小节，
              进度慢阈值：已完成 ≤ <strong>{{ slowData.slow_threshold }}</strong> 小节
            </div>
            <div v-if="slowStudents.length === 0" class="empty">暂无进度慢的学生</div>
            <div v-else class="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>姓名</th>
                    <th>班级</th>
                    <th>已完成</th>
                    <th>总小节</th>
                    <th>已开播</th>
                    <th>有效时长(分)</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="s in slowStudents" :key="s.user_id">
                    <td>{{ s.name }}</td>
                    <td>{{ s.class_name || '-' }}</td>
                    <td>{{ s.completed_sections }}</td>
                    <td>{{ s.total_sections }}</td>
                    <td>{{ s.open_sections }}</td>
                    <td>{{ s.effective_minutes }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div class="modal-footer" v-if="slowStudents.length > 0">
            <button class="btn primary" @click="sendSlowReminder" :disabled="sendingSlowReminder">
              {{ sendingSlowReminder ? '发送中...' : '发送私信提醒' }}
            </button>
          </div>
        </div>
      </div>

      <!-- ==================== 发送结果弹窗 ==================== -->
      <div v-if="showSendResultModal" class="modal-overlay" @click.self="showSendResultModal = false">
        <div class="modal-content">
          <div class="modal-header">
            <h3>发送结果</h3>
            <button class="modal-close" @click="showSendResultModal = false">✕</button>
          </div>
          <div class="modal-body">
            <div class="send-result-summary">
              <span class="result-item success">成功 <strong>{{ sendResults.success }}</strong> 人</span>
              <span class="result-item fail">失败 <strong>{{ sendResults.fail }}</strong> 人</span>
              <span class="result-item skip">跳过 <strong>{{ sendResults.skip }}</strong> 人</span>
            </div>
            <div class="table-wrapper" v-if="sendResults.results && sendResults.results.length > 0" style="margin-top:12px">
              <table>
                <thead>
                  <tr>
                    <th>姓名</th>
                    <th>状态</th>
                    <th>原因</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in sendResults.results" :key="r.name">
                    <td>{{ r.name }}</td>
                    <td>
                      <span class="tag" :class="r.status === 'success' ? 'done' : r.status === 'fail' ? 'warn' : ''">
                        {{ r.status === 'success' ? '成功' : r.status === 'fail' ? '失败' : '跳过' }}
                      </span>
                    </td>
                    <td>{{ r.reason || '-' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import api from '../utils/api'
import { useAuthStore } from '../utils/auth'

const router = useRouter()
const auth = useAuthStore()
const isAdmin = computed(() => auth.user.value?.role === 'admin')
const isTeacherOrAdmin = computed(() => ['teacher', 'admin'].includes(auth.user.value?.role))
const isOpsOrAdmin = computed(() => auth.user.value?.role === 'admin')

/** API Key 状态 */
const apiKeyInfo = ref({ has_key: false, masked: '' })
const apiKeyFull = ref('')       // 仅在新生成时临时保存完整值
const apiKeyNewlyGenerated = ref(false)
const generatingKey = ref(false)
const agentDrawerOpen = ref(false)

const defaultAgentInfo = {
  configured: false,
  status: 'unknown',
  reachable: false,
  endpoint: '',
  status_code: null,
  latency_ms: null,
  checked_at: null,
  message: '尚未检测',
  error: '',
  age_seconds: null,
}
const agentInfo = ref(defaultAgentInfo)
const agentLoading = ref(false)

/** 课程列表 */
const courses = ref([])
const selectedCourseId = ref('')

/** 班级概览数据 */
const overview = ref({ total_students: 0, completed_students: 0, completion_rate: 0, require_minutes: 60, section_count: 0 })
const students = ref([])
const sending = ref(false)

/** 进度慢的学生弹窗 */
const showSlowModal = ref(false)
const slowStudents = ref([])
const slowLoading = ref(false)
const slowData = ref({ open_sections: 0, total_sections: 0, slow_threshold: 0 })

/** 发送私信提醒 */
const sendingSlowReminder = ref(false)
const showSendResultModal = ref(false)
const sendResults = ref({ results: [], total: 0, success: 0, fail: 0, skip: 0 })

/** 今日学习数据 */
const todayData = ref(null)

/** 学生表格搜索、排序、班级筛选 */
const studentSearch = ref('')
const sortBy = ref('name')
const selectedClass = ref('')
const classList = ref([])

/** 分页 */
const currentPage = ref(1)
const pageSize = ref(20)
const pagination = ref({ page: 1, page_size: 20, total: 0, total_pages: 0 })

/** 展开行：学生小节级进度 */
const expandedRow = ref(null)
const sectionData = ref([])
const loadingSections = ref(false)

/** ECharts */
const chartRef = ref(null)
let chartInstance = null

/** 学生列表直接使用后端返回的当前页数据（不再前端过滤排序） */

onMounted(async () => {
  const res = await api.get('/courses?status=active')
  if (res.data.code === 0) {
    courses.value = res.data.data
    if (courses.value.length > 0) {
      const preferred = courses.value.find(c => c.description && c.require_minutes >= 60)
      selectedCourseId.value = preferred ? preferred.id : courses.value[0].id
      await loadData()
    }
  }
  // 加载班级列表（班级筛选下拉框）
  await loadClassList()

  // 加载 API Key 状态
  if (isTeacherOrAdmin.value) {
    await loadApiKeyStatus()
    await loadAgentConnectivityStatus()
  }
})

watch(selectedCourseId, () => {
  currentPage.value = 1
  selectedClass.value = ''
  studentSearch.value = ''
  expandedRow.value = null
  loadData()
})

async function loadData() {
  if (!selectedCourseId.value) return
  try {
    const params = {
      course_id: selectedCourseId.value,
      page: currentPage.value,
      page_size: pageSize.value,
      sort_by: sortBy.value,
    }
    if (selectedClass.value) params.class_name = selectedClass.value
    if (studentSearch.value.trim()) params.search = studentSearch.value.trim()

    const [overviewRes, todayRes] = await Promise.all([
      api.get('/stats/class-overview', { params }),
      api.get('/stats/daily-summary', { params: { course_id: selectedCourseId.value } }).catch(() => null),
    ])

    if (overviewRes.data.code === 0) {
      overview.value = overviewRes.data.data
      students.value = overviewRes.data.data.students || []
      pagination.value = overviewRes.data.data.pagination || {}
    }

    if (todayRes && todayRes.data?.code === 0) {
      todayData.value = todayRes.data.data
    } else {
      todayData.value = null
    }

    // 切换条件后收起展开行
    expandedRow.value = null

    await nextTick()
    renderChart()
  } catch (e) {
    console.error('加载统计失败:', e)
  }
}

/** 筛选条件变化时：重置到第1页并重新加载 */
function onFilterChange() {
  currentPage.value = 1
  loadData()
}

/** 跳转到指定页码 */
function goPage(p) {
  currentPage.value = p
  loadData()
}

/** 加载班级列表 */
async function loadClassList() {
  try {
    const res = await api.get('/stats/class-list')
    if (res.data.code === 0) {
      classList.value = res.data.data || []
    }
  } catch {
    classList.value = []
  }
}

/** 展开/收起学生行，懒加载小节级进度 */
async function toggleExpand(student) {
  if (expandedRow.value === student.user_id) {
    expandedRow.value = null
    return
  }
  expandedRow.value = student.user_id
  loadingSections.value = true
  sectionData.value = []
  try {
    const res = await api.get('/stats/student-sections', {
      params: { course_id: selectedCourseId.value, user_id: student.user_id },
    })
    if (res.data.code === 0) {
      sectionData.value = res.data.data.sections || []
    }
  } catch (e) {
    console.error('加载小节进度失败:', e)
    sectionData.value = []
  } finally {
    loadingSections.value = false
  }
}

/** 计算小节完成百分比 */
function secPct(sec) {
  if (!sec.duration_seconds || sec.duration_seconds <= 0) {
    return sec.is_completed ? 100 : (sec.video_progress > 0 ? 100 : 0)
  }
  return Math.min((sec.video_progress / sec.duration_seconds) * 100, 100)
}

function renderChart() {
  if (!chartRef.value) return
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }

  // 基于后端返回的 completion_distribution 绘制完成进度分布图（0/N ~ N/N）
  const dist = overview.value.completion_distribution || {}
  const sectionCount = overview.value.section_count || 12

  // 构建标签和数据：0/12, 1/12, ..., 12/12
  const labels = []
  const values = []
  const colors = []
  for (let i = 0; i <= sectionCount; i++) {
    labels.push(`${i}/${sectionCount}`)
    values.push(dist[String(i)] || 0)
    // 颜色渐变：0档偏灰 → 中间偏黄 → 满档偏绿
    if (i === 0) colors.push('#d9d9d9')
    else if (i === sectionCount) colors.push('#52c41a')
    else colors.push(i >= sectionCount * 0.5 ? '#73d13d' : '#faad14')
  }

  chartInstance.setOption({
    tooltip: {
      trigger: 'axis',
      formatter: (params) => `${params[0].name}：${params[0].value} 人`,
    },
    grid: { left: 50, right: 20, top: 20, bottom: 40 },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: { fontSize: 11, interval: 0, rotate: labels.length > 13 ? 30 : 0 },
    },
    yAxis: { type: 'value', axisLabel: { fontSize: 11 }, name: '人数' },
    series: [{
      type: 'bar',
      data: values.map((v, i) => ({ value: v, itemStyle: { color: colors[i] } })),
      barMaxWidth: 30,
      itemStyle: { borderRadius: [4, 4, 0, 0] },
      label: { show: true, position: 'top', fontSize: 12 },
    }],
  })
}

function toggleAgentDrawer() {
  agentDrawerOpen.value = !agentDrawerOpen.value
}

function agentToneClass(status) {
  if (status === 'ok') return 'tone-ok'
  if (status === 'degraded') return 'tone-warn'
  if (status === 'down') return 'tone-down'
  if (status === 'unconfigured') return 'tone-muted'
  return 'tone-muted'
}

function agentStatusLabel(status) {
  const map = {
    ok: '联通',
    degraded: '响应异常',
    down: '不可达',
    unconfigured: '未配置',
    unknown: '未检测',
  }
  return map[status] || '未检测'
}

function formatAgentStatusCode(value) {
  return value === null || value === undefined ? '-' : `HTTP ${value}`
}

function formatAgentLatency(value) {
  return value === null || value === undefined ? '-' : `${value} ms`
}

function formatAgentCheckedAt(value) {
  if (!value) return '-'
  const d = new Date(value)
  if (!Number.isNaN(d.getTime())) {
    return d.toLocaleString('zh-CN', { hour12: false })
  }
  return String(value).replace('T', ' ').slice(0, 19)
}

async function loadAgentConnectivityStatus() {
  try {
    const res = await api.get('/ops/agent')
    if (res.data.code === 0) {
      agentInfo.value = res.data.data
    }
  } catch (e) {
    console.error('加载智能体联通状态失败:', e)
  }
}

async function checkAgentConnectivity() {
  if (agentLoading.value) return
  agentLoading.value = true
  try {
    const res = await api.post('/ops/agent/check')
    if (res.data.code === 0) {
      agentInfo.value = res.data.data
    }
  } catch (e) {
    alert('检测智能体联通失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    agentLoading.value = false
  }
}

/** 删除课程 */
async function deleteCourse() {
  if (!confirm('确定删除该课程？学生的历史学习数据将保留。')) return
  try {
    await api.delete(`/courses/${selectedCourseId.value}`)
    alert('课程已删除')
    selectedCourseId.value = ''
    // 重新加载课程列表
    const res = await api.get('/courses?status=active')
    if (res.data.code === 0) courses.value = res.data.data
    if (courses.value.length > 0) {
      selectedCourseId.value = courses.value[0].id
      await loadData()
    }
  } catch (e) {
    alert('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function sendReminder() {
  sending.value = true
  try {
    await api.post('/notify/study-reminder', { course_id: selectedCourseId.value })
    alert('提醒已发送')
  } catch (e) {
    alert('发送失败')
  } finally {
    sending.value = false
  }
}

async function showSlowStudents() {
  if (!selectedCourseId.value) return
  slowLoading.value = true
  try {
    const res = await api.get('/stats/slow-students', {
      params: { course_id: selectedCourseId.value },
    })
    if (res.data.code === 0) {
      slowData.value = res.data.data
      slowStudents.value = res.data.data.students || []
      showSlowModal.value = true
    }
  } catch (e) {
    alert('加载失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    slowLoading.value = false
  }
}

async function sendSlowReminder() {
  if (!selectedCourseId.value || slowStudents.value.length === 0) return
  sendingSlowReminder.value = true
  try {
    const res = await api.post('/notify/send-slow-reminder', { course_id: selectedCourseId.value })
    if (res.data.code === 0) {
      sendResults.value = res.data.data
      showSendResultModal.value = true
    } else {
      alert(res.data.msg || '发送失败')
    }
  } catch (e) {
    alert('发送失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    sendingSlowReminder.value = false
  }
}

async function sendDailyReport() {
  sending.value = true
  try {
    await api.post('/notify/daily-report', { course_id: selectedCourseId.value })
    alert('报告已发送')
  } catch (e) {
    alert('发送失败')
  } finally {
    sending.value = false
  }
}

async function exportExcel() {
  try {
    const res = await api.get('/notify/export', {
      params: { course_id: selectedCourseId.value },
      responseType: 'blob',
    })
    const blob = new Blob([res.data], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `study_report_${selectedCourseId.value}.xlsx`
    a.click()
    window.URL.revokeObjectURL(url)
  } catch (e) {
    alert('导出失败: ' + (e.response?.statusText || e.message))
  }
}

/** 加载 API Key 状态（是否已生成、掩码值）
 *  keepNewlyGenerated: 设为 true 时不清除 apiKeyNewlyGenerated 标记，
 *  避免刚生成完整 Key 后被 loadApiKeyStatus 立即覆盖为掩码
 */
async function loadApiKeyStatus(keepNewlyGenerated = false) {
  try {
    const res = await api.get('/auth/api-key')
    if (res.data.code === 0) {
      apiKeyInfo.value = res.data.data
      if (!keepNewlyGenerated) {
        apiKeyNewlyGenerated.value = false
      }
    }
  } catch { /* 忽略 */ }
}

/** 生成/重新生成 API Key */
async function generateApiKey() {
  if (apiKeyInfo.value.has_key) {
    if (!confirm('重新生成会使旧密钥立即失效，确定继续？')) return
  }
  generatingKey.value = true
  try {
    const res = await api.post('/auth/generate-api-key')
    if (res.data.code === 0) {
      apiKeyFull.value = res.data.data.api_key
      apiKeyNewlyGenerated.value = true
      await loadApiKeyStatus(true)
    }
  } catch (e) {
    alert('生成失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    generatingKey.value = false
  }
}

/** 复制 API Key 到剪贴板 */
function copyApiKey() {
  navigator.clipboard.writeText(apiKeyFull.value).then(() => {
    alert('已复制到剪贴板')
  }).catch(() => {
    // fallback
    const input = document.createElement('input')
    input.value = apiKeyFull.value
    document.body.appendChild(input)
    input.select()
    document.execCommand('copy')
    document.body.removeChild(input)
    alert('已复制到剪贴板')
  })
}
</script>

<style scoped>
/* 页面整体：左右留内边距，最大宽度960px居中，适配宽屏 */
.dashboard { padding: 16px; max-width: 960px; margin: 0 auto; }
.page-title { font-size: 20px; margin-bottom: 16px; }

/* 课程选择下拉框 */
.selector { margin-bottom: 16px; }
.selector select {
  width: 100%; padding: 10px; border: 1px solid #d9d9d9; border-radius: 6px;
  font-size: 14px; background: #fff;
}

/* 概览卡片：5列等宽网格 */
.overview-cards { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 20px; }
.card {
  background: #fff; border-radius: 8px; padding: 16px; text-align: center;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.card-num { font-size: 28px; font-weight: 700; color: #333; }
.card-num.done { color: #52c41a; }    /* 已完成：绿色 */
.card-num.warn { color: #ff4d4f; }    /* 未完成：红色 */
.card-num.primary { color: #1890ff; } /* 完成率：蓝色 */
.card-label { font-size: 13px; color: #999; margin-top: 4px; }

/* 图表区域 */
.chart-section { background: #fff; border-radius: 8px; padding: 16px; margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
.chart-section h3 { font-size: 16px; margin-bottom: 10px; }
.chart-container { height: 260px; }

/* 学生详情表格区域 */
.student-section { background: #fff; border-radius: 8px; padding: 16px; margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
.student-section h3 { font-size: 16px; margin-bottom: 10px; }

/* 表格横向滚动容器（移动端小屏适配） */
.table-wrapper { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { background: #f5f7fa; padding: 10px 8px; text-align: left; font-weight: 600; color: #666; }
td { padding: 10px 8px; border-bottom: 1px solid #f0f0f0; }

/* 未完成学生行：浅黄色背景高亮提醒 */
tr.incomplete { background: #fff7e6; }

/* 状态标签：圆角小胶囊，绿色=已完成，黄色=未完成 */
.tag { font-size: 12px; padding: 2px 8px; border-radius: 10px; }
.tag.done { background: #f6ffed; color: #52c41a; }
.tag.warn { background: #fff7e6; color: #faad14; }

/* 操作按钮区域：横向排列，自动换行 */
.actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 8px; }

/* 通用按钮样式 */
.btn {
  padding: 8px 20px; border: 1px solid #d9d9d9; border-radius: 6px;
  background: #fff; font-size: 14px; cursor: pointer;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn.primary { background: #1890ff; color: #fff; border-color: #1890ff; }
.btn.success { background: #52c41a; color: #fff; border-color: #52c41a; }
.btn.info { background: #722ed1; color: #fff; border-color: #722ed1; }
.btn.info:hover { background: #531dab; }
.btn.danger { color: #ff4d4f; border-color: #ffccc7; }
.btn.danger:hover { background: #fff1f0; }

.empty { text-align: center; padding: 40px; color: #999; }
.top-actions { margin-bottom: 16px; }
.top-actions .btn { text-decoration: none; display: inline-block; }

/* 智能体联通入口 */
.agent-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.btn-chevron {
  font-size: 11px;
  line-height: 1;
}

/* 智能体联通抽屉 */
.agent-drawer-shell {
  max-height: 0;
  opacity: 0;
  overflow: hidden;
  transform: translateY(-8px);
  margin-bottom: 0;
  transition: max-height 0.28s ease, opacity 0.2s ease, transform 0.28s ease, margin-bottom 0.28s ease;
}
.agent-drawer-shell.open {
  max-height: 420px;
  opacity: 1;
  transform: translateY(0);
  margin-bottom: 16px;
}
.agent-drawer-panel {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  border: 1px solid #f0f0f0;
}
.agent-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.agent-close {
  width: 28px;
  height: 28px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  background: #fff;
  color: #666;
  font-size: 14px;
  cursor: pointer;
}
.agent-close:hover {
  border-color: #1890ff;
  color: #1890ff;
}

.agent-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}
.agent-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.agent-title { font-size: 16px; font-weight: 600; color: #333; }
.agent-hint { margin-top: 4px; font-size: 12px; color: #999; }
.agent-pill {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
}
.tone-ok { background: #f6ffed; color: #52c41a; }
.tone-warn { background: #fff7e6; color: #faad14; }
.tone-down { background: #fff1f0; color: #ff4d4f; }
.tone-muted { background: #f5f5f5; color: #8c8c8c; }
.agent-card {
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 12px;
}
.agent-card.tone-ok { background: #f6ffed; border-color: #d9f7be; }
.agent-card.tone-warn { background: #fffbe6; border-color: #ffe58f; }
.agent-card.tone-down { background: #fff2f0; border-color: #ffccc7; }
.agent-card.tone-muted { background: #fafafa; border-color: #e8e8e8; }
.agent-row {
  display: flex;
  gap: 12px;
  justify-content: space-between;
  flex-wrap: wrap;
}
.agent-row-bottom { margin-top: 10px; }
.agent-kv { font-size: 12px; color: #999; min-width: 140px; }
.agent-kv strong {
  display: block;
  margin-top: 2px;
  font-size: 13px;
  color: #333;
  word-break: break-all;
}
.agent-kv-grow { flex: 1; min-width: 220px; }
.agent-error { margin-top: 8px; font-size: 12px; color: #cf1322; word-break: break-all; }

/* 今日概况 */
.today-section { background: #fff; border-radius: 8px; padding: 16px; margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
.today-section h3 { font-size: 16px; margin-bottom: 10px; }
.today-cards { display: flex; gap: 16px; }
.today-item { display: flex; flex-direction: column; align-items: center; }
.today-num { font-size: 22px; font-weight: 700; color: #1890ff; }
.today-label { font-size: 12px; color: #999; margin-top: 2px; }

/* 学生表格区域增强 */
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
.section-header h3 { font-size: 16px; margin: 0; }
.table-controls { display: flex; gap: 8px; }
.search-input {
  padding: 6px 10px; border: 1px solid #d9d9d9; border-radius: 4px;
  font-size: 13px; width: 140px; outline: none;
}
.search-input:focus { border-color: #1890ff; }
.sort-select {
  padding: 6px 8px; border: 1px solid #d9d9d9; border-radius: 4px;
  font-size: 12px; cursor: pointer;
}
.empty-cell { text-align: center; color: #999; padding: 30px; }

/* 未开始学生行：灰色底+红色标签 */
tr.not-started { background: #fafafa; }
.tag.not-started-tag { background: #f5f5f5; color: #999; }

/* 响应式：平板（768px以下） */
@media (max-width: 768px) {
  .dashboard { padding: 12px; }
  .overview-cards { grid-template-columns: repeat(3, 1fr); gap: 10px; }
  .card-num { font-size: 22px; }
  .top-actions { display: flex; flex-wrap: wrap; gap: 6px; }
  .top-actions .btn { font-size: 13px; padding: 7px 14px; }
  .agent-header { flex-direction: column; align-items: stretch; }
  .agent-header-actions { justify-content: flex-end; }
  .agent-drawer-panel { padding: 14px; }
  .today-cards { gap: 12px; }
  .chart-container { height: 220px; }
}

/* 响应式：手机（480px以下） */
@media (max-width: 480px) {
  .dashboard { padding: 10px; max-width: 100%; }
  .page-title { font-size: 17px; margin-bottom: 12px; }

  /* 概览卡片：5列 → 2列 */
  .overview-cards { grid-template-columns: repeat(2, 1fr); gap: 8px; }
  .card { padding: 12px 8px; }
  .card-num { font-size: 20px; }
  .card-label { font-size: 11px; }

  /* 顶部操作按钮栏：允许换行，缩小按钮 */
  .top-actions {
    display: flex; flex-wrap: wrap; gap: 6px;
    margin-bottom: 12px;
  }
  .top-actions .btn {
    font-size: 12px; padding: 6px 10px;
  }

  .agent-drawer-shell.open { margin-bottom: 12px; }
  .agent-drawer-panel { padding: 12px; }
  .agent-header-actions { width: 100%; justify-content: space-between; }
  .agent-row { flex-direction: column; gap: 8px; }
  .agent-kv { min-width: 0; }

  /* 今日概况卡片：纵向堆叠或紧凑排列 */
  .today-cards {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }
  .today-item {
    flex-direction: row;
    justify-content: space-between;
    padding: 8px 12px;
    background: #fafafa;
    border-radius: 6px;
  }
  .today-num { font-size: 18px; }

  /* 表格控制区：搜索框和排序下拉换行 */
  .section-header { flex-direction: column; align-items: stretch; gap: 8px; }
  .table-controls { width: 100%; flex-wrap: wrap; }
  .search-input { width: 100%; box-sizing: border-box; flex: 1 1 auto; min-width: 120px; }
  .sort-select { flex: 1 1 auto; min-width: 140px; }

  /* 图表高度缩减 */
  .chart-container { height: 200px; }

  /* 操作按钮区 */
  .actions { flex-direction: column; }
  .actions .btn { width: 100%; text-align: center; box-sizing: border-box; }

  /* API Key 区域 */
  .api-key-section { padding: 10px 12px; }
  .api-key-header { flex-direction: column; align-items: flex-start; gap: 4px; }
  .api-key-display { flex-direction: column; align-items: flex-start; }
}

/* API Key 区域 */
.api-key-section {
  background: #fffbe6; border: 1px solid #ffe58f; border-radius: 8px;
  padding: 12px 16px; margin-bottom: 16px;
}
.api-key-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.api-key-label { font-size: 14px; font-weight: 600; color: #8c6d1f; }
.api-key-hint { font-size: 12px; color: #a08040; }
.api-key-display { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.api-key-display code {
  background: #fff; border: 1px solid #d9d9d9; border-radius: 4px;
  padding: 4px 10px; font-size: 13px; color: #333; word-break: break-all;
}
.api-key-note { font-size: 12px; color: #ff4d4f; }
.btn-sm {
  padding: 4px 12px; border: 1px solid #d9d9d9; border-radius: 4px;
  background: #fff; font-size: 12px; cursor: pointer;
}
.btn-sm.primary { background: #1890ff; color: #fff; border-color: #1890ff; }
.btn-sm:disabled { opacity: 0.5; cursor: not-allowed; }

/* 展开行样式 */
tr.clickable { cursor: pointer; }
tr.clickable:hover { background: #f0f7ff; }
.expand-cell { color: #999; text-align: center; font-size: 12px; user-select: none; }
.expand-row td { background: #fafbfc !important; padding: 12px 16px; }
.loading-cell { text-align: center; color: #999; padding: 16px; }
.section-detail-list { display: flex; flex-direction: column; gap: 8px; }
.section-detail-item {
  display: flex; align-items: center; gap: 10px;
  padding: 6px 8px; background: #fff; border-radius: 4px; border: 1px solid #f0f0f0;
}
.sec-title { font-size: 13px; color: #333; flex-shrink: 0; width: 200px; }
.sec-progress-bar { flex: 1; height: 8px; background: #f0f0f0; border-radius: 4px; overflow: hidden; }
.sec-progress-fill { height: 100%; background: #1890ff; border-radius: 4px; transition: width 0.3s; }
.sec-progress-fill.completed { background: #52c41a; }
.sec-status-text { font-size: 12px; color: #999; width: 40px; text-align: right; flex-shrink: 0; }

/* 分页控件 */
.pagination {
  display: flex; justify-content: space-between; align-items: center;
  margin-top: 12px; flex-wrap: wrap; gap: 8px;
}
.page-info { font-size: 12px; color: #999; }
.page-controls { display: flex; gap: 6px; align-items: center; }
.page-size-select {
  padding: 4px 8px; border: 1px solid #d9d9d9; border-radius: 4px;
  font-size: 12px; cursor: pointer;
}

/* 班级筛选 */
.class-select {
  padding: 6px 10px; border: 1px solid #d9d9d9; border-radius: 4px;
  font-size: 13px; cursor: pointer;
}

/* 进度慢的学生弹窗 */
.modal-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.45); z-index: 1000;
  display: flex; align-items: center; justify-content: center;
}
.modal-content {
  background: #fff; border-radius: 12px; width: 90%; max-width: 700px;
  max-height: 80vh; display: flex; flex-direction: column;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
}
.modal-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 20px; border-bottom: 1px solid #f0f0f0;
}
.modal-header h3 { font-size: 17px; margin: 0; }
.modal-close {
  background: none; border: none; font-size: 20px; color: #999;
  cursor: pointer; padding: 0 4px; line-height: 1;
}
.modal-close:hover { color: #333; }
.modal-body { padding: 16px 20px; overflow-y: auto; }
.slow-summary {
  font-size: 13px; color: #666; margin-bottom: 16px;
  padding: 10px 14px; background: #fffbe6; border-radius: 6px;
  border: 1px solid #ffe58f;
}
.slow-summary strong { color: #cf1322; }

/* 弹窗底部按钮 */
.modal-footer {
  padding: 12px 20px; border-top: 1px solid #f0f0f0;
  display: flex; justify-content: flex-end; gap: 8px;
}

/* 发送结果汇总 */
.send-result-summary {
  display: flex; gap: 16px; flex-wrap: wrap;
  padding: 12px 16px; background: #fafafa; border-radius: 6px;
}
.result-item { font-size: 14px; }
.result-item strong { font-size: 18px; margin: 0 2px; }
.result-item.success { color: #52c41a; }
.result-item.fail { color: #ff4d4f; }
.result-item.skip { color: #999; }
</style>
