import { ref, onMounted, onUnmounted } from 'vue'
import api from '../utils/api'

/**
 * 学习追踪器 - 前端核心模块
 * 负责采集学习行为并定时上报心跳
 *
 * 功能：
 * 1. 30秒定时心跳上报
 * 2. 页面可见性检测（切出后台自动暂停）
 * 3. 5分钟无交互空闲检测
 * 4. 随机8-20分钟弹窗防挂机
 * 5. 页面卸载时自动结束会话
 */
export function useStudyTracker(courseId) {
  const sessionId = ref('')
  const isPlaying = ref(false)
  const isPageVisible = ref(true)
  const videoCurrentTime = ref(0)
  const effectiveMinutes = ref(0)
  const videoProgress = ref(0)
  const isEffective = ref(true)
  const showVerify = ref(false)
  const lastActionTime = ref(Date.now())
  const requireMinutes = ref(60)

  let heartbeatTimer = null
  let idleCheckTimer = null
  let verifyTimer = null

  // 启动学习会话
  const startSession = async () => {
    try {
      const res = await api.post('/heartbeat/start', { course_id: courseId })
      if (res.data.code === 0) {
        sessionId.value = res.data.data.session_id
        startHeartbeat()
        startIdleCheck()
        scheduleVerify()
      }
    } catch (e) {
      console.error('启动学习会话失败:', e)
    }
  }

  // 心跳上报：每30秒
  const startHeartbeat = () => {
    heartbeatTimer = setInterval(async () => {
      try {
        const res = await api.post('/heartbeat/beat', {
          course_id: courseId,
          is_playing: isPlaying.value,
          is_page_visible: isPageVisible.value,
          video_current_time: videoCurrentTime.value,
        })
        if (res.data.code === 0) {
          const d = res.data.data
          effectiveMinutes.value = d.effective_minutes
          videoProgress.value = d.video_progress
          isEffective.value = d.is_effective
        }
      } catch (e) {
        console.warn('心跳上报失败:', e)
      }
    }, 30000)
  }

  // 空闲检测：每60秒
  const startIdleCheck = () => {
    idleCheckTimer = setInterval(() => {
      const idle = (Date.now() - lastActionTime.value) / 1000
      if (idle > 300) {
        showVerify.value = true
      }
    }, 60000)
  }

  // 随机防挂机弹窗：8-20分钟
  const scheduleVerify = () => {
    const delay = (8 + Math.random() * 12) * 60 * 1000
    verifyTimer = setTimeout(() => {
      showVerify.value = true
      scheduleVerify()
    }, delay)
  }

  // 页面可见性
  const handleVisibility = () => {
    isPageVisible.value = !document.hidden
    if (document.hidden) {
      isPlaying.value = false
    }
  }

  // 记录操作（重置空闲）
  const recordAction = () => {
    lastActionTime.value = Date.now()
  }

  // 结束会话
  const endSession = async () => {
    try {
      await api.post('/heartbeat/end', {
        course_id: courseId,
        is_playing: isPlaying.value,
        is_page_visible: isPageVisible.value,
        video_current_time: videoCurrentTime.value,
      })
    } catch (e) {
      console.warn('结束会话失败:', e)
    }
    cleanup()
  }

  const cleanup = () => {
    clearInterval(heartbeatTimer)
    clearInterval(idleCheckTimer)
    clearTimeout(verifyTimer)
  }

  // 手动发一次心跳（视频状态变化时）
  const sendAction = async (action) => {
    try {
      const res = await api.post('/heartbeat/beat', {
        course_id: courseId,
        is_playing: isPlaying.value,
        is_page_visible: isPageVisible.value,
        video_current_time: videoCurrentTime.value,
        action,
      })
      if (res.data.code === 0) {
        effectiveMinutes.value = res.data.data.effective_minutes
        videoProgress.value = res.data.data.video_progress
      }
    } catch (e) {
      console.warn('动作上报失败:', e)
    }
  }

  onMounted(() => {
    document.addEventListener('visibilitychange', handleVisibility)
    document.addEventListener('click', recordAction)
    document.addEventListener('touchstart', recordAction)
    document.addEventListener('keydown', recordAction)
    window.addEventListener('beforeunload', endSession)
    startSession()
  })

  onUnmounted(() => {
    document.removeEventListener('visibilitychange', handleVisibility)
    document.removeEventListener('click', recordAction)
    document.removeEventListener('touchstart', recordAction)
    document.removeEventListener('keydown', recordAction)
    window.removeEventListener('beforeunload', endSession)
    endSession()
  })

  return {
    sessionId,
    isPlaying,
    isPageVisible,
    effectiveMinutes,
    videoProgress,
    isEffective,
    showVerify,
    requireMinutes,
    setVideoTime: (t) => {
      videoCurrentTime.value = t
      recordAction()
    },
    setPlaying: (v) => {
      isPlaying.value = v
      recordAction()
      sendAction(v ? 'play' : 'pause')
    },
    verifyPass: () => {
      showVerify.value = false
      recordAction()
    },
    endSession,
  }
}
