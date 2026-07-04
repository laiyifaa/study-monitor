/**
 * ============================================================================
 * 模块：Axios 请求封装 (api.js)
 * ============================================================================
 * 功能：
 *   创建预配置的 Axios 实例，通过拦截器实现：
 *   1. 请求拦截：自动在每个请求的 Authorization 头注入 Bearer token
 *   2. 响应拦截：统一处理 401 未授权错误，清除过期登录态并重定向首页
 *
 * 在系统中的角色：
 *   - 前端所有 API 请求的统一出口，各页面组件 import 此实例发请求
 *   - 是认证闭环的关键环节：auth.js 存 token → api.js 自动注入 token →
 *     后端校验 token → 401 时 api.js 触发 auth.js 清除 token
 *
 * 与其他模块的交互关系：
 *   - 【核心交互】auth.js：请求拦截时读取 token，401 时调用 auth.logout()
 *     api.js → 读取 → auth.js 的 token ref（请求注入）
 *     api.js → 写入 → auth.js 的 logout()（401 清除登录态）
 *   - router/index.js：401 时通过 window.location.hash 跳转首页，
 *     router 守卫随后拦截越权访问，形成安全闭环
 *   - 各页面组件：import api 后直接调用 api.get/post/put/delete
 *     组件无需关心 token 注入和错误处理，全部由拦截器代理
 *
 * 认证交互时序（请求→401→重登）：
 *   页面调用 api.get('/xxx')
 *     → 请求拦截：从 auth.js 读取 token，注入 Authorization: Bearer xxx
 *     → 后端返回 401（token 过期/无效）
 *     → 响应拦截：检测到 401 + token 存在（说明是登录态过期而非未登录）
 *     → 调用 auth.logout() 清除本地登录态
 *     → 跳转首页 '#' → App.vue onMounted 检测未登录 → 重新 tryDingTalkLogin
 * ============================================================================
 */

import axios from 'axios'
import { useAuthStore } from './auth'  // 【交互】读取 token 和调用 logout

/**
 * 创建 Axios 实例
 * - baseURL: '/api' — 所有请求 URL 自动加上 /api 前缀，
 *   配合 Vite 的 proxy 配置将 /api 代理到后端服务地址，
 *   避免跨域问题（开发环境），生产环境由 Nginx 反代
 * - timeout: 15000 — 15秒超时，网课视频相关接口可能较慢，
 *   但也不能无限等待，15秒是用户体验和网络稳定性的平衡值
 */
const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

/**
 * 请求拦截器：自动注入 Bearer Token
 *
 * 每个发往后端的请求都会经过此拦截器，自动在 Header 中附加 JWT token。
 * 这样各业务组件发起请求时无需手动传递 token，降低遗漏风险。
 *
 * token 读取方式：auth.token.value || auth.token
 * - auth.token 是 Vue3 的 ref 对象，正常情况通过 .value 读取
 * - 但某些边界情况下（如热更新/循环依赖）可能拿到原始字符串
 * - 双重读取确保兼容性，避免因 ref 包装导致 token 为空而请求失败
 */
api.interceptors.request.use((config) => {
  const auth = useAuthStore()
  // 兼容 ref 或 plain string：ref 取 .value，原始字符串直接用
  const tokenVal = auth.token.value || auth.token
  if (tokenVal) {
    // JWT 标准格式：Authorization: Bearer <token>
    // 后端 FastAPI 的 OAuth2PasswordBearer 会解析此 Header
    config.headers.Authorization = `Bearer ${tokenVal}`
  }
  return config
})

/**
 * 响应拦截器：统一错误处理
 *
 * 成功响应：直接原样返回，由业务组件处理数据
 * 错误响应：重点处理 401（未授权），其他错误直接抛出
 *
 * 401 处理的关键区分：
 * - 已登录状态收到 401 → token 过期/无效 → 清除登录态 + 跳转首页
 *   清除后 App.vue 会重新触发 tryDingTalkLogin，实现自动重登
 * - 未登录状态收到 401 → 本来就没 token，不做特殊处理
 *   避免在用户首次访问课程列表时被重定向，影响体验
 *
 * 跳转方式用 window.location.hash 而非 router.push：
 * - 拦截器在 Vue 组件上下文之外，可能拿不到 router 实例
 * - 直接修改 hash 简单可靠，且会触发 router 的路由匹配
 */
api.interceptors.response.use(
  (response) => response,  // 成功响应，原样返回
  (error) => {
    if (error.response?.status === 401) {
      // 免登进行中时，忽略 401（这些是免登完成前发出的旧请求）
      const auth = useAuthStore()
      if (auth.dingtalkLoginInProgress) {
        return Promise.reject(error)
      }
      // 判断当前是否有 token：有 token 说明是"登录过期"，无 token 说明是"未登录"
      // 仅在登录过期时清除登录态，避免未登录用户的首次请求触发登出逻辑
      const tokenVal = auth.token.value || auth.token
      if (tokenVal) {
        // 【交互】调用 auth.js 的 logout，清除 token + user + localStorage
        auth.logout()
        // Token 过期时跳转登录页，而非首页
        // 首页是公开页面，用户可能不知道为何看到空数据
        // 登录页明确提示需要重新认证，体验更好
        if (window.location.hash !== '#/login') {
          window.location.hash = '#/login'
        }
      }
    }
    // 非 401 错误（400/403/404/500...）直接抛出，由业务组件 catch 处理
    return Promise.reject(error)
  }
)

export default api
