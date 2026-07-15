export function getMediaUrl(url) {
  if (!url) return ''
  const normalized = typeof url === 'string' ? url.trim() : ''
  if (!normalized) return ''
  if (/^https?:\/\//i.test(normalized)) return normalized
  if (normalized.startsWith('/api/')) return normalized
  if (normalized.startsWith('/uploads/')) return `/api${normalized}`
  if (normalized.startsWith('uploads/')) return `/api/${normalized}`
  if (normalized.startsWith('homework/')) return `/api/${normalized}`
  if (!normalized.includes('/')) return `/api/uploads/${normalized}`
  return normalized
}

export function getAbsoluteMediaUrl(url) {
  const mediaUrl = getMediaUrl(url)
  return toAbsoluteUrl(mediaUrl)
}

export function toAbsoluteUrl(url) {
  return url ? new URL(url, window.location.origin).href : ''
}

export function getFileExtension(file) {
  if (typeof file !== 'string') return ''
  const normalized = file.trim().split('?')[0].split('#')[0]
  const match = normalized.match(/\.([a-z0-9]+)$/i)
  return match ? match[1].toLowerCase() : ''
}

export function isImageFile(file) {
  return ['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(getFileExtension(file))
}

export function isPdf(file) {
  return getFileExtension(file) === 'pdf'
}

export function isDocumentFile(file) {
  return ['doc', 'docx'].includes(getFileExtension(file))
}

export function getFileName(file) {
  if (typeof file !== 'string') return 'question-file'
  const normalized = file.trim().split('?')[0].split('#')[0]
  const raw = normalized.split('/').filter(Boolean).pop() || 'question-file'
  try {
    return decodeURIComponent(raw)
  } catch {
    return raw
  }
}

export function fileLabel(file) {
  if (isPdf(file)) return 'PDF'
  if (isDocumentFile(file)) return getFileExtension(file).toUpperCase()
  const extension = getFileExtension(file)
  if (extension) return extension.toUpperCase()
  return '文件'
}

export function getAttachmentDisplayName(sectionTitle, kind, index = 0, total = 1) {
  const title = typeof sectionTitle === 'string' && sectionTitle.trim() ? sectionTitle.trim() : '附件'
  const kindLabel = kind === 'answer' ? '答案' : '作业'
  const suffix = total > 1 ? `${index + 1}` : ''
  return `${title} ${kindLabel}${suffix}`.trim()
}

export function getAttachmentDownloadName(sectionTitle, kind, index = 0, total = 1, file = '') {
  const baseName = getAttachmentDisplayName(sectionTitle, kind, index, total)
  const extension = getFileExtension(file)
  return extension ? `${baseName}.${extension}` : baseName
}

export function triggerBrowserDownload(url, filename = '') {
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()
}

export function openFileDownload(url, filename = '') {
  const targetUrl = url + (url.includes('?') ? '&' : '?') + 'download=1&_t=' + Date.now()
  const win = window.open(targetUrl, '_blank')
  if (!win) {
    window.location.href = targetUrl
  }
}
