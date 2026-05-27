import axios from 'axios'
import { useAuthStore } from './auth'

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

// 请求拦截：自动加 token
api.interceptors.request.use((config) => {
  const auth = useAuthStore()
  const tokenVal = auth.token.value || auth.token  // 兼容 ref 或 plain string
  if (tokenVal) {
    config.headers.Authorization = `Bearer ${tokenVal}`
  }
  return config
})

// 响应拦截：统一处理错误
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const auth = useAuthStore()
      // 仅在已登录状态下收到 401 才清除登录态（token 过期/无效）
      // 未登录状态下不触发跳转，让页面自行处理空数据展示
      const tokenVal = auth.token.value || auth.token
      if (tokenVal) {
        auth.logout()
        // 钉钉环境自动重登，浏览器环境停在首页
        if (window.location.hash !== '#/') {
          window.location.hash = '#/'
        }
      }
    }
    return Promise.reject(error)
  }
)

export default api
