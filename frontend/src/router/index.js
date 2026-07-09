/**
 * ============================================================================
 * 模块：路由配置与权限守卫 (router/index.js)
 * ============================================================================
 * 功能：
 *   1. 定义所有页面路由（路径、组件、元信息）
 *   2. 通过 beforeEach 导航守卫实现角色权限控制
 *   3. 动态设置页面标题
 *
 * 在系统中的角色：
 *   - 前端路由是单页应用的核心，决定了 URL 与页面组件的映射关系
 *   - 权限守卫是安全防线，阻止未授权用户访问 teacher/student 专属页面
 *   - 与 auth.js 配合：守卫从 localStorage 读取 user 角色信息判断权限
 *
 * 路由设计说明：
 *   - '/' 课程列表：公开页面，未登录也可查看（降低使用门槛）
 *   - '/course/:courseId' 课程详情：展示课程信息+小节列表
 *   - '/learn/:courseId/:sectionId' 学习页：仅 student 角色可访问，teacher 也能听课所以放行
 *   - '/my-progress' 我的进度：仅 student 角色可访问
 *   - '/teacher' 统计看板：仅 teacher/admin 可访问
 *   - '/course-edit/:courseId?' 编辑课程：仅 teacher/admin 可访问，courseId 可选（新建/编辑）
 *   - '/:pathMatch(.*)*' 404兜底：跳转课程列表而非空白页
 *
 * 使用 Hash 模式（createWebHashHistory）的原因：
 *   - 钉钉 H5 微应用在钉钉客户端内打开，不支持服务端配置 SPA fallback
 *   - Hash 模式（URL 中带 #）不需要后端配合，所有路由由前端处理
 *   - 如果用 History 模式，刷新页面会 404（后端没有对应的路由处理）
 *
 * 与其他模块的交互关系：
 *   - auth.js：守卫读取 localStorage 中 user 字段判断角色（不直接 import auth.js，
 *     是因为守卫在应用初始化阶段就可能执行，直接读 localStorage 更安全）
 *   - App.vue：App.vue 的 tryDingTalkLogin 要先于守卫执行完成（onMounted → 路由跳转）
 *   - api.js：api.js 的 401 处理会将用户重定向到首页（window.location.hash = '#/'），
 *     与本文件的守卫形成闭环：api.js 清除登录态 + 守卫拦截越权访问
 * ============================================================================
 */

import { createRouter, createWebHashHistory } from 'vue-router'

/**
 * 路由表定义
 * - component 使用 () => import() 动态导入，实现路由懒加载
 *   首屏只加载 CourseList，其他页面按需加载，减少首屏体积
 * - meta 字段用于存储路由级元信息：
 *   - title：页面标题，在 beforeEach 中设置 document.title
 *   - role：允许访问的最低角色，在 beforeEach 中做权限校验
 */
