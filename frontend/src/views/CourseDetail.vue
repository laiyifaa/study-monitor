<!--
  @模块：CourseDetail.vue — 课程详情页（小节列表）
  @页面用途：展示课程信息和所有小节，学生可点击小节进入学习，
            教师可看到小节管理入口。
  @数据流：
    1. 组件挂载 → 调用 GET /courses/:courseId（含 sections 列表）
    2. 并行获取当前用户的学习进度 GET /stats/my-progress
    3. 小节卡片展示进度，点击进入 /learn/:courseId/:sectionId
  @路由：/course/:courseId
-->
<template>
  <div class="course-detail-page">
    <!-- 返回导航 -->
    <div class="back-nav">
      <a href="javascript:void(0)" @click="$router.back()" class="back-link">&larr; 返回课程列表</a>
    </div>

    <div v-if="loading" class="loading">加载中...</div>

    <template v-else-if="course">
      <!-- 课程信息卡片 -->
      <div class="course-info-card">
        <h2 class="course-title">{{ course.title }}</h2>
        <p v-if="course.description" class="course-desc">{{ course.description }}</p>
        <div class="course-meta">
          <span>总时长：{{ course.total_duration_minutes || course.require_minutes }} 分钟</span>
          <span>{{ course.section_count }} 个小节</span>
          <span v-if="course.end_date">截止：{{ course.end_date.split(' ')[0] }}</span>
        </div>
        <!-- 课程总进度 -->
        <div v-if="overallProgress !== null" class="total-progress">
          <div class="tp-header">
            <span>学习进度</span>
            <span class="tp-pct">{{ Math.round(overallProgress.completion_rate * 100) }}%</span>
          </div>
          <div class="tp-bar">
            <div class="tp-fill" :style="{ width: Math.min(overallProgress.completion_rate * 100, 100) + '%' }"></div>
          </div>
          <div class="tp-text">{{ overallProgress.effective_minutes }} / {{ course.total_duration_minutes || course.require_minutes }} 分钟</div>
        </div>
      </div>

      <!-- 小节列表 -->
      <div class="section-list">
        <div class="sl-header">小节列表</div>
        <div v-if="sections.length === 0" class="empty-section">暂无小节，请联系教师添加</div>
        <div
          v-for="sec in sections"
          :key="sec.id"
          class="section-card"
          @click="goLearn(sec)"
        >
          <div class="sc-left">
            <span class="sc-order">{{ sec.sort_order || 1 }}</span>
          </div>
          <div class="sc-body">
            <div class="sc-title">{{ sec.title }}</div>
            <div class="sc-meta">
              <span v-if="sec.video_type === 'local'">本地上传</span>
              <span v-else>外部链接</span>
              <span v-if="sec.duration_seconds > 0">{{ formatDuration(sec.duration_seconds) }}</span>
              <!-- v4.0: 开播时间状态 — 教师/管理员显示"预览" -->
              <span v-if="sec.open_time && !isSectionOpen(sec) && !isTeacherOrAdmin" class="sc-locked">未开播 {{ formatOpenTime(sec.open_time) }}</span>
              <span v-if="sec.open_time && !isSectionOpen(sec) && isTeacherOrAdmin" class="sc-preview">未开播 {{ formatOpenTime(sec.open_time) }}</span>
            </div>
            <!-- 小节进度条 -->
            <div v-if="getSectionProgress(sec.id)" class="sc-progress">
              <div class="sc-bar">
                <div class="sc-fill" :style="{ width: Math.min((getSectionProgress(sec.id).effective_minutes / (getSectionProgress(sec.id).require_minutes || 1)) * 100, 100) + '%' }"></div>
              </div>
              <span class="sc-pct">{{ getSectionProgress(sec.id).effective_minutes }}分钟</span>
            </div>
          </div>
          <div class="sc-action">
            <span v-if="getSectionProgress(sec.id)?.is_completed" class="sc-done">已完成</span>
            <span v-else-if="sec.open_time && !isSectionOpen(sec) && !isTeacherOrAdmin" class="sc-locked-tag">未开播</span>
            <span v-else-if="sec.open_time && !isSectionOpen(sec) && isTeacherOrAdmin" class="sc-preview-tag">预览</span>
            <span v-else class="sc-go">去学习</span>
          </div>
        </div>
      </div>

      <!-- 作业入口 -->
      <div class="homework-entry" @click="goHomework">
        <span>课程作业</span>
        <span class="he-arrow">&rarr;</span>
      </div>
    </template>

    <!-- 底部导航 -->
    <div class="bottom-nav">
      <router-link to="/" class="nav-item">课程</router-link>
      <router-link to="/my-progress" class="nav-item">我的进度</router-link>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../utils/auth'
import api from '../utils/api'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const courseId = computed(() => parseInt(route.params.courseId) || 0)

/** 当前用户是否为教师或管理员 */
const isTeacherOrAdmin = computed(() => ['teacher', 'admin'].includes(auth.user.value?.role))

const course = ref(null)
const sections = ref([])
const sectionProgressMap = ref({})  // section_id → progress data
const loading = ref(true)

// 课程总进度
const overallProgress = computed(() => {
  if (!course.value) return null
  // 从 my-progress 数据中找对应课程的进度
  return progressData.value.find(p => p.course_id === course.value.id) || null
})
const progressData = ref([])

function getSectionProgress(sectionId) {
  return sectionProgressMap.value[sectionId] || null
}

function formatDuration(seconds) {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return s > 0 ? `${m}分${s}秒` : `${m}分钟`
}

