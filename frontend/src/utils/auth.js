/**
 * ============================================================================
 * 模块：认证状态管理 (auth.js)
 * ============================================================================
 * 功能：
 *   管理用户认证状态的简易 store（不引入 Pinia，减少依赖体积）：
 *   1. 维护 token 和 user 的响应式状态，自动同步 localStorage
 *   2. 实现钉钉免登流程：获取 authCode → 后端换 JWT → 保存凭证
 *   3. 提供登录/登出方法，供全局使用
 *
 * 在系统中的角色：
 *   - 前端认证核心，所有模块的权限判断都依赖此处的状态
 *   - 是钉钉免登流程的执行者，也是 token 生命周期的管理者
 *   - 以闭包单例模式运行：模块顶层定义 ref，useAuthStore() 返回同一份引用
 *
 * 架构选型说明（为什么不用 Pinia）：
 *   - 本项目认证逻辑简单，只有 token + user 两个状态
 *   - Pinia 会增加打包体积和配置复杂度
 *   - 用 Vue3 ref + 闭包即可实现全局共享的响应式状态
 *   - 如果未来状态复杂度增加（如多角色切换、权限细粒度），可迁移到 Pinia
 *
 * 与其他模块的交互关系：
 *   - 【核心交互】api.js：
 *     api.js 的请求拦截器读取 auth.token 注入请求头
 *     api.js 的 401 响应拦截器调用 auth.logout() 清除登录态
 *     api.js 还是 tryDingTalkLogin 中 POST /auth/dingtalk 的请求工具
 *   - App.vue：onMounted 时调用 auth.tryDingTalkLogin() 触发免登
 *   - router/index.js：权限守卫读取 localStorage 中的 user 判断角色
 *     （注意：守卫直接读 localStorage 而非 auth.user，因为守卫执行时机更早）
 *   - 各页面组件：调用 useAuthStore() 获取 isStudent/isTeacher 做条件渲染
 *
 * 钉钉免登流程详解：
 *   1. 检测 dd.env.platform 是否为 'notInDingTalk'
 *      → 不是：在钉钉客户端内，走免登流程
 *      → 是：浏览器环境，静默跳过（降级为游客模式）
 *   2. 调用 dd.runtime.permission.requestAuthCode 获取 authCode
 *      authCode 是钉钉临时授权码，有效期仅 5 分钟，只能使用一次
 *   3. 将 authCode 发送到后端 /auth/dingtalk 接口
 *      后端用 authCode 向钉钉服务端换取用户信息 → 创建/查找本地用户 → 返回 JWT
 *   4. 收到后端响应后，调用 setAuth 保存 token 和 user
 *      token 用于后续 API 请求的身份验证
 *      user 包含角色信息，用于前端权限控制
 *
 * 闭包单例模式说明：
 *   token 和 user 定义在模块顶层（闭包中），所有调用 useAuthStore() 的地方
 *   拿到的都是同一份 ref 引用。这保证了：
 *   - App.vue 调用 tryDingTalkLogin 成功后 setAuth
 *   - api.js 请求拦截器能立即读取到最新 token
 *   - 页面组件的 isStudent/isTeacher 计算属性自动更新
 * ============================================================================
 */

import { ref, computed } from 'vue'
import * as dd from 'dingtalk-jsapi'   // 钉钉 JSAPI：提供运行环境检测和免登能力
import api from './api'                 // 【交互】用于向后端发送 /auth/dingtalk 请求

/**
 * 认证状态（模块级闭包变量，全局共享）
 *
 * - token：JWT 令牌，后端签发，用于 API 请求的身份验证
 *   初始值从 localStorage 恢复，实现页面刷新后登录态不丢失
 * - user：当前登录用户对象，包含 role 等字段
 *   role 值：'student' | 'teacher' | 'admin'
 *   初始值同样从 localStorage 恢复
 */
const token = ref(localStorage.getItem('token') || '')
const user = ref(JSON.parse(localStorage.getItem('user') || 'null'))

/**
 * 免登进行中标记
 * - true：免登流程正在执行中，401 拦截器不应清除 token（免登完成前的旧请求）
 * - false：免登已完成或未触发，401 正常处理
 */
const dingtalkLoginInProgress = ref(false)

/**
 * 认证 Store 工厂函数
 *
 * 返回认证相关的所有状态和方法，供组件和其他模块使用。
 * 由于 token/user 是模块顶层闭包变量，每次调用返回同一份引用。
 *
 * @returns {Object} 认证 store 对象
 *   - token {Ref<string>} — JWT 令牌（响应式）
 *   - user {Ref<Object|null>} — 当前用户信息（响应式）
 *   - isLoggedIn {ComputedRef<boolean>} — 是否已登录
 *   - isStudent {ComputedRef<boolean>} — 当前用户是否为学生
 *   - isTeacher {ComputedRef<boolean>} — 当前用户是否为教师/管理员
 *   - tryDingTalkLogin {Function} — 尝试钉钉免登
 *   - setAuth {Function} — 设置认证信息
 *   - logout {Function} — 登出
 */
