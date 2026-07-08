<!--
  @模块：FeedbackOverview.vue — 课程评价概览（教师/管理员）
  @页面用途：查看某课程下所有小节的评价统计，点击可进入查看评价详情
-->
<template>
  <div class="overview-page">
    <div class="back-nav">
      <a href="javascript:void(0)" @click="$router.back()" class="back-link">&larr; 返回</a>
    </div>
    <h2>课程评价概览</h2>

    <div v-if="loading" class="loading">加载中...</div>
    <template v-else>
      <div v-if="sections.length === 0" class="empty-hint">该课程暂无小节</div>
      <div v-else>
        <!-- 总览卡片 -->
        <div class="summary-card">
          <div class="summary-item">
            <span class="summary-num">{{ totalFeedbacks }}</span>
            <span class="summary-label">总评价数</span>
          </div>
          <div class="summary-item">
            <span class="summary-num">{{ overallAvg }}</span>
            <span class="summary-label">综合评分</span>
          </div>
          <div class="summary-item">
            <span class="summary-num">{{ ratedSections }}</span>
            <span class="summary-label">已评价小节</span>
          </div>
        </div>

        <!-- 小节评价列表 -->
        <div class="section-list">
          <div v-for="sec in sections" :key="sec.section_id" class="section-card" @click="goDetail(sec.section_id)">
            <div class="sc-header">
              <span class="sc-title">{{ sec.section_title }}</span>
              <span class="sc-arrow">→</span>
            </div>
            <div class="sc-stats">
              <div class="sc-rating">
                <span class="sc-stars">
                  <span v-for="i in 5" :key="i" class="star" :class="{ filled: i <= Math.round(sec.avg_rating) }">★</span>
                </span>
                <span class="sc-avg">{{ sec.avg_rating }}</span>
              </div>
              <span class="sc-count">{{ sec.total_count }} 条评价</span>
            </div>
            <!-- 迷你分布条 -->
            <div v-if="sec.total_count > 0" class="sc-dist">
              <div v-for="star in [5,4,3,2,1]" :key="star" class="mini-dist-row">
                <span class="mini-star">{{ star }}★</span>
                <div class="mini-bar"><div class="mini-fill" :style="{ width: getDistWidth(sec, star) }"></div></div>
                <span class="mini-count">{{ sec.rating_distribution[String(star)] || 0 }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../utils/api'

const route = useRoute()
const router = useRouter()
const courseId = parseInt(route.params.courseId)

const loading = ref(true)
const sections = ref([])

const totalFeedbacks = computed(() => sections.value.reduce((s, sec) => s + sec.total_count, 0))
const ratedSections = computed(() => sections.value.filter(sec => sec.total_count > 0).length)
const overallAvg = computed(() => {
  const rated = sections.value.filter(sec => sec.total_count > 0)
  if (rated.length === 0) return '—'
  const sum = rated.reduce((s, sec) => s + sec.avg_rating * sec.total_count, 0)
  const count = rated.reduce((s, sec) => s + sec.total_count, 0)
  return (sum / count).toFixed(1)
})

function getDistWidth(sec, star) {
  const count = sec.rating_distribution[String(star)] || 0
  const total = sec.total_count || 1
  return Math.round(count / total * 100) + '%'
}

function goDetail(sectionId) {
  router.push(`/feedback/${sectionId}`)
}

onMounted(async () => {
  try {
    const res = await api.get('/feedback/course-stats', { params: { course_id: courseId } })
    if (res.data.code === 0) {
      sections.value = res.data.data
    }
  } catch (e) {
    console.error('加载课程评价概览失败:', e)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.overview-page { padding: 16px; max-width: 640px; margin: 0 auto; }
h2 { font-size: 20px; margin-bottom: 16px; }
.back-nav { margin-bottom: 12px; }
.back-link { color: #1890ff; font-size: 14px; text-decoration: none; cursor: pointer; }
.loading { text-align: center; padding: 40px; color: #999; }
.empty-hint { text-align: center; color: #999; padding: 40px; font-size: 14px; }

/* 总览卡片 */
.summary-card {
  display: flex; gap: 16px; margin-bottom: 20px;
  background: #fff; border-radius: 10px; padding: 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.summary-item { flex: 1; text-align: center; }
.summary-num { display: block; font-size: 28px; font-weight: 700; color: #fa8c16; }
.summary-label { font-size: 12px; color: #999; }

/* 小节列表 */
.section-list { display: flex; flex-direction: column; gap: 12px; }
.section-card {
  background: #fff; border-radius: 10px; padding: 14px 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06); cursor: pointer;
  transition: box-shadow 0.2s;
}
.section-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.12); }
.sc-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.sc-title { font-size: 15px; font-weight: 500; }
.sc-arrow { color: #999; font-size: 14px; }
.sc-stats { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; }
.sc-rating { display: flex; align-items: center; gap: 4px; }
.sc-stars { font-size: 14px; color: #d9d9d9; }
.sc-stars .filled { color: #fa8c16; }
.sc-avg { font-size: 14px; font-weight: 600; color: #fa8c16; }
.sc-count { font-size: 12px; color: #999; }

/* 迷你分布 */
.sc-dist { padding-top: 6px; border-top: 1px solid #f5f5f5; }
.mini-dist-row { display: flex; align-items: center; gap: 4px; margin-bottom: 2px; font-size: 11px; }
.mini-star { width: 22px; color: #999; }
.mini-bar { flex: 1; height: 4px; background: #f0f0f0; border-radius: 2px; overflow: hidden; }
.mini-fill { height: 100%; background: #fa8c16; border-radius: 2px; }
.mini-count { width: 16px; text-align: right; color: #999; }
</style>
