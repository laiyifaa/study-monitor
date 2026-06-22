<!--
  @模块：StudentProgress.vue — 我的进度页
  @页面用途：展示当前学生在所有课程中的学习进度，包括小节级别的子进度
  @数据流：
    1. 组件挂载 → 调用 GET /stats/my-progress 获取当前学生的所有课程进度
    2. 后端返回 { code: 0, data: ProgressItem[] } → 填充 courses 响应式数组
    3. 每个卡片展示课程进度+小节进度列表，点击小节可跳转学习页
  @后端API：
    - GET /stats/my-progress：获取当前登录学生在所有课程的进度汇总
      返回字段：course_id, title, is_completed, completion_rate,
                effective_minutes, require_minutes, video_progress, end_date,
                sections[] (section_id, title, effective_minutes, video_progress, is_completed)
  @依赖：
    - utils/api：封装了 axios 的请求工具
-->
<template>
  <div class="progress-page">
    <h2 class="page-title">我的学习进度</h2>

    <!-- 加载中状态提示 -->
    <div v-if="loading" class="loading">加载中...</div>

    <!-- 课程为空时的提示 -->
    <div v-else-if="courses.length === 0" class="empty">暂无课程</div>

    <!-- 课程进度卡片列表 -->
    <div v-else class="course-list">
      <div v-for="c in courses" :key="c.course_id" class="course-card">
        <!-- 卡片头部：课程标题 + 完成状态标签 -->
        <div class="card-header">
          <h3>{{ c.title }}</h3>
          <span class="badge" :class="c.is_completed ? 'done' : 'ongoing'">
            {{ c.is_completed ? '已完成' : '学习中' }}
          </span>
        </div>

        <!-- 课程总进度条 -->
        <div class="progress-row">
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: c.completion_rate * 100 + '%' }"></div>
          </div>
          <span class="progress-text">{{ Math.round(c.completion_rate * 100) }}%</span>
        </div>

        <!-- 课程总体信息 -->
        <div class="info-row">
          <span>有效时长：{{ c.effective_minutes }} 分钟<span v-if="c.require_minutes"> / 要求 {{ c.require_minutes }} 分钟</span></span>
          <span v-if="c.sections && c.sections.length > 0">{{ getCompletedSectionCount(c) }}/{{ c.sections.length }} 小节</span>
        </div>
        <div v-if="!c.require_minutes && c.total_section_minutes > 0" class="info-row sub">
          <span>视频总时长：{{ c.total_section_minutes }} 分钟</span>
        </div>

        <!-- 截止日期 -->
        <div v-if="c.end_date" class="deadline">
          截止日期：{{ c.end_date }}
        </div>

        <!-- 小节进度列表（可折叠） -->
        <div v-if="c.sections && c.sections.length > 0" class="section-collapse-area">
          <div class="section-toggle" @click="toggleSection(c.course_id)">
            <span class="toggle-text">{{ expandedSections[c.course_id] ? '收起小节' : '展开小节' }}（{{ c.sections.length }}）</span>
            <span class="toggle-arrow" :class="{ expanded: expandedSections[c.course_id] }">▶</span>
          </div>
          <transition name="slide">
            <div v-show="expandedSections[c.course_id]" class="section-progress-list">
              <div
                v-for="sec in c.sections"
                :key="sec.section_id"
                class="section-progress-item"
                @click="goLearn(c.course_id, sec.section_id)"
              >
                <div class="spi-left">
                  <span class="spi-dot" :class="sec.is_completed ? 'done' : (sec.effective_minutes > 0 ? 'active' : '')"></span>
                </div>
                <div class="spi-body">
                  <div class="spi-title">{{ sec.title }}</div>
                  <div class="spi-meta">
                    <span>{{ sec.effective_minutes }}分钟</span>
                    <span v-if="sec.require_minutes > 0" class="spi-req">/ 要求{{ sec.require_minutes }}分钟</span>
                  </div>
                  <div class="spi-bar">
                    <div class="spi-fill" :style="{ width: getSectionProgress(sec) + '%' }"></div>
                  </div>
                </div>
                <div class="spi-right">
                  <span v-if="sec.is_completed" class="spi-done">已完成</span>
                  <span v-else-if="sec.effective_minutes > 0" class="spi-partial">学习中</span>
                  <span v-else class="spi-notstart">未开始</span>
                </div>
              </div>
            </div>
          </transition>
        </div>

        <!-- 跳转课程详情按钮 -->
        <router-link :to="`/course/${c.course_id}`" class="continue-btn">
          查看课程详情
        </router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../utils/api'

const router = useRouter()

/** 课程进度列表数据 */
const courses = ref([])

/** 加载状态标识 */
const loading = ref(true)

