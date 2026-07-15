<!--
  @模块：StudyReport.vue — 学习总结报告（v4.0 新增）
  @页面用途：支持个人/班级/全平台三种维度的学习报告查看
-->
<template>
  <div class="report-page">
    <div class="back-nav">
      <a href="javascript:void(0)" @click="$router.back()" class="back-link">&larr; 返回</a>
    </div>
    <h2>学习报告</h2>

    <!-- 报告类型切换 -->
    <div class="type-tabs">
      <button :class="['tab', { active: reportType === 'personal' }]" @click="switchType('personal')">个人报告</button>
      <button v-if="isTeacherOrAdmin" :class="['tab', { active: reportType === 'class' }]" @click="switchType('class')">班级报告</button>
      <button v-if="isAdmin" :class="['tab', { active: reportType === 'platform' }]" @click="switchType('platform')">全平台报告</button>
    </div>

    <!-- 班级报告筛选 -->
    <div v-if="reportType === 'class'" class="class-filter">
      <select v-model="className" @change="loadReport">
        <option value="">请选择班级</option>
        <option v-for="cls in classes" :key="cls" :value="cls">{{ cls }}</option>
      </select>
    </div>

    <div v-if="loading" class="loading">加载中...</div>

    <!-- 个人报告 -->
    <template v-else-if="reportType === 'personal' && personalData">
      <div class="report-card">
        <h3>{{ personalData.user_name }} 的学习报告</h3>
        <div class="stat-grid">
          <div class="stat-item"><span class="stat-num">{{ getWatchedTotal() }}</span><span class="stat-label">总观看时长(分)</span></div>
          <div class="stat-item"><span class="stat-num">{{ personalData.total_sessions }}</span><span class="stat-label">学习次数</span></div>
        </div>
      </div>
      <!-- 课程进度列表 -->
      <div class="report-card">
        <h3>各课程进度</h3>
        <div v-for="c in personalData.course_progress" :key="c.course_id" class="course-progress-item">
          <div class="cpi-title">{{ c.title }}</div>
          <div class="cpi-bar"><div class="cpi-fill" :style="{ width: c.completion_rate * 100 + '%' }"></div></div>
          <div class="cpi-info">已观看 {{ getCourseWatchedMin(c) }} / 总时长 {{ c.require_minutes }} 分钟 · {{ c.is_completed ? '已完成' : '未完成' }}</div>
        </div>
      </div>
      <!-- 最近7天分布 -->
      <div v-if="personalData.daily_distribution_7d?.length" class="report-card">
        <h3>近7天学习分布</h3>
        <div class="daily-chart">
          <div v-for="d in personalData.daily_distribution_7d" :key="d.date" class="daily-bar">
            <div class="db-fill" :style="{ height: getDailyHeight(d.effective_minutes) }"></div>
            <span class="db-label">{{ d.date.slice(5) }}</span>
            <span class="db-val">{{ d.effective_minutes }}'</span>
          </div>
        </div>
      </div>
    </template>

    <!-- 班级报告 -->
    <template v-else-if="reportType === 'class' && classData">
      <div class="report-card">
        <h3>{{ classData.class_name }} 班级报告</h3>
        <div class="stat-grid">
          <div class="stat-item"><span class="stat-num">{{ classData.total_students }}</span><span class="stat-label">总人数</span></div>
          <div class="stat-item"><span class="stat-num">{{ classData.active_students }}</span><span class="stat-label">已学习</span></div>
          <div class="stat-item"><span class="stat-num">{{ classData.total_effective_minutes }}</span><span class="stat-label">总时长(分)</span></div>
          <div class="stat-item"><span class="stat-num">{{ (classData.participation_rate * 100).toFixed(1) }}%</span><span class="stat-label">参与率</span></div>
        </div>
      </div>
      <div class="report-card">
        <h3>学习时长排名</h3>
        <div v-for="(s, i) in classData.ranking?.slice(0, 20)" :key="s.user_id" class="rank-item">
          <span class="ri-order">{{ i + 1 }}</span>
          <span class="ri-name">{{ s.real_name || s.name }}</span>
          <span class="ri-min">{{ s.effective_minutes }}分</span>
        </div>
      </div>
    </template>

    <!-- 全平台报告 -->
    <template v-else-if="reportType === 'platform' && platformData">
      <div class="report-card">
        <h3>全平台报告</h3>
        <div class="stat-grid">
          <div class="stat-item"><span class="stat-num">{{ platformData.total_students }}</span><span class="stat-label">学生总数</span></div>
          <div class="stat-item"><span class="stat-num">{{ platformData.total_teachers }}</span><span class="stat-label">教师数</span></div>
          <div class="stat-item"><span class="stat-num">{{ platformData.total_courses }}</span><span class="stat-label">有效课程</span></div>
          <div class="stat-item"><span class="stat-num">{{ platformData.active_students }}</span><span class="stat-label">活跃学生</span></div>
          <div class="stat-item"><span class="stat-num">{{ platformData.total_effective_minutes }}</span><span class="stat-label">总时长(分)</span></div>
        </div>
      </div>
      <div v-if="platformData.class_stats?.length" class="report-card">
        <h3>各班级概况</h3>
        <div v-for="cls in platformData.class_stats" :key="cls.class_name" class="class-stat-item">
          <span class="cs-name">{{ cls.class_name }}</span>
          <span class="cs-active">{{ cls.active_students }}人学习</span>
          <span class="cs-min">{{ cls.total_effective_minutes }}分</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../utils/api'
