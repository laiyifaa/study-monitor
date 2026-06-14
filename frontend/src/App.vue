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
      <span class="app-title">在线学习平台</span>
    </div>
    <div v-if="auth.isLoggedIn.value" class="header-right">
      <!-- 运维面板入口：ops 和 admin 可见 -->
      <router-link v-if="auth.user.value?.role === 'ops' || auth.user.value?.role === 'admin'" to="/ops" class="btn-ops-link">运维</router-link>
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

  <!-- ====== 修改密码弹窗 ====== -->
  <div v-if="showChangePw" class="modal-overlay" @click.self="showChangePw = false">
    <div class="modal-card">
      <h3>修改密码</h3>
      <div class="form-item">
        <label>当前密码</label>
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
      <div class="modal-actions">
        <button class="btn-sm primary" @click="doChangePassword" :disabled="pwLoading">
          {{ pwLoading ? '修改中...' : '确认修改' }}
        </button>
        <button class="btn-sm" @click="showChangePw = false">取消</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from './utils/auth'  // 【交互】引用 auth.js 的认证状态管理
import api from './utils/api'

const router = useRouter()
// 获取认证 store 的单例实例
const auth = useAuthStore()

/** ============ 修改密码弹窗状态 ============ */
const showChangePw = ref(false)
const pwForm = ref({ old_password: '', new_password: '', confirm_password: '' })
const pwLoading = ref(false)
const pwError = ref('')

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
  if (role === 'ops') return '运维'
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
  if (!pwForm.value.old_password) {
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
    const res = await api.post('/auth/change-password', {
      old_password: pwForm.value.old_password,
      new_password: pwForm.value.new_password,
    })
    if (res.data.code === 0) {
      alert('密码修改成功')
      showChangePw.value = false
      pwForm.value = { old_password: '', new_password: '', confirm_password: '' }
    } else {
      pwError.value = res.data.msg || '修改失败'
    }
  } catch (e) {
    pwError.value = e.response?.data?.detail || '网络异常，请稍后重试'
  } finally {
    pwLoading.value = false
  }
}

onMounted(async () => {
  // 应用首次加载/刷新时，检查是否已有有效 token
  if (!auth.isLoggedIn.value) {
    // 尝试钉钉免登：检测钉钉环境 → 获取 authCode → 后端换 JWT
    // 如果不在钉钉环境（如本地浏览器调试），此函数会静默跳过
    await auth.tryDingTalkLogin()
  }
})
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
.role-tag.ops { background: #e6fffb; color: #13c2c2; }

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
</style>
