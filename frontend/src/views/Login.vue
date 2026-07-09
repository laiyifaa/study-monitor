<!--
  @模块：Login.vue — 浏览器登录页
  @页面用途：非钉钉环境（PC浏览器/开发调试）的账号+密码登录
  @数据流：
    1. 用户输入账号+密码 → 调用 POST /auth/login
    2. 后端验证成功 → 返回 JWT + 用户信息
    3. 前端保存到 auth store + localStorage → 跳转到对应首页
       - 学生 → /my-progress
       - 教师/管理员 → /teacher
  @说明：
    钉钉环境走 App.vue 的 tryDingTalkLogin 免登流程，不经过此页面
    此页面仅在浏览器环境中手动导航到 /login 或 token 过期后使用
-->
<template>
  <div class="login-page">
    <div class="login-card">
      <!-- 系统标题和说明 -->
      <div class="login-header">
        <h1>在线学习平台</h1>
        <p class="subtitle">欢迎登录</p>
      </div>

      <!-- 钉钉免登等待状态 -->
      <div v-if="isDingTalkLoggingIn" class="dingtalk-waiting">
        <div class="spinner"></div>
        <p>正在自动登录中...</p>
        <p class="waiting-hint">钉钉环境检测到，正在为您免登</p>
      </div>

      <!-- 登录表单（非免登等待状态时显示） -->
      <template v-else>
      <form @submit.prevent="handleLogin" class="login-form">
        <div class="form-item">
          <label>账号</label>
          <input
            v-model="username"
            type="text"
            placeholder="请输入账号"
            autocomplete="username"
            :disabled="loading"
          />
        </div>
        <div class="form-item">
          <label>密码</label>
          <input
            v-model="password"
            type="password"
            placeholder="请输入密码"
            autocomplete="current-password"
            :disabled="loading"
          />
        </div>

        <!-- 忘记密码链接 -->
        <div class="forgot-link-wrap">
          <span class="forgot-link" @click="showForgotPw = true">忘记密码？</span>
        </div>

        <!-- 错误提示 -->
        <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>

        <!-- 登录按钮 -->
        <button type="submit" class="btn-login" :disabled="loading">
          {{ loading ? '登录中...' : '登 录' }}
        </button>
      </form>

      <!-- 底部提示 -->
      <div class="login-footer">
        <p>钉钉环境打开自动免登，无需手动登录</p>
      </div>
      </template>
    </div>

    <!-- ====== 忘记密码弹窗 ====== -->
    <div v-if="showForgotPw" class="modal-overlay" @click.self="showForgotPw = false">
      <div class="modal-card">
        <h3>忘记密码</h3>
        <div class="form-item">
          <label>账号</label>
          <input v-model="forgotForm.account" type="text" placeholder="请输入您的账号" />
        </div>
        <div class="form-item">
          <label>新密码</label>
          <input v-model="forgotForm.new_password" type="password" placeholder="至少6位" />
        </div>
        <div class="form-item">
          <label>确认新密码</label>
          <input v-model="forgotForm.confirm_password" type="password" placeholder="再次输入新密码" />
        </div>
        <div v-if="forgotError" class="error-msg">{{ forgotError }}</div>
        <div class="modal-actions">
          <button class="btn-sm primary" @click="doForgotPassword" :disabled="forgotLoading">
            {{ forgotLoading ? '重置中...' : '确认重置' }}
          </button>
          <button class="btn-sm" @click="showForgotPw = false">取消</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../utils/auth'
import * as dd from 'dingtalk-jsapi'
import api from '../utils/api'

const router = useRouter()
const auth = useAuthStore()

/** 表单状态 */
const username = ref('')
const password = ref('')
const loading = ref(false)
const errorMsg = ref('')

/** 是否在钉钉环境中且正在等待免登 */
const isDingTalkLoggingIn = ref(false)

/** ============ 忘记密码弹窗状态 ============ */
const showForgotPw = ref(false)
const forgotForm = ref({ account: '', new_password: '', confirm_password: '' })
const forgotLoading = ref(false)
const forgotError = ref('')

/**
 * 钉钉环境检测：如果用户在钉钉客户端内打开登录页，
 * 说明 App.vue 的免登流程可能还没完成（或已完成但路由还没跳转）。
 * 此时显示"正在免登中..."状态，而不是让用户面对登录表单。
 */
onMounted(() => {
  const isInDingTalk = dd.env.platform !== 'notInDingTalk'
  if (isInDingTalk) {
    // 在钉钉环境中，等待免登结果
    isDingTalkLoggingIn.value = true
    // 免登由 App.vue 的 onMounted 触发，这里等一小段时间检查结果
    // 如果已登录（App.vue 免登成功），直接跳转
    setTimeout(() => {
      if (auth.isLoggedIn.value) {
        const role = auth.user.value?.role
        if (role === 'teacher' || role === 'admin') {
          router.replace('/teacher')
        } else {
          router.replace('/my-progress')
        }
      } else {
        // 免登未成功，显示登录表单（降级为手动登录）
        isDingTalkLoggingIn.value = false
      }
    }, 3000)
  }
})

/**
 * 处理登录表单提交
 * 流程：调用 /auth/login → 保存凭证 → 按角色跳转不同首页
 */
