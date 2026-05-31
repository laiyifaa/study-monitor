<!--
  @模块：AdminPanel.vue — 管理后台
  @页面用途：管理员/教师操作用户和班级的管理界面
  @布局：标签页切换（用户管理 / 班级管理）
  @权限：仅 admin/teacher 可访问
-->
<template>
  <div class="admin-page">
    <!-- 返回导航 -->
    <div class="back-nav">
      <router-link to="/teacher" class="back-link">&larr; 返回统计看板</router-link>
    </div>
    <h2 class="page-title">管理后台</h2>

    <!-- 标签页切换 -->
    <div class="tabs">
      <button :class="['tab', activeTab === 'users' && 'active']" @click="activeTab = 'users'">用户管理</button>
      <button :class="['tab', activeTab === 'classes' && 'active']" @click="activeTab = 'classes'">班级管理</button>
    </div>

    <!-- ====== 用户管理 ====== -->
    <div v-if="activeTab === 'users'" class="tab-content">
      <!-- 筛选栏 -->
      <div class="filter-bar">
        <select v-model="userFilter.role" @change="loadUsers">
          <option value="">全部角色</option>
          <option value="student">学生</option>
          <option value="teacher">教师</option>
          <option value="admin">管理员</option>
        </select>
        <select v-model="userFilter.class_name" @change="loadUsers">
          <option value="">全部班级</option>
          <option v-for="c in classes" :key="c.class_name" :value="c.class_name">{{ c.class_name }}</option>
        </select>
        <input v-model="userFilter.search" placeholder="搜索姓名..." @input="debounceLoadUsers" />
        <button class="btn-sm primary" @click="showCreateUser">+ 新增用户</button>
      </div>

      <!-- 用户表格 -->
      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>姓名</th>
              <th>角色</th>
              <th>班级</th>
              <th>密码</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in users" :key="u.id">
              <td>{{ u.id }}</td>
              <td>{{ u.name }}</td>
              <td>
                <!-- 管理员可修改角色 -->
                <select v-if="isAdmin" :value="u.role" @change="changeRole(u.id, $event.target.value)" class="role-select">
                  <option value="student">学生</option>
                  <option value="teacher">教师</option>
                  <option value="admin">管理员</option>
                </select>
                <!-- 教师只能查看 -->
                <span v-else class="role-tag" :class="u.role">{{ roleLabel(u.role) }}</span>
              </td>
              <td>{{ u.class_name || '-' }}</td>
              <td>
                <span :class="u.has_password ? 'pw-set' : 'pw-unset'">
                  {{ u.has_password ? '已设置' : '未设置' }}
                </span>
              </td>
              <td>
                <button class="btn-sm" @click="showResetPw(u)">重置密码</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ====== 班级管理 ====== -->
    <div v-if="activeTab === 'classes'" class="tab-content">
      <!-- 创建班级 -->
      <div class="filter-bar">
        <input v-model="newClassName" placeholder="输入新班级名称" />
        <button class="btn-sm primary" @click="createClass">创建班级</button>
      </div>

      <!-- 班级表格 -->
      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>班级名称</th>
              <th>学生数</th>
              <th>教师数</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in classes" :key="c.class_name">
              <td>{{ c.class_name }}</td>
              <td>{{ c.student_count }}</td>
              <td>{{ c.teacher_count }}</td>
              <td>
                <button class="btn-sm" @click="showAssignStudents(c.class_name)">分配学生</button>
                <button v-if="isAdmin" class="btn-sm warn" @click="deleteClass(c.class_name)">删除</button>
              </td>
            </tr>
            <tr v-if="classes.length === 0">
              <td colspan="4" class="empty-cell">暂无班级数据</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ====== 重置密码弹窗 ====== -->
    <div v-if="resetPwUser" class="modal-overlay" @click.self="resetPwUser = null">
      <div class="modal-card">
        <h3>重置密码 — {{ resetPwUser.name }}</h3>
        <div class="form-item">
          <label>新密码</label>
          <input v-model="newPassword" type="text" placeholder="至少6位" />
        </div>
        <div class="modal-actions">
          <button class="btn-sm primary" @click="doResetPassword" :disabled="resetting">
            {{ resetting ? '重置中...' : '确认重置' }}
          </button>
          <button class="btn-sm" @click="resetPwUser = null">取消</button>
        </div>
      </div>
    </div>

    <!-- ====== 分配学生弹窗 ====== -->
    <div v-if="assignTarget" class="modal-overlay" @click.self="assignTarget = null">
      <div class="modal-card">
        <h3>分配学生到 {{ assignTarget }}</h3>
        <div class="student-list">
          <label v-for="u in allStudents" :key="u.id" class="student-check">
            <input type="checkbox" :value="u.id" v-model="checkedStudentIds" />
            <span>{{ u.name }} <small>({{ u.class_name || '未分班' }})</small></span>
          </label>
        </div>
        <div class="modal-actions">
          <button class="btn-sm primary" @click="doAssignStudents" :disabled="assigning">
            {{ assigning ? '分配中...' : `确认分配 (${checkedStudentIds.length}人)` }}
          </button>
          <button class="btn-sm" @click="assignTarget = null">取消</button>
        </div>
      </div>
    </div>

    <!-- ====== 新增用户弹窗 ====== -->
    <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
      <div class="modal-card">
        <h3>新增用户</h3>
        <div class="form-item">
          <label>姓名 *</label>
          <input v-model="newUser.name" placeholder="请输入用户姓名" />
        </div>
        <div class="form-item">
          <label>角色</label>
          <select v-model="newUser.role" class="form-select">
            <option value="student">学生</option>
            <option value="teacher">教师</option>
            <option value="admin">管理员</option>
          </select>
        </div>
        <div class="form-item">
          <label>班级</label>
          <select v-model="newUser.class_name" class="form-select">
            <option value="">不分配班级</option>
            <option v-for="c in classes" :key="c.class_name" :value="c.class_name">{{ c.class_name }}</option>
          </select>
        </div>
        <div class="form-item">
          <label>初始密码</label>
          <input v-model="newUser.password" type="text" placeholder="至少6位" />
        </div>
        <div class="modal-actions">
          <button class="btn-sm primary" @click="doCreateUser" :disabled="creating">
            {{ creating ? '创建中...' : '确认创建' }}
          </button>
          <button class="btn-sm" @click="showCreateModal = false">取消</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '../utils/auth'
