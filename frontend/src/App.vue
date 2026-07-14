<!--
  ============================================================================
  模块：根组件 (App.vue)
  ============================================================================
  功能：
    应用的根组件，负责两件事：
    1. 渲染 <router-view />，作为所有页面组件的容器
    2. 在 onMounted 时检测登录态，若未登录则尝试钉钉免登

  在系统中的角色：
    - 整个单页应用的外壳，所有页面都通过 <router-view /> 在此处渲染
    - 是认证流程的起点：每次应用加载/刷新时，都会在此触发 tryDingTalkLogin
    - 与 router/index.js 配合：路由守卫控制页面权限，App.vue 负责获取登录凭证

  与其他模块的交互关系：
    - 调用 auth.js 的 useAuthStore() 获取认证状态和登录方法
    - auth.tryDingTalkLogin() 内部调用 api.js 发起 /auth/dingtalk 请求
    - 登录成功后 auth.js 将 token/user 写入 localStorage，后续 router 守卫读取
    - <router-view /> 渲染 router/index.js 中匹配的页面组件

  认证时序（应用启动时）：
    main.js 挂载 → App.vue onMounted → 检测 isLoggedIn
      → 未登录：tryDingTalkLogin() → 获取 authCode → POST /auth/dingtalk
        → 成功：setAuth(token, user) → localStorage 持久化
        → 失败：静默降级，用户以游客身份浏览课程列表
      → 已登录：跳过，直接展示当前路由页面
  ============================================================================
-->