async function handleLogin() {
  // 基础校验
  if (!username.value.trim()) {
    errorMsg.value = '请输入账号'
    return
  }
  if (!password.value) {
    errorMsg.value = '请输入密码'
    return
  }

  loading.value = true
  errorMsg.value = ''

  try {
    const res = await api.post('/auth/login', {
      username: username.value.trim(),
      password: password.value,
    })

    if (res.data.code === 0) {
      // 登录成功：保存 token 和用户信息
      const { token: jwt, user: userInfo } = res.data.data
      auth.setAuth(jwt, userInfo)

      // 按角色跳转到对应首页
      if (userInfo.role === 'teacher' || userInfo.role === 'admin') {
        router.push('/teacher')
      } else {
        router.push('/my-progress')
      }
    } else {
      // 后端返回业务错误（账号或密码错误、未设置密码等）
      errorMsg.value = res.data.msg || '登录失败'
    }
  } catch (e) {
    // 网络错误或服务器异常
    if (e.response?.status === 401) {
      errorMsg.value = '账号或密码错误'
    } else {
      errorMsg.value = '网络异常，请稍后重试'
    }
  } finally {
    loading.value = false
  }
}

/**
 * 执行忘记密码重置
 */
async function doForgotPassword() {
  forgotError.value = ''
  if (!forgotForm.value.account.trim()) {
    forgotError.value = '请输入账号'
    return
  }
  if (forgotForm.value.new_password.length < 6) {
    forgotError.value = '新密码至少6位'
    return
  }
  if (forgotForm.value.new_password !== forgotForm.value.confirm_password) {
    forgotError.value = '两次输入的密码不一致'
    return
  }

  forgotLoading.value = true
  try {
    const res = await api.post('/auth/forgot-password', {
      account: forgotForm.value.account.trim(),
      new_password: forgotForm.value.new_password,
    })
    if (res.data.code === 0) {
      alert('密码重置成功，请使用新密码登录')
      showForgotPw.value = false
      forgotForm.value = { account: '', new_password: '', confirm_password: '' }
      // 自动填充账号，方便用户直接登录
      username.value = forgotForm.value.account
    } else {
      forgotError.value = res.data.msg || '重置失败'
    }
  } catch (e) {
    forgotError.value = '网络异常，请稍后重试'
  } finally {
    forgotLoading.value = false
  }
}
</script>

<style scoped>
/* 登录页面：全屏居中布局 */
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
}

/* 登录卡片：白色圆角卡片 */
.login-card {
  background: #fff;
  border-radius: 12px;
  padding: 40px 32px;
  width: 100%;
  max-width: 380px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
}

/* 标题区 */
.login-header {
  text-align: center;
  margin-bottom: 32px;
}
.login-header h1 {
  font-size: 22px;
  color: #333;
  margin-bottom: 8px;
}
.subtitle {
  color: #999;
  font-size: 14px;
}

/* 表单项 */
.form-item {
  margin-bottom: 20px;
}
.form-item label {
  display: block;
  font-size: 14px;
  color: #333;
  margin-bottom: 8px;
  font-weight: 500;
}
.form-item input {
  width: 100%;
  padding: 12px 16px;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  font-size: 15px;
  transition: border-color 0.2s;
  outline: none;
}
.form-item input:focus {
  border-color: #1890ff;
  box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.1);
}
.form-item input:disabled {
  background: #f5f5f5;
  cursor: not-allowed;
}

/* 忘记密码链接 */
.forgot-link-wrap {
  text-align: right;
  margin-bottom: 16px;
}
.forgot-link {
  font-size: 13px;
  color: #1890ff;
  cursor: pointer;
}
.forgot-link:hover {
  text-decoration: underline;
}

/* 错误提示 */
.error-msg {
  color: #ff4d4f;
  font-size: 13px;
  margin-bottom: 16px;
  padding: 8px 12px;
  background: #fff2f0;
  border-radius: 6px;
}

/* 登录按钮 */
.btn-login {
  width: 100%;
  padding: 12px;
  background: #1890ff;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}
.btn-login:hover:not(:disabled) {
  background: #40a9ff;
}
.btn-login:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 底部提示 */
.login-footer {
  margin-top: 24px;
  text-align: center;
}
.login-footer p {
  font-size: 12px;
  color: #bbb;
  line-height: 1.8;
}

/* 钉钉免登等待状态 */
.dingtalk-waiting {
  text-align: center;
  padding: 20px 0;
}
.dingtalk-waiting p {
  font-size: 15px;
  color: #333;
  margin-top: 16px;
}
.dingtalk-waiting .waiting-hint {
  font-size: 12px;
  color: #999;
  margin-top: 8px;
}
.spinner {
  display: inline-block;
  width: 36px;
  height: 36px;
  border: 3px solid #e6f7ff;
  border-top-color: #1890ff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 弹窗样式 */
.modal-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.4); display: flex; align-items: center;
  justify-content: center; z-index: 200;
}
.modal-card {
  background: #fff; border-radius: 12px; padding: 24px;
  width: 90%; max-width: 400px; box-shadow: 0 12px 40px rgba(0,0,0,0.15);
}
.modal-card h3 { font-size: 16px; margin-bottom: 16px; }
.modal-card .form-item { margin-bottom: 14px; }
.modal-card .form-item label { display: block; font-size: 13px; color: #666; margin-bottom: 4px; }
.modal-card .form-item input {
  width: 100%; padding: 8px 12px; border: 1px solid #d9d9d9;
  border-radius: 6px; font-size: 14px; box-sizing: border-box;
}
.modal-actions { display: flex; gap: 10px; justify-content: flex-end; }
.btn-sm { padding: 6px 16px; border: 1px solid #d9d9d9; border-radius: 4px; background: #fff; font-size: 13px; cursor: pointer; }
.btn-sm.primary { background: #1890ff; color: #fff; border-color: #1890ff; }
.btn-sm:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