import api from '../utils/api'

const auth = useAuthStore()
const isAdmin = computed(() => auth.user.value?.role === 'admin')

/** 标签页切换 */
const activeTab = ref('users')

/** ============ 用户管理状态 ============ */
const users = ref([])
const classes = ref([])
const userFilter = ref({ role: '', class_name: '', search: '' })
let debounceTimer = null

/** ============ 班级管理状态 ============ */
const newClassName = ref('')

/** ============ 弹窗状态 ============ */
const resetPwUser = ref(null)     // 正在重置密码的用户
const newPassword = ref('')
const resetting = ref(false)

const assignTarget = ref(null)    // 正在分配学生的班级名
const allStudents = ref([])       // 所有学生列表（弹窗用）
const checkedStudentIds = ref([]) // 勾选的学生ID
const assigning = ref(false)

/** ============ 新增用户弹窗状态 ============ */
const showCreateModal = ref(false)  // 新增用户弹窗是否可见
const creating = ref(false)         // 创建请求进行中
const newUser = ref({               // 新增用户表单数据
  name: '',
  role: 'student',
  class_name: '',
  password: '123456',
})

/**
 * 加载用户列表
 */
async function loadUsers() {
  const params = {}
  if (userFilter.value.role) params.role = userFilter.value.role
  if (userFilter.value.class_name) params.class_name = userFilter.value.class_name
  if (userFilter.value.search) params.search = userFilter.value.search

  const res = await api.get('/admin/users', { params })
  if (res.data.code === 0) {
    users.value = res.data.data
  }
}

/**
 * 输入搜索的防抖：300ms 后再发请求
 */
function debounceLoadUsers() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => loadUsers(), 300)
}

/**
 * 加载班级列表
 */
async function loadClasses() {
  const res = await api.get('/admin/classes')
  if (res.data.code === 0) {
    classes.value = res.data.data
  }
}

/**
 * 角色中文名
 */
function roleLabel(role) {
  return { student: '学生', teacher: '教师', admin: '管理员' }[role] || role
}