/** 记录哪些课程的小节列表已展开 */
const expandedSections = reactive({})

/**
 * 切换课程小节列表的展开/收起
 */
function toggleSection(courseId) {
  expandedSections[courseId] = !expandedSections[courseId]
}

/**
 * 计算小节进度百分比
 */
function getSectionProgress(sec) {
  if (sec.is_completed) return 100
  if (sec.require_minutes > 0) {
    return Math.min(Math.round(sec.effective_minutes / sec.require_minutes * 100), 99)
  }
  return 0
}

/**
 * 统计已完成小节数量
 */
function getCompletedSectionCount(course) {
  if (!course.sections) return 0
  return course.sections.filter(s => s.is_completed).length
}

/**
 * 跳转到小节学习页
 */
function goLearn(courseId, sectionId) {
  router.push(`/learn/${courseId}/${sectionId}`)
}

/**
 * 组件挂载时获取当前学生的进度数据
 */
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
/* 页面整体 */
.progress-page { padding: 16px; max-width: 768px; margin: 0 auto; }
.page-title { font-size: 20px; margin-bottom: 16px; }

/* 加载中与空状态 */
.loading, .empty { text-align: center; padding: 40px; color: #999; }

/* 课程进度卡片 */
.course-card {
  background: #fff; border-radius: 10px; padding: 16px;
  margin-bottom: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

/* 卡片头部 */
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.card-header h3 { font-size: 16px; }

/* 状态标签 */
.badge { font-size: 12px; padding: 2px 8px; border-radius: 10px; }
.badge.done { background: #f6ffed; color: #52c41a; }
.badge.ongoing { background: #e6f7ff; color: #1890ff; }

/* 进度条 */
.progress-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.progress-bar { flex: 1; height: 8px; background: #f0f0f0; border-radius: 4px; overflow: hidden; }
.progress-fill { height: 100%; background: #1890ff; transition: width 0.3s; border-radius: 4px; }
.progress-text { font-size: 13px; font-weight: 600; color: #1890ff; min-width: 40px; }

/* 详细信息行 */
.info-row { display: flex; justify-content: space-between; font-size: 13px; color: #666; }
.info-row.sub { margin-top: 2px; font-size: 12px; color: #999; }

/* 截止日期 */
.deadline { font-size: 12px; color: #ff4d4f; margin-top: 4px; }

/* 小节折叠区域 */
.section-collapse-area { margin-top: 12px; border-top: 1px solid #f0f0f0; padding-top: 6px; }

/* 折叠切换按钮 */
.section-toggle {
  display: flex; justify-content: space-between; align-items: center;
  padding: 6px 0; cursor: pointer; user-select: none;
}
.section-toggle:active { opacity: 0.7; }
.toggle-text { font-size: 13px; color: #1890ff; }
.toggle-arrow {
  font-size: 10px; color: #999; transition: transform 0.25s;
  display: inline-block;
}
.toggle-arrow.expanded { transform: rotate(90deg); }

/* 折叠动画 */
.slide-enter-active, .slide-leave-active {
  transition: all 0.25s ease;
  overflow: hidden;
}
.slide-enter-from, .slide-leave-to {
  opacity: 0;
  max-height: 0;
}
.slide-enter-to, .slide-leave-from {
  opacity: 1;
  max-height: 500px;
}

/* 小节进度列表 */
.section-progress-list { overflow: hidden; }

.section-progress-item {
  display: flex; align-items: center; gap: 8px; padding: 6px 0;
  cursor: pointer;
}
.section-progress-item:active { background: #f9f9f9; border-radius: 4px; }

.spi-left { flex-shrink: 0; }
/* 小节状态圆点 */
.spi-dot {
  display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #d9d9d9;
}
.spi-dot.done { background: #52c41a; }
.spi-dot.active { background: #1890ff; }

.spi-body { flex: 1; min-width: 0; }
.spi-title { font-size: 13px; color: #333; margin-bottom: 2px; }
.spi-meta { font-size: 11px; color: #999; margin-bottom: 3px; }
.spi-req { color: #bbb; }
/* 小节进度条 */
.spi-bar { height: 3px; background: #f0f0f0; border-radius: 2px; overflow: hidden; }
.spi-fill { height: 100%; background: #52c41a; border-radius: 2px; transition: width 0.3s; }

.spi-right { flex-shrink: 0; font-size: 12px; }
.spi-done { color: #52c41a; }
.spi-partial { color: #1890ff; }
.spi-notstart { color: #d9d9d9; }

/* 继续学习链接按钮 */
.continue-btn {
  display: inline-block; margin-top: 10px; color: #1890ff; text-decoration: none;
  font-size: 14px; font-weight: 500;
}
</style>