export function useAuthStore() {
  /**
   * 是否已登录 — 基于 token 是否存在判断
   * 用于 App.vue 决定是否需要触发免登流程
   */
  const isLoggedIn = computed(() => !!token.value)

  /**
   * 是否为学生角色
   * 用于页面组件的条件渲染（如显示"我的进度"入口）
   */
  const isStudent = computed(() => user.value?.role === 'student')

  /**
   * 是否为教师或管理员角色
   * admin 归入 teacher 类别，因为管理员拥有教师的所有权限
   * 用于页面组件的条件渲染（如显示"学习统计"入口）
   */
  const isTeacher = computed(() => user.value?.role === 'teacher' || user.value?.role === 'admin')

  /**
   * 尝试钉钉免登
   *
   * 核心流程：
   *   1. 检测运行环境是否为钉钉客户端
   *   2. 调用钉钉 JSAPI 获取 authCode（临时授权码）
   *   3. 将 authCode 发送到后端换取 JWT + 用户信息
   *   4. 成功后调用 setAuth 保存凭证
   *
   * 异常处理策略：
   *   - 整个 try-catch 包裹，任何环节失败都静默降级
   *   - 不抛出错误，不阻塞应用加载，用户以游客身份浏览
   *   - console.warn 输出警告日志，便于开发调试
   *
   * dd.ready() 的作用：
   *   钉钉 JSAPI 需要在 dd.ready 回调中调用，确保运行环境已就绪。
   *   用 Promise 包装使代码可以用 await 同步书写，避免回调地狱。
   *
   * corpId 来源：
   *   import.meta.env.VITE_DINGTALK_CORPID — 构建时从 .env 文件注入，
   *   是钉钉企业的唯一标识，requestAuthCode 需要此参数。
   *   缺少 corpId 时 authCode 获取会失败，但不影响非钉钉环境使用。
   */
  async function tryDingTalkLogin() {
    dingtalkLoginInProgress.value = true
    try {
      const platform = dd.env.platform
      const corpId = import.meta.env.VITE_DINGTALK_CORP_ID || ''
      console.log('[免登调试] platform:', platform, 'corpId:', corpId || '(空)')

      // 判断是否在钉钉客户端内运行
      // dd.env.platform 返回平台标识，'notInDingTalk' 表示不在钉钉环境中
      if (platform !== 'notInDingTalk') {
        if (!corpId) {
          console.error('[免登调试] corpId 为空，免登无法执行。请检查 .env.production 文件是否存在。')
          return
        }

        // 获取钉钉临时授权码 authCode
        const authCode = await new Promise((resolve, reject) => {
          dd.ready(() => {
            dd.runtime.permission.requestAuthCode({
              corpId: corpId,
              onSuccess: (result) => {
                console.log('[免登调试] requestAuthCode 成功, code:', result.code?.substring(0, 8) + '...')
                resolve(result.code)
              },
              onFail: (err) => {
                console.error('[免登调试] requestAuthCode 失败:', JSON.stringify(err))
                reject(err)
              },
            })
          })
        })

        // 【交互】通过 api.js 向后端发送 authCode 换取 JWT
        // 后端接口：POST /api/auth/dingtalk，参数 { auth_code: string }
        // 后端逻辑：authCode → 钉钉服务端换用户信息 → 创建/查找用户 → 签发 JWT
        const resp = await api.post('/auth/dingtalk', { auth_code: authCode })
        if (resp.data.code === 0) {
          // 后端返回 code=0 表示成功，data 中包含 token 和 user
          setAuth(resp.data.data.token, resp.data.data.user)
        }
      }
      // 不在钉钉环境：静默跳过，不打日志（避免浏览器调试时刷屏）
    } catch (e) {
      // 免登失败可能的原因：网络异常、corpId 无效、authCode 过期、后端异常
      // 不阻断应用运行，用户可手动刷新重试
      console.warn('钉钉免登失败:', e)
    } finally {
      dingtalkLoginInProgress.value = false
    }
  }

  /**
   * 设置认证信息（登录成功后调用）
   *
   * 同时更新内存中的响应式变量和 localStorage 持久化存储。
   * - 响应式变量：使 Vue 组件即时感知登录状态变化
   * - localStorage：实现页面刷新后登录态不丢失
   *
   * @param {string} newToken — JWT 令牌字符串
   * @param {Object} newUser — 用户信息对象（至少包含 role 字段）
   */
  function setAuth(newToken, newUser) {
    token.value = newToken
    user.value = newUser
    localStorage.setItem('token', newToken)
    localStorage.setItem('user', JSON.stringify(newUser))  // user 是对象，需序列化存储
  }

  /**
   * 登出（清除登录态）
   *
   * 清除内存和 localStorage 中的 token 和 user。
   * 调用场景：
   *   1. api.js 检测到 401（token 过期/无效）时调用
   *   2. 未来可扩展：用户主动点击退出登录按钮时调用
   *
   * 注意：此方法只清前端状态，不调后端注销接口。
   * JWT 是无状态的，后端不维护会话，前端删除即等效登出。
   */
  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  return { token, user, isLoggedIn, isStudent, isTeacher, tryDingTalkLogin, setAuth, logout, dingtalkLoginInProgress }
}