/**
 * 修改用户角色
 */
async function changeRole(userId, newRole) {
  try {
    const res = await api.put(`/admin/users/${userId}/role`, { role: newRole })
    if (res.data.code === 0) {
      await loadUsers()
    } else {
      alert(res.data.msg || '修改失败')
    }
  } catch (e) {
    alert('修改失败')
  }
}

/**
 * 显示重置密码弹窗
 */
function showResetPw(user) {
  resetPwUser.value = user
  newPassword.value = ''
}

/**
 * 执行重置密码
 */
async function doResetPassword() {
  if (newPassword.value.length < 6) {
    alert('密码至少6位')
    return
  }
  resetting.value = true
  try {
    const res = await api.post(`/admin/users/${resetPwUser.value.id}/reset-password`, {
      new_password: newPassword.value,
    })
    if (res.data.code === 0) {
      alert('密码重置成功')
      resetPwUser.value = null
      await loadUsers()
    } else {
      alert(res.data.msg || '重置失败')
    }
  } catch (e) {
    alert('重置失败')
  } finally {
    resetting.value = false
  }
}

/**
 * 创建班级
 */
async function createClass() {
  if (!newClassName.value.trim()) return
  try {
    const res = await api.post('/admin/classes', { class_name: newClassName.value.trim() })
    if (res.data.code === 0) {
      newClassName.value = ''
      await loadClasses()
    } else {
      alert(res.data.msg || '创建失败')
    }
  } catch (e) {
    alert('创建失败')
  }
}

/**
 * 删除班级
 */
async function deleteClass(className) {
  if (!confirm(`确定删除班级"${className}"？学生将被移出班级，但账号和数据保留。`)) return
  try {
    const res = await api.delete(`/admin/classes/${encodeURIComponent(className)}`)
    if (res.data.code === 0) {
      await loadClasses()
      await loadUsers()
    } else {
      alert(res.data.msg || '删除失败')
    }
  } catch (e) {
    alert('删除失败')
  }
}

/**
 * 显示分配学生弹窗
 */
async function showAssignStudents(className) {
  assignTarget.value = className
  // 加载所有学生
  const res = await api.get('/admin/users', { params: { role: 'student' } })
  if (res.data.code === 0) {
    allStudents.value = res.data.data
    // 默认勾选已在该班级的学生
    checkedStudentIds.value = res.data.data
      .filter(u => u.class_name === className)
      .map(u => u.id)
  }
}

/**
 * 执行分配学生
 */
async function doAssignStudents() {
  if (checkedStudentIds.value.length === 0) {
    alert('请至少选择一名学生')
    return
  }
  assigning.value = true
  try {
    const res = await api.put(`/admin/classes/${encodeURIComponent(assignTarget.value)}/students`, {
      user_ids: checkedStudentIds.value,
    })
    if (res.data.code === 0) {
      alert(res.data.msg || '分配成功')
      assignTarget.value = null
      await loadClasses()
      await loadUsers()
    } else {
      alert(res.data.msg || '分配失败')
    }
  } catch (e) {
    alert('分配失败')
  } finally {
    assigning.value = false
  }
}

/**
 * 打开新增用户弹窗，重置表单
 */
function showCreateUser() {
  newUser.value = { name: '', role: 'student', class_name: '', password: '123456' }
  showCreateModal.value = true
}

/**
 * 执行新增用户
 * 流程：
 *   1. 校验姓名和密码
 *   2. 调用 POST /admin/users 创建用户
 *   3. 创建成功后刷新用户列表和班级列表
 */
async function doCreateUser() {
  if (!newUser.value.name.trim()) {
    alert('请输入用户姓名')
    return
  }
  if (newUser.value.password.length < 6) {
    alert('密码至少6位')
    return
  }

  creating.value = true
  try {
    const res = await api.post('/admin/users', {
      name: newUser.value.name.trim(),
      role: newUser.value.role,
      class_name: newUser.value.class_name,
      password: newUser.value.password,
    })
    if (res.data.code === 0) {
      alert(`用户 "${res.data.data.name}" 创建成功，ID=${res.data.data.id}`)
      showCreateModal.value = false
      await Promise.all([loadUsers(), loadClasses()])
    } else {
      alert(res.data.msg || '创建失败')
    }
  } catch (e) {
    alert('创建失败')
  } finally {
    creating.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadUsers(), loadClasses()])
})
</script>