const routes = [
  {
    path: '/',
    name: 'CourseList',
    component: () => import('../views/CourseList.vue'),
    meta: { title: '课程列表' },  // 无 role 限制，公开页面
  },
  {
    // 浏览器登录页：非钉钉环境下手动输入用户名+密码登录
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { title: '登录' },  // 无 role 限制，登录页本身不需要认证
  },
  {
    // 课程详情页：展示课程信息+小节列表，学生点击小节进入学习
    path: '/course/:courseId',
    name: 'CourseDetail',
    component: () => import('../views/CourseDetail.vue'),
    meta: { title: '课程详情' },  // 无 role 限制，登录即可
  },
  {
    path: '/learn/:courseId/:sectionId',  // :courseId 课程ID + :sectionId 小节ID
    name: 'StudentLearn',
    component: () => import('../views/StudentLearn.vue'),
    meta: { title: '在线学习', role: 'student' },  // 仅学生角色
  },
  {
    path: '/my-progress',
    name: 'MyProgress',
    component: () => import('../views/StudentProgress.vue'),
    meta: { title: '我的进度', role: 'student' },  // 仅学生角色
  },
  {
    path: '/teacher',
    name: 'TeacherDashboard',
    component: () => import('../views/TeacherDashboard.vue'),
    meta: { title: '学习统计', role: 'teacher' },  // 仅教师/管理员
  },
  {
    path: '/course-edit/:courseId?',  // courseId 可选：无参=新建课程，有参=编辑课程
    name: 'CourseEdit',
    component: () => import('../views/CourseEdit.vue'),
    meta: { title: '编辑课程', role: 'teacher' },  // 仅教师/管理员
  },
  {
    // 管理后台：用户管理+班级管理，仅管理员/教师可访问
    path: '/admin',
    name: 'AdminPanel',
    component: () => import('../views/AdminPanel.vue'),
    meta: { title: '管理后台', role: 'teacher' },  // 仅教师/管理员
  },
  {
    // 教师端作业管理：发布作业、查看提交、批改报告
    path: '/homework/:courseId',
    name: 'HomeworkManage',
    component: () => import('../views/HomeworkManage.vue'),
    meta: { title: '作业管理', role: 'teacher' },
  },
  {
    // 学生端作业列表：查看作业、上传图片、查看批改报告
    path: '/student-homework/:courseId',
    name: 'StudentHomework',
    component: () => import('../views/StudentHomework.vue'),
    meta: { title: '课程作业', role: 'student' },
  },
  {
    // 运维监控面板：服务器资源、容器状态、业务数据、存储信息
    path: '/ops',
    name: 'OpsPanel',
    component: () => import('../views/OpsPanel.vue'),
    meta: { title: '运维监控', role: 'admin' },  // 仅管理员
  },
  {
    // v4.0: 公告列表
    path: '/announcements',
    name: 'AnnouncementList',
    component: () => import('../views/AnnouncementList.vue'),
    meta: { title: '通知公告' },
  },
  {
    // v4.0: 发布公告
    path: '/announcement-create',
    name: 'AnnouncementCreate',
    component: () => import('../views/AnnouncementCreate.vue'),
    meta: { title: '发布公告', role: 'teacher' },
  },
  {
    // v4.0: 学习排行榜
    path: '/leaderboard/:courseId',
    name: 'Leaderboard',
    component: () => import('../views/Leaderboard.vue'),
    meta: { title: '学习排行榜' },
  },
  {
    // v4.0: 小节评价
    path: '/feedback/:sectionId',
    name: 'SectionFeedback',
    component: () => import('../views/SectionFeedback.vue'),
    meta: { title: '课程评价' },
  },
  {
    // 课程评价概览（教师/管理员查看某课程所有小节评价统计）
    path: '/feedback-overview/:courseId',
    name: 'FeedbackOverview',
    component: () => import('../views/FeedbackOverview.vue'),
    meta: { title: '课程评价概览', role: 'teacher' },
  },
  {
    // v4.0: 签到日历
    path: '/checkin',
    name: 'CheckInCalendar',
    component: () => import('../views/CheckInCalendar.vue'),
    meta: { title: '学习签到', role: 'student' },
  },
  {
    // v4.0: 学习报告
    path: '/study-report',
    name: 'StudyReport',
    component: () => import('../views/StudyReport.vue'),
    meta: { title: '学习报告' },
  },
  {
    // v4.0: 使用指南
    path: '/guide',
    name: 'UserGuide',
    component: () => import('../views/UserGuide.vue'),
    meta: { title: '使用指南' },
  },
  {
    // 404 兜底路由：匹配所有未定义的路径
    // 不用专门的 404 页面，而是重定向到课程列表，对用户更友好
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('../views/CourseList.vue'),
    meta: { title: '课程列表' },
  },
]

// 创建路由实例
// createWebHashHistory() 使用 hash 模式（URL 中带 #），适合钉钉 H5 微应用
const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

/**
 * 全局前置守卫 (beforeEach)
 *
 * 每次路由跳转前执行，负责两件事：
 * 1. 设置页面标题（document.title）
 * 2. 角色权限校验（基于 meta.role 和 localStorage 中的用户角色）
 *
 * 权限逻辑：
 *   - 无 meta.role 的路由（如课程列表）：所有人可访问
 *   - meta.role='student'：admin 和 teacher 也能访问（教师也需要能看学习页面）
 *   - meta.role='teacher'：仅 admin 和 teacher 可访问
 *   - 未登录用户访问受限路由：重定向到首页 '/'
 *
 * 为什么在此直接读 localStorage 而不用 auth.js？
 *   - 守卫可能在 auth.js 初始化之前执行（路由初始化先于组件挂载）
 *   - 直接读 localStorage 更可靠，不依赖 Vue 响应式系统的初始化顺序
 */
router.beforeEach((to, from, next) => {
  // 动态设置页面标题，用于浏览器标签页和钉钉标题栏显示
  document.title = to.meta.title || '在线学习平台'

  // 检查目标路由是否需要特定角色
  const requiredRole = to.meta.role
  if (requiredRole) {
    // 从 localStorage 读取用户信息（JSON 格式）
    const userStr = localStorage.getItem('user')
    if (!userStr) {
      // 未登录（localStorage 无 user 记录），跳转到登录页
      // 携带原始目标路径，登录成功后可自动跳回
      return next({ path: '/login', query: { redirect: to.fullPath } })
    }
    try {
      const user = JSON.parse(userStr)
      // admin 拥有最高权限，放行所有页面
      if (user.role === 'admin') {
        return next()
      }
      // teacher 专属页面：仅 teacher 角色可访问
      if (requiredRole === 'teacher' && user.role !== 'teacher') {
        return next('/')
      }
      // student 专属页面：teacher 也能访问学生页面（预览学生视角）
      if (requiredRole === 'student' && user.role !== 'student' && user.role !== 'teacher') {
        return next('/')
      }
    } catch {
      // JSON 解析失败（localStorage 数据被篡改或损坏），跳转登录页
      return next('/login')
    }
  }

  // 无需角色校验的页面，直接放行
  next()
})

export default router
