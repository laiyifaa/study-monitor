/**
 * ═══════════════════════════════════════════════════════════════════
 * 模块：useDingTalk — 钉钉 JSAPI 封装
 * ═══════════════════════════════════════════════════════════════════
 *
 * 【功能】
 *   对钉钉客户端 JSAPI 做二次封装，提供免登授权码获取、
 *   导航栏标题设置、文件预览、链接跳转等能力的 Promise 化调用。
 *
 * 【设计思路】
 *   - 钉钉 H5 微应用必须通过 dd.ready() 回调才能安全调用 JSAPI，
 *     本模块将回调风格统一转为 Promise，方便 async/await 使用。
 *   - 通过 isDingTalk 标识判断当前是否运行在钉钉容器内，
 *     调用方可据此做降级处理（如浏览器环境跳转登录页）。
 *
 * 【使用场景】
 *   - 学生在钉钉工作台打开网课应用时，自动调用 getAuthCode 获取
 *     免登授权码，后端据此换取用户身份，实现零输入登录。
 *   - 教师端设置页面标题、预览学习报告文件、跳转外部链接等。
 *
 * 【暴露的接口】
 *   isDingTalk   — boolean  是否运行在钉钉容器内
 *   getAuthCode  — (corpId: string) => Promise<string>  获取免登授权码
 *   setTitle     — (title: string) => void              设置导航栏标题
 *   previewFile  — (url: string, name: string) => void   预览文件
 *   openLink     — (url: string) => void                 在钉钉内打开链接
 * ═══════════════════════════════════════════════════════════════════
 */
import * as dd from 'dingtalk-jsapi'

export function useDingTalk() {
  /**
   * 判断当前是否运行在钉钉客户端容器内
   * - dd.env.platform 在钉钉内返回平台标识（如 'pc' / 'android' / 'ios'）
   * - 在浏览器中直接打开时返回 'notInDingTalk'
   * - 调用方据此决定是否走免登流程，还是降级到账号密码登录
   */
  const isDingTalk = dd.env.platform !== 'notInDingTalk'

  /**
   * 获取免登授权码（authCode）
   *
   * 调用链路：
   *   1. 前端调用 getAuthCode(corpId)
   *   2. 钉钉 JSAPI → 钉钉服务端 → 返回 authCode
   *   3. 前端将 authCode 发送给后端 POST /auth/dingtalk
   *   4. 后端用 authCode + corpId + corpSecret 调用钉钉开放平台换取 userid
   *   5. 后端查库匹配学生身份，签发 JWT 并返回
   *
   * @param {string} corpId - 企业/组织的 corpId（在钉钉开放平台应用详情中获取）
   * @returns {Promise<string>} 授权码 authCode，有效期 5 分钟
   */
  const getAuthCode = (corpId) =>
    new Promise((resolve, reject) => {
      // dd.ready 确保钉钉 JSAPI 桥接初始化完毕后才执行
      dd.ready(() => {
        dd.runtime.permission.requestAuthCode({
          corpId,
          onSuccess: (result) => resolve(result.code),
          onFail: (err) => reject(err),
        })
      })
    })

  /**
   * 设置钉钉 H5 页面导航栏标题
   *
   * - 仅在钉钉容器内生效，浏览器调用无效果
   * - 通常在页面路由切换后调用，让导航栏标题与页面内容一致
   *
   * @param {string} title - 要显示的导航栏标题文本
   */
  const setTitle = (title) => {
    dd.ready(() => {
      dd.biz.navigation.setTitle({ title })
    })
  }

  /**
   * 在钉钉内置文件预览器中打开文件
   *
   * - 支持常见文档格式（pdf/doc/xls/ppt 等）
   * - 钉钉客户端负责下载和渲染，无需额外安装阅读器
   * - 适用于预览学习报告、课程资料等
   *
   * @param {string} url  - 文件的下载地址（需公网可访问）
   * @param {string} name - 文件名（含扩展名，影响预览器选择）
   */
  const previewFile = (url, name) => {
    dd.ready(() => {
      dd.biz.file.preview({ url, fileName: name })
    })
  }

  /**
   * 在钉钉内打开外部链接
   *
   * - 会在钉钉内置浏览器中打开，而非系统浏览器
   * - 适用于跳转到通知公告、外部学习平台等
   *
   * @param {string} url - 要打开的目标链接
   */
  const openLink = (url) => {
    dd.ready(() => {
      dd.biz.util.openLink({ url })
    })
  }

  return { isDingTalk, getAuthCode, setTitle, previewFile, openLink }
}
