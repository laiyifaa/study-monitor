<!--
  @模块：Leaderboard.vue — 学习排行榜（v4.0 新增）
  @页面用途：按课程维度展示有效学习时长排名，类似游戏排行榜
-->
<template>
  <div class="leaderboard-page">
    <div class="back-nav">
      <a href="javascript:void(0)" @click="$router.back()" class="back-link">&larr; 返回</a>
    </div>
    <h2>学习排行榜</h2>

    <!-- 班级筛选 -->
    <div class="filter-bar">
      <select v-model="className" @change="loadData">
        <option value="">全部班级</option>
        <option v-for="cls in classes" :key="cls" :value="cls">{{ cls }}</option>
      </select>
    </div>

    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="ranking.length === 0" class="empty">暂无学习数据</div>
    <div v-else class="ranking-list">
      <!-- 前三名特殊样式 -->
      <div v-for="s in ranking" :key="s.user_id" class="rank-item" :class="getRankClass(s.rank)">
        <div class="ri-rank">
          <span v-if="s.rank <= 3" class="rank-medal">{{ ['🥇','🥈','🥉'][s.rank - 1] }}</span>
          <span v-else class="rank-num">{{ s.rank }}</span>
        </div>
        <div class="ri-info">
          <div class="ri-name">{{ s.real_name || s.name }}</div>
          <div v-if="s.class_name" class="ri-class">{{ s.class_name }}</div>
        </div>
        <div class="ri-minutes">{{ s.watched_minutes ?? s.effective_minutes }} 分钟</div>
      </div>
    </div>

    <div class="course-title">{{ courseTitle }}</div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../utils/api'

const route = useRoute()
const courseId = parseInt(route.params.courseId)

const ranking = ref([])
const courseTitle = ref('')
const className = ref('')
const classes = ref([])
const loading = ref(true)

function getRankClass(rank) {
  if (rank === 1) return 'gold'
  if (rank === 2) return 'silver'
  if (rank === 3) return 'bronze'
  return ''
}

async function loadData() {
  loading.value = true
  try {
    const params = { course_id: courseId }
    if (className.value) params.class_name = className.value
    const res = await api.get('/stats/leaderboard', { params })
    if (res.data.code === 0) {
      ranking.value = res.data.data.ranking
      courseTitle.value = res.data.data.course_title
    }
  } catch (e) {
    console.error('获取排行榜失败:', e)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadData()
  // 获取班级列表用于筛选
  try {
    const res = await api.get('/admin/classes')
    if (res.data.code === 0) {
      classes.value = res.data.data.map(c => c.class_name)
    }
  } catch { /* ignore */ }
})
</script>

<style scoped>
.leaderboard-page { padding: 16px; max-width: 640px; margin: 0 auto; }
h2 { font-size: 20px; margin-bottom: 16px; }
.back-nav { margin-bottom: 12px; }
.back-link { color: #1890ff; font-size: 14px; text-decoration: none; cursor: pointer; }

.filter-bar { margin-bottom: 16px; }
.filter-bar select { width: 100%; padding: 8px 12px; border: 1px solid #d9d9d9; border-radius: 6px; font-size: 14px; background: #fff; }

.loading, .empty { text-align: center; padding: 40px; color: #999; }
.course-title { text-align: center; font-size: 13px; color: #999; margin-top: 16px; }

.rank-item {
  display: flex; align-items: center; gap: 12px; padding: 12px 14px;
  background: #fff; border-radius: 8px; margin-bottom: 6px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}
.rank-item.gold { background: #fffbe6; border: 1px solid #ffe58f; }
.rank-item.silver { background: #f5f5f5; border: 1px solid #e8e8e8; }
.rank-item.bronze { background: #fff7e6; border: 1px solid #ffe7ba; }

.ri-rank { flex-shrink: 0; width: 32px; text-align: center; }
.rank-medal { font-size: 22px; }
.rank-num { font-size: 16px; font-weight: 600; color: #999; }

.ri-info { flex: 1; }
.ri-name { font-size: 15px; font-weight: 500; }
.ri-class { font-size: 12px; color: #999; }

.ri-minutes { font-size: 14px; font-weight: 600; color: #1890ff; white-space: nowrap; }
</style>
