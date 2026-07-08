<!--
  @模块：StudentLearn.vue — 在线学习页（系统核心页面）
  @页面用途：学生在线观看小节视频，自动计时有效学习时长，支持防挂机验证弹窗。
            是整个学习进度监督系统的核心交互页面。
  @数据流：
    1. 组件挂载 → 调用 GET /sections/:sectionId 获取小节信息（视频类型、视频地址）
       同时调用 GET /courses/:courseId 获取课程信息（要求时长）
    2. 视频播放 → 通过 useStudyTracker 组合式函数自动计时并上报心跳
    3. 心跳上报 → composable 内部定时调用 POST /heartbeat/beat 上报当前播放进度
    4. 防挂机 → composable 内部检测到长时间无操作时弹出验证弹窗
    5. 组件卸载 → 清理 postMessage 监听器，composable 内部停止心跳
  @视频播放双模式：
    - url 模式：外部链接（B站/腾讯视频等），通过 iframe 嵌入，通过 postMessage 接收播放状态
    - local 模式：本地上传的 MP4 文件，使用 HTML5 <video> 标签播放，原生事件监听
  @后端API：
    - GET /sections/:sectionId：获取小节详情（video_type, video_url 等）
    - GET /courses/:courseId：获取课程详情（require_minutes 等）
    - POST /heartbeat/*：由 useStudyTracker 内部调用，上报学习进度心跳
  @依赖：
    - composables/useStudyTracker：学习计时核心逻辑（心跳上报、有效时长计算、防挂机验证）
    - composables/useDingTalk：钉钉 H5 微应用 API 封装（设置标题等）
    - utils/api：封装了 axios 的请求工具
-->
<template>
  <div class="learn-page">
    <!-- 返回导航 -->
    <div class="back-nav-bar">
      <a href="javascript:void(0)" @click="$router.back()" class="back-link">&larr; 返回课程</a>
    </div>

    <!-- ==================== 顶部状态栏 ==================== -->
    <div class="status-bar">
      <!-- 学习状态指示：绿色圆点=学习中，红色圆点=已暂停 -->
      <div class="status-item">
        <span class="dot" :class="isEffective ? 'active' : 'inactive'"></span>
        <span>{{ isEffective ? '学习中' : '已暂停' }}</span>
      </div>
      <!-- 已累计的有效学习时长（仅实际观看视频时计入） -->
      <div class="status-item">
        <span class="label">有效时长</span>
        <span class="value">{{ effectiveMinutes }} 分钟</span>
      </div>
      <!-- 视频播放进度（秒数转为 分:秒 格式） -->
      <div class="status-item">
        <span class="label">播放进度</span>
        <span class="value">{{ formatTime(videoProgress) }}</span>
      </div>
      <!-- 快捷跳转到"我的进度"页 -->
      <router-link to="/my-progress" class="link">我的进度</router-link>
    </div>

    <!-- ==================== 进度条 ==================== -->
    <!-- 有效时长/要求时长的可视化进度，上限100% -->
    <div class="progress-bar">
      <div class="progress-fill" :style="{ width: Math.min(effectiveMinutes / requireMinutes * 100, 100) + '%' }"></div>
    </div>
    <div class="progress-text">
      {{ effectiveMinutes }} / {{ requireMinutes }} 分钟
    </div>

    <!-- ==================== 未开播提示（v4.0） ==================== -->
    <!-- 学生：锁屏不可观看；教师/管理员：仅提示条，可正常查看 -->
    <div v-if="sectionLocked && !isTeacherOrAdmin" class="locked-overlay">
      <div class="locked-card">
        <div class="locked-icon">🔒</div>
        <h3>课程尚未开播</h3>
        <p>开播时间：{{ openTimeInfo }}</p>
        <p class="locked-hint">开播后即可开始学习</p>
      </div>
    </div>
    <div v-if="sectionLocked && isTeacherOrAdmin" class="teacher-preview-hint">
      <span class="tph-icon">👁</span>
      <span>该课程尚未开播（{{ openTimeInfo }}），当前为教师预览模式</span>
    </div>

    <!-- ==================== 视频播放区域 ==================== -->
    <!-- 根据 video_type 切换 iframe / HTML5 video 两种播放方式 -->
    <!-- 教师预览模式：不锁屏，显示视频 -->
    <div v-if="!sectionLocked || isTeacherOrAdmin" class="video-container">
      <!-- 外部链接模式：iframe 嵌入第三方视频播放页 -->
      <iframe
        v-if="videoType === 'url' && videoUrl"
        :src="videoUrl"
        class="video-iframe"
        allow="autoplay; fullscreen; encrypted-media"
        allowfullscreen
        @load="onPlayerLoad"
      ></iframe>
      <!-- 本地上传模式：HTML5 <video> 标签播放 MP4 文件 -->
      <video
        v-else-if="videoType === 'local' && videoUrl"
        ref="videoPlayer"
        class="video-player"
        controls
        autoplay
        playsinline
        @play="onVideoPlay"
        @pause="onVideoPause"
        @timeupdate="onVideoTimeUpdate"
        @loadedmetadata="onVideoLoaded"
      >
        <source :src="videoSourceUrl" type="video/mp4" />
        您的浏览器不支持视频播放
      </video>
      <!-- 视频未加载时的占位提示 -->
      <div v-else class="video-placeholder">
        <p>课程视频加载中...</p>
      </div>
    </div>

    <!-- ==================== 播放控制提示 ==================== -->
    <div class="controls-hint">
      <p>1. 视频播放时自动计时</p>
      <p>2. 切换到其他应用将暂停计时</p>
      <p>3. 暂停视频时立即停止计时</p>
    </div>

    <!-- ==================== 作业入口 ==================== -->
    <div class="homework-entry">
      <router-link :to="`/student-homework/${courseId}`" class="hw-btn">
        查看课程作业 &rarr;
      </router-link>
    </div>

    <!-- ==================== 防挂机验证弹窗 ==================== -->
    <!-- 由 useStudyTracker 的 showVerify 控制，长时间无操作时弹出 -->
    <div v-if="showVerify" class="verify-overlay">
      <div class="verify-dialog">
        <h3>学习验证</h3>
        <p>请点击确认继续学习</p>
        <!-- 点击确认后调用 verifyPass，composable 内部重置计时器 -->
        <button class="verify-btn" @click="verifyPass">确认继续</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useStudyTracker } from '../composables/useStudyTracker'
import { useDingTalk } from '../composables/useDingTalk'
import { useAuthStore } from '../utils/auth'
import api from '../utils/api'

/** 当前路由实例，用于获取路径参数 courseId */
const route = useRoute()

