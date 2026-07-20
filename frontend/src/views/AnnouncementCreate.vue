<!--
  @模块：AnnouncementCreate.vue — 发布公告（v4.0 新增，v6.0 图文+强制弹窗）
  @页面用途：教师/管理员发布新公告，支持图片上传和强制弹窗
-->
<template>
  <div class="create-page">
    <div class="back-nav">
      <a href="javascript:void(0)" @click="$router.back()" class="back-link">&larr; 返回</a>
    </div>
    <h2>发布公告</h2>
    <div class="form-card">
      <div class="form-group">
        <label>公告标题<span class="required">*</span></label>
        <input v-model="form.title" placeholder="请输入公告标题" />
      </div>
      <div class="form-group">
        <label>关联课程</label>
        <select v-model="form.course_id">
          <option :value="null">全平台公告</option>
          <option v-for="c in courses" :key="c.id" :value="c.id">{{ c.title }}</option>
        </select>
      </div>
      <div class="form-group">
        <label>优先级</label>
        <div class="priority-radio">
          <label :class="{ active: form.priority === 'normal' }"><input type="radio" v-model="form.priority" value="normal" /> 普通</label>
          <label :class="{ active: form.priority === 'important' }"><input type="radio" v-model="form.priority" value="important" /> 重要</label>
          <label :class="{ active: form.priority === 'urgent' }"><input type="radio" v-model="form.priority" value="urgent" /> 紧急</label>
        </div>
      </div>
      <div class="form-group">
        <label class="checkbox-label">
          <input type="checkbox" v-model="form.popup" />
          <span>强制弹窗通知</span>
        </label>
        <p class="form-hint">勾选后，所有用户登录时将自动弹出此公告，确认后才可关闭</p>
      </div>
      <div class="form-group">
        <label>公告内容</label>
        <textarea v-model="form.content" rows="6" placeholder="请输入公告内容"></textarea>
      </div>
      <div class="form-group">
        <label>公告图片（最多 9 张，单张不超过 10MB）</label>
        <div class="image-upload-area">
          <label class="upload-btn" v-if="form.image_urls.length < 9">
            <input type="file" accept="image/*" multiple @change="handleImageSelect" />
            + 添加图片
          </label>
          <span v-if="uploading" class="upload-status">上传中...</span>
        </div>
        <div v-if="form.image_urls.length > 0" class="image-preview-list">
          <div v-for="(url, idx) in form.image_urls" :key="idx" class="image-preview-item">
            <img :src="getImageUrl(url)" />
            <button class="image-remove-btn" @click="removeImage(idx)">&times;</button>
          </div>
        </div>
      </div>
      <div class="form-actions">
        <button class="btn primary" @click="onSubmit" :disabled="submitting">
          {{ submitting ? '发布中...' : '发布公告' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../utils/api'
import { getMediaUrl } from '../utils/homeworkFiles'

const router = useRouter()
const courses = ref([])
const submitting = ref(false)
const uploading = ref(false)
const form = ref({
  title: '',
  content: '',
  priority: 'normal',
  course_id: null,
  image_urls: [],
  popup: false,
})

function getImageUrl(url) {
  return getMediaUrl(url)
}

onMounted(async () => {
  try {
    const res = await api.get('/courses?status=active')
    if (res.data.code === 0) courses.value = res.data.data
  } catch { /* ignore */ }
})

async function handleImageSelect(e) {
  const files = Array.from(e.target.files)
  if (files.length === 0) return
  e.target.value = ''

  const remaining = 9 - form.value.image_urls.length
  const toUpload = files.slice(0, remaining)

  uploading.value = true
  for (const file of toUpload) {
    if (file.size > 10 * 1024 * 1024) {
      alert(`图片 ${file.name} 超过 10MB，已跳过`)
      continue
    }
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await api.post('/announcements/upload-image', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      if (res.data.code === 0) {
        form.value.image_urls.push(res.data.data.url)
      } else {
        alert(res.data.detail || '图片上传失败')
      }
    } catch (err) {
      alert('图片上传失败: ' + (err.response?.data?.detail || err.message))
    }
  }
  uploading.value = false
}

function removeImage(idx) {
  form.value.image_urls.splice(idx, 1)
}

async function onSubmit() {
  if (!form.value.title.trim()) { alert('请输入公告标题'); return }
  submitting.value = true
  try {
    const res = await api.post('/announcements', form.value)
    if (res.data.code === 0) {
      alert('公告发布成功')
      router.push('/announcements')
    } else {
      alert(res.data.detail || '发布失败')
    }
  } catch (e) {
    alert('发布失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.create-page { padding: 16px; max-width: 640px; margin: 0 auto; }
h2 { font-size: 20px; margin-bottom: 16px; }
.back-nav { margin-bottom: 12px; }
.back-link { color: #1890ff; font-size: 14px; text-decoration: none; cursor: pointer; }

.form-card { background: #fff; border-radius: 10px; padding: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
.form-group { margin-bottom: 16px; }
.form-group label { display: block; font-size: 14px; font-weight: 500; margin-bottom: 6px; }
.required { color: #ff4d4f; }
.form-group input[type="text"], .form-group input:not([type]), .form-group textarea, .form-group select {
  width: 100%; padding: 10px 12px; border: 1px solid #d9d9d9; border-radius: 6px;
  font-size: 14px; box-sizing: border-box;
}
.form-group input:focus, .form-group textarea:focus { border-color: #1890ff; outline: none; }

.priority-radio { display: flex; gap: 16px; }
.priority-radio label { display: flex; align-items: center; gap: 4px; font-size: 14px; cursor: pointer; padding: 4px 8px; border-radius: 4px; border: 1px solid #d9d9d9; }
.priority-radio label.active { border-color: #1890ff; color: #1890ff; background: #e6f7ff; }
.priority-radio input { margin: 0; }

.checkbox-label { display: flex !important; align-items: center; gap: 8px; cursor: pointer; }
.checkbox-label input[type="checkbox"] { width: auto !important; margin: 0; }
.form-hint { font-size: 12px; color: #999; margin: 4px 0 0 0; }

.image-upload-area { display: flex; align-items: center; gap: 12px; }
.upload-btn {
  display: inline-block; padding: 8px 16px; border: 1px dashed #1890ff; border-radius: 6px;
  color: #1890ff; font-size: 14px; cursor: pointer; background: #f0f8ff;
}
.upload-btn input { display: none; }
.upload-status { font-size: 13px; color: #faad14; }

.image-preview-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.image-preview-item {
  position: relative; width: 80px; height: 80px; border-radius: 6px; overflow: hidden;
  border: 1px solid #e8e8e8;
}
.image-preview-item img { width: 100%; height: 100%; object-fit: cover; }
.image-remove-btn {
  position: absolute; top: 2px; right: 2px; width: 20px; height: 20px; border-radius: 50%;
  background: rgba(0,0,0,0.5); color: #fff; border: none; font-size: 14px; line-height: 18px;
  text-align: center; cursor: pointer; padding: 0;
}

.form-actions { margin-top: 16px; }
.btn { padding: 8px 20px; border: 1px solid #d9d9d9; border-radius: 6px; background: #fff; font-size: 14px; cursor: pointer; }
.btn.primary { background: #1890ff; color: #fff; border-color: #1890ff; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
