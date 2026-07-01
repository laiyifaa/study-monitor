<!--
  @模块：SectionFeedback.vue — 小节评价（v4.0 新增）
  @页面用途：学生对小节评价打分，查看其他同学评价和统计
-->
<template>
  <div class="feedback-page">
    <div class="back-nav">
      <a href="javascript:void(0)" @click="$router.back()" class="back-link">&larr; 返回</a>
    </div>
    <h2>课程评价</h2>

    <div v-if="loading" class="loading">加载中...</div>
    <template v-else>
      <!-- 评价统计 -->
      <div v-if="stats" class="stats-card">
        <div class="stats-avg">
          <span class="avg-num">{{ stats.avg_rating }}</span>
          <span class="avg-label">平均评分</span>
        </div>
        <div class="stats-dist">
          <div v-for="star in [5,4,3,2,1]" :key="star" class="dist-row">
            <span class="dist-star">{{ star }}星</span>
            <div class="dist-bar"><div class="dist-fill" :style="{ width: getDistWidth(star) }"></div></div>
            <span class="dist-count">{{ stats.rating_distribution[String(star)] || 0 }}</span>
          </div>
        </div>
        <div class="stats-total">共 {{ stats.total_count }} 条评价</div>
      </div>

      <!-- 我的评价 -->
      <div class="my-feedback-section">
        <h3>我的评价</h3>
        <div v-if="myFeedback">
          <div class="stars-display">
            <span v-for="i in 5" :key="i" class="star" :class="{ filled: i <= myFeedback.rating }">★</span>
          </div>
          <p v-if="myFeedback.comment" class="fb-comment">{{ myFeedback.comment }}</p>
        </div>
        <div v-else>
          <!-- 星级评分 -->
          <div class="star-rating">
            <span v-for="i in 5" :key="i" class="star-btn" :class="{ active: i <= myRating }" @click="myRating = i">★</span>
          </div>
          <textarea v-model="myComment" rows="3" placeholder="说说你的感受（可选）" maxlength="500"></textarea>
          <button class="btn primary" @click="submitFeedback" :disabled="submitting">
            {{ submitting ? '提交中...' : '提交评价' }}
          </button>
        </div>
      </div>

      <!-- 评价列表 -->
      <div class="feedback-list">
        <h3>全部评价 ({{ feedbackList.length }})</h3>
        <div v-if="feedbackList.length === 0" class="empty-hint">暂无评价</div>
        <div v-for="fb in feedbackList" :key="fb.id" class="feedback-item">
          <div class="fi-header">
            <span class="fi-name">{{ fb.user_name }}</span>
            <span class="fi-stars">
              <span v-for="i in 5" :key="i" :class="{ filled: i <= fb.rating }">★</span>
            </span>
          </div>
          <p v-if="fb.comment" class="fi-comment">{{ fb.comment }}</p>
          <span class="fi-time">{{ formatTime(fb.created_at) }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import api from '../utils/api'
import { useAuthStore } from '../utils/auth'

const route = useRoute()
const auth = useAuthStore()
const sectionId = parseInt(route.params.sectionId)

const loading = ref(true)
const myFeedback = ref(null)
const myRating = ref(5)
const myComment = ref('')
const submitting = ref(false)
const feedbackList = ref([])
const stats = ref(null)

function getDistWidth(star) {
  if (!stats.value) return '0%'
  const count = stats.value.rating_distribution[String(star)] || 0
  const total = stats.value.total_count || 1
  return Math.round(count / total * 100) + '%'
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

async function submitFeedback() {
  submitting.value = true
  try {
    const res = await api.post('/feedback', {
      section_id: sectionId,
      rating: myRating.value,
      comment: myComment.value,
    })
    if (res.data.code === 0) {
      myFeedback.value = res.data.data
      // 重新加载评价列表和统计
      await Promise.all([loadFeedbackList(), loadStats()])
    } else {
      alert(res.data.detail || '提交失败')
    }
  } catch (e) {
    alert('提交失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    submitting.value = false
  }
}

async function loadFeedbackList() {
  try {
    const res = await api.get('/feedback', { params: { section_id: sectionId } })
    if (res.data.code === 0) feedbackList.value = res.data.data
  } catch { /* ignore */ }
}

async function loadStats() {
  try {
    const res = await api.get('/feedback/stats', { params: { section_id: sectionId } })
    if (res.data.code === 0) stats.value = res.data.data
  } catch { /* ignore */ }
}

onMounted(async () => {
  try {
    // 并行加载：我的评价 + 评价列表 + 统计
    const promises = [
      api.get('/feedback/my', { params: { section_id: sectionId } }).catch(() => null),
      loadFeedbackList(),
    ]
    // 如果是教师，也加载统计
    if (auth.user.value?.role !== 'student') {
      promises.push(loadStats())
    } else {
      promises.push(loadStats())
    }

    const [myRes] = await Promise.all(promises)
    if (myRes && myRes.data?.code === 0) {
      myFeedback.value = myRes.data.data
    }
  } catch (e) {
    console.error('加载评价失败:', e)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.feedback-page { padding: 16px; max-width: 640px; margin: 0 auto; }
h2 { font-size: 20px; margin-bottom: 16px; }
h3 { font-size: 15px; margin-bottom: 10px; }
.back-nav { margin-bottom: 12px; }
.back-link { color: #1890ff; font-size: 14px; text-decoration: none; cursor: pointer; }
.loading { text-align: center; padding: 40px; color: #999; }

/* 统计卡片 */
.stats-card { background: #fff; border-radius: 10px; padding: 16px; margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); display: flex; gap: 20px; align-items: center; flex-wrap: wrap; }
.stats-avg { text-align: center; }
.avg-num { display: block; font-size: 36px; font-weight: 700; color: #fa8c16; }
.avg-label { font-size: 12px; color: #999; }
.stats-dist { flex: 1; min-width: 150px; }
.dist-row { display: flex; align-items: center; gap: 6px; margin-bottom: 3px; font-size: 12px; }
.dist-star { width: 28px; color: #999; }
.dist-bar { flex: 1; height: 6px; background: #f0f0f0; border-radius: 3px; overflow: hidden; }
.dist-fill { height: 100%; background: #fa8c16; border-radius: 3px; transition: width 0.3s; }
.dist-count { width: 20px; text-align: right; color: #999; }
.stats-total { width: 100%; font-size: 12px; color: #999; text-align: center; }

/* 我的评价 */
.my-feedback-section { background: #fff; border-radius: 10px; padding: 16px; margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
.star-rating { margin-bottom: 10px; }
.star-btn { font-size: 28px; color: #d9d9d9; cursor: pointer; transition: color 0.2s; }
.star-btn.active { color: #fa8c16; }
.star-btn:hover { color: #fa8c16; }
textarea { width: 100%; padding: 10px; border: 1px solid #d9d9d9; border-radius: 6px; font-size: 14px; box-sizing: border-box; margin-bottom: 10px; resize: vertical; }
textarea:focus { border-color: #1890ff; outline: none; }
.stars-display { margin-bottom: 6px; }
.star { font-size: 20px; color: #d9d9d9; }
.star.filled { color: #fa8c16; }
.fb-comment { font-size: 14px; color: #666; }

/* 评价列表 */
.feedback-list { margin-top: 16px; }
.empty-hint { text-align: center; color: #999; padding: 20px; font-size: 14px; }
.feedback-item { border-bottom: 1px solid #f0f0f0; padding: 10px 0; }
.fi-header { display: flex; align-items: center; gap: 8px; }
.fi-name { font-size: 13px; font-weight: 500; }
.fi-stars { font-size: 14px; color: #d9d9d9; }
.fi-stars .filled { color: #fa8c16; }
.fi-comment { font-size: 13px; color: #666; margin: 4px 0; }
.fi-time { font-size: 11px; color: #999; }

.btn { padding: 8px 20px; border: 1px solid #d9d9d9; border-radius: 6px; background: #fff; font-size: 14px; cursor: pointer; }
.btn.primary { background: #1890ff; color: #fff; border-color: #1890ff; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
