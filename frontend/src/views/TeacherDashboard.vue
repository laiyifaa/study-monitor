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
      <router-link to="/" class="btn" target="_blank">预览课程</router-link>
      <router-link to="/admin" class="btn">管理后台</router-link>
      <router-link v-if="isOpsOrAdmin" to="/ops" class="btn info">运维面板</router-link>
      <template v-if="selectedCourseId">
        <router-link :to="`/course-edit/${selectedCourseId}`" class="btn">编辑课程</router-link>
        <router-link :to="`/homework/${selectedCourseId}`" class="btn success">作业管理</router-link>
        <router-link :to="`/leaderboard/${selectedCourseId}`" class="btn">排行榜</router-link>
        <button v-if="isAdmin" class="btn danger" @click="deleteCourse">删除课程</button>
      </template>
      <!-- v4.0: 全局功能入口 -->
      <router-link to="/announcements" class="btn">公告管理</router-link>
      <router-link to="/study-report" class="btn">学习报告</router-link>
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
          <div class="card-num primary">{{ (overview.completion_rate * 100).toFixed(1) }}%</div>
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
        <h3>学习时长分布</h3>
        <!-- 图表挂载容器，由 renderChart() 初始化 ECharts 实例 -->
        <div ref="chartRef" class="chart-container"></div>
      </div>

      <!-- ==================== 学生详情表格 ==================== -->
      <div class="student-section">
        <div class="section-header">
          <h3>学生详情</h3>
          <div class="table-controls">
            <input v-model="studentSearch" placeholder="搜索姓名..." class="search-input" />
            <select v-model="sortBy" class="sort-select">
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
                <th>姓名</th>
                <th>班级</th>
                <th>有效时长(分)</th>
                <th>要求(分)</th>
                <th>完成率</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <!-- 已有学习记录的学生（搜索+排序后） -->
              <tr v-for="s in filteredStudents" :key="s.user_id" :class="{ incomplete: !s.is_completed }">
                <td>{{ s.name }}</td>
                <td>{{ s.class_name || '-' }}</td>
                <td>{{ s.effective_minutes }}</td>
                <td>{{ s.require_minutes }}</td>
                <td>{{ (s.completion_rate * 100).toFixed(1) }}%</td>
                <td>
                  <span class="tag" :class="s.is_completed ? 'done' : 'warn'">
                    {{ s.is_completed ? '已完成' : '未完成' }}
                  </span>
                </td>
              </tr>
              <!-- 完全没开始的学生（不在 study_session 中） -->
              <tr v-for="s in notStartedStudents" :key="'ns-'+s.id" class="not-started">
                <td>{{ s.name }}</td>
                <td>{{ s.class_name || '-' }}</td>
                <td>0</td>
                <td>{{ overview.require_minutes || '-' }}</td>
                <td>0.0%</td>
                <td><span class="tag not-started-tag">未开始</span></td>
              </tr>
              <!-- 无数据提示 -->
              <tr v-if="filteredStudents.length === 0 && notStartedStudents.length === 0">
                <td colspan="6" class="empty-cell">暂无学生数据</td>
              </tr>
            </tbody>
          </table>
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
        <!-- 导出Excel：浏览器端 blob 下载 -->
        <button class="btn" @click="exportExcel">导出 Excel</button>
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
const isTeacherOrAdmin = computed(() => ['teacher', 'admin', 'ops'].includes(auth.user.value?.role))
const isOpsOrAdmin = computed(() => auth.user.value?.role === 'ops' || auth.user.value?.role === 'admin')

/** API Key 状态 */
const apiKeyInfo = ref({ has_key: false, masked: '' })
const apiKeyFull = ref('')       // 仅在新生成时临时保存完整值
const apiKeyNewlyGenerated = ref(false)
const generatingKey = ref(false)

/** 课程列表 */
const courses = ref([])
const selectedCourseId = ref('')

/** 班级概览数据 */
const overview = ref({ total_students: 0, completed_students: 0, completion_rate: 0, require_minutes: 60, section_count: 0 })
const students = ref([])
const sending = ref(false)

/** 今日学习数据 */
const todayData = ref(null)