<template>
  <!-- 全局顶栏：显示用户信息和退出按钮，登录页不显示 -->
  <header v-if="showHeader" class="app-header">
    <div class="header-left">
      <span class="app-title" @click="goHome">在线学习平台</span>
    </div>
    <div v-if="auth.isLoggedIn.value" class="header-right">
      <!-- 运维面板入口：管理员可见 -->
      <router-link v-if="auth.user.value?.role === 'admin'" to="/ops" class="btn-ops-link">运维</router-link>
      <!-- v4.0: 新功能入口 -->
      <router-link to="/announcements" class="btn-feature-link announcement-link">
        公告
        <span v-if="unreadCount > 0" class="unread-badge">{{ unreadCount > 99 ? '99+' : unreadCount }}</span>
      </router-link>
      <router-link v-if="auth.user.value?.role === 'student'" to="/checkin" class="btn-feature-link">签到</router-link>
      <router-link to="/study-report" class="btn-feature-link">报告</router-link>
      <router-link to="/guide" class="btn-feature-link">指南</router-link>
      <!-- 用户角色标签 -->
      <span class="role-tag" :class="auth.user.value?.role">{{ roleLabel }}</span>
      <!-- 用户姓名 -->
      <span class="user-name">{{ auth.user.value?.name }}</span>
      <!-- 修改密码按钮 -->
      <button class="btn-changepw" @click="showChangePw = true">改密</button>
      <!-- 退出按钮 -->
      <button class="btn-logout" @click="handleLogout">退出</button>
    </div>
    <div v-else class="header-right">
      <router-link to="/login" class="btn-login-link">登录</router-link>
    </div>
  </header>

  <!-- 路由出口：所有页面组件（CourseList、StudentLearn、TeacherDashboard...）
       都在此处渲染，由 router/index.js 的路由表决定显示哪个 -->
  <router-view />

  <!-- ====== 修改密码弹窗（must_change_password时不可关闭） ====== -->
  <div v-if="showChangePw" class="modal-overlay" @click.self="!mustChangePw && (showChangePw = false)">
    <div class="modal-card">
      <h3>{{ mustChangePw ? '首次登录，请修改密码' : (hasPassword ? '修改密码' : '设置密码') }}</h3>
      <p v-if="mustChangePw" class="pw-notice">您的账号使用的是初始默认密码，为了账号安全，请立即修改密码后继续使用。</p>
      <p v-if="mustChangePw" class="pw-hint">默认账号：中考考号，默认密码：中考准考证号后六位</p>
      <div v-if="hasPassword && !mustChangePw" class="form-item">
        <label>当前密码</label>
        <input v-model="pwForm.old_password" type="password" placeholder="请输入当前密码" />
      </div>
      <div v-if="mustChangePw" class="form-item">
        <label>当前密码（初始默认密码）</label>
        <input v-model="pwForm.old_password" type="password" placeholder="请输入当前密码" />
      </div>
      <div class="form-item">
        <label>新密码</label>
        <input v-model="pwForm.new_password" type="password" placeholder="至少6位" />
      </div>
      <div class="form-item">
        <label>确认新密码</label>
        <input v-model="pwForm.confirm_password" type="password" placeholder="再次输入新密码" />
      </div>
      <div v-if="pwError" class="pw-error">{{ pwError }}</div>
      <div v-if="pwSuccess" class="pw-success">{{ pwSuccess }}</div>
      <div class="modal-actions">
        <button class="btn-sm primary" @click="doChangePassword" :disabled="pwLoading">
          {{ pwLoading ? '修改中...' : '确认修改' }}
        </button>
        <button v-if="!mustChangePw" class="btn-sm" @click="showChangePw = false">取消</button>
      </div>
    </div>
  </div>

  <!-- ====== 绑定账号弹窗（钉钉免登无法自动匹配时弹出） ====== -->
  <div v-if="auth.bindInfo.value" class="modal-overlay" @click.self="closeBindDialog">
    <div class="modal-card">
      <div class="modal-header">
        <h3>绑定账号</h3>
        <button class="btn-close" @click="closeBindDialog" title="关闭">×</button>
      </div>
      <p class="bind-hint">钉钉用户「{{ auth.bindInfo.value.dingtalk_name }}」需要绑定学习平台账号</p>
      <div class="bind-credential-hint">
        默认账号：中考考号，默认密码：准考证号后六位
      </div>
      <div class="form-item">
        <label>请输入您的账号</label>
        <input v-model="bindAccountInput" type="text" placeholder="请输入账号（如准考证号）" />
      </div>
      <div class="form-item">
        <label>请输入密码</label>
        <input v-model="bindPasswordInput" type="password" placeholder="请输入密码" />
      </div>
      <div v-if="bindError" class="pw-error">{{ bindError }}</div>
      <div class="modal-actions">
        <button class="btn-sm" @click="closeBindDialog">跳过，使用账号密码登录</button>
        <button class="btn-sm primary" @click="doBindAccount" :disabled="bindLoading">
          {{ bindLoading ? '绑定中...' : '确认绑定' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from './utils/auth'  // 【交互】引用 auth.js 的认证状态管理
import * as dd from 'dingtalk-jsapi'  // 钉钉环境检测：判断是否在钉钉客户端内
import api from './utils/api'

const router = useRouter()
// 获取认证 store 的单例实例
const auth = useAuthStore()

/** ============ 未读公告数 ============ */
const unreadCount = ref(0)

async function fetchUnreadCount() {
  if (!auth.isLoggedIn.value) return
  try {
    const res = await api.get('/announcements/unread-count')
    if (res.data.code === 0) {
      unreadCount.value = res.data.data.count
    }
  } catch (e) {
    // 静默失败，不影响使用
  }
}

/** ============ 修改密码弹窗状态 ============ */
const showChangePw = ref(false)
const pwForm = ref({ old_password: '', new_password: '', confirm_password: '' })

/** 用户是否已设置密码（钉钉免登用户首次没有密码） */
const hasPassword = computed(() => !!auth.user.value?.has_password)
/** 是否必须修改密码（批量导入的默认密码，安全性低，首次登录强制修改） */
const mustChangePw = computed(() => !!auth.user.value?.must_change_password)
const pwLoading = ref(false)
const pwError = ref('')
const pwSuccess = ref('')

/** ============ 绑定账号弹窗状态 ============ */
const bindAccountInput = ref('')
const bindPasswordInput = ref('')
const bindError = ref('')
const bindLoading = ref(false)

/**
 * 关闭绑定弹窗，跳转到登录页用账号密码登录
 */
function closeBindDialog() {
  auth.bindInfo.value = null
  bindAccountInput.value = ''
  bindPasswordInput.value = ''
  bindError.value = ''
  router.push('/login')
}

/**
 * 执行绑定账号
 */
async function doBindAccount() {
  bindError.value = ''
  if (!bindAccountInput.value.trim()) {
    bindError.value = '请输入账号'
    return
  }
  bindLoading.value = true
  try {
    const result = await auth.bindAccount(bindAccountInput.value.trim(), bindPasswordInput.value)
    if (result === true) {
      // 绑定成功，清空表单并跳转到对应首页
      bindAccountInput.value = ''
      bindPasswordInput.value = ''
      bindError.value = ''
      // 绑定成功后 setAuth 已在 bindAccount 内部执行，按角色跳转
      const role = auth.user.value?.role
      if (role === 'teacher' || role === 'admin') {
        router.replace('/teacher')
      } else {
        router.replace('/my-progress')
      }
    } else {
      // 绑定失败，显示错误信息
      bindError.value = typeof result === 'string' ? result : '绑定失败'
    }
  } catch (e) {
    bindError.value = '网络异常，请稍后重试'
  } finally {
    bindLoading.value = false
  }
}

/**
 * 是否显示顶栏
 * 登录页不需要顶栏（已有自己的标题和布局），其他页面都显示
 */
const showHeader = computed(() => {
  return router.currentRoute.value.path !== '/login'
})

/**
 * 角色中文标签
 * 在顶栏显示当前用户的角色，方便用户确认身份
 */
const roleLabel = computed(() => {
  const role = auth.user.value?.role
  if (role === 'teacher') return '教师'
  if (role === 'admin') return '管理员'
  return '学生'
})

/**
 * 退出登录
 * 清除认证状态后跳转到登录页
 */
function handleLogout() {
  auth.logout()
  router.push('/login')
}

/**
 * 执行自助修改密码
 * 流程：前端校验 → 调用 POST /auth/change-password → 成功后关闭弹窗
 */
async function doChangePassword() {
  pwError.value = ''
  // 有密码时（含must_change_password）必须输入旧密码
  if (hasPassword.value && !pwForm.value.old_password) {
    pwError.value = '请输入当前密码'
    return
  }
  if (pwForm.value.new_password.length < 6) {
    pwError.value = '新密码至少6位'
    return
  }
  if (pwForm.value.new_password !== pwForm.value.confirm_password) {
    pwError.value = '两次输入的新密码不一致'
    return
  }

  pwLoading.value = true
  try {
    const payload = {
      new_password: pwForm.value.new_password,
    }
    // 有密码时才发送旧密码（must_change_password时也有密码，需要验证）
    if (hasPassword.value) {
      payload.old_password = pwForm.value.old_password
    }
    const res = await api.post('/auth/change-password', payload)
    if (res.data.code === 0) {
      pwSuccess.value = '密码修改成功'
      showChangePw.value = false
      pwForm.value = { old_password: '', new_password: '', confirm_password: '' }
      // 更新本地状态
      if (auth.user.value) {
        auth.user.value.has_password = true
        auth.user.value.must_change_password = false
      }
      // 3秒后清除成功提示
      setTimeout(() => { pwSuccess.value = '' }, 3000)
    } else {
      pwError.value = res.data.msg || '修改失败'
    }
  } catch (e) {
    pwError.value = e.response?.data?.detail || '网络异常，请稍后重试'
  } finally {
    pwLoading.value = false
  }
}

const route = useRoute()

/** ============ 路由变化时刷新未读数 ============ */
// 离开公告页时立即刷新，确保红点及时消失
watch(() => route.path, (newPath, oldPath) => {
  if (oldPath === '/announcements' && newPath !== '/announcements') {
    fetchUnreadCount()
  }
})

onMounted(async () => {
  // 页面刷新时，若用户已登录且需修改密码，直接弹窗
  // 修复：钉钉免登用户不应弹改密窗，通过双重判断排除：
  //   1. loginMethod === 'dingtalk' → 钉钉登录，不弹
  //   2. 当前在钉钉环境中 → 也不弹（兜底，防止 login_method 丢失）
  // 修复：has_password 字段可能不存在于旧版 localStorage 的 user 对象中，
  //   用 nullish coalescing 兜底，避免 undefined 误触发
  const isInDingTalk = dd.env.platform !== 'notInDingTalk'
  if (auth.isLoggedIn.value && auth.loginMethod.value !== 'dingtalk' && !isInDingTalk) {
    const hasPw = auth.user.value?.has_password ?? true  // 字段缺失时视为有密码，不误触发
    if (auth.user.value?.must_change_password || !hasPw) {
      showChangePw.value = true
    }
  }

  // 应用首次加载/刷新时，检查是否已有有效 token
  if (!auth.isLoggedIn.value) {
    // 尝试钉钉免登
    try {
      await auth.tryDingTalkLogin()
    } catch (e) {
      // 免登失败静默降级，用户以游客身份浏览
    }

    // 免登成功后，如果用户仍停留在 /login 页面，按角色自动跳转到对应首页
    // 这是解决"钉钉免登成功但卡在登录页"问题的关键逻辑
    if (auth.isLoggedIn.value && router.currentRoute.value.path === '/login') {
      const role = auth.user.value?.role
      if (role === 'teacher' || role === 'admin') {
        router.replace('/teacher')
      } else {
        router.replace('/my-progress')
      }
    }
  }

  // 登录后：获取未读公告数
  if (auth.isLoggedIn.value) {
    fetchUnreadCount()
    // 每60秒轮询一次未读数
    setInterval(fetchUnreadCount, 60000)
  }
})

/**
 * 监听 auth.pendingChangePw → 新登录后自动弹出改密弹窗
 * 
 * 为什么不用 computed + watch 组合：
 *   之前用 shouldShowChangePw computed 跨组件监听，
 *   但 Login.vue 的 setAuth + router.push 交替执行时，
 *   Vue 响应式时序导致 watch 回调可能被延迟或跳过。
 *   现在改用 auth store 的 pendingChangePw 标志，
 *   setAuth() 时直接设置，避免时序问题。
 */
watch(() => auth.pendingChangePw.value, (val) => {
  if (val) {
    showChangePw.value = true
    auth.pendingChangePw.value = false  // 消费掉标志，避免重复触发
  }
})

/**
 * 点击标题回到主页
 * 学生 → /my-progress，教师/管理员 → /teacher
 *
 * 使用 router.replace() 代替 router.push()：
 *   钉钉 WebView 的 history 管理与标准浏览器不同，
 *   push() 可能导致返回键陷入死循环（当前页→目标页→返回→当前页…）
 *
 * 加 DingTalk fallback（window.location.hash）：
 *   极端情况下 replace() 也可能被钉钉吞掉，
 *   直接改 hash 可确保页面一定会跳转
 */
function goHome() {
  const role = auth.user.value?.role
  const target = role === 'student' ? '/my-progress' : '/teacher'
  if (router.currentRoute.value.path === target) {
    // 已经在目标页面，滚动到顶部
    window.scrollTo({ top: 0, behavior: 'smooth' })
    return
  }
  router.replace(target).catch(() => {
    // replace 失败（钉钉 WebView 兼容性问题），降级为直接改 hash
    window.location.hash = target
  })
}
</script>

<style>
/* 全局样式重置：消除浏览器默认边距，统一盒模型 */
* { margin: 0; padding: 0; box-sizing: border-box; }

/* 全局字体与背景色 */
body { font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif; background: #f5f7fa; color: #333; }

/* ====== 全局顶栏样式 ====== */
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  height: 48px;
  background: #fff;
  border-bottom: 1px solid #f0f0f0;
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}

.header-left {
  display: flex;
  align-items: center;
}

.app-title {
  font-size: 16px;
  font-weight: 600;
  color: #1890ff;
  text-decoration: none;
  cursor: pointer;
}
.app-title:hover {
  opacity: 0.8;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 角色标签 */
.role-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 500;
}
.role-tag.student { background: #e6f7ff; color: #1890ff; }
.role-tag.teacher { background: #f6ffed; color: #52c41a; }
.role-tag.admin { background: #fff7e6; color: #fa8c16; }


/* 用户姓名 */
.user-name {
  font-size: 14px;
  color: #333;
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 退出按钮 */
.btn-logout {
  font-size: 13px;
  padding: 4px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: #fff;
  color: #666;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-logout:hover {
  color: #ff4d4f;
  border-color: #ff4d4f;
}

/* 登录链接 */
.btn-login-link {
  font-size: 13px;
  padding: 4px 12px;
  border: 1px solid #1890ff;
  border-radius: 4px;
  color: #1890ff;
  text-decoration: none;
  transition: all 0.2s;
}
.btn-login-link:hover {
  background: #1890ff;
  color: #fff;
}

/* 运维面板入口 */
.btn-ops-link {
  font-size: 12px;
  padding: 3px 10px;
  border: 1px solid #13c2c2;
  border-radius: 4px;
  color: #13c2c2;
  text-decoration: none;
  transition: all 0.2s;
}
.btn-ops-link:hover {
  background: #13c2c2;
  color: #fff;
}

/* v4.0: 新功能入口按钮 */
.btn-feature-link {
  font-size: 12px;
  padding: 3px 10px;
  border: 1px solid #1890ff;
  border-radius: 4px;
  color: #1890ff;
  text-decoration: none;
  transition: all 0.2s;
  position: relative;
}
.btn-feature-link:hover {
  background: #1890ff;
  color: #fff;
}

/* 公告红点 */
.announcement-link {
  position: relative;
}
.unread-badge {
  position: absolute;
  top: -6px;
  right: -6px;
  min-width: 16px;
  height: 16px;
  line-height: 16px;
  padding: 0 4px;
  background: #ff4d4f;
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  border-radius: 8px;
  text-align: center;
  pointer-events: none;
}

/* 修改密码按钮 */
.btn-changepw {
  font-size: 12px;
  padding: 3px 10px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: #fff;
  color: #666;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-changepw:hover {
  color: #1890ff;
  border-color: #1890ff;
}

/* 弹窗 */
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
.pw-error { color: #ff4d4f; font-size: 13px; margin-bottom: 10px; }
.pw-success { color: #52c41a; font-size: 13px; margin-bottom: 10px; }
.pw-notice { color: #fa8c16; font-size: 13px; margin-bottom: 14px; padding: 8px 12px; background: #fff7e6; border-radius: 6px; line-height: 1.5; }
.pw-hint { color: #1890ff; font-size: 12px; margin-bottom: 14px; padding: 8px 12px; background: #e6f7ff; border-radius: 6px; line-height: 1.5; }

/* 绑定账号弹窗提示 */
.bind-hint {
  font-size: 13px;
  color: #666;
  margin-bottom: 14px;
  line-height: 1.5;
}

/* 绑定弹窗默认账号提示 */
.bind-credential-hint {
  font-size: 12px;
  color: #1890ff;
  margin-bottom: 14px;
  padding: 8px 12px;
  background: #e6f7ff;
  border-radius: 6px;
  line-height: 1.5;
}

/* 弹窗头部（标题+关闭按钮） */
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0;
}
.modal-header h3 {
  margin-bottom: 0;
}

/* 关闭按钮 */
.btn-close {
  width: 28px;
  height: 28px;
  border: none;
  background: none;
  font-size: 20px;
  color: #999;
  cursor: pointer;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  transition: all 0.2s;
}
.btn-close:hover {
  background: #f0f0f0;
  color: #333;
}

/* ====== 全局响应式：顶栏适配 ====== */
@media (max-width: 600px) {
  .app-header { height: 44px; padding: 0 10px; }
  .app-title { font-size: 14px; }
  .header-right { gap: 4px; flex-wrap: nowrap; overflow-x: auto; }

  /* 隐藏部分功能链接文字，只保留图标感 */
  .btn-feature-link { font-size: 11px; padding: 2px 6px; white-space: nowrap; }
  .user-name { max-width: 50px; font-size: 12px; }
  .role-tag { font-size: 10px; padding: 1px 5px; }
  .btn-changepw { display: none; }  /* 手机端隐藏改密按钮，用其他方式访问 */
  .btn-logout { font-size: 12px; padding: 3px 8px; }
}

/* 超小屏：进一步精简 */
@media (max-width: 380px) {
  .app-header { height: 42px; padding: 0 8px; }
  .app-title { font-size: 13px; }
  .btn-feature-link { padding: 2px 4px; font-size: 10px; }
  .btn-ops-link { display: none; }  /* 超小屏隐藏运维入口 */
  .user-name { max-width: 36px; font-size: 11px; }
}
</style>
