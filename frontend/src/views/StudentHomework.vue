<template>
  <div class="student-homework-page">
    <h2 class="page-title">课程作业</h2>

    <div v-if="loading" class="loading">加载中...</div>

    <template v-else>
      <div v-if="!assignment" class="empty">
        <p>暂无作业</p>
      </div>

      <div v-else class="assignment-detail">
        <div class="assignment-header">
          <h3>{{ assignment.title }}</h3>
          <span class="status-badge" :class="assignment.status">{{ statusText(assignment.status) }}</span>
        </div>
        <p class="desc">{{ assignment.description || '暂无描述' }}</p>
        <div class="meta">
          <span v-if="assignment.deadline">截止：{{ formatDate(assignment.deadline) }}</span>
        </div>

        <div v-if="assignment.status === 'published'" class="submit-section">
          <button class="btn-primary" @click="showSubmitModal = true">提交作业</button>
          <button class="btn-secondary" @click="loadMySubmission">查看我的提交</button>
        </div>

        <div v-if="mySubmission" class="my-submission">
          <h4>我的提交</h4>
          <div class="submission-images">
            <img v-for="(img, i) in mySubmission.images" :key="i" :src="img" class="preview" />
          </div>
          <div v-if="mySubmission.report" class="report">
            <div class="score">分数：{{ mySubmission.report.score }}</div>
            <div class="feedback">{{ mySubmission.report.feedback }}</div>
          </div>
          <div v-else class="pending">等待批改中...</div>
        </div>
      </div>
    </template>

    <div v-if="showSubmitModal" class="modal-overlay" @click.self="closeSubmitModal">
      <div class="modal">
        <h3>提交作业</h3>
        <div class="form-group">
          <label>上传作业图片</label>
          <input type="file" multiple accept="image/*" @change="handleFileSelect" />
        </div>
        <div v-if="previewImages.length > 0" class="preview-images">
          <img v-for="(img, i) in previewImages" :key="i" :src="img" class="preview" />
        </div>
        <div v-if="uploading" class="uploading">上传中...</div>
        <div class="modal-actions">
          <button class="btn-secondary" @click="closeSubmitModal">取消</button>
          <button class="btn-primary" :disabled="uploading || uploadedUrls.length === 0" @click="submitHomework">提交</button>
        </div>
      </div>
    </div>

    <div class="bottom-nav">
      <router-link to="/" class="nav-item">课程</router-link>
      <router-link to="/my-progress" class="nav-item">我的进度</router-link>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../utils/api.js'

const route = useRoute()
const courseId = route.params.courseId

const loading = ref(false)
const assignment = ref(null)
const mySubmission = ref(null)
const showSubmitModal = ref(false)

const previewImages = ref([])
const uploadedUrls = ref([])
const uploading = ref(false)

onMounted(() => {
  loadAssignment()
})

async function loadAssignment() {
  loading.value = true
  try {
    const res = await api.get(`/homework/assignments/${courseId}`)
    assignment.value = res.data.data
    if (assignment.value) {
      loadMySubmission()
    }
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function loadMySubmission() {
  if (!assignment.value) return
  try {
    const res = await api.get('/homework/my-submissions', {
      params: { assignment_id: assignment.value.id }
    })
    const list = res.data.data || []
    mySubmission.value = list[0] || null
  } catch (e) {
    console.error(e)
  }
}

async function handleFileSelect(e) {
  const files = Array.from(e.target.files)
  if (files.length === 0) return

  previewImages.value = files.map(f => URL.createObjectURL(f))
  uploadedUrls.value = []
  uploading.value = true

  for (const file of files) {
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await api.post('/homework/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      uploadedUrls.value.push(res.data.data.url)
    } catch (err) {
      alert('上传失败：' + err.message)
    }
  }
  uploading.value = false
}

async function submitHomework() {
  if (uploadedUrls.value.length === 0) {
    alert('请先上传图片')
    return
  }
  try {
    await api.post('/homework/submissions', {
      assignment_id: assignment.value.id,
      images: uploadedUrls.value,
    })
    alert('提交成功')
    closeSubmitModal()
    loadMySubmission()
  } catch (e) {
    alert('提交失败：' + (e.response?.data?.detail || e.message))
  }
}

function closeSubmitModal() {
  showSubmitModal.value = false
  previewImages.value = []
  uploadedUrls.value = []
}

function statusText(status) {
  return { draft: '草稿', published: '已发布', closed: '已关闭' }[status] || status
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString('zh-CN')
}
</script>

<style scoped>
.student-homework-page {
  max-width: 800px;
  margin: 0 auto;
  padding: 20px;
  padding-bottom: 70px;
}

.page-title {
  margin-bottom: 20px;
}

.btn-primary {
  background: #1890ff;
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
}

.btn-primary:disabled {
  background: #d9d9d9;
  cursor: not-allowed;
}

.btn-secondary {
  background: #f0f0f0;
  color: #333;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
}

.assignment-detail {
  background: white;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.assignment-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.status-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.status-badge.draft { background: #f0f0f0; color: #666; }
.status-badge.published { background: #e6f7ff; color: #1890ff; }
.status-badge.closed { background: #fff7e6; color: #fa8c16; }

.desc {
  color: #666;
  margin-bottom: 8px;
}

.meta {
  font-size: 12px;
  color: #999;
  margin-bottom: 16px;
}

.submit-section {
  display: flex;
  gap: 8px;
  margin-top: 16px;
}

.my-submission {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #f0f0f0;
}

.my-submission h4 {
  margin-bottom: 12px;
}

.submission-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.preview {
  width: 100px;
  height: 100px;
  object-fit: cover;
  border-radius: 4px;
}

.report {
  background: #f6ffed;
  padding: 12px;
  border-radius: 4px;
}

.score {
  font-weight: 500;
  color: #52c41a;
  font-size: 18px;
}

.feedback {
  margin-top: 8px;
}

.pending {
  color: #fa8c16;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.modal {
  background: white;
  border-radius: 8px;
  padding: 24px;
  width: 500px;
  max-height: 80vh;
  overflow-y: auto;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 4px;
  font-weight: 500;
}

.form-group input[type="file"] {
  width: 100%;
}

.preview-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.uploading {
  color: #1890ff;
  margin-bottom: 16px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}

.loading, .empty {
  text-align: center;
  padding: 40px;
  color: #999;
}

.bottom-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  background: white;
  display: flex;
  border-top: 1px solid #f0f0f0;
}

.nav-item {
  flex: 1;
  text-align: center;
  padding: 12px;
  color: #666;
  text-decoration: none;
}

.nav-item.router-link-exact-active {
  color: #1890ff;
}
</style>
