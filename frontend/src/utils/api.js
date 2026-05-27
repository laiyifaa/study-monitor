import axios from 'axios'
import { useAuthStore } from './auth'

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

// 请求拦截：自动加 token
api.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
})

// 响应拦截：统一处理错误
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const auth = useAuthStore()
      auth.logout()
      window.location.href = '/'
    }
    return Promise.reject(error)
  }
)

export default api
