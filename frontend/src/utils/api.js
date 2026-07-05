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
 * 401 竞态条件处理：
 *   免登场景下，页面加载时会发出无 token 的请求（如 my-progress），
 *   这些请求的 401 响应可能在免登完成后才到达。
 *   如果 401 拦截器此时清掉刚写入的 token，用户就会退出登录。
 *   解决方案：在请求 config 上记录发送时使用的 token（_sentToken），
 *   401 时只在「失败请求的 token === 当前 token」时才执行登出，
 *   从而区分「过期 token 的 401」和「无 token 旧请求的 401」。
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
 * 同时在 config._sentToken 中记录本次请求使用的 token，
 * 供响应拦截器判断 401 是否来自当前有效的 token。
 */
api.interceptors.request.use((config) => {
  const auth = useAuthStore()
  // 兼容 ref 或 plain string：ref 取 .value，原始字符串直接用
  const tokenVal = auth.token.value || auth.token
  if (tokenVal) {
    // JWT 标准格式：Authorization: Bearer <token>
    // 后端 FastAPI 的 OAuth2PasswordBearer 会解析此 Header
    config.headers.Authorization = `Bearer ${tokenVal}`
    // 记录本次请求使用的 token，用于 401 时判断是否是当前 token
    config._sentToken = tokenVal
  }
  return config
})

/**
 * 响应拦截器：统一错误处理
 *
 * 成功响应：直接原样返回，由业务组件处理数据
 * 错误响应：重点处理 401（未授权），其他错误直接抛出
 *
 * 401 处理逻辑（防竞态）：
 * - 免登场景：页面加载时发出无 token 请求 → 免登成功写入 token →
 *   无 token 请求的 401 延迟到达 → 不应清除刚写入的 token
 * - 真实过期：已登录用户的 token 过期 → 401 → 应清除登录态
 *
 * 判断依据：config._sentToken 是否等于当前 token
 * - 相等：说明是当前 token 过期，需要登出
 * - 不等或无值：说明是旧请求/无 token 请求的 401，忽略
 */
api.interceptors.response.use(
  (response) => response,  // 成功响应，原样返回
  (error) => {
    if (error.response?.status === 401) {
      const auth = useAuthStore()
      const currentToken = auth.token.value || auth.token
      const sentToken = error.config?._sentToken

      // 只在「失败请求使用的 token === 当前 token」时才登出
      // 这排除了两种不需要登出的情况：
      // 1. 请求没有携带 token（sentToken 为空）→ 免登前的旧请求
      // 2. 请求携带的 token 与当前 token 不同 → 已被新 token 替代的旧请求
      if (sentToken && sentToken === currentToken) {
        auth.logout()
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
