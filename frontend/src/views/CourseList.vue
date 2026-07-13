<!--
  @模块：CourseList.vue — 课程列表页
  @页面用途：学生登录后的首页，以卡片布局展示所有有效课程及学习进度
  @数据流：
    1. 组件挂载 → 并行请求课程列表 + 我的进度
    2. 将进度数据合并到课程卡片中
    3. 用户点击课程卡片 → 路由跳转至 /course/:courseId 进入课程详情
  @后端API：
    - GET /courses?status=active：获取所有有效课程（含 section_count）
    - GET /stats/my-progress：获取当前学生的学习进度
-->
<template>
  <div class="course-list-page">
    <h2 class="page-title">课程列表</h2>

    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="courses.length === 0" class="empty">暂无课程</div>

    <div v-else class="courses">
      <div v-for="c in courses" :key="c.id" class="course-card" @click="goDetail(c)">
        <div class="card-body">
          <div class="card-header-row">
            <h3>{{ c.title }}</h3>
            <span v-if="c.progress" class="status-badge" :class="statusClass(c.progress)">
              {{ statusText(c.progress) }}
            </span>
          </div>
          <p class="desc">{{ c.description || '暂无描述' }}</p>
          <div class="meta">
            <span>{{ c.section_count || 0 }} 个小节</span>
            <span>总时长：{{ c.total_duration_minutes || 0 }} 分钟</span>
            <span v-if="c.end_date">截止：{{ c.end_date.split(' ')[0] }}</span>
          </div>
          <!-- 进度条 -->
          <div v-if="c.progress && c.progress.effective_minutes > 0" class="mini-progress">
            <div class="mini-bar">
              <div class="mini-fill" :style="{ width: Math.min(c.progress.completion_rate * 100, 100) + '%' }"></div>
            </div>
            <span class="mini-text">{{ c.progress.effective_minutes }}/{{ c.total_duration_minutes || c.require_minutes }}分钟</span>
          </div>
          <!-- 小节学习进度 -->
          <div v-if="c.progress && c.progress.section_count > 0" class="section-progress">
            已学 {{ c.progress.completed_sections }}/{{ c.progress.section_count }} 小节
          </div>
        </div>
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
    const [courseRes, progressRes] = await Promise.all([
      api.get('/courses?status=active'),
      api.get('/stats/my-progress').catch(() => ({ data: { code: 1, data: [] } })),
    ])

    let courseList = []
    if (courseRes.data.code === 0) {
      courseList = courseRes.data.data
    }

    const progressMap = {}
    if (progressRes.data.code === 0) {
      for (const p of progressRes.data.data) {
        progressMap[p.course_id] = p
      }
    }

    courses.value = courseList.map(c => ({
      ...c,
      progress: progressMap[c.id] || null,
    }))
  } catch (e) {
    console.error('获取课程列表失败:', e)
  } finally {
    loading.value = false
  }
})

function statusClass(p) {
  if (p.is_completed) return 'done'
  if (p.effective_minutes > 0) return 'ongoing'
  return 'not_started'
}

function statusText(p) {
  if (p.is_completed) return '已完成'
  if (p.effective_minutes > 0) return '学习中'
  return '未开始'
}

const goDetail = (course) => {
  router.push(`/course/${course.id}`)
}
</script>

<style scoped>
.course-list-page { padding: 16px; padding-bottom: 70px; }
.page-title { font-size: 20px; margin-bottom: 16px; }
.loading, .empty { text-align: center; padding: 40px; color: #999; }

.course-card {
  background: #fff; border-radius: 10px; margin-bottom: 12px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06); overflow: hidden;
  cursor: pointer;
}
.course-card:active { background: #f5f5f5; }

.card-body { padding: 14px 16px; }

.card-header-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.card-header-row h3 { font-size: 15px; }

.status-badge { font-size: 11px; padding: 1px 8px; border-radius: 10px; flex-shrink: 0; }
.status-badge.done { background: #f6ffed; color: #52c41a; }
.status-badge.ongoing { background: #e6f7ff; color: #1890ff; }
.status-badge.not_started { background: #f5f5f5; color: #999; }

.desc { font-size: 13px; color: #999; margin-bottom: 6px; }
.meta { display: flex; gap: 16px; font-size: 12px; color: #666; }

.mini-progress { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.mini-bar { flex: 1; height: 4px; background: #f0f0f0; border-radius: 2px; overflow: hidden; }
.mini-fill { height: 100%; background: #1890ff; border-radius: 2px; transition: width 0.3s; }
.mini-text { font-size: 11px; color: #999; white-space: nowrap; }

.section-progress { font-size: 11px; color: #52c41a; margin-top: 4px; }

.bottom-nav {
  position: fixed; bottom: 0; left: 0; right: 0; height: 56px;
  background: #fff; display: flex; border-top: 1px solid #eee;
}
.nav-item {
  flex: 1; display: flex; align-items: center; justify-content: center;
  text-decoration: none; color: #999; font-size: 14px;
}
.nav-item.active { color: #1890ff; }

/* ====== 响应式：手机（480px以下） ====== */
@media (max-width: 480px) {
  .course-list-page { padding: 12px; padding-bottom: 60px; }
  .page-title { font-size: 17px; margin-bottom: 12px; }
  .card-body { padding: 12px; }
  .card-header-row h3 { font-size: 14px; }
  .meta { flex-wrap: wrap; gap: 8px 12px; }
  .desc { font-size: 12px; }
}
</style>
