/**
 * ═══════════════════════════════════════════════════════════════════
 * 模块：deviceInfo — 设备信息采集工具
 * ═══════════════════════════════════════════════════════════════════
 *
 * 【功能】
 *   采集学生登录时的设备信息（操作系统、浏览器/WebView、屏幕分辨率、
 *   是否钉钉/微信环境、是否移动端、网络类型等），用于后续设备兼容性
 *   问题排查（如某些设备视频无法播放时定位具体设备分布）。
 *
 * 【设计思路】
 *   - 采集动作在登录请求时触发，非侵入式，所有字段失败时返回空值/默认值
 *   - 不引入第三方 UA 解析库，自实现一套针对钉钉/微信 WebView 优化的轻量解析
 *   - 输出对象结构与后端 DeviceInfo schema 严格对齐，便于后端直接接收
 *
 * 【使用场景】
 *   - Login.vue 的 handleLogin() 调用 collectDeviceInfo() 后随登录请求带上
 *   - auth.js 的 tryDingTalkLogin() / bindAccount() 同理
 *
 * 【暴露的接口】
 *   collectDeviceInfo()   — () => Object  采集设备信息，返回后端 DeviceInfo 兼容对象
 *   parseUserAgent(ua)    — (string) => Object  解析UA字符串，返回 {os, browser, isMobile}
 * ═══════════════════════════════════════════════════════════════════
 */

import * as dd from 'dingtalk-jsapi'

/**
 * 解析 User-Agent 字符串，返回操作系统、浏览器、是否移动端信息
 *
 * 识别优先级（覆盖中国 K12 家长最常见的环境）：
 *   1. 钉钉 WebView（iOS/Android）  — DingTalk/x.x.x
 *   2. 微信 WebView（iOS/Android）   — MicroMessenger/x.x.x
 *   3. QQ 浏览器 WebView             — QQ/x.x.x
 *   4. iOS Safari                     — iPhone; CPU iPhone OS like Mac OS X
 *   5. Android Chrome                 — Android ... Chrome/x.x.x
 *   6. 桌面 Chrome/Edge/Firefox/Safari
 *
 * @param {string} ua — navigator.userAgent
 * @returns {{os: string, browser: string, isMobile: boolean, inDingtalk: boolean, inWechat: boolean}}
 */
export function parseUserAgent(ua = '') {
  const result = {
    os: '',
    browser: '',
    isMobile: false,
    inDingtalk: false,
    inWechat: false,
  }
  if (!ua) return result

  // —— 操作系统 & 是否移动端 ——
  // iOS: "iPhone; CPU iPhone OS 15_2 like Mac OS X"
  // Android: "Android 12; ...)"
  const iosMatch = ua.match(/iPhone OS\s+(\d+[_\.]\d+(?:[_\.]\d+)?)/i)
  const androidMatch = ua.match(/Android\s+(\d+(?:\.\d+)?)/i)
  const isIPhone = /iPhone/i.test(ua)
  const isIPad = /iPad/i.test(ua) || (/Macintosh/i.test(ua) && 'ontouchend' in document)

  if (iosMatch) {
    result.os = `iOS ${iosMatch[1].replace(/_/g, '.')}`
    result.isMobile = true
  } else if (androidMatch) {
    result.os = `Android ${androidMatch[1]}`
    result.isMobile = true
  } else if (isIPad) {
    result.os = 'iPadOS'
    result.isMobile = true
  } else if (/Windows NT\s+(\d+\.\d+)/i.test(ua)) {
    const v = ua.match(/Windows NT\s+(\d+\.\d+)/i)[1]
    const map = { '10.0': 'Windows 10/11', '6.3': 'Windows 8.1', '6.2': 'Windows 8', '6.1': 'Windows 7' }
    result.os = map[v] || `Windows NT ${v}`
  } else if (/Macintosh|Mac OS X\s+(\d+[_\.]\d+)/i.test(ua)) {
    const m = ua.match(/Mac OS X\s+(\d+[_\.]\d+)/i)
    result.os = m ? `macOS ${m[1].replace(/_/g, '.')}` : 'macOS'
  } else if (/Linux/i.test(ua)) {
    result.os = 'Linux'
  }

  // —— 浏览器 / WebView 识别 ——
  // 钉钉 UA 形如：Mozilla/5.0 ... DingTalk/6.5.20.21 ...
  // 微信 UA 形如：Mozilla/5.0 ... MicroMessenger/8.0.27 ...
  const dingtalkMatch = ua.match(/DingTalk\/(\d+(?:\.\d+)+)/i)
  if (dingtalkMatch) {
    result.inDingtalk = true
    const platform = isIPhone ? 'iOS' : (androidMatch ? 'Android' : 'PC')
    result.browser = `DingTalk-${platform} ${dingtalkMatch[1]}`
  } else if (/MicroMessenger\/(\d+(?:\.\d+)+)/i.test(ua)) {
    result.inWechat = true
    const v = ua.match(/MicroMessenger\/(\d+(?:\.\d+)+)/i)[1]
    const platform = isIPhone ? 'iOS' : (androidMatch ? 'Android' : 'PC')
    result.browser = `WeChat-${platform} ${v}`
  } else if (/QQ\/(\d+(?:\.\d+)+)/i.test(ua)) {
    const v = ua.match(/QQ\/(\d+(?:\.\d+)+)/i)[1]
    result.browser = `QQBrowser ${v}`
  } else if (/Edge\/(\d+)/i.test(ua)) {
    result.browser = `Edge ${ua.match(/Edge\/(\d+)/i)[1]}`
  } else if (/Edg\/(\d+)/i.test(ua)) {
    // 新版 Edge (Chromium)
    result.browser = `Edge ${ua.match(/Edg\/(\d+)/i)[1]}`
  } else if (/Chrome\/(\d+)/i.test(ua) && !/Edg/i.test(ua)) {
    result.browser = `Chrome ${ua.match(/Chrome\/(\d+)/i)[1]}`
  } else if (/Firefox\/(\d+)/i.test(ua)) {
    result.browser = `Firefox ${ua.match(/Firefox\/(\d+)/i)[1]}`
  } else if (/Version\/(\d+[\.\d]+).*Safari/i.test(ua)) {
    result.browser = `Safari ${ua.match(/Version\/(\d+[\.\d]+)/i)[1]}`
  } else {
    // 兜底：截取 UA 前 60 字符作为标识
    result.browser = ua.substring(0, 60)
  }

  // 移动端兜底判定（部分国产浏览器 UA 可能不带 iOS/Android 关键字但带 Mobile）
  if (!result.isMobile && /Mobile|Android|iPhone|iPod/i.test(ua)) {
    result.isMobile = true
  }

  return result
}

