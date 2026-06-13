/**
 * ═══════════════════════════════════════════════════════════════════════════════
 * 模块：useStudyTracker — 学习追踪器（前端防刷课核心）
 * ═══════════════════════════════════════════════════════════════════════════════
 *
 * 【功能】
 *   负责采集学生学习行为并定时上报心跳，是"22中暑假网课学习进度监督系统"
 *   前端防刷课体系的核心 composable，实现以下五大机制：
 *
 *   1. 定时心跳上报 —— 每 30 秒向后端发送一次学习状态快照，
 *      后端据此累计计算有效学习时长。
 *   2. 页面可见性检测 —— 监听 document.hidden，学生切出页面时
 *      自动暂停计时，切回恢复。
 *   3. 空闲检测 —— 每 60 秒检查用户最近交互时间，
 *      超过 5 分钟无操作则弹出人机验证弹窗。
 *   4. 随机防挂机弹窗 —— 在 8~20 分钟随机间隔弹出验证，
 *      打破挂机脚本的可预测性。
 *   5. 页面卸载保障 —— beforeunload 时自动调用 endSession，
 *      确保会话正常关闭，后端能精确计算时长。
 *
 * 【设计思路】
 *   - 采用"前端采集 + 后端裁定"双层架构：前端只负责如实上报
 *     is_playing / is_page_visible 等状态，有效时长由后端统一判定，
 *     前端无法篡改结果。
 *   - 人机验证弹窗（showVerify）由前端控制弹出时机，验证通过后
 *     上报 'verify' 事件留存审计记录；后端可据此判断异常会话。
 *   - 所有定时器在组件卸载时通过 cleanup() 统一清除，避免内存泄漏。
 *
 * 【使用场景】
 *   - 在课程学习页面（在线学习页）中调用，传入当前 course_id，
 *     即可自动启动追踪全流程。
 *   - 视频播放器通过 setPlaying / setVideoTime 回调同步播放状态。
 *   - 人机验证组件通过 showVerify 控制显隐，verifyPass 回调确认通过。
 *
 * 【与后端 API 交互】
 *   POST /heartbeat/start — 启动学习会话，返回 session_id + require_minutes
 *   POST /heartbeat/beat  — 心跳上报，返回 effective_minutes / video_progress / is_effective
 *   POST /heartbeat/end   — 结束学习会话，后端计算最终时长并关闭会话
 *
 * 【暴露的接口】
 *   sessionId        — ref<string>   当前学习会话 ID
 *   isPlaying        — ref<boolean>  视频是否正在播放
 *   isPageVisible    — ref<boolean>  页面是否可见（未切后台）
 *   effectiveMinutes — ref<number>   已累计有效学习时长（分钟）
 *   videoProgress    — ref<number>   视频观看进度百分比
 *   isEffective      — ref<boolean>  当前心跳周期是否被判定为有效学习
 *   showVerify       — ref<boolean>  是否显示人机验证弹窗
 *   requireMinutes   — ref<number>   课程要求学习时长（分钟）
 *   setVideoTime(t)  — 更新视频播放进度并重置空闲计时
 *   setPlaying(v)    — 更新播放状态并主动上报 play/pause 动作
 *   verifyPass()     — 人机验证通过回调，关闭弹窗并上报 verify 事件
 *   endSession()     — 手动结束学习会话
 * ═══════════════════════════════════════════════════════════════════════════════
 */
import { ref, onMounted, onUnmounted } from 'vue'
import api from '../utils/api'

