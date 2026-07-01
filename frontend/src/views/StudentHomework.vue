<template>
  <div class="student-homework-page">
    <h2 class="page-title">课程作业</h2>

    <div v-if="loading" class="loading">加载中...</div>

    <template v-else>
      <div v-for="section in sections" :key="section.id" class="section-card">
        <div class="section-header">
          <h3>{{ section.title }}</h3>
        </div>
        <div v-if="!assignmentMap[section.id]" class="section-empty">
          <p>暂无作业</p>
        </div>
        <div v-else class="assignment-detail">
          <div class="assignment-header">
            <h4>{{ assignmentMap[section.id].title }}</h4>
            <span class="status-badge" :class="assignmentMap[section.id].status">{{ statusText(assignmentMap[section.id].status) }}</span>
          </div>
          <p class="desc">{{ assignmentMap[section.id].description || '暂无描述' }}</p>
          <div v-if="assignmentMap[section.id].question_files && assignmentMap[section.id].question_files.length > 0" class="question-files">
            <h4>题目文件</h4>
            <div class="question-files-list">
              <div v-for="(file, i) in assignmentMap[section.id].question_files" :key="i" class="question-file">
                <img v-if="!file.endsWith('.pdf')" :src="file" class="question-image" @click="previewImage(file)" />
                <a v-else :href="file" target="_blank" class="pdf-link">📄 查看 PDF</a>
              </div>
            </div>
          </div>
          <div class="meta">
            <span v-if="assignmentMap[section.id].deadline">截止：{{ formatDate(assignmentMap[section.id].deadline) }}</span>
            <span v-if="isOverdue(assignmentMap[section.id])" class="overdue-hint">（已截止）</span>
          </div>

          <div v-if="assignmentMap[section.id].status === 'published'" class="submit-section">
            <button class="btn-primary" @click="openSubmitModal(section.id)">
              {{ mySubmissionMap[section.id] ? '修改提交' : '提交作业' }}
            </button>
          </div>
        </div>

        <div v-if="mySubmissionMap[section.id]" class="my-submission">
          <h4>我的提交</h4>
          <div class="submission-images">
            <img v-for="(img, i) in mySubmissionMap[section.id].images" :key="i" :src="img" class="preview" />
          </div>
          <div v-if="mySubmissionMap[section.id].report" class="report">
            <div class="score">分数：{{ mySubmissionMap[section.id].report.score }}</div>
            <div v-if="getQuestions(mySubmissionMap[section.id].report)" class="questions-detail">
              <div v-for="q in getQuestions(mySubmissionMap[section.id].report)" :key="q.index" class="question-item">
                <span class="q-index">第{{ q.index }}题</span>
                <span class="q-score" :class="{ correct: q.correct }">{{ q.score }}/{{ q.max_score }}</span>
                <span class="q-status">{{ q.correct ? '✓' : '✗' }}</span>
                <div v-if="q.comment" class="q-comment">{{ q.comment }}</div>
              </div>
            </div>
            <div v-if="getIssues(mySubmissionMap[section.id].report)" class="issues-list">
              <h5>问题汇总</h5>
              <ul>
                <li v-for="(issue, i) in getIssues(mySubmissionMap[section.id].report)" :key="i">{{ issue }}</li>
              </ul>
            </div>
          </div>
          <div v-else class="pending">等待批改中...</div>
        </div>
      </div>

      <div v-if="sections.length === 0" class="empty">暂无作业</div>
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
const sections = ref([])
const assignmentMap = ref({})
const mySubmissionMap = ref({})
const showSubmitModal = ref(false)
const currentSectionId = ref(null)

const previewImages = ref([])
const uploadedUrls = ref([])
const uploading = ref(false)

onMounted(() => {
  loadData()
})

