import * as dd from 'dingtalk-jsapi'

/**
 * 钉钉 JSAPI 封装
 */
export function useDingTalk() {
  const isDingTalk = dd.env.platform !== 'notInDingTalk'

  // 获取免登授权码
  const getAuthCode = (corpId) =>
    new Promise((resolve, reject) => {
      dd.ready(() => {
        dd.runtime.permission.requestAuthCode({
          corpId,
          onSuccess: (result) => resolve(result.code),
          onFail: (err) => reject(err),
        })
      })
    })

  // 设置导航栏标题
  const setTitle = (title) => {
    dd.ready(() => {
      dd.biz.navigation.setTitle({ title })
    })
  }

  // 预览文件
  const previewFile = (url, name) => {
    dd.ready(() => {
      dd.biz.file.preview({ url, fileName: name })
    })
  }

  // 打开链接
  const openLink = (url) => {
    dd.ready(() => {
      dd.biz.util.openLink({ url })
    })
  }

  return { isDingTalk, getAuthCode, setTitle, previewFile, openLink }
}