/** 完全没开始的学生（不在 study_session 中，但属于该课程关联班级） */
const notStartedStudents = ref([])

/** 学生表格搜索和排序 */
const studentSearch = ref('')
const sortBy = ref('name')

/** ECharts */
const chartRef = ref(null)
let chartInstance = null

/**
 * 过滤+排序后的学生列表
 */
const filteredStudents = computed(() => {
  let list = [...students.value]

  // 搜索过滤
  if (studentSearch.value.trim()) {
    const kw = studentSearch.value.trim().toLowerCase()
    list = list.filter(s => s.name.toLowerCase().includes(kw))
  }

  // 排序
  switch (sortBy.value) {
    case 'completion_desc':
      list.sort((a, b) => b.completion_rate - a.completion_rate)
      break
    case 'completion_asc':
      list.sort((a, b) => a.completion_rate - b.completion_rate)
      break
    case 'minutes_desc':
      list.sort((a, b) => b.effective_minutes - a.effective_minutes)
      break
    default:
      list.sort((a, b) => a.name.localeCompare(b.name, 'zh'))
  }
  return list
})

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
  // 加载 API Key 状态
  if (isTeacherOrAdmin.value) loadApiKeyStatus()
})

watch(selectedCourseId, () => loadData())

async function loadData() {
  if (!selectedCourseId.value) return
  try {
    // 并行请求：班级概览 + 今日统计
    const [overviewRes, todayRes] = await Promise.all([
      api.get('/stats/class-overview', { params: { course_id: selectedCourseId.value } }),
      api.get('/stats/daily-summary', { params: { course_id: selectedCourseId.value } }).catch(() => null),
    ])

    if (overviewRes.data.code === 0) {
      overview.value = overviewRes.data.data
      students.value = overviewRes.data.data.students

      // 查找未开始的学生：获取所有学生，减去已有记录的
      await loadNotStartedStudents()
    }

    // 今日数据
    if (todayRes && todayRes.data?.code === 0) {
      todayData.value = todayRes.data.data
    } else {
      todayData.value = null
    }

    await nextTick()
    renderChart()
  } catch (e) {
    console.error('加载统计失败:', e)
  }
}

/**
 * 获取完全没开始学习的学生
 * 从管理接口拿所有学生，减去已有学习记录的
 */
async function loadNotStartedStudents() {
  try {
    const res = await api.get('/admin/users', { params: { role: 'student' } })
    if (res.data.code === 0) {
      const startedIds = new Set(students.value.map(s => s.user_id))
      notStartedStudents.value = res.data.data.filter(u => !startedIds.has(u.id))
    }
  } catch {
    notStartedStudents.value = []
  }
}

function renderChart() {
  if (!chartRef.value) return
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }

  const allStudents = [...students.value, ...notStartedStudents.value.map(s => ({ completion_rate: 0 }))]
  const buckets = [0, 0, 0, 0, 0]
  allStudents.forEach(s => {
    const r = s.completion_rate
    if (r < 0.25) buckets[0]++
    else if (r < 0.5) buckets[1]++
    else if (r < 0.75) buckets[2]++
    else if (r < 1) buckets[3]++
    else buckets[4]++
  })

  chartInstance.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: 'category',
      data: ['未开始(<25%)', '25-50%', '50-75%', '75-100%', '已完成'],
      axisLabel: { fontSize: 11 },
    },
    yAxis: { type: 'value', axisLabel: { fontSize: 11 } },
    series: [{
      type: 'bar',
      data: buckets,
      itemStyle: {
        color: (params) => {
          const colors = ['#ff4d4f', '#faad14', '#1890ff', '#52c41a', '#52c41a']
          return colors[params.dataIndex]
        },
        borderRadius: [4, 4, 0, 0],
      },
      barWidth: '50%',
    }],
  })
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
.btn.danger { color: #ff4d4f; border-color: #ffccc7; }
.btn.danger:hover { background: #fff1f0; }

.empty { text-align: center; padding: 40px; color: #999; }
.top-actions { margin-bottom: 16px; }
.top-actions .btn { text-decoration: none; display: inline-block; }

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
</style>
