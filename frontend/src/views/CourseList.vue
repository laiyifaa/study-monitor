<template>
  <div class="course-list-page">
    <h2 class="page-title">课程列表</h2>

    <div v-if="loading" class="loading">加载中...</div>

    <div v-else-if="courses.length === 0" class="empty">暂无课程</div>

    <div v-else class="courses">
      <div v-for="c in courses" :key="c.id" class="course-card" @click="goLearn(c)">
        <div class="card-body">
          <h3>{{ c.title }}</h3>
          <p class="desc">{{ c.description || '暂无描述' }}</p>
          <div class="meta">
            <span>要求：{{ c.require_minutes }} 分钟</span>
            <span v-if="c.end_date">截止：{{ c.end_date }}</span>
          </div>
        </div>
        <div class="card-action">去学习</div>
      </div>
    </div>

    <div class="bottom-nav">
      <router-link to="/" class="nav-item active">课程</router-link>
      <router-link to="/my-progress" class="nav-item">我的进度</router-link>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../utils/api'

const router = useRouter()
const courses = ref([])
const loading = ref(true)

onMounted(async () => {
  try {
    const res = await api.get('/courses?status=active')
    if (res.data.code === 0) {
      courses.value = res.data.data
    }
  } catch (e) {
    console.error('获取课程列表失败:', e)
  } finally {
    loading.value = false
  }
})

const goLearn = (course) => {
  router.push(`/learn/${course.id}`)
}
</script>

<style scoped>
.course-list-page { padding: 16px; padding-bottom: 70px; }
.page-title { font-size: 20px; margin-bottom: 16px; }
.loading, .empty { text-align: center; padding: 40px; color: #999; }
.course-card {
  background: #fff; border-radius: 10px; margin-bottom: 12px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06); overflow: hidden;
  display: flex; align-items: center; cursor: pointer;
}
.course-card:active { background: #f5f5f5; }
.card-body { flex: 1; padding: 16px; }
.card-body h3 { font-size: 16px; margin-bottom: 6px; }
.desc { font-size: 13px; color: #999; margin-bottom: 8px; }
.meta { display: flex; gap: 16px; font-size: 12px; color: #666; }
.card-action {
  padding: 16px 20px; color: #1890ff; font-weight: 500; font-size: 14px;
  border-left: 1px solid #f0f0f0;
}
.bottom-nav {
  position: fixed; bottom: 0; left: 0; right: 0; height: 56px;
  background: #fff; display: flex; border-top: 1px solid #eee;
}
.nav-item {
  flex: 1; display: flex; align-items: center; justify-content: center;
  text-decoration: none; color: #999; font-size: 14px;
}
.nav-item.active { color: #1890ff; }
</style>
