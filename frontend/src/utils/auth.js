import { ref, computed } from 'vue'
import * as dd from 'dingtalk-jsapi'
import api from './api'

// 简易状态管理（不引入 pinia）
const token = ref(localStorage.getItem('token') || '')
const user = ref(JSON.parse(localStorage.getItem('user') || 'null'))

export function useAuthStore() {
  const isLoggedIn = computed(() => !!token.value)
  const isStudent = computed(() => user.value?.role === 'student')
  const isTeacher = computed(() => user.value?.role === 'teacher' || user.value?.role === 'admin')

  async function tryDingTalkLogin() {
    try {
      // 判断是否在钉钉环境
      if (dd.env.platform !== 'notInDingTalk') {
        const authCode = await new Promise((resolve, reject) => {
          dd.ready(() => {
            dd.runtime.permission.requestAuthCode({
              corpId: import.meta.env.VITE_DINGTALK_CORP_ID || '',
              onSuccess: (result) => resolve(result.code),
              onFail: (err) => reject(err),
            })
          })
        })

        const resp = await api.post('/auth/dingtalk', { auth_code: authCode })
        if (resp.data.code === 0) {
          setAuth(resp.data.data.token, resp.data.data.user)
        }
      }
    } catch (e) {
      console.warn('钉钉免登失败:', e)
    }
  }

  function setAuth(newToken, newUser) {
    token.value = newToken
    user.value = newUser
    localStorage.setItem('token', newToken)
    localStorage.setItem('user', JSON.stringify(newUser))
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  return { token, user, isLoggedIn, isStudent, isTeacher, tryDingTalkLogin, setAuth, logout }
}