/** 认证状态，用于判断用户角色 */
const auth = useAuthStore()

/** 当前用户是否为教师或管理员 */
const isTeacherOrAdmin = computed(() => ['teacher', 'admin'].includes(auth.user.value?.role))

/** 从路由参数解构出课程ID和小节ID */
const courseId = parseInt(route.params.courseId)
const sectionId = parseInt(route.params.sectionId) || null

/** 视频类型：'url'（外部链接iframe）或 'local'（本地上传HTML5 video） */
const videoType = ref('url')

/** 视频地址：url 模式为完整链接，local 模式为服务器文件名 */
const videoUrl = ref('')

/** CDN 加速地址：后端开启 CDN 时返回，优先使用；为空时降级到原始路径 */
const videoCdnUrl = ref('')

/** 小节是否未开播（v4.0） */
const sectionLocked = ref(false)
const openTimeInfo = ref('')

/** HTML5 video 元素的模板引用，用于读取 currentTime */
const videoPlayer = ref(null)

/**
 * 计算本地视频的播放源地址：
 * 1. 优先使用 CDN 地址（video_cdn_url）—— 天翼云 CDN 加速
 * 2. 降级到 Nginx 静态路径 /uploads/videos/ —— 走 sendfile 零拷贝，性能远超 FastAPI FileResponse
 *
 * 注意：不使用 /api/courses/video-file/ 路径，因为：
 * - 视频文件只挂载到前端 Nginx 容器，后端容器内无视频文件（会导致 404）
 * - 即使后端容器有文件，FastAPI FileResponse 也受 Python GIL 限制，并发能力远不如 Nginx sendfile
 * - Nginx sendfile 直接在内核态完成磁盘→网卡的数据传输，不经过用户态
 */
const videoSourceUrl = computed(() => {
  if (videoCdnUrl.value) return videoCdnUrl.value
  return `/uploads/videos/${videoUrl.value}`
})