import { useAuthStore } from '../utils/auth'

const auth = useAuthStore()
const isTeacherOrAdmin = computed(() => ['teacher', 'admin'].includes(auth.user.value?.role))
const isAdmin = computed(() => auth.user.value?.role === 'admin')

const reportType = ref('personal')
const loading = ref(false)
const personalData = ref(null)
const classData = ref(null)
const platformData = ref(null)
const className = ref('')
const classes = ref([])
const maxDailyMinutes = ref(60)

/** 个人报告：汇总各课程已观看分钟数 */
function getWatchedTotal() {
  if (!personalData.value?.course_progress) return 0
  return personalData.value.course_progress.reduce((sum, c) => sum + parseFloat(getCourseWatchedMin(c)), 0).toFixed(1)
}

/** 单课程已观看分钟数 = completion_rate × require_minutes */
function getCourseWatchedMin(c) {
  if (!c.completion_rate || !c.require_minutes) return '0'
  return (c.completion_rate * c.require_minutes).toFixed(1)
}

function getDailyHeight(minutes) {
  return Math.max((minutes / maxDailyMinutes.value) * 100, minutes > 0 ? 10 : 0) + '%'
}

function switchType(type) {
  reportType.value = type
  loadReport()
}

async function loadReport() {
  loading.value = true
  try {
    const params = { report_type: reportType.value }
    if (reportType.value === 'class' && className.value) params.class_name = className.value

    const res = await api.get('/stats/study-report', { params })
    if (res.data.code === 0) {
      const data = res.data.data
      if (reportType.value === 'personal') {
        personalData.value = data
        if (data.daily_distribution_7d?.length) {
          maxDailyMinutes.value = Math.max(...data.daily_distribution_7d.map(d => d.effective_minutes), 10)
        }
      } else if (reportType.value === 'class') {
        classData.value = data
      } else {
        platformData.value = data
      }
    }
  } catch (e) {
    console.error('获取报告失败:', e)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadReport()
  // 加载班级列表
  if (isTeacherOrAdmin.value) {
    try {
      const res = await api.get('/admin/classes')
      if (res.data.code === 0) classes.value = res.data.data.map(c => c.class_name)
    } catch { /* ignore */ }
  }
})
</script>

<style scoped>
.report-page { padding: 16px; max-width: 768px; margin: 0 auto; }
h2 { font-size: 20px; margin-bottom: 16px; }
h3 { font-size: 15px; margin-bottom: 10px; }
.back-nav { margin-bottom: 12px; }
.back-link { color: #1890ff; font-size: 14px; text-decoration: none; cursor: pointer; }
.loading { text-align: center; padding: 40px; color: #999; }

.type-tabs { display: flex; gap: 8px; margin-bottom: 16px; }
.tab { padding: 6px 16px; border: 1px solid #d9d9d9; border-radius: 6px; background: #fff; font-size: 14px; cursor: pointer; }
.tab.active { background: #1890ff; color: #fff; border-color: #1890ff; }

.class-filter { margin-bottom: 16px; }
.class-filter select { width: 100%; padding: 8px 12px; border: 1px solid #d9d9d9; border-radius: 6px; font-size: 14px; background: #fff; }

.report-card { background: #fff; border-radius: 10px; padding: 16px; margin-bottom: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }

.stat-grid { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 10px; }
.stat-item { text-align: center; min-width: 60px; }
.stat-num { display: block; font-size: 22px; font-weight: 700; color: #1890ff; }
.stat-label { font-size: 12px; color: #999; }

/* 课程进度 */
.course-progress-item { margin-bottom: 10px; }
.cpi-title { font-size: 14px; margin-bottom: 4px; }
.cpi-bar { height: 6px; background: #f0f0f0; border-radius: 3px; overflow: hidden; margin-bottom: 3px; }
.cpi-fill { height: 100%; background: linear-gradient(90deg, #1890ff, #52c41a); border-radius: 3px; transition: width 0.3s; }
.cpi-info { font-size: 12px; color: #999; }

/* 7天柱状图 */
.daily-chart { display: flex; gap: 6px; align-items: flex-end; height: 100px; }
.daily-bar { flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; position: relative; }
.db-fill { width: 100%; background: #1890ff; border-radius: 3px 3px 0 0; position: absolute; bottom: 20px; transition: height 0.3s; }
.db-label { position: absolute; bottom: 4px; font-size: 10px; color: #999; }
.db-val { position: absolute; top: 0; font-size: 10px; color: #666; }

/* 排名列表 */
.rank-item { display: flex; align-items: center; gap: 10px; padding: 6px 0; border-bottom: 1px solid #f0f0f0; }
.ri-order { width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; border-radius: 50%; background: #f0f0f0; font-size: 12px; font-weight: 600; }
.ri-name { flex: 1; font-size: 14px; }
.ri-min { font-size: 13px; color: #1890ff; font-weight: 500; }

/* 班级概况 */
.class-stat-item { display: flex; align-items: center; gap: 12px; padding: 6px 0; border-bottom: 1px solid #f0f0f0; }
.cs-name { flex: 1; font-size: 14px; }
.cs-active { font-size: 12px; color: #666; }
.cs-min { font-size: 13px; color: #1890ff; }
</style>
