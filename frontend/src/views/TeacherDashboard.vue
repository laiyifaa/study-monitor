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

    <!-- 新建课程按钮 + 管理后台入口 + 编辑/删除课程 -->
    <div class="top-actions">
      <router-link to="/course-edit/0" class="btn primary">+ 新建课程</router-link>
      <router-link to="/admin" class="btn">管理后台</router-link>
      <template v-if="selectedCourseId">
        <router-link :to="`/course-edit/${selectedCourseId}`" class="btn">编辑课程</router-link>
        <button v-if="isAdmin" class="btn danger" @click="deleteCourse">删除课程</button>
      </template>
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
      <!-- ==================== 概览卡片：4格网格 ==================== -->
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

/** 课程列表 */
const courses = ref([])
const selectedCourseId = ref('')

/** 班级概览数据 */
const overview = ref({ total_students: 0, completed_students: 0, completion_rate: 0, require_minutes: 60 })
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

/* 概览卡片：4列等宽网格 */
.overview-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
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

/* 响应式：小屏幕下概览卡片改为2列 */
@media (max-width: 600px) {
  .overview-cards { grid-template-columns: repeat(2, 1fr); }
}
</style>