async function loadData() {
  loading.value = true
  try {
    const [sectionsRes, assignmentsRes] = await Promise.all([
      api.get('/sections', { params: { course_id: courseId } }),
      api.get(`/homework/course/${courseId}`)
    ])
    sections.value = sectionsRes.data.data || []
    const assignments = assignmentsRes.data.data || []
    const map = {}
    for (const a of assignments) {
      map[a.section_id] = a
    }
    assignmentMap.value = map
    await loadMySubmissions()
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function loadMySubmissions() {
  try {
    const res = await api.get('/homework/my-submissions', {
      params: { course_id: courseId }
    })
    const list = res.data.data || []
    const map = {}
    for (const s of list) {
      if (!map[s.assignment_id] || new Date(s.submitted_at) > new Date(map[s.assignment_id].submitted_at)) {
        map[s.assignment_id] = s
      }
    }
    const subMap = {}
    for (const [aid, sub] of Object.entries(map)) {
      const assignment = Object.values(assignmentMap.value).find(a => a.id === Number(aid) || a.id === aid)
      if (assignment) {
        subMap[assignment.section_id] = sub
      }
    }
    mySubmissionMap.value = subMap
  } catch (e) {
    console.error(e)
  }
}

function openSubmitModal(sectionId) {
  currentSectionId.value = sectionId
  showSubmitModal.value = true
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
  const assignment = assignmentMap.value[currentSectionId.value]
  if (!assignment) return
  try {
    await api.post('/homework/submissions', {
      assignment_id: assignment.id,
      images: uploadedUrls.value,
    })
    alert('提交成功')
    closeSubmitModal()
    loadMySubmissions()
  } catch (e) {
    alert('提交失败：' + (e.response?.data?.detail || e.message))
  }
}

function closeSubmitModal() {
  showSubmitModal.value = false
  currentSectionId.value = null
  previewImages.value = []
  uploadedUrls.value = []
}

function isOverdue(assignment) {
  if (!assignment?.deadline) return false
  return new Date(assignment.deadline) < new Date()
}

function statusText(status) {
  return { draft: '草稿', published: '已发布', closed: '已关闭' }[status] || status
}

function getMediaUrl(url) {
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

function isPdf(file) {
  return typeof file === 'string' && file.toLowerCase().endsWith('.pdf')
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString('zh-CN')
}

function previewImage(url) {
  window.open(url, '_blank')
}

function getQuestions(report) {
  if (!report?.detail) return null
  try {
    const detail = typeof report.detail === 'string' ? JSON.parse(report.detail) : report.detail
    return detail.questions || null
  } catch {
    return null
  }
}

function getIssues(report) {
  if (!report?.detail) return null
  try {
    const detail = typeof report.detail === 'string' ? JSON.parse(report.detail) : report.detail
    return detail.issues || null
  } catch {
    return null
  }
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

.section-card {
  background: white;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  margin-bottom: 16px;
}

.section-header {
  border-bottom: 1px solid #f0f0f0;
  padding-bottom: 8px;
  margin-bottom: 12px;
}

.section-header h3 {
  margin: 0;
  font-size: 16px;
  color: #333;
}

.section-empty {
  text-align: center;
  padding: 12px 0;
  color: #999;
}

.assignment-detail {
  padding: 0;
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

.late-badge {
  background: #fff1f0;
  color: #ff4d4f;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  vertical-align: middle;
}

.overdue-hint {
  color: #ff4d4f;
  font-size: 12px;
}

.desc {
  color: #666;
  margin-bottom: 8px;
}

.question-files {
  margin: 16px 0;
  padding: 12px;
  background: #f9f9f9;
  border-radius: 4px;
}

.question-files h4 {
  margin-bottom: 8px;
  font-size: 14px;
}

.question-files-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.question-file {
  display: inline-block;
}

.question-image {
  max-width: 200px;
  max-height: 200px;
  border-radius: 4px;
  cursor: pointer;
}

.pdf-link {
  display: inline-block;
  padding: 8px 16px;
  background: #1890ff;
  color: white;
  border-radius: 4px;
  text-decoration: none;
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

.questions-detail {
  margin: 12px 0;
  padding: 12px;
  background: white;
  border-radius: 4px;
}

.question-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
}

.question-item:last-child {
  border-bottom: none;
}

.q-index {
  font-weight: 500;
  min-width: 50px;
}

.q-score {
  min-width: 60px;
  color: #ff4d4f;
}

.q-score.correct {
  color: #52c41a;
}

.q-status {
  font-size: 16px;
}

.q-comment {
  flex: 1;
  color: #666;
  font-size: 13px;
}

.issues-list {
  margin: 12px 0;
  padding: 12px;
  background: #fff7e6;
  border-radius: 4px;
}

.issues-list h5 {
  margin-bottom: 8px;
  color: #fa8c16;
}

.issues-list ul {
  margin: 0;
  padding-left: 20px;
}

.issues-list li {
  margin: 4px 0;
  color: #666;
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
