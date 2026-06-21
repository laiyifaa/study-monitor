<!--
  @模块：CheckInCalendar.vue — 每日签到日历（v4.0 新增）
  @页面用途：GitHub 贡献图风格的学习签到展示，记录每天学习情况
-->
<template>
  <div class="checkin-page">
    <div class="back-nav">
      <a href="javascript:void(0)" @click="$router.back()" class="back-link">&larr; 返回</a>
    </div>
    <h2>学习签到</h2>

    <div class="year-selector">
      <button @click="year--; loadData()" :disabled="year <= 2024">&lt;</button>
      <span>{{ year }}年</span>
      <button @click="year++; loadData()" :disabled="year >= 2030">&gt;</button>
    </div>

    <div class="stats-summary">
      <div class="ss-item">
        <span class="ss-num">{{ totalDays }}</span>
        <span class="ss-label">学习天数</span>
      </div>
      <div class="ss-item">
        <span class="ss-num">{{ totalMinutes }}</span>
        <span class="ss-label">总时长(分)</span>
      </div>
      <div class="ss-item">
        <span class="ss-num">{{ maxStreak }}</span>
        <span class="ss-label">最长连续</span>
      </div>
    </div>

    <!-- 月份标签 -->
    <div class="month-tabs">
      <button v-for="m in 12" :key="m" :class="['month-tab', { active: month === m }]" @click="month = m; loadData()">
        {{ m }}月
      </button>
      <button :class="['month-tab', { active: month === null }]" @click="month = null; loadData()">全年</button>
    </div>

    <div v-if="loading" class="loading">加载中...</div>
    <div v-else class="calendar-grid">
      <div v-for="day in calendarDays" :key="day.date" class="day-cell" :class="getLevel(day)" :title="`${day.date}: ${day.effective_minutes}分钟`">
      </div>
    </div>

    <div class="legend">
      <span class="legend-label">少</span>
      <span class="legend-cell level-0"></span>
      <span class="legend-cell level-1"></span>
      <span class="legend-cell level-2"></span>
      <span class="legend-cell level-3"></span>
      <span class="legend-cell level-4"></span>
      <span class="legend-label">多</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../utils/api'

const year = ref(new Date().getFullYear())
const month = ref(null)
const days = ref([])
const loading = ref(true)

const dayMap = computed(() => {
  const map = {}
  days.value.forEach(d => { map[d.date] = d })
  return map
})

const totalDays = computed(() => days.value.filter(d => d.has_study).length)
const totalMinutes = computed(() => Math.round(days.value.reduce((sum, d) => sum + d.effective_minutes, 0)))
const maxStreak = computed(() => {
  let streak = 0, max = 0
  const sorted = [...days.value].sort((a, b) => a.date.localeCompare(b.date))
  sorted.forEach(d => {
    if (d.has_study) { streak++; max = Math.max(max, streak) }
    else { streak = 0 }
  })
  return max
})

// 生成当月/当年所有日期的格子
const calendarDays = computed(() => {
  const result = []
  let start, end
  if (month.value) {
    start = new Date(year.value, month.value - 1, 1)
    end = new Date(year.value, month.value, 0)
  } else {
    start = new Date(year.value, 0, 1)
    end = new Date(year.value, 11, 31)
  }
  for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
    const dateStr = d.toISOString().slice(0, 10)
    result.push(dayMap.value[dateStr] || { date: dateStr, has_study: false, effective_minutes: 0 })
  }
  return result
})

function getLevel(day) {
  if (!day.has_study) return 'level-0'
  if (day.effective_minutes < 15) return 'level-1'
  if (day.effective_minutes < 30) return 'level-2'
  if (day.effective_minutes < 60) return 'level-3'
  return 'level-4'
}

async function loadData() {
  loading.value = true
  try {
    const params = { year: year.value }
    if (month.value) params.month = month.value
    const res = await api.get('/stats/checkin-calendar', { params })
    if (res.data.code === 0) days.value = res.data.data.days
  } catch (e) {
    console.error('获取签到数据失败:', e)
  } finally {
    loading.value = false
  }
}

onMounted(() => loadData())
</script>

<style scoped>
.checkin-page { padding: 16px; max-width: 768px; margin: 0 auto; }
h2 { font-size: 20px; margin-bottom: 16px; }
.back-nav { margin-bottom: 12px; }
.back-link { color: #1890ff; font-size: 14px; text-decoration: none; cursor: pointer; }

.year-selector { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.year-selector button { border: 1px solid #d9d9d9; border-radius: 4px; background: #fff; padding: 4px 10px; cursor: pointer; }
.year-selector span { font-size: 16px; font-weight: 600; }

.stats-summary { display: flex; gap: 24px; margin-bottom: 20px; background: #fff; border-radius: 10px; padding: 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
.ss-item { text-align: center; }
.ss-num { display: block; font-size: 24px; font-weight: 700; color: #1890ff; }
.ss-label { font-size: 12px; color: #999; }

.month-tabs { display: flex; gap: 4px; margin-bottom: 12px; flex-wrap: wrap; }
.month-tab { padding: 4px 10px; border: 1px solid #d9d9d9; border-radius: 4px; background: #fff; font-size: 12px; cursor: pointer; }
.month-tab.active { background: #1890ff; color: #fff; border-color: #1890ff; }

.loading { text-align: center; padding: 40px; color: #999; }

.calendar-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 3px; margin-bottom: 12px; }
.day-cell { aspect-ratio: 1; border-radius: 2px; min-width: 12px; }
.level-0 { background: #ebedf0; }
.level-1 { background: #9be9a8; }
.level-2 { background: #40c463; }
.level-3 { background: #30a14e; }
.level-4 { background: #216e39; }

.legend { display: flex; align-items: center; gap: 4px; font-size: 12px; color: #999; }
.legend-cell { width: 12px; height: 12px; border-radius: 2px; }
.legend-label { font-size: 11px; }
</style>
