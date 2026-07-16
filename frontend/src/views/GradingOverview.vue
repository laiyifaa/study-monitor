<template>
  <div class="overview-page">
    <div class="back-nav">
      <a href="javascript:void(0)" @click="$router.back()" class="back-link">&larr; 返回</a>
    </div>
    <div class="page-header-row">
      <h2>批改概览</h2>
      <div class="header-controls">
        <select v-model="selectedCourseId" @change="loadOverview" class="course-select">
          <option value="">全部课程</option>
          <option v-for="c in allCourses" :key="c.id" :value="c.id">{{ c.title }}</option>
        </select>
        <button class="btn-sm" @click="loadOverview" :disabled="loading">{{ loading ? '加载中...' : '刷新' }}</button>
        <label class="auto-refresh-label">
          <input type="checkbox" v-model="autoRefresh" @change="toggleAutoRefresh" />
          自动刷新
        </label>
      </div>
    </div>

    <div v-if="loading" class="loading">加载中...</div>
    <template v-else-if="summary.total_courses">
      <div class="summary-card">
        <div class="summary-item">
          <span class="summary-num">{{ summary.total_assignments }}</span>
          <span class="summary-label">总作业</span>
        </div>
        <div class="summary-item">
          <span class="summary-num">{{ summary.total_submissions }}</span>
          <span class="summary-label">总提交</span>
        </div>
        <div class="summary-item">
          <span class="summary-num success">{{ summary.graded }}</span>
          <span class="summary-label">已批改</span>
        </div>
        <div class="summary-item">
          <span class="summary-num warning">{{ summary.pending }}</span>
          <span class="summary-label">待批改</span>
        </div>
        <div class="summary-item">
          <span class="summary-num info">{{ summary.in_progress }}</span>
          <span class="summary-label">批改中</span>
        </div>
        <div class="summary-item">
          <span class="summary-num danger">{{ summary.failed }}</span>
          <span class="summary-label">失败</span>
        </div>
      </div>

      <div v-for="course in courses" :key="course.id" class="course-card">
        <div class="course-header" @click="toggleCourse(course.id)">
          <span class="course-title">{{ course.title }}</span>
          <span class="course-summary">
            {{ course.summary.graded }}/{{ course.summary.total_submissions }} 已批改
            <span v-if="course.summary.failed > 0" class="fail-badge">{{ course.summary.failed }} 失败</span>
            <span v-if="course.summary.in_progress > 0" class="progress-badge">{{ course.summary.in_progress }} 处理中</span>
          </span>
          <span class="chevron">{{ expandedCourses[course.id] ? '▾' : '▸' }}</span>
        </div>
        <div v-if="expandedCourses[course.id]" class="course-body">
          <div class="progress-bar-container">
            <div class="progress-bar">
              <div class="progress-segment success" :style="{ width: coursePercent(course, 'graded') + '%' }"></div>
              <div class="progress-segment info" :style="{ width: coursePercent(course, 'in_progress') + '%' }"></div>
              <div class="progress-segment danger" :style="{ width: coursePercent(course, 'failed') + '%' }"></div>
            </div>
            <span class="progress-label">{{ coursePercent(course, 'graded') }}%</span>
          </div>

          <div v-for="sec in course.sections" :key="sec.section_id" class="section-item">
            <div class="section-header-row">
              <div class="section-info">
                <span class="section-title">{{ sec.section_title }}</span>
                <span class="section-assignment">{{ sec.title }}</span>
              </div>
              <div class="section-status-group">
                <span class="status-tag" :class="sec.grading_status">{{ sec.grading_status === 'graded' ? '已批改' : '待批改' }}</span>
                <span class="mode-tag">{{ sec.grading_mode === 'auto' ? '智能' : sec.grading_mode }}</span>
              </div>
            </div>
            <div class="progress-bar-container small">
              <div class="progress-bar">
                <div class="progress-segment success" :style="{ width: sectionPercent(sec, 'graded') + '%' }"></div>
                <div class="progress-segment info" :style="{ width: sectionPercent(sec, 'in_progress') + '%' }"></div>
                <div class="progress-segment danger" :style="{ width: sectionPercent(sec, 'failed') + '%' }"></div>
              </div>
              <span class="progress-label">{{ sec.graded }}/{{ sec.total_submissions }}</span>
            </div>
            <div class="section-actions">
              <router-link :to="`/homework/${course.id}`" class="btn-sm">作业管理</router-link>
              <button v-if="!sec.grading_triggered && sec.total_submissions > 0" class="btn-sm primary" @click.stop="triggerGrading(sec)">触发批改</button>
            </div>
            <div v-if="sec.failed_tasks && sec.failed_tasks.length > 0" class="failed-tasks">
              <div class="failed-tasks-header" @click="toggleFailedTasks(sec.section_id)">
                <span class="fail-label">失败任务 ({{ sec.failed_tasks.length }})</span>
                <span class="chevron small">{{ expandedFailed[sec.section_id] ? '▾' : '▸' }}</span>
              </div>
              <div v-if="expandedFailed[sec.section_id]" class="failed-tasks-body">
                <div v-for="ft in sec.failed_tasks" :key="ft.submission_id" class="failed-task-item">
                  <span class="ft-student">{{ ft.student_name }}</span>
                  <span class="ft-error" :title="ft.error">{{ ft.error }}</span>
                  <span class="ft-retry">重试 {{ ft.retry_count }} 次</span>
                  <button class="btn-sm" :disabled="retryingId === ft.submission_id" @click.stop="retryTask(ft.submission_id, sec)">
                    {{ retryingId === ft.submission_id ? '重试中...' : '重新批改' }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
    <div v-else class="empty-hint">暂无数据</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../utils/api.js'

const route = useRoute()
const loading = ref(false)
const allCourses = ref([])
const courses = ref([])
const summary = ref({})
const selectedCourseId = ref(route.params.courseId || '')
const expandedCourses = ref({})
const expandedFailed = ref({})
const autoRefresh = ref(false)
const retryingId = ref(null)
let refreshTimer = null

const allCourseFilterList = computed(() => allCourses.value)

function toggleCourse(id) {
  expandedCourses.value[id] = !expandedCourses.value[id]
}

function toggleFailedTasks(id) {
  expandedFailed.value[id] = !expandedFailed.value[id]
}

function coursePercent(course, key) {
  const total = course.summary.total_submissions
  if (!total) return 0
  return Math.round((course.summary[key] || 0) / total * 100)
}

function sectionPercent(sec, key) {
  const total = sec.total_submissions
  if (!total) return 0
  return Math.round((sec[key] || 0) / total * 100)
}

async function loadCourses() {
  try {
    const res = await api.get('/courses')
    allCourses.value = res.data?.data || res.data || []
  } catch {
    allCourses.value = []
  }
}

async function loadOverview() {
  loading.value = true
  try {
    const params = {}
    if (selectedCourseId.value) params.course_id = selectedCourseId.value
    const res = await api.get('/homework/grading-overview', { params })
    const data = res.data?.data || {}
    courses.value = data.courses || []
    summary.value = data.summary || {}
  } catch (e) {
    alert('加载失败：' + (e.response?.data?.detail || e.message))
    courses.value = []
    summary.value = {}
  } finally {
    loading.value = false
  }
}

async function triggerGrading(sec) {
  try {
    const res = await api.post(`/homework/trigger-grading/${sec.assignment_id}`)
    const msg = res.data?.data?.message || '批改任务已启动'
    alert(msg)
    await loadOverview()
  } catch (e) {
    alert('触发失败：' + (e.response?.data?.detail || e.message))
  }
}

async function retryTask(submissionId, sec) {
  retryingId.value = submissionId
  try {
    await api.post(`/homework/regrade/${submissionId}`)
    alert('已重新触发批改')
    await loadOverview()
  } catch (e) {
    alert('重试失败：' + (e.response?.data?.detail || e.message))
  } finally {
    retryingId.value = null
  }
}

function toggleAutoRefresh() {
  if (autoRefresh.value) {
    refreshTimer = setInterval(loadOverview, 5000)
  } else {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

onMounted(async () => {
  await loadCourses()
  await loadOverview()
  if (allCourses.value.length > 0 && !selectedCourseId.value) {
    const firstId = allCourses.value[0].id
  }
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
})
</script>

<style scoped>
.overview-page {
  max-width: 1000px;
  margin: 0 auto;
  padding: 24px 20px;
}
.back-nav { margin-bottom: 12px; }
.back-link { color: #1890ff; text-decoration: none; font-size: 14px; }
.page-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 20px;
}
.page-header-row h2 { margin: 0; font-size: 22px; }
.header-controls {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.course-select {
  padding: 6px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  font-size: 14px;
  background: #fff;
}
.auto-refresh-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #666;
  cursor: pointer;
}
.summary-card {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 24px;
}
.summary-item {
  flex: 1;
  min-width: 100px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 16px 12px;
  text-align: center;
}
.summary-num {
  display: block;
  font-size: 28px;
  font-weight: 700;
  color: #333;
}
.summary-num.success { color: #52c41a; }
.summary-num.warning { color: #faad14; }
.summary-num.info { color: #1890ff; }
.summary-num.danger { color: #ff4d4f; }
.summary-label {
  font-size: 13px;
  color: #888;
  margin-top: 4px;
  display: block;
}
.course-card {
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  margin-bottom: 12px;
  overflow: hidden;
}
.course-header {
  display: flex;
  align-items: center;
  padding: 14px 16px;
  background: #fafafa;
  cursor: pointer;
  user-select: none;
}
.course-title { flex: 1; font-size: 16px; font-weight: 600; }
.course-summary { font-size: 13px; color: #888; margin-right: 12px; }
.fail-badge { color: #ff4d4f; font-weight: 600; margin-left: 8px; }
.progress-badge { color: #1890ff; font-weight: 600; margin-left: 8px; }
.chevron { font-size: 14px; color: #999; transition: transform .2s; }
.chevron.small { font-size: 12px; }
.course-body { padding: 0 16px 16px; }
.progress-bar-container {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 12px 0;
}
.progress-bar-container.small { margin: 8px 0; }
.progress-bar {
  flex: 1;
  height: 10px;
  background: #f0f0f0;
  border-radius: 5px;
  overflow: hidden;
  display: flex;
}
.progress-bar-container.small .progress-bar { height: 8px; }
.progress-segment { height: 100%; transition: width .3s; }
.progress-segment.success { background: #52c41a; }
.progress-segment.info { background: #1890ff; }
.progress-segment.danger { background: #ff4d4f; }
.progress-label { font-size: 13px; color: #666; white-space: nowrap; }
.section-item {
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 8px;
}
.section-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.section-info { display: flex; flex-direction: column; gap: 2px; }
.section-title { font-size: 14px; font-weight: 600; }
.section-assignment { font-size: 12px; color: #999; }
.section-status-group { display: flex; gap: 6px; }
.status-tag {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
  background: #f0f0f0;
  color: #666;
}
.status-tag.graded { background: #f6ffed; color: #52c41a; }
.mode-tag {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
  background: #e6f7ff;
  color: #1890ff;
}
.section-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
.btn-sm {
  padding: 4px 12px;
  font-size: 13px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  color: #333;
}
.btn-sm.primary {
  background: #1890ff;
  border-color: #1890ff;
  color: #fff;
}
.btn-sm:disabled { opacity: .5; cursor: not-allowed; }
.failed-tasks { margin-top: 8px; }
.failed-tasks-header {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 4px 0;
  user-select: none;
}
.fail-label { font-size: 13px; color: #ff4d4f; font-weight: 600; }
.failed-tasks-body {
  background: #fff2f0;
  border: 1px solid #ffccc7;
  border-radius: 4px;
  padding: 8px;
}
.failed-task-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
  font-size: 13px;
  flex-wrap: wrap;
}
.failed-task-item + .failed-task-item { border-top: 1px solid #ffccc7; }
.ft-student { font-weight: 600; min-width: 60px; }
.ft-error { flex: 1; color: #888; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 300px; }
.ft-retry { color: #999; font-size: 12px; white-space: nowrap; }
.loading { text-align: center; padding: 40px; color: #888; }
.empty-hint { text-align: center; padding: 60px; color: #999; font-size: 15px; }
</style>
