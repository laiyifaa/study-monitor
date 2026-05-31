/**
 * ============================================================================
 * 模块：Vue 应用入口 (main.js)
 * ============================================================================
 * 功能：
 *   创建 Vue3 应用实例，注册全局插件（路由），并挂载到 DOM。
 *   这是整个前端应用的启动点，所有模块由此加载。
 *
 * 在系统中的角色：
 *   - 系统启动入口，相当于 main() 函数
 *   - 本文件仅做"组装"工作：把 App 根组件和 router 路由器组合在一起
 *   - 实际业务逻辑分散在 App.vue（认证触发）、router（权限守卫）、各页面组件中
 *
 * 与其他模块的交互关系：
 *   - 引入 App.vue → 根组件，App.vue 的 onMounted 会调用 auth.js 的钉钉免登
 *   - 引入 router/index.js → 路由实例，内含权限守卫，依赖 auth.js 读取登录态
 *   - 整个应用的认证链路：main.js 挂载 → App.vue 触发 tryDingTalkLogin →
 *     auth.js 获取 authCode → api.js 请求后端换 JWT → token 存入 localStorage
 * ============================================================================
 */

import { createApp } from 'vue'
import App from './App.vue'       // 根组件：包含钉钉自动登录逻辑和全局样式
import router from './router'     // 路由实例：包含路由表和 beforeEach 权限守卫

// 创建 Vue 应用实例，以 App.vue 作为根组件
const app = createApp(App)

// 注册路由插件，使 <router-view> 和 <router-link> 可用，
// 同时激活 router.beforeEach 导航守卫（权限控制的核心）
app.use(router)

// 将应用挂载到 index.html 中的 <div id="app"></div>
// 挂载后触发 App.vue 的 onMounted 生命周期，开始钉钉免登流程
app.mount('#app')