/**
 * 从 useStudyTracker 组合式函数解构出学习计时相关状态和方法：
 * - isPlaying：视频是否正在播放
 * - isEffective：当前是否在有效计时（播放中 + 前台 + 非长时间暂停）
 * - effectiveMinutes：已累计的有效学习时长（分钟）
 * - videoProgress：视频播放进度百分比
 * - showVerify：是否显示防挂机验证弹窗
 * - requireMinutes：课程要求的学习时长
 * - setVideoTime(time)：更新当前视频播放时间点（用于心跳上报）
 * - setPlaying(bool)：更新视频播放/暂停状态
 * - verifyPass()：防挂机验证通过，重置计时器继续计时
 */
const {
  isPlaying, isEffective, effectiveMinutes, videoProgress,
  showVerify, requireMinutes, lastVideoProgress, setVideoTime, setPlaying, verifyPass,
} = useStudyTracker(courseId, sectionId)

/** 钉钉 API 封装，用于设置 H5 微应用的页面标题 */
const { setTitle } = useDingTalk()

/**
 * 将秒数格式化为 分:秒 显示
 * video_progress 后端存的是视频播放到的秒数（如 135.3 秒）
 * 格式化后显示为 "2:15" 而非 "135.3%"（后者会超过 100%，误导用户）
 *
 * @param {number} seconds - 视频播放到的秒数
 * @returns {string} 格式化后的时间字符串
 */