export function useStudyTracker(courseId, sectionId = null) {
  // ──────────────────────────────────────────────
  // 响应式状态定义
  // ──────────────────────────────────────────────

  /** 当前学习会话 ID，由后端 POST /heartbeat/start 返回，全局唯一标识本次学习 */
  const sessionId = ref('')

  /** 视频是否正在播放，由播放器通过 setPlaying(true/false) 更新 */
  const isPlaying = ref(false)

  /** 页面是否可见（未切到后台），由 visibilitychange 事件驱动更新 */
  const isPageVisible = ref(true)

  /** 视频当前播放时间（秒），由播放器通过 setVideoTime(t) 实时同步 */
  const videoCurrentTime = ref(0)

  /** 已累计有效学习时长（分钟），由后端每次心跳返回更新 */
  const effectiveMinutes = ref(0)

  /** 视频观看进度百分比（0~100），由后端每次心跳返回更新 */
  const videoProgress = ref(0)

  /** 当前心跳周期是否被后端判定为"有效学习"，
   *  后端根据 is_playing && is_page_visible 综合判定 */
  const isEffective = ref(true)

  /** 是否显示人机验证弹窗，空闲超时或随机防挂机触发时置为 true */
  const showVerify = ref(false)

  /** 用户最近一次交互的时间戳（毫秒），用于空闲检测判断 */
  const lastActionTime = ref(Date.now())

  /** 课程要求学习时长（分钟），由后端 POST /heartbeat/start 返回 */
  const requireMinutes = ref(60)

  // ──────────────────────────────────────────────
  // 定时器引用（非响应式，组件内部使用）
  // ──────────────────────────────────────────────

  /** 心跳上报定时器 —— 每 30 秒触发一次 */
  let heartbeatTimer = null

  /** 空闲检测定时器 —— 每 60 秒检查一次是否超过 5 分钟无操作 */
  let idleCheckTimer = null

  /** 随机防挂机弹窗定时器 —— 8~20 分钟后触发，触发后重新调度 */
  let verifyTimer = null

  // ──────────────────────────────────────────────
  // 核心流程：启动学习会话
  // ──────────────────────────────────────────────

  /**
   * 启动学习会话
   *
   * 流程：
   *   1. 调用后端 POST /heartbeat/start，传入 course_id
   *   2. 后端创建会话记录，返回 session_id
   *   3. 启动三个定时器：心跳上报 / 空闲检测 / 随机防挂机
   *
   * 后端交互：POST /heartbeat/start
   *   请求体：{ course_id }
   *   响应体：{ code: 0, data: { session_id, require_minutes?, ... } }
   */
  const startSession = async () => {
    try {
      const res = await api.post('/heartbeat/start', { course_id: courseId, section_id: sectionId })
      if (res.data.code === 0) {
        // 保存会话 ID，后续心跳和结束会话都需要携带
        sessionId.value = res.data.data.session_id
        // 依次启动三大定时机制
        startHeartbeat()
        startIdleCheck()
        scheduleVerify()
      }
    } catch (e) {
      console.error('启动学习会话失败:', e)
    }
  }

  // ──────────────────────────────────────────────
  // 机制一：定时心跳上报
  // ──────────────────────────────────────────────

  /**
   * 启动心跳上报定时器
   *
   * 每 30 秒（30000ms）向后端发送一次学习状态快照，后端据此：
   *   - 若 is_playing && is_page_visible → 本周期计入有效时长
   *   - 若不满足 → 本周期不计入有效时长
   *   - 累计返回 effective_minutes / video_progress / is_effective
   *
   * 后端交互：POST /heartbeat/beat
   *   请求体：{ course_id, is_playing, is_page_visible, video_current_time }
   *   响应体：{ code: 0, data: { effective_minutes, video_progress, is_effective } }
   */
  const startHeartbeat = () => {
    heartbeatTimer = setInterval(async () => {
      try {
        const res = await api.post('/heartbeat/beat', {
          course_id: courseId,
          section_id: sectionId,
          is_playing: isPlaying.value,
          is_page_visible: isPageVisible.value,
          video_current_time: videoCurrentTime.value,
        })
        if (res.data.code === 0) {
          const d = res.data.data
          // 同步后端计算的有效时长与进度
          effectiveMinutes.value = d.effective_minutes
          videoProgress.value = d.video_progress
          isEffective.value = d.is_effective
        }
      } catch (e) {
        // 心跳失败不中断学习流程，仅打印警告，等待下次心跳重试
        console.warn('心跳上报失败:', e)
      }
    }, 30000)
  }

  // ──────────────────────────────────────────────
  // 机制二：空闲检测
  // ──────────────────────────────────────────────

  /**
   * 启动空闲检测定时器
   *
   * 每 60 秒（60000ms）检查一次：
   *   - 计算距离用户最近一次交互的秒数 = (当前时间 - lastActionTime) / 1000
   *   - 若超过 300 秒（5 分钟）无操作 → 弹出人机验证弹窗
   *
   * 用户的 click / touchstart / keydown 事件会更新 lastActionTime，
   * 确保"人在电脑前"的情况下不会误触发验证。
   */
  const startIdleCheck = () => {
    idleCheckTimer = setInterval(() => {
      // 计算空闲时长（秒）
      const idle = (Date.now() - lastActionTime.value) / 1000
      // 空闲超过 5 分钟（300 秒），弹出人机验证
      if (idle > 300) {
        showVerify.value = true
      }
    }, 60000)
  }

  // ──────────────────────────────────────────────
  // 机制三：随机防挂机弹窗
  // ──────────────────────────────────────────────

  /**
   * 调度随机防挂机弹窗
   *
   * 间隔计算：8 + Math.random() * 12 → 范围 [8, 20) 分钟
   *   即最短 8 分钟、最长约 20 分钟弹一次验证
   *
   * 设计意图：
   *   - 固定间隔容易被挂机脚本预测并自动点击绕过
   *   - 随机间隔增加不可预测性，迫使真人持续关注页面
   *   - 弹窗后立即递归调度下一次，形成持续防挂机循环
   */
  const scheduleVerify = () => {
    // 随机延迟：8~20 分钟，转为毫秒
    const delay = (8 + Math.random() * 12) * 60 * 1000
    verifyTimer = setTimeout(() => {
      // 触发人机验证弹窗
      showVerify.value = true
      // 弹窗后重新调度下一次随机验证，保持持续防挂机
      scheduleVerify()
    }, delay)
  }

  // ──────────────────────────────────────────────
  // 页面可见性检测
  // ──────────────────────────────────────────────

  /**
   * 处理页面可见性变化事件
   *
   * 当学生切换标签页或最小化浏览器时：
   *   - document.hidden = true → 页面不可见
   *     → isPageVisible = false，下一心跳周期后端不计入有效时长
   *     → isPlaying = false，自动"暂停"视频播放状态
   *   - document.hidden = false → 页面重新可见
   *     → isPageVisible = true，恢复正常计时
   *
   * 注意：此处仅修改状态标记，不直接调用后端 API，
   * 实际时长调整由下次心跳上报时后端根据 is_page_visible 判定。
   */
  const handleVisibility = () => {
    isPageVisible.value = !document.hidden
    if (document.hidden) {
      // 页面不可见时强制标记为未播放，防止切后台挂机
      isPlaying.value = false
    }
  }

  // ──────────────────────────────────────────────
  // 用户交互记录
  // ──────────────────────────────────────────────

  /**
   * 记录用户操作时间，重置空闲计时
   *
   * 用户的 click / touchstart / keydown 事件均会触发此函数，
   * 更新 lastActionTime 为当前时间戳，使空闲检测不会误判。
   */
  const recordAction = () => {
    lastActionTime.value = Date.now()
  }

  // ──────────────────────────────────────────────
  // 结束学习会话
  // ──────────────────────────────────────────────

  /**
   * 结束学习会话
   *
   * 流程：
   *   1. 调用后端 POST /heartbeat/end，携带当前状态快照
   *   2. 后端关闭会话记录，计算本次学习的最终有效时长
   *   3. 清除所有定时器，防止组件卸载后继续上报
   *
   * 后端交互：POST /heartbeat/end
   *   请求体：{ course_id, is_playing, is_page_visible, video_current_time }
   *   响应体：{ code: 0, data: { ... } }
   */
  const endSession = async () => {
    try {
      await api.post('/heartbeat/end', {
        course_id: courseId,
        section_id: sectionId,
        is_playing: isPlaying.value,
        is_page_visible: isPageVisible.value,
        video_current_time: videoCurrentTime.value,
      })
    } catch (e) {
      // 结束会话失败仅警告，不影响页面关闭流程
      console.warn('结束会话失败:', e)
    }
    // 无论 API 成败，都必须清除定时器
    cleanup()
  }

  /**
   * 清除所有定时器
   *
   * 在 endSession 或组件卸载时调用，防止：
   *   - 心跳继续向后端发送无效请求
   *   - 空闲检测弹窗在已离开的页面上触发
   *   - 随机验证定时器泄漏
   */
  const cleanup = () => {
    clearInterval(heartbeatTimer)
    clearInterval(idleCheckTimer)
    clearTimeout(verifyTimer)
  }

  // ──────────────────────────────────────────────
  // 手动心跳上报（视频状态变化时）
  // ──────────────────────────────────────────────

  /**
   * 手动发送一次心跳，附带动作标识
   *
   * 与定时心跳的区别：
   *   - 定时心跳：每 30 秒自动发送，无 action 字段
   *   - 手动心跳：视频 play/pause/verify 等状态变化时即时发送，
   *     携带 action 字段供后端审计记录
   *
   * 后端交互：POST /heartbeat/beat
   *   请求体：{ course_id, is_playing, is_page_visible, video_current_time, action }
   *   action 取值：'play' | 'pause' | 'verify'
   *
   * @param {string} action - 动作标识，如 'play'、'pause'、'verify'
   */
  const sendAction = async (action) => {
    try {
      const res = await api.post('/heartbeat/beat', {
        course_id: courseId,
        section_id: sectionId,
        is_playing: isPlaying.value,
        is_page_visible: isPageVisible.value,
        video_current_time: videoCurrentTime.value,
        action,
      })
      if (res.data.code === 0) {
        // 即时同步后端返回的有效时长和进度，前端 UI 可实时响应
        effectiveMinutes.value = res.data.data.effective_minutes
        videoProgress.value = res.data.data.video_progress
      }
    } catch (e) {
      console.warn('动作上报失败:', e)
    }
  }

  // ──────────────────────────────────────────────
  // 生命周期钩子：注册 / 注销事件监听
  // ──────────────────────────────────────────────

  /**
   * 组件挂载时：
   *   1. 注册 visibilitychange 监听 —— 检测页面切出/切回
   *   2. 注册 click / touchstart / keydown 监听 —— 记录用户交互，重置空闲计时
   *   3. 注册 beforeunload 监听 —— 页面关闭/刷新时自动结束会话
   *   4. 启动学习会话（startSession）
   */
  onMounted(() => {
    // 页面可见性变化 → 暂停/恢复有效时长计时
    document.addEventListener('visibilitychange', handleVisibility)
    // 用户交互事件 → 更新 lastActionTime，防止空闲误判
    document.addEventListener('click', recordAction)
    document.addEventListener('touchstart', recordAction)
    document.addEventListener('keydown', recordAction)
    // 页面卸载前 → 确保会话正常关闭，后端精确结算时长
    window.addEventListener('beforeunload', endSession)
    // 启动完整的学习追踪流程
    startSession()
  })

  /**
   * 组件卸载时：
   *   1. 移除所有事件监听，防止内存泄漏
   *   2. 调用 endSession 结束会话并清除定时器
   */
  onUnmounted(() => {
    document.removeEventListener('visibilitychange', handleVisibility)
    document.removeEventListener('click', recordAction)
    document.removeEventListener('touchstart', recordAction)
    document.removeEventListener('keydown', recordAction)
    window.removeEventListener('beforeunload', endSession)
    endSession()
  })

  // ──────────────────────────────────────────────
  // 对外暴露的接口
  // ──────────────────────────────────────────────

  return {
    sessionId,
    isPlaying,
    isPageVisible,
    effectiveMinutes,
    videoProgress,
    isEffective,
    showVerify,
    requireMinutes,

    /**
     * 更新视频当前播放时间
     *
     * 由视频播放器的 timeupdate 事件调用，
     * 同步播放进度到 videoCurrentTime，同时重置空闲计时。
     *
     * @param {number} t - 当前播放时间（秒）
     */
    setVideoTime: (t) => {
      videoCurrentTime.value = t
      // 视频进度变化说明用户正在观看，重置空闲计时
      recordAction()
    },

    /**
     * 更新视频播放状态
     *
     * 由视频播放器的 play/pause 事件调用，
     * 更新 isPlaying 状态，重置空闲计时，并主动上报动作到后端。
     *
     * @param {boolean} v - true 表示播放中，false 表示已暂停
     */
    setPlaying: (v) => {
      isPlaying.value = v
      // 播放/暂停属于明确用户操作，重置空闲计时
      recordAction()
      // 即时上报 play/pause 动作，不等 30 秒心跳周期
      sendAction(v ? 'play' : 'pause')
    },

    /**
     * 人机验证通过回调
     *
     * 由人机验证弹窗组件在验证成功后调用：
     *   1. 关闭验证弹窗（showVerify = false）
     *   2. 重置空闲计时
     *   3. 上报 'verify' 事件，后端留存审计记录
     */
    verifyPass: () => {
      showVerify.value = false
      recordAction()
      // 上报验证通过事件，留存审计记录
      sendAction('verify')
    },

    endSession,
  }
}
