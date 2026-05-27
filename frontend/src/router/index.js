import { createRouter, createWebHistory } from 'vue-router'

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
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  document.title = to.meta.title || '学习进度监督'
  next()
})

export default router