function formatTime(seconds) {
  if (!seconds || seconds <= 0) return '0:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

/**
 * 组件挂载：获取小节和课程信息并初始化视频播放
 * 流程：
 *   1. 请求小节详情 → 设置视频类型、视频地址
 *   2. 请求课程详情 → 获取要求时长、课程名称（设置标题）
 *   3. 设置钉钉H5微应用标题和浏览器标签页标题
 *   4. 注册 window message 监听器（接收 iframe 播放器状态）
 */
onMounted(async () => {
  try {
    // 并行请求小节详情和课程详情
    const [sectionRes, courseRes] = await Promise.all([
      api.get(`/sections/${sectionId}`),
      api.get(`/courses/${courseId}`),
    ])
    // 从小节获取视频信息
    if (sectionRes.data.code === 0) {
      const section = sectionRes.data.data
      videoType.value = section.video_type || 'url'
      videoUrl.value = section.video_url || ''
      videoCdnUrl.value = section.video_cdn_url || ''
      // v4.0: 检查小节开播时间
      if (section.open_time) {
        const openTime = new Date(section.open_time)
        if (openTime > new Date()) {
          sectionLocked.value = true
          openTimeInfo.value = `${openTime.getMonth() + 1}月${openTime.getDate()}日 ${openTime.getHours()}:${String(openTime.getMinutes()).padStart(2, '0')}`
        }
      }
    }
    // 从课程获取要求时长和标题
    if (courseRes.data.code === 0) {
      const course = courseRes.data.data
      requireMinutes.value = course.require_minutes
      setTitle(course.title)
      document.title = course.title
    }
  } catch (e) {
    console.error('获取学习信息失败:', e)
  }

  // 监听 iframe 发来的 postMessage（通用视频播放器适配 / 钉钉悟空智能体通信预留）
  window.addEventListener('message', handleMessage)
})

/**
 * 组件卸载：清理 postMessage 监听器，防止内存泄漏
 */
onUnmounted(() => {
  window.removeEventListener('message', handleMessage)
})

/**
 * 处理来自 iframe 的播放器消息
 * 通用视频播放器消息协议：
 *   { type: 'player:status', playing: bool, currentTime: float, duration: float }
 *   { type: 'player:play' }
 *   { type: 'player:pause' }
 *   { type: 'player:timeupdate', currentTime: float }
 *
 * 安全说明：生产环境应校验 event.origin，此处为简化实现
 * @param {MessageEvent} event - postMessage 事件对象
 */
const handleMessage = (event) => {
  const data = event.data
  if (!data || typeof data !== 'object') return

  // 状态更新消息：同步播放时间和播放状态
  if (data.type === 'player:status' || data.type === 'player:timeupdate') {
    if (typeof data.currentTime === 'number' && data.currentTime > 0) {
      setVideoTime(data.currentTime)
    }
    if (typeof data.playing === 'boolean') {
      setPlaying(data.playing)
    }
  } else if (data.type === 'player:play') {
    // 播放事件
    setPlaying(true)
    if (typeof data.currentTime === 'number') {
      setVideoTime(data.currentTime)
    }
  } else if (data.type === 'player:pause') {
    // 暂停事件
    setPlaying(false)
  }
}

/**
 * iframe 加载完成回调
 * 1. 向 iframe 内的播放器发送注册消息（host:register），请求其推送播放状态
 * 2. 降级模式：无论 iframe 是否支持 postMessage 协议，都直接开启计时
 *    （确保无 postMessage 响应时学生仍能记录学习时长）
 */
const onPlayerLoad = () => {
  const iframe = document.querySelector('.video-iframe')
  if (iframe?.contentWindow) {
    try {
      iframe.contentWindow.postMessage({
        type: 'host:register',
        heartbeatInterval: 30,
      }, '*')
    } catch (e) {
      // 跨域 iframe 可能无法发送，忽略
    }
  }
  // 标记开始播放（降级模式：无 postMessage 响应时仍开启计时）
  setPlaying(true)
}

/**
 * HTML5 video 播放事件：通知 composable 开始计时
 */
const onVideoPlay = () => {
  setPlaying(true)
}

/**
 * HTML5 video 暂停事件：通知 composable 停止计时
 */
const onVideoPause = () => {
  setPlaying(false)
}

/**
 * HTML5 video 时间更新事件：持续同步当前播放时间点
 * 用于心跳上报时携带准确的播放进度
 */
const onVideoTimeUpdate = () => {
  if (videoPlayer.value) {
    setVideoTime(videoPlayer.value.currentTime)
  }
}

/**
 * HTML5 video 元数据加载完成：从历史进度恢复播放位置
 * 实现断点续播 —— 学生重新进入学习页时，视频从上次观看的位置继续播放
 */
const onVideoLoaded = () => {
  restoreVideoProgress()
}

/**
 * 恢复视频播放进度（断点续播）
 * 当 lastVideoProgress 有值且 video 元素可操作时，跳转到上次观看位置
 */
const restoreVideoProgress = () => {
  if (videoPlayer.value && lastVideoProgress.value > 0) {
    // 避免跳到超出视频总时长
    const target = Math.min(lastVideoProgress.value, videoPlayer.value.duration || Infinity)
    if (target > 0 && Math.abs(videoPlayer.value.currentTime - target) > 1) {
      videoPlayer.value.currentTime = target
      setVideoTime(target)
    }
  }
}

// 监听 lastVideoProgress 变化：如果 startSession 返回较晚，
// 在视频已加载后才拿到历史进度，此时也需要恢复
watch(lastVideoProgress, (val) => {
  if (val > 0 && videoPlayer.value && videoPlayer.value.readyState >= 1) {
    restoreVideoProgress()
  }
})
</script>

<style scoped>
/* 页面整体：最小高度撑满视口 */
.learn-page { min-height: 100vh; }

/* 顶部状态栏：横向排列各状态项 + 跳转链接 */
.status-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; background: #fff; border-bottom: 1px solid #eee;
}
.status-item { display: flex; align-items: center; gap: 6px; font-size: 14px; }

