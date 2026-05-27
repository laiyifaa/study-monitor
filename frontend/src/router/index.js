import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'CourseList',
    component: () => import('../views/CourseList.vue'),
    meta: { title: '课程列表' },
  },
  {
    path: '/learn/:courseId',
    name: 'StudentLearn',
    component: () => import('../views/StudentLearn.vue'),
    meta: { title: '在线学习', role: 'student' },
  },
  {
    path: '/my-progress',
    name: 'MyProgress',
    component: () => import('../views/StudentProgress.vue'),
    meta: { title: '我的进度', role: 'student' },
  },
  {
    path: '/teacher',
    name: 'TeacherDashboard',
    component: () => import('../views/TeacherDashboard.vue'),
    meta: { title: '学习统计', role: 'teacher' },
  },
  {
    path: '/course-edit/:courseId?',
    name: 'CourseEdit',
    component: () => import('../views/CourseEdit.vue'),
    meta: { title: '编辑课程', role: 'teacher' },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('../views/CourseList.vue'),
    meta: { title: '课程列表' },
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  document.title = to.meta.title || '学习进度监督'

  // 角色权限守卫
  const requiredRole = to.meta.role
  if (requiredRole) {
    const userStr = localStorage.getItem('user')
    if (!userStr) {
      // 未登录，回首页
      return next('/')
    }
    try {
      const user = JSON.parse(userStr)
      // admin 放行所有页面，teacher/student 按角色匹配
      if (user.role === 'admin') {
        return next()
      }
      if (requiredRole === 'teacher' && user.role !== 'teacher') {
        return next('/')
      }
      if (requiredRole === 'student' && user.role !== 'student' && user.role !== 'teacher') {
        return next('/')
      }
    } catch {
      return next('/')
    }
  }

  next()
})

export default router
