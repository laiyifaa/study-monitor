<template>
  <div class="dashboard">
    <h2 class="page-title">学习统计看板</h2>

    <!-- 课程选择 -->
    <div class="selector">
      <select v-model="selectedCourseId" @change="loadData">
        <option value="">请选择课程</option>
        <option v-for="c in courses" :key="c.id" :value="c.id">{{ c.title }}</option>
      </select>
    </div>

    <div v-if="!selectedCourseId" class="empty">请选择一门课程查看统计</div>

    <template v-else>
      <!-- 概览卡片 -->
      <div class="overview-cards">
        <div class="card">
          <div class="card-num">{{ overview.total_students }}</div>
          <div class="card-label">全班人数</div>
        </div>
        <div class="card">
          <div class="card-num done">{{ overview.completed_students }}</div>
          <div class="card-label">已完成</div>
        </div>
        <div class="card">
          <div class="card-num warn">{{ overview.total_students - overview.completed_students }}</div>
          <div class="card-label">未完成</div>
        </div>
        <div class="card">
          <div class="card-num primary">{{ (overview.completion_rate * 100).toFixed(1) }}%</div>
          <div class="card-label">完成率</div>
        </div>
      </div>

      <!-- 图表 -->
      <div class="chart-section">
        <h3>学习时长分布</h3>
        <div ref="chartRef" class="chart-container"></div>
      </div>

      <!-- 学生列表 -->
      <div class="student-section">
        <h3>学生详情</h3>
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
              <tr v-for="s in students" :key="s.user_id" :class="{ incomplete: !s.is_completed }">
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
            </tbody>
          </table>
        </div>
      </div>

      <!-- 操作按钮 -->
      <div class="actions">
        <button class="btn primary" @click="sendReminder" :disabled="sending">
          {{ sending ? '发送中...' : '发送学习提醒' }}
        </button>
        <button class="btn" @click="sendDailyReport" :disabled="sending">
          {{ sending ? '发送中...' : '发送每日报告' }}
        </button>
        <button class="btn" @click="exportExcel">导出 Excel</button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, watch } from 'vue'
import * as echarts from 'echarts'
import api from '../utils/api'

const courses = ref([])
const selectedCourseId = ref('')
const overview = ref({ total_students: 0, completed_students: 0, completion_rate: 0 })
const students = ref([])
const sending = ref(false)
const chartRef = ref(null)
let chartInstance = null

onMounted(async () => {
  const res = await api.get('/courses?status=active')
  if (res.data.code === 0) {
    courses.value = res.data.data
    if (courses.value.length > 0) {
      selectedCourseId.value = courses.value[0].id
      await loadData()
    }
  }
})

watch(selectedCourseId, () => loadData())

async function loadData() {
  if (!selectedCourseId.value) return
  try {
    const res = await api.get('/stats/class-overview', { params: { course_id: selectedCourseId.value } })
    if (res.data.code === 0) {
      overview.value = res.data.data
      students.value = res.data.data.students
      await nextTick()
      renderChart()
    }
  } catch (e) {
    console.error('加载统计失败:', e)
  }
}

function renderChart() {
  if (!chartRef.value) return
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }

  const completed = students.value.filter(s => s.is_completed).length
  const incomplete = students.value.length - completed

  // 时长分布直方图
  const buckets = [0, 0, 0, 0, 0] // <25%, 25-50%, 50-75%, 75-100%, >=100%
  students.value.forEach(s => {
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
      data: ['<25%', '25-50%', '50-75%', '75-100%', '已完成'],
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
.dashboard { padding: 16px; max-width: 960px; margin: 0 auto; }
.page-title { font-size: 20px; margin-bottom: 16px; }
.selector { margin-bottom: 16px; }
.selector select {
  width: 100%; padding: 10px; border: 1px solid #d9d9d9; border-radius: 6px;
  font-size: 14px; background: #fff;
}
.overview-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
.card {
  background: #fff; border-radius: 8px; padding: 16px; text-align: center;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.card-num { font-size: 28px; font-weight: 700; color: #333; }
.card-num.done { color: #52c41a; }
.card-num.warn { color: #ff4d4f; }
.card-num.primary { color: #1890ff; }
.card-label { font-size: 13px; color: #999; margin-top: 4px; }
.chart-section { background: #fff; border-radius: 8px; padding: 16px; margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
.chart-section h3 { font-size: 16px; margin-bottom: 10px; }
.chart-container { height: 260px; }
.student-section { background: #fff; border-radius: 8px; padding: 16px; margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
.student-section h3 { font-size: 16px; margin-bottom: 10px; }
.table-wrapper { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { background: #f5f7fa; padding: 10px 8px; text-align: left; font-weight: 600; color: #666; }
td { padding: 10px 8px; border-bottom: 1px solid #f0f0f0; }
tr.incomplete { background: #fff7e6; }
.tag { font-size: 12px; padding: 2px 8px; border-radius: 10px; }
.tag.done { background: #f6ffed; color: #52c41a; }
.tag.warn { background: #fff7e6; color: #faad14; }
.actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 8px; }
.btn {
  padding: 8px 20px; border: 1px solid #d9d9d9; border-radius: 6px;
  background: #fff; font-size: 14px; cursor: pointer;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn.primary { background: #1890ff; color: #fff; border-color: #1890ff; }
.empty { text-align: center; padding: 40px; color: #999; }

@media (max-width: 600px) {
  .overview-cards { grid-template-columns: repeat(2, 1fr); }
}
</style>
