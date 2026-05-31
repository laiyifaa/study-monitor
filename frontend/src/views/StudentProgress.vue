<!--
  @模块：StudentProgress.vue — 我的进度页
  @页面用途：展示当前学生在所有课程中的学习进度，包括完成率进度条、有效时长、视频进度
  @数据流：
    1. 组件挂载 → 调用 GET /stats/my-progress 获取当前学生的所有课程进度
    2. 后端返回 { code: 0, data: ProgressItem[] } → 填充 courses 响应式数组
    3. 每个卡片展示进度条+时长+状态，点击"去学习"跳转学习页
  @后端API：
    - GET /stats/my-progress：获取当前登录学生在所有课程的进度汇总
      返回字段：course_id, title, is_completed, completion_rate,
                effective_minutes, require_minutes, video_progress, end_date
  @依赖：
    - utils/api：封装了 axios 的请求工具（自动携带 token）
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
      <!-- v-for 遍历每门课程的进度数据 -->
      <div v-for="c in courses" :key="c.course_id" class="course-card">
        <!-- 卡片头部：课程标题 + 完成状态标签 -->
        <div class="card-header">
          <h3>{{ c.title }}</h3>
          <!-- 根据完成状态动态切换标签样式和文案 -->
          <span class="badge" :class="c.is_completed ? 'done' : 'ongoing'">
            {{ c.is_completed ? '已完成' : '学习中' }}
          </span>
        </div>

        <!-- 进度条：宽度按完成百分比动态计算 -->
        <div class="progress-row">
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: c.completion_rate * 100 + '%' }"></div>
          </div>
          <!-- 百分比文字，四舍五入取整 -->
          <span class="progress-text">{{ Math.round(c.completion_rate * 100) }}%</span>
        </div>

        <!-- 详细信息行：有效时长 / 视频进度 -->
        <div class="info-row">
          <span>有效时长：{{ c.effective_minutes }} / {{ c.require_minutes }} 分钟</span>
          <span>播放进度：{{ formatProgress(c.video_progress) }}</span>
        </div>

        <!-- 截止日期：仅当课程设置了截止日期时显示，使用红色警告色 -->
        <div v-if="c.end_date" class="deadline">
          截止日期：{{ c.end_date }}
        </div>

        <!-- 跳转学习页按钮：已完成显示"继续学习"，未完成显示"去学习" -->
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

/** 课程进度列表数据，由后端 GET /stats/my-progress 接口填充 */
const courses = ref([])

/** 加载状态标识 */
const loading = ref(true)

/**
 * 格式化视频进度（秒数 → 分:秒）
 * 后端 video_progress 存的是视频播放到的秒数位置（如 135.3 秒），
 * 不是百分比。直接加 % 显示会超过 100%，改为时间格式更准确。
 */
function formatProgress(seconds) {
  if (!seconds || seconds <= 0) return '0:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

/**
 * 组件挂载时获取当前学生的进度数据
 * 流程：请求 → 成功则填充 courses → 无论成败都关闭 loading
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
/* 页面整体：左右留内边距，最大宽度768px居中（适配平板） */
.progress-page { padding: 16px; max-width: 768px; margin: 0 auto; }
.page-title { font-size: 20px; margin-bottom: 16px; }

/* 加载中与空状态 */
.loading, .empty { text-align: center; padding: 40px; color: #999; }

/* 课程进度卡片：白色背景圆角卡片 */
.course-card {
  background: #fff; border-radius: 10px; padding: 16px;
  margin-bottom: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

/* 卡片头部：标题与状态标签两端对齐 */
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.card-header h3 { font-size: 16px; }

/* 状态标签：圆角小胶囊 */
.badge { font-size: 12px; padding: 2px 8px; border-radius: 10px; }
.badge.done { background: #f6ffed; color: #52c41a; }    /* 已完成：绿色系 */
.badge.ongoing { background: #e6f7ff; color: #1890ff; }  /* 学习中：蓝色系 */

/* 进度条行：进度条 + 百分比文字横向排列 */
.progress-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
/* 进度条底色轨道 */
.progress-bar { flex: 1; height: 8px; background: #f0f0f0; border-radius: 4px; overflow: hidden; }
/* 进度条填充：宽度由行内样式动态控制，带过渡动画 */
.progress-fill { height: 100%; background: #1890ff; transition: width 0.3s; border-radius: 4px; }
.progress-text { font-size: 13px; font-weight: 600; color: #1890ff; min-width: 40px; }

/* 详细信息行：有效时长与视频进度两端对齐 */
.info-row { display: flex; justify-content: space-between; font-size: 13px; color: #666; }

/* 截止日期：红色警告色 */
.deadline { font-size: 12px; color: #ff4d4f; margin-top: 4px; }

/* 继续学习/去学习 链接按钮 */
.continue-btn {
  display: inline-block; margin-top: 10px; color: #1890ff; text-decoration: none;
  font-size: 14px; font-weight: 500;
}
</style>