/* 状态圆点：8px 小圆点，绿/红双色切换 */
.dot { width: 8px; height: 8px; border-radius: 50%; }
.dot.active { background: #52c41a; }
.dot.inactive { background: #ff4d4f; }
.label { color: #999; }
.value { font-weight: 600; color: #1890ff; }
.link { color: #1890ff; font-size: 13px; text-decoration: none; }

/* 顶部进度条：4px 细条，蓝绿渐变填充 */
.progress-bar { height: 4px; background: #f0f0f0; }
.progress-fill { height: 100%; background: linear-gradient(90deg, #1890ff, #52c41a); transition: width 0.5s; }
.progress-text { text-align: center; font-size: 12px; color: #999; padding: 4px; }

/* 视频容器：16:9 等比缩放，黑色背景 */
.video-container {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: #000;
  overflow: hidden;
}

/* iframe 播放器：绝对定位填满容器 */
.video-iframe {
  position: absolute; top: 0; left: 0;
  width: 100%; height: 100%; border: none;
}

/* HTML5 video 播放器：绝对定位填满容器 */
.video-player {
  width: 100%; height: 100%;
  position: absolute; top: 0; left: 0;
  background: #000;
}

/* 视频加载中占位：居中灰色提示 */
.video-placeholder {
  display: flex; align-items: center; justify-content: center;
  position: absolute; top: 0; left: 0; width: 100%; height: 100%;
  color: #666;
}

/* 控制提示文字区域 */
.controls-hint { padding: 16px; font-size: 13px; color: #999; line-height: 2; }

/* 作业入口按钮 */
.homework-entry {
  padding: 16px;
  text-align: center;
}
.hw-btn {
  display: inline-block;
  padding: 10px 28px;
  background: #1890ff;
  color: #fff;
  border-radius: 6px;
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  transition: background 0.2s;
}
.hw-btn:hover {
  background: #096dd9;
}
.hw-btn:active {
  background: #0050b3;
}

/* 防挂机验证弹窗遮罩：全屏半透明黑色覆盖 */
.verify-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center;
  z-index: 9999;
}

/* 验证弹窗对话框：白色圆角卡片，固定宽度 */
.verify-dialog {
  background: #fff; border-radius: 12px; padding: 32px 24px; text-align: center;
  width: 280px;
}
.verify-dialog h3 { font-size: 18px; margin-bottom: 12px; }
.verify-dialog p { font-size: 14px; color: #666; margin-bottom: 20px; }

/* 确认按钮：主题蓝色，点击时加深 */
.verify-btn {
  background: #1890ff; color: #fff; border: none; padding: 10px 40px;
  border-radius: 6px; font-size: 16px; cursor: pointer;
}
.verify-btn:active { background: #096dd9; }

/* 未开播锁屏提示（v4.0） */
.locked-overlay {
  display: flex; align-items: center; justify-content: center;
  min-height: 300px; padding: 40px 20px;
}
.locked-card {
  text-align: center; background: #fff; border-radius: 12px; padding: 32px 24px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
.locked-icon { font-size: 48px; margin-bottom: 12px; }
.locked-card h3 { font-size: 18px; margin-bottom: 8px; color: #333; }
.locked-card p { font-size: 14px; color: #666; }
.locked-hint { color: #999; font-size: 13px; margin-top: 8px; }

/* 教师预览提示条 */
.teacher-preview-hint {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 14px; margin: 0 0 8px 0;
  background: #e6f7ff; border: 1px solid #91d5ff; border-radius: 6px;
  font-size: 13px; color: #096dd9;
}
.tph-icon { font-size: 16px; }

/* 返回导航栏 */
.back-nav-bar {
  padding: 10px 16px; background: #fff; border-bottom: 1px solid #eee;
}
.back-link { color: #1890ff; font-size: 14px; text-decoration: none; cursor: pointer; }
.back-link:hover { text-decoration: underline; }

/* ====== 响应式：手机（480px以下） ====== */
@media (max-width: 480px) {
  /* 状态栏：4项太挤，缩小字体+隐藏"我的进度"文字链接 */
  .status-bar {
    padding: 8px 10px;
    flex-wrap: wrap;
    gap: 4px 8px;
  }
  .status-item { font-size: 12px; gap: 4px; }
  .dot { width: 6px; height: 6px; }
  .label { font-size: 11px; }
  .value { font-size: 12px; }
  /* "我的进度"在超小屏上缩小或换行 */
  .link { font-size: 11px; white-space: nowrap; }

  /* 进度条文字 */
  .progress-text { font-size: 11px; }

  /* 控制提示 */
  .controls-hint { padding: 12px 10px; font-size: 12px; line-height: 1.8; }

  /* 作业入口 */
  .homework-entry { padding: 12px; }
  .hw-btn { padding: 8px 20px; font-size: 13px; }

  /* 验证弹窗 */
  .verify-dialog { width: 260px; padding: 24px 18px; }
  .verify-dialog h3 { font-size: 16px; }
  .verify-btn { padding: 8px 30px; font-size: 14px; }

  /* 锁屏提示 */
  .locked-card { padding: 24px 18px; }
  .locked-icon { font-size: 36px; }
  .locked-card h3 { font-size: 16px; }
  .locked-card p { font-size: 13px; }

  /* 返回导航 */
  .back-nav-bar { padding: 8px 10px; }
  .back-link { font-size: 13px; }
}
</style>
