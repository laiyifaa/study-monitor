<!--
  @模块：CourseList.vue — 课程列表页
  @页面用途：学生登录后的首页，以卡片布局展示所有有效课程及学习进度
  @数据流：
    1. 组件挂载 → 并行请求课程列表 + 我的进度
    2. 将进度数据合并到课程卡片中，直接显示完成率
    3. 用户点击课程卡片 → 路由跳转至 /learn/:courseId 进入学习页
  @后端API：
    - GET /courses?status=active：获取所有有效课程
    - GET /stats/my-progress：获取当前学生的学习进度
-->
<template>
  <div class="course-list-page">
    <h2 class="page-title">课程列表</h2>

    <!-- 加载中状态提示 -->
    <div v-if="loading" class="loading">加载中...</div>

    <!-- 课程为空时的提示 -->
    <div v-else-if="courses.length === 0" class="empty">暂无课程</div>

    <!-- 课程卡片列表 -->
    <div v-else class="courses">
      <div v-for="c in courses" :key="c.id" class="course-card" @click="goLearn(c)">
        <div class="card-body">
          <div class="card-header-row">
            <h3>{{ c.title }}</h3>
            <!-- 学习状态标签：未开始/学习中/已完成 -->
            <span v-if="c.progress" class="status-badge" :class="statusClass(c.progress)">
              {{ statusText(c.progress) }}
            </span>
          </div>
          <p class="desc">{{ c.description || '暂无描述' }}</p>
          <div class="meta">
            <span>要求：{{ c.require_minutes }} 分钟</span>
            <span v-if="c.end_date">截止：{{ c.end_date }}</span>
          </div>
          <!-- 进度条：有进度数据时显示 -->
          <div v-if="c.progress && c.progress.effective_minutes > 0" class="mini-progress">
            <div class="mini-bar">
              <div class="mini-fill" :style="{ width: Math.min(c.progress.completion_rate * 100, 100) + '%' }"></div>
            </div>
            <span class="mini-text">{{ c.progress.effective_minutes }}/{{ c.require_minutes }}分钟</span>
          </div>
        </div>
        <div class="card-actions">
          <span class="action-btn" @click.stop="goLearn(c)">{{ c.progress?.is_completed ? '再看看' : '去学习' }}</span>
          <span class="action-btn homework" @click.stop="goHomework(c)">作业</span>
        </div>
      </div>
    </div>

    <!-- 底部导航栏 -->
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

/**
 * 组件挂载：并行获取课程列表和学习进度，合并到卡片中
 */
onMounted(async () => {
  try {
    // 并行请求课程和进度
    const [courseRes, progressRes] = await Promise.all([
      api.get('/courses?status=active'),
      api.get('/stats/my-progress').catch(() => ({ data: { code: 1, data: [] } })),
    ])

    let courseList = []
    if (courseRes.data.code === 0) {
      courseList = courseRes.data.data
    }

    // 构建进度映射：course_id → 进度数据
    const progressMap = {}
    if (progressRes.data.code === 0) {
      for (const p of progressRes.data.data) {
        progressMap[p.course_id] = p
      }
    }

    // 将进度数据合并到课程对象
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

/** 状态标签样式 */
function statusClass(p) {
  if (p.is_completed) return 'done'
  if (p.effective_minutes > 0) return 'ongoing'
  return 'not_started'
}

/** 状态标签文字 */
function statusText(p) {
  if (p.is_completed) return '已完成'
  if (p.effective_minutes > 0) return '学习中'
  return '未开始'
}

const goLearn = (course) => {
  router.push(`/learn/${course.id}`)
}

const goHomework = (course) => {
  router.push(`/student-homework/${course.id}`)
}
</script>

<style scoped>
.course-list-page { padding: 16px; padding-bottom: 70px; }
.page-title { font-size: 20px; margin-bottom: 16px; }
.loading, .empty { text-align: center; padding: 40px; color: #999; }

.course-card {
  background: #fff; border-radius: 10px; margin-bottom: 12px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06); overflow: hidden;
  display: flex; align-items: stretch; cursor: pointer;
}
.course-card:active { background: #f5f5f5; }

.card-body { flex: 1; padding: 14px 16px; }

/* 标题行：标题+状态标签 */
.card-header-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.card-header-row h3 { font-size: 15px; }

/* 状态标签 */
.status-badge {
  font-size: 11px; padding: 1px 8px; border-radius: 10px; flex-shrink: 0;
}
.status-badge.done { background: #f6ffed; color: #52c41a; }
.status-badge.ongoing { background: #e6f7ff; color: #1890ff; }
.status-badge.not_started { background: #f5f5f5; color: #999; }

.desc { font-size: 13px; color: #999; margin-bottom: 6px; }
.meta { display: flex; gap: 16px; font-size: 12px; color: #666; }

/* 迷你进度条 */
.mini-progress { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.mini-bar { flex: 1; height: 4px; background: #f0f0f0; border-radius: 2px; overflow: hidden; }
.mini-fill { height: 100%; background: #1890ff; border-radius: 2px; transition: width 0.3s; }
.mini-text { font-size: 11px; color: #999; white-space: nowrap; }

.card-actions {
  padding: 16px 18px;
  border-left: 1px solid #f0f0f0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
}

.action-btn {
  color: #1890ff;
  font-weight: 500;
  font-size: 14px;
  cursor: pointer;
}

.action-btn.homework {
  color: #52c41a;
  font-size: 13px;
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