<style scoped>
.admin-page { padding: 16px; max-width: 960px; margin: 0 auto; }
.page-title { font-size: 20px; margin-bottom: 16px; }

/* 标签页 */
.tabs { display: flex; gap: 0; margin-bottom: 20px; border-bottom: 2px solid #f0f0f0; }
.tab {
  padding: 10px 24px; border: none; background: none; font-size: 15px;
  color: #999; cursor: pointer; border-bottom: 2px solid transparent;
  margin-bottom: -2px; transition: all 0.2s;
}
.tab.active { color: #1890ff; border-bottom-color: #1890ff; font-weight: 600; }

/* 筛选栏 */
.filter-bar { display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
.filter-bar select, .filter-bar input {
  padding: 8px 12px; border: 1px solid #d9d9d9; border-radius: 6px; font-size: 13px;
}
.filter-bar input { flex: 1; min-width: 120px; }

/* 表格 */
.table-wrapper { overflow-x: auto; background: #fff; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { background: #f5f7fa; padding: 10px 8px; text-align: left; font-weight: 600; color: #666; }
td { padding: 10px 8px; border-bottom: 1px solid #f0f0f0; }
.empty-cell { text-align: center; color: #999; padding: 30px; }

/* 角色标签 */
.role-tag { font-size: 12px; padding: 2px 8px; border-radius: 10px; }
.role-tag.student { background: #e6f7ff; color: #1890ff; }
.role-tag.teacher { background: #f6ffed; color: #52c41a; }
.role-tag.admin { background: #fff7e6; color: #fa8c16; }

/* 角色下拉 */
.role-select {
  padding: 3px 6px; border: 1px solid #d9d9d9; border-radius: 4px;
  font-size: 12px; cursor: pointer;
}

/* 密码状态 */
.pw-set { color: #52c41a; font-size: 12px; }
.pw-unset { color: #faad14; font-size: 12px; }

/* 小按钮 */
.btn-sm {
  padding: 4px 12px; border: 1px solid #d9d9d9; border-radius: 4px;
  background: #fff; font-size: 12px; cursor: pointer; transition: all 0.2s;
}
.btn-sm:hover { border-color: #1890ff; color: #1890ff; }
.btn-sm.primary { background: #1890ff; color: #fff; border-color: #1890ff; }
.btn-sm.primary:hover { background: #40a9ff; }
.btn-sm.warn { color: #ff4d4f; border-color: #ffccc7; }
.btn-sm.warn:hover { background: #fff1f0; border-color: #ff4d4f; }

/* 弹窗 */
.modal-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.4); display: flex; align-items: center;
  justify-content: center; z-index: 200;
}
.modal-card {
  background: #fff; border-radius: 12px; padding: 24px;
  width: 90%; max-width: 440px; box-shadow: 0 12px 40px rgba(0,0,0,0.15);
}
.modal-card h3 { font-size: 16px; margin-bottom: 16px; }
.form-item { margin-bottom: 16px; }
.form-item label { display: block; font-size: 13px; color: #666; margin-bottom: 6px; }
.form-item input {
  width: 100%; padding: 10px 12px; border: 1px solid #d9d9d9;
  border-radius: 6px; font-size: 14px;
}
/* 表单内下拉选择框 */
.form-select {
  width: 100%; padding: 10px 12px; border: 1px solid #d9d9d9;
  border-radius: 6px; font-size: 14px; background: #fff; cursor: pointer;
}
.modal-actions { display: flex; gap: 10px; justify-content: flex-end; }

/* 学生列表（弹窗内） */
.student-list {
  max-height: 300px; overflow-y: auto; margin-bottom: 16px;
  border: 1px solid #f0f0f0; border-radius: 6px; padding: 8px;
}
.student-check {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 4px; cursor: pointer; font-size: 14px;
}
.student-check:hover { background: #f5f7fa; }
.student-check small { color: #999; }

/* 返回导航 */
.back-nav { margin-bottom: 8px; }
.back-link { color: #1890ff; font-size: 14px; text-decoration: none; }
.back-link:hover { text-decoration: underline; }
</style>
