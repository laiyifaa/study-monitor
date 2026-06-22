<!--
  @模块：Login.vue — 浏览器登录页
  @页面用途：非钉钉环境（PC浏览器/开发调试）的用户名+密码登录
  @数据流：
    1. 用户输入姓名+密码 → 调用 POST /auth/login
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

      <!-- 登录表单 -->
      <form @submit.prevent="handleLogin" class="login-form">
        <div class="form-item">
          <label>用户名</label>
          <input
            v-model="username"
            type="text"
            placeholder="请输入姓名"
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

        <!-- 错误提示 -->
        <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>

        <!-- 登录按钮 -->
        <button type="submit" class="btn-login" :disabled="loading">
          {{ loading ? '登录中...' : '登 录' }}
        </button>
      </form>

      <!-- 快捷填入：点击只填充表单，不提交，不影响钉钉免登 -->
      <div class="quick-fill">
        <span class="quick-fill-label">快捷登录</span>
        <button class="quick-btn" @click="fillAccount('admin')" :disabled="loading">管理员</button>
        <button class="quick-btn student" @click="fillAccount('student')" :disabled="loading">学生</button>
      </div>

      <!-- 底部提示 -->
      <div class="login-footer">
        <p>钉钉环境打开自动免登，无需手动登录</p>
        <p>首次使用请联系管理员设置密码</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../utils/auth'
import api from '../utils/api'

const router = useRouter()
const auth = useAuthStore()

/** 表单状态 */
const username = ref('')
const password = ref('')
const loading = ref(false)
const errorMsg = ref('')

/**
 * 快捷填入测试账号（仅填充表单，不触发登录）
 */
const quickAccounts = {
  admin:   { username: '张老师', password: 'teacher123' },
  student: { username: '王小明', password: '123456' },
}

function fillAccount(role) {
  const account = quickAccounts[role]
  if (account) {
    username.value = account.username
    password.value = account.password
    errorMsg.value = ''
  }
}

/**
 * 处理登录表单提交
 * 流程：调用 /auth/login → 保存凭证 → 按角色跳转不同首页
 */
async function handleLogin() {
  // 基础校验
  if (!username.value.trim()) {
    errorMsg.value = '请输入用户名'
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
      // 后端返回业务错误（用户名或密码错误、未设置密码等）
      errorMsg.value = res.data.msg || '登录失败'
    }
  } catch (e) {
    // 网络错误或服务器异常
    if (e.response?.status === 401) {
      errorMsg.value = '用户名或密码错误'
    } else {
      errorMsg.value = '网络异常，请稍后重试'
    }
  } finally {
    loading.value = false
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

/* 快捷填入区域 */
.quick-fill {
  margin-top: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.quick-fill-label {
  font-size: 12px;
  color: #bbb;
  margin-right: 4px;
}
.quick-btn {
  padding: 4px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: #fafafa;
  font-size: 12px;
  color: #666;
  cursor: pointer;
  transition: all 0.2s;
}
.quick-btn:hover:not(:disabled) {
  border-color: #1890ff;
  color: #1890ff;
  background: #e6f7ff;
}
.quick-btn.student:hover:not(:disabled) {
  border-color: #52c41a;
  color: #52c41a;
  background: #f6ffed;
}
.quick-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
