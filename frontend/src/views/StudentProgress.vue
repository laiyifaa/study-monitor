<template>
  <div class="progress-page">
    <h2 class="page-title">我的学习进度</h2>

    <div v-if="loading" class="loading">加载中...</div>

    <div v-else-if="courses.length === 0" class="empty">暂无课程</div>

    <div v-else class="course-list">
      <div v-for="c in courses" :key="c.course_id" class="course-card">
        <div class="card-header">
          <h3>{{ c.title }}</h3>
          <span class="badge" :class="c.is_completed ? 'done' : 'ongoing'">
            {{ c.is_completed ? '已完成' : '学习中' }}
          </span>
        </div>
        <div class="progress-row">
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: c.completion_rate * 100 + '%' }"></div>
          </div>
          <span class="progress-text">{{ Math.round(c.completion_rate * 100) }}%</span>
        </div>
        <div class="info-row">
          <span>有效时长：{{ c.effective_minutes }} / {{ c.require_minutes }} 分钟</span>
          <span>视频进度：{{ c.video_progress }}%</span>
        </div>
        <div v-if="c.end_date" class="deadline">
          截止日期：{{ c.end_date }}
        </div>
        <router-link :to="`/learn/${c.course_id}`" class="continue-btn">
          {{ c.is_completed ? '继续学习' : '去学习' }}
        </router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../utils/api'

const courses = ref([])
const loading = ref(true)

onMounted(async () => {
  try {
    const res = await api.get('/stats/my-progress')
    if (res.data.code === 0) {
      courses.value = res.data.data
    }
  } catch (e) {
    console.error('获取进度失败:', e)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.progress-page { padding: 16px; max-width: 768px; margin: 0 auto; }
.page-title { font-size: 20px; margin-bottom: 16px; }
.loading, .empty { text-align: center; padding: 40px; color: #999; }
.course-card {
  background: #fff; border-radius: 10px; padding: 16px;
  margin-bottom: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.card-header h3 { font-size: 16px; }
.badge { font-size: 12px; padding: 2px 8px; border-radius: 10px; }
.badge.done { background: #f6ffed; color: #52c41a; }
.badge.ongoing { background: #e6f7ff; color: #1890ff; }
.progress-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.progress-bar { flex: 1; height: 8px; background: #f0f0f0; border-radius: 4px; overflow: hidden; }
.progress-fill { height: 100%; background: #1890ff; transition: width 0.3s; border-radius: 4px; }
.progress-text { font-size: 13px; font-weight: 600; color: #1890ff; min-width: 40px; }
.info-row { display: flex; justify-content: space-between; font-size: 13px; color: #666; }
.deadline { font-size: 12px; color: #ff4d4f; margin-top: 4px; }
.continue-btn {
  display: inline-block; margin-top: 10px; color: #1890ff; text-decoration: none;
  font-size: 14px; font-weight: 500;
}
</style>
