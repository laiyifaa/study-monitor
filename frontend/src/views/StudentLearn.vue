<template>
  <div class="learn-page">
    <!-- 顶部状态栏 -->
    <div class="status-bar">
      <div class="status-item">
        <span class="dot" :class="isEffective ? 'active' : 'inactive'"></span>
        <span>{{ isEffective ? '学习中' : '已暂停' }}</span>
      </div>
      <div class="status-item">
        <span class="label">有效时长</span>
        <span class="value">{{ effectiveMinutes }} 分钟</span>
      </div>
      <div class="status-item">
        <span class="label">进度</span>
        <span class="value">{{ videoProgress }}%</span>
      </div>
      <router-link to="/my-progress" class="link">我的进度</router-link>
    </div>

    <!-- 进度条 -->
    <div class="progress-bar">
      <div class="progress-fill" :style="{ width: Math.min(effectiveMinutes / requireMinutes * 100, 100) + '%' }"></div>
    </div>
    <div class="progress-text">
      {{ effectiveMinutes }} / {{ requireMinutes }} 分钟
    </div>

    <!-- 视频播放区域：iframe 嵌入悟空播放器 -->
    <div class="video-container">
      <iframe
        v-if="courseWukongUrl"
        :src="courseWukongUrl"
        class="video-iframe"
        allow="autoplay; fullscreen; encrypted-media"
        allowfullscreen
        @load="onPlayerLoad"
      ></iframe>
      <div v-else class="video-placeholder">
        <p>课程视频加载中...</p>
      </div>
    </div>

    <!-- 播放控制提示 -->
    <div class="controls-hint">
      <p>1. 视频播放时自动计时</p>
      <p>2. 切换到其他应用将暂停计时</p>
      <p>3. 暂停超过5分钟将暂停计时</p>
    </div>

    <!-- 防挂机验证弹窗 -->
    <div v-if="showVerify" class="verify-overlay">
      <div class="verify-dialog">
        <h3>学习验证</h3>
        <p>请点击确认继续学习</p>
        <button class="verify-btn" @click="verifyPass">确认继续</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useStudyTracker } from '../composables/useStudyTracker'
import { useDingTalk } from '../composables/useDingTalk'
import api from '../utils/api'

const route = useRoute()
const courseId = parseInt(route.params.courseId)
const courseWukongUrl = ref('')

const {
  isPlaying, isEffective, effectiveMinutes, videoProgress,
  showVerify, requireMinutes, setVideoTime, setPlaying, verifyPass,
} = useStudyTracker(courseId)

const { setTitle } = useDingTalk()

onMounted(async () => {
  try {
    const res = await api.get(`/courses/${courseId}`)
    if (res.data.code === 0) {
      const course = res.data.data
      courseWukongUrl.value = course.wukong_url
      requireMinutes.value = course.require_minutes
      setTitle(course.title)
      document.title = course.title
    }
  } catch (e) {
    console.error('获取课程信息失败:', e)
  }
})

const onPlayerLoad = () => {
  // iframe 加载完成后，标记播放
  setPlaying(true)
}
</script>

<style scoped>
.learn-page { min-height: 100vh; display: flex; flex-direction: column; }
.status-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; background: #fff; border-bottom: 1px solid #eee;
}
.status-item { display: flex; align-items: center; gap: 6px; font-size: 14px; }
.dot { width: 8px; height: 8px; border-radius: 50%; }
.dot.active { background: #52c41a; }
.dot.inactive { background: #ff4d4f; }
.label { color: #999; }
.value { font-weight: 600; color: #1890ff; }
.link { color: #1890ff; font-size: 13px; text-decoration: none; }
.progress-bar { height: 4px; background: #f0f0f0; }
.progress-fill { height: 100%; background: linear-gradient(90deg, #1890ff, #52c41a); transition: width 0.5s; }
.progress-text { text-align: center; font-size: 12px; color: #999; padding: 4px; }
.video-container { flex: 1; min-height: 220px; background: #000; }
.video-iframe { width: 100%; height: 100%; border: none; min-height: 220px; }
.video-placeholder { display: flex; align-items: center; justify-content: center; height: 220px; color: #666; }
.controls-hint { padding: 16px; font-size: 13px; color: #999; line-height: 2; }
.verify-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center;
  z-index: 9999;
}
.verify-dialog {
  background: #fff; border-radius: 12px; padding: 32px 24px; text-align: center;
  width: 280px;
}
.verify-dialog h3 { font-size: 18px; margin-bottom: 12px; }
.verify-dialog p { font-size: 14px; color: #666; margin-bottom: 20px; }
.verify-btn {
  background: #1890ff; color: #fff; border: none; padding: 10px 40px;
  border-radius: 6px; font-size: 16px; cursor: pointer;
}
.verify-btn:active { background: #096dd9; }
</style>