/**
 * v4.0: 判断小节是否已开播
 */
function isSectionOpen(section) {
  if (!section.open_time) return true
  return new Date(section.open_time) <= new Date()
}

/**
 * v4.0: 格式化开播时间显示
 */
function formatOpenTime(openTime) {
  const d = new Date(openTime)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}

const goLearn = (section) => {
  router.push(`/learn/${courseId.value}/${section.id}`)
}

const goHomework = () => {
  router.push(`/student-homework/${courseId.value}`)
}

onMounted(async () => {
  try {
    const [courseRes, progressRes] = await Promise.all([
      api.get(`/courses/${courseId.value}`),
      api.get('/stats/my-progress').catch(() => ({ data: { code: 1, data: [] } })),
    ])

    if (courseRes.data.code === 0) {
      course.value = courseRes.data.data
      sections.value = courseRes.data.data.sections || []
    }

    if (progressRes.data.code === 0) {
      progressData.value = progressRes.data.data
      // 找到本课程的进度，构建小节进度映射
      const cp = progressRes.data.data.find(p => p.course_id === courseId.value)
      if (cp && cp.sections) {
        for (const sp of cp.sections) {
          sectionProgressMap.value[sp.section_id] = sp
        }
      }
    }
  } catch (e) {
    console.error('获取课程详情失败:', e)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.course-detail-page { padding: 16px; padding-bottom: 70px; }
.loading { text-align: center; padding: 40px; color: #999; }

/* 返回导航 */
.back-nav { margin-bottom: 12px; }
.back-link { color: #1890ff; font-size: 14px; text-decoration: none; cursor: pointer; }

/* 课程信息卡片 */
.course-info-card {
  background: #fff; border-radius: 10px; padding: 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06); margin-bottom: 16px;
}
.course-title { font-size: 18px; margin-bottom: 6px; }
.course-desc { font-size: 13px; color: #999; margin-bottom: 8px; }
.course-meta {
  display: flex; gap: 16px; font-size: 12px; color: #666; margin-bottom: 10px;
}

/* 课程总进度 */
.total-progress { margin-top: 8px; }
.tp-header { display: flex; justify-content: space-between; font-size: 13px; color: #666; margin-bottom: 4px; }
.tp-pct { font-weight: 600; color: #1890ff; }
.tp-bar { height: 6px; background: #f0f0f0; border-radius: 3px; overflow: hidden; }
.tp-fill { height: 100%; background: linear-gradient(90deg, #1890ff, #52c41a); border-radius: 3px; transition: width 0.3s; }
.tp-text { font-size: 11px; color: #999; margin-top: 3px; }

/* 小节列表 */
.section-list { margin-bottom: 16px; }
.sl-header { font-size: 15px; font-weight: 600; margin-bottom: 10px; }
.empty-section { text-align: center; padding: 30px; color: #999; font-size: 14px; }

.section-card {
  background: #fff; border-radius: 8px; margin-bottom: 8px; padding: 12px 14px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04); display: flex; align-items: center;
  cursor: pointer; gap: 12px;
}
.section-card:active { background: #f9f9f9; }

/* 左侧序号 */
.sc-left { flex-shrink: 0; }
.sc-order {
  display: flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border-radius: 50%;
  background: #e6f7ff; color: #1890ff; font-size: 13px; font-weight: 600;
}

.sc-body { flex: 1; min-width: 0; }
.sc-title { font-size: 14px; font-weight: 500; margin-bottom: 2px; }
.sc-meta { font-size: 11px; color: #999; display: flex; gap: 10px; }

/* 小节进度条 */
.sc-progress { display: flex; align-items: center; gap: 6px; margin-top: 5px; }
.sc-bar { flex: 1; height: 3px; background: #f0f0f0; border-radius: 2px; overflow: hidden; }
.sc-fill { height: 100%; background: #52c41a; border-radius: 2px; transition: width 0.3s; }
.sc-pct { font-size: 10px; color: #999; white-space: nowrap; }

.sc-action { flex-shrink: 0; }
.sc-done { font-size: 12px; color: #52c41a; font-weight: 500; }
.sc-go { font-size: 12px; color: #1890ff; font-weight: 500; }

/* v4.0: 未开播状态 */
.sc-locked { color: #fa8c16; font-size: 11px; }
.sc-locked-tag { font-size: 12px; color: #fa8c16; font-weight: 500; }

/* 教师/管理员预览状态 */
.sc-preview { color: #1890ff; font-size: 11px; }
.sc-preview-tag { font-size: 12px; color: #1890ff; font-weight: 500; }

/* 作业入口 */
.homework-entry {
  background: #fff; border-radius: 8px; padding: 14px; margin-bottom: 16px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04); display: flex;
  justify-content: space-between; cursor: pointer;
}
.homework-entry:active { background: #f9f9f9; }
.he-arrow { color: #ccc; }

/* 底部导航 */
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
  .course-detail-page { padding: 12px; padding-bottom: 60px; }
  .course-title { font-size: 16px; }
  .course-info-card { padding: 12px; }
  .course-meta { flex-wrap: wrap; gap: 8px 12px; font-size: 11px; }
  .section-card { padding: 10px 12px; gap: 10px; }
  .sc-order { width: 24px; height: 24px; font-size: 12px; }
  .sc-title { font-size: 13px; }
  .sc-meta { flex-wrap: wrap; gap: 6px; }
  .sl-header { font-size: 14px; }
  .homework-entry { padding: 12px; }
}
</style>