/**
 * 采集完整设备信息，返回与后端 DeviceInfo schema 对齐的对象
 *
 * 字段对应：
 *   platform      ← navigator.platform
 *   os            ← parseUserAgent().os
 *   browser       ← parseUserAgent().browser
 *   screen        ← `${screen.width}x${screen.height}`
 *   in_dingtalk   ← parseUserAgent().inDingtalk（同时校验钉钉 JSAPI dd.env.platform）
 *   in_wechat     ← parseUserAgent().inWechat
 *   is_mobile     ← parseUserAgent().isMobile
 *   network_type  ← navigator.connection.effectiveType（部分浏览器支持）
 *
 * 任何采集异常都不抛错，返回空值，确保不影响登录流程。
 *
 * @returns {Object} 与后端 DeviceInfo schema 对齐的对象
 */
export function collectDeviceInfo() {
  if (typeof window === 'undefined' || !navigator) {
    return {
      platform: '',
      os: '',
      browser: '',
      screen: '',
      in_dingtalk: false,
      in_wechat: false,
      is_mobile: false,
      network_type: '',
    }
  }

  const ua = navigator.userAgent || ''
  const parsed = parseUserAgent(ua)

  // 屏幕：避免 SSR 时无 window.screen 报错
  let screenSize = ''
  try {
    if (window.screen && window.screen.width && window.screen.height) {
      screenSize = `${window.screen.width}x${window.screen.height}`
    }
  } catch (_) { /* 忽略 */ }

  // 网络类型：navigator.connection 仅在部分浏览器可用（Chrome 系列）
  let networkType = ''
  try {
    const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection
    if (conn && conn.effectiveType) {
      networkType = conn.effectiveType  // 如 '4g' / 'wifi'（部分浏览器把 wifi 归到 4g）
    }
  } catch (_) { /* 忽略 */ }

  // 钉钉环境判断：UA 检测 + 钉钉 JSAPI 双重校验
  // dd.env.platform 在钉钉内返回 'ios'/'android'/'pc'，非钉钉返回 'notInDingTalk'
  let inDingtalk = parsed.inDingtalk
  try {
    if (dd && dd.env && dd.env.platform && dd.env.platform !== 'notInDingTalk') {
      inDingtalk = true
      // 如果 UA 没识别出操作系统，从 dd.env.platform 补充
      if (!parsed.os) {
        const p = dd.env.platform.toLowerCase()
        if (p === 'ios') parsed.os = 'iOS'
        else if (p === 'android') parsed.os = 'Android'
        else if (p === 'pc') parsed.os = 'PC'
      }
    }
  } catch (_) { /* 忽略 dd.env 异常 */ }

  return {
    platform: (navigator.platform || '').toString().substring(0, 50),
    os: (parsed.os || '').substring(0, 100),
    browser: (parsed.browser || '').substring(0, 100),
    screen: screenSize,
    in_dingtalk: inDingtalk,
    in_wechat: parsed.inWechat,
    is_mobile: parsed.isMobile,
    network_type: networkType.substring(0, 20),
  }
}
