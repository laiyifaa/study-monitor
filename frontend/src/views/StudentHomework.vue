<template>
  <div class="student-homework-page">
    <div class="page-heading">
      <h2 class="page-title">课程作业</h2>
      <p>查看题目、提交作业图片和批改反馈</p>
    </div>

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
          <div v-if="hasAttachmentGroup(section.id)" class="attachment-grid">
            <div v-if="hasQuestionFiles(section.id)" class="attachment-group">
              <h4>题目附件</h4>
              <div class="question-files-list">
                <div v-for="(file, i) in getQuestionFiles(section.id)" :key="`q-${i}`" class="question-file">
                  <img v-if="isImageFile(file)" :src="getMediaUrl(file)" :title="getAttachmentDisplayName(section.title, 'homework', i, getQuestionFiles(section.id).length)" class="question-image" @click="previewImage(getMediaUrl(file))" />
                  <button v-else type="button" class="file-link" :title="getAttachmentDisplayName(section.title, 'homework', i, getQuestionFiles(section.id).length)" @click="openQuestionFile(section.id, file, i)">{{ getAttachmentDisplayName(section.title, 'homework', i, getQuestionFiles(section.id).length) }}</button>
                </div>
              </div>
            </div>
            <div v-if="hasAnswerFiles(section.id)" class="attachment-group">
              <h4>答案附件</h4>
              <div class="question-files-list">
                <div v-for="file in getAnswerFiles(section.id)" :key="`a-${section.id}-${file.index}`" class="question-file">
                  <button type="button" class="file-link" :title="getAttachmentDisplayName(section.title, 'answer', file.index, getAnswerFiles(section.id).length)" @click="openStudentAnswerFile(section.id, file)">{{ getAttachmentDisplayName(section.title, 'answer', file.index, getAnswerFiles(section.id).length) }}</button>
                </div>
              </div>
            </div>
          </div>
          <div class="meta">
            <span v-if="assignmentMap[section.id].deadline">截止：{{ formatDate(assignmentMap[section.id].deadline) }}</span>
            <span v-if="isOverdue(assignmentMap[section.id])" class="overdue-hint">（已截止）</span>
            <span v-if="mySubmissionMap[section.id]" class="submitted-hint">已提交</span>
            <span v-if="mySubmissionMap[section.id]?.is_late" class="submitted-hint late">迟交</span>
          </div>

          <div v-if="assignmentMap[section.id].status === 'published'" class="submit-section">
            <button class="btn-primary" :disabled="isSubmissionLocked(section.id)" @click="openSubmitModal(section.id)">
              {{ submitButtonText(section.id) }}
            </button>
          </div>
          </div>

          <div v-if="mySubmissionMap[section.id]" class="my-submission">
            <div class="submission-head">
              <h4>我的提交</h4>
              <button
                v-if="mySubmissionMap[section.id].report"
                type="button"
                class="btn-sm report-toggle"
                :aria-expanded="isReportExpanded(section.id)"
                @click="toggleReport(section.id)"
              >
                {{ isReportExpanded(section.id) ? '收起批改' : '查看批改' }}
              </button>
            </div>
            <div class="submission-images">
              <img
                v-for="(img, i) in mySubmissionMap[section.id].images"
                :key="i"
                :src="getMediaUrl(img)"
                class="preview"
                @click="previewImage(getMediaUrl(img))"
              />
            </div>
            <div v-if="mySubmissionMap[section.id].report" class="report-accordion">
              <div class="report-summary-row">
                <div class="report-summary-text">
                  <span class="report-pill">已批改</span>
                  <span v-if="mySubmissionMap[section.id].report.score != null" class="report-score">
                    {{ mySubmissionMap[section.id].report.score }}/{{ mySubmissionMap[section.id].report.full_score }}
                  </span>
                  <span v-if="mySubmissionMap[section.id].report.accuracy != null" class="report-accuracy">
                    正确率 {{ (mySubmissionMap[section.id].report.accuracy * 100).toFixed(0) }}%
                  </span>
                  <span v-if="mySubmissionMap[section.id].report.correct_count != null || mySubmissionMap[section.id].report.wrong_count != null" class="report-counts">
                    <span v-if="mySubmissionMap[section.id].report.correct_count != null" class="count-correct">✓{{ mySubmissionMap[section.id].report.correct_count }}</span>
                    <span v-if="mySubmissionMap[section.id].report.wrong_count != null" class="count-wrong">✗{{ mySubmissionMap[section.id].report.wrong_count }}</span>
                  </span>
                </div>
              </div>
              <div class="report-note">
                各位同学，平台AI给出的作业得分只是系统识别结果，不作为最终评价。大家不用纠结，核心任务是：对照平台答案详解，把空白题目补做完，在《学习手册》上红笔手写订正。
              </div>
              <div v-if="isReportExpanded(section.id)" class="report-body">
                <div class="feedback">总评：{{ mySubmissionMap[section.id].report.feedback || '暂无评语' }}</div>
              </div>
            </div>
            <div v-else-if="mySubmissionMap[section.id].status === 'returned'" class="returned-notice">
              <div class="returned-header">已被打回</div>
              <div v-if="mySubmissionMap[section.id].return_reason" class="returned-reason">
                原因：{{ mySubmissionMap[section.id].return_reason }}
              </div>
              <div class="returned-hint">请修改后重新提交</div>
            </div>
            <div v-else-if="mySubmissionMap[section.id].task?.status === 'failed'" class="failed-notice">
              <div class="failed-header">批改失败</div>
              <div v-if="mySubmissionMap[section.id].task?.error_message" class="failed-reason">
                原因：{{ mySubmissionMap[section.id].task.error_message }}
              </div>
              <div class="failed-hint">可先查看答案附件</div>
            </div>
            <div v-else class="pending">等待批改中...</div>
          </div>
          <div v-else class="pending">暂未提交作业</div>
        </div>
      <div v-if="sections.length === 0" class="empty">暂无作业</div>
    </template>

    <div v-if="showSubmitModal" class="modal-overlay" @click.self="closeSubmitModal">
      <div class="modal">
        <h3>提交作业</h3>
        <div v-if="isResubmitReturned" class="returned-warning">
          <strong>作业已被打回，请根据反馈修改后重新提交</strong>
          <span v-if="returnedReasonText">打回原因：{{ returnedReasonText }}</span>
        </div>
        <div class="form-group">
          <div
            class="drop-zone"
            :class="{ 'drop-zone--dragging': isDragging }"
            @dragenter.prevent="isDragging = true"
            @dragover.prevent="isDragging = true"
            @dragleave.prevent="isDragging = false"
            @drop.prevent="handleDrop"
            @click="selectFiles"
          >
            <span class="drop-zone-text">点击或拖拽图片到此处上传</span>
            <span class="drop-zone-hint">支持 JPG/PNG/GIF/WebP，可多选</span>
          </div>
          <input
            ref="fileInputRef"
            type="file"
            multiple
            accept="image/*"
            style="display:none"
            @change="handleFileSelect"
          />
        </div>
        <div v-if="fileItems.length > 0" class="file-list">
          <div class="file-list-header">
            <span>共 {{ fileItems.length }} 张，已上传 {{ doneCount }} 张</span>
          </div>
          <div v-for="item in fileItems" :key="item.id" class="file-item">
            <img :src="item.preview" class="file-thumb" />
            <div class="file-info">
              <span class="file-name">{{ item.file.name }}</span>
              <span class="file-size">{{ formatSize(item.file.size) }}</span>
            </div>
            <span v-if="item.status === 'pending'" class="file-status pending">待上传</span>
            <span v-else-if="item.status === 'uploading'" class="file-status uploading">上传中…</span>
            <span v-else-if="item.status === 'done'" class="file-status done">已上传</span>
            <span v-else-if="item.status === 'failed'" class="file-status failed">
              失败
              <button class="retry-btn" @click.stop="retryFile(item.id)">重试</button>
            </span>
            <button class="remove-btn" @click="removeFile(item.id)">×</button>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn-secondary" @click="closeSubmitModal">取消</button>
          <button
            class="btn-primary"
            :disabled="doneCount === 0 || isAnyUploading"
            @click="submitHomework"
          >
            <template v-if="isAnyUploading">上传中 {{ doneCount }}/{{ fileItems.length }}…</template>
            <template v-else-if="hasAnyFailed">提交（跳过失败图片）</template>
            <template v-else>提交</template>
          </button>
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
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useDingTalk } from '../composables/useDingTalk.js'
import api from '../utils/api.js'
import {
  getAttachmentDisplayName,
  getAttachmentDownloadName,
  getAbsoluteMediaUrl,
  getMediaUrl,
  isDocumentFile,
  isImageFile,
  isPdf,
  toAbsoluteUrl,
  openFileDownload,
} from '../utils/homeworkFiles.js'

const route = useRoute()
const courseId = route.params.courseId
const { isDingTalk } = useDingTalk()

const loading = ref(false)
const sections = ref([])
const assignmentMap = ref({})
const mySubmissionMap = ref({})
const expandedReports = ref({})
const showSubmitModal = ref(false)
const currentSectionId = ref(null)

const fileInputRef = ref(null)
const fileItems = ref([])
const isDragging = ref(false)

function selectFiles() {
  fileInputRef.value?.click()
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + 'B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'KB'
  return (bytes / (1024 * 1024)).toFixed(1) + 'MB'
}

let fileIdCounter = 0
function nextFileId() {
  return ++fileIdCounter
}

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
    const currentCourseId = String(courseId)
    const map = {}
    for (const s of list) {
      const assignment = s.assignment
      if (!assignment?.id || String(assignment.course_id) !== currentCourseId) {
        continue
      }
      const assignmentId = String(assignment.id)
      if (!map[assignmentId] || new Date(s.submitted_at) > new Date(map[assignmentId].submitted_at)) {
        map[assignmentId] = s
      }
    }
    const subMap = {}
    for (const sub of Object.values(map)) {
      const sectionId = sub.assignment?.section_id
      if (sectionId) {
        subMap[sectionId] = sub
      }
    }
    mySubmissionMap.value = subMap
  } catch (e) {
    console.error(e)
  }
}

function openSubmitModal(sectionId) {
  if (isSubmissionLocked(sectionId)) return
  currentSectionId.value = sectionId
  showSubmitModal.value = true
}

async function handleFileSelect(e) {
  const files = Array.from(e.target.files)
  if (files.length === 0) return
  addFiles(files)
  e.target.value = ''
}

function handleDrop(e) {
  isDragging.value = false
  const rawFiles = Array.from(e.dataTransfer.files)
  const imageFiles = rawFiles.filter(f => f.type.startsWith('image/'))
  if (imageFiles.length === 0) return
  addFiles(imageFiles)
}

function addFiles(files) {
  const newItems = files.map(file => ({
    id: nextFileId(),
    file,
    url: '',
    preview: URL.createObjectURL(file),
    status: 'pending',
    error: '',
  }))
  fileItems.value = [...fileItems.value, ...newItems]
  uploadAllPending()
}

async function uploadAllPending() {
  const pending = fileItems.value.filter(f => f.status === 'pending' || f.status === 'failed')
  if (pending.length === 0) return

  pending.forEach(f => (f.status = 'uploading'))

  const results = await Promise.allSettled(
    pending.map(item => {
      const fd = new FormData()
      fd.append('file', item.file)
      return api.post('/homework/upload', fd, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
    })
  )

  results.forEach((result, i) => {
    const item = pending[i]
    if (result.status === 'fulfilled') {
      item.url = result.value.data.data.url
      item.status = 'done'
    } else {
      item.status = 'failed'
      const err = result.reason
      item.error = err?.response?.data?.detail || err?.message || '上传失败'
    }
  })
}

function retryFile(id) {
  const item = fileItems.value.find(f => f.id === id)
  if (!item) return
  item.status = 'pending'
  item.error = ''
  uploadAllPending()
}

function removeFile(id) {
  const item = fileItems.value.find(f => f.id === id)
  if (item) URL.revokeObjectURL(item.preview)
  fileItems.value = fileItems.value.filter(f => f.id !== id)
}

const doneCount = computed(() => fileItems.value.filter(f => f.status === 'done').length)
const hasAnyFailed = computed(() => fileItems.value.some(f => f.status === 'failed'))
const isAnyUploading = computed(() => fileItems.value.some(f => f.status === 'uploading'))

async function submitHomework() {
  const urls = fileItems.value.filter(f => f.status === 'done').map(f => f.url)
  if (urls.length === 0) return
  const assignment = assignmentMap.value[currentSectionId.value]
  if (!assignment) return
  try {
    await api.post('/homework/submissions', {
      assignment_id: assignment.id,
      images: urls,
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
  fileItems.value.forEach(f => URL.revokeObjectURL(f.preview))
  fileItems.value = []
  isDragging.value = false
}

function isOverdue(assignment) {
  if (!assignment?.deadline) return false
  return new Date(assignment.deadline) < new Date()
}

function isSubmissionLocked(sectionId) {
  const sub = mySubmissionMap.value[sectionId]
  if (!sub) return false
  if (sub.status === 'returned') return false
  return Boolean(sub.report)
}

function submitButtonText(sectionId) {
  const sub = mySubmissionMap.value[sectionId]
  if (!sub) return '提交作业'
  if (sub.status === 'returned') return '修改后重新提交'
  if (sub.report) return '已批改，不可再提交'
  return '修改提交'
}

const isResubmitReturned = computed(() => {
  if (!currentSectionId.value) return false
  return mySubmissionMap.value[currentSectionId.value]?.status === 'returned'
})

const returnedReasonText = computed(() => {
  if (!currentSectionId.value) return ''
  return mySubmissionMap.value[currentSectionId.value]?.return_reason || ''
})

function isReportExpanded(sectionId) {
  return Boolean(expandedReports.value[sectionId])
}

function toggleReport(sectionId) {
  expandedReports.value = {
    ...expandedReports.value,
    [sectionId]: !expandedReports.value[sectionId],
  }
}

function getQuestionFiles(sectionId) {
  return assignmentMap.value[sectionId]?.question_files || []
}

function getAnswerFiles(sectionId) {
  const submission = mySubmissionMap.value[sectionId]
  if (!submission?.can_view_answer_files) return []
  return submission.answer_files || []
}

function hasQuestionFiles(sectionId) {
  return getQuestionFiles(sectionId).length > 0
}

function hasAnswerFiles(sectionId) {
  return getAnswerFiles(sectionId).length > 0
}

function hasAttachmentGroup(sectionId) {
  return hasQuestionFiles(sectionId) || hasAnswerFiles(sectionId)
}

function statusText(status) {
  return { draft: '草稿', published: '已发布', closed: '已关闭' }[status] || status
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString('zh-CN')
}

function previewImage(url) {
  if (isDingTalk) {
    window.open(getAbsoluteMediaUrl(url), '_blank')
    return
  }
  window.open(url, '_blank')
}

function getSectionTitle(sectionId) {
  return sections.value.find(section => String(section.id) === String(sectionId))?.title || ''
}

function openQuestionFile(sectionId, file, index = 0) {
  const mediaUrl = getMediaUrl(file)
  if (!mediaUrl) return
  const sectionTitle = getSectionTitle(sectionId)
  const total = getQuestionFiles(sectionId).length
  const downloadName = getAttachmentDownloadName(sectionTitle, 'homework', index, total, file)

  if (isDingTalk) {
    if (isPdf(file)) {
      window.open(getAbsoluteMediaUrl(file), '_blank')
    } else {
      openFileDownload(getAbsoluteMediaUrl(file), downloadName)
    }
    return
  }

  if (isPdf(file)) {
    window.open(mediaUrl, '_blank')
    return
  }

  openFileDownload(mediaUrl, downloadName)
}

function openStudentAnswerFile(sectionId, file) {
  const sectionTitle = getSectionTitle(sectionId)
  const total = getAnswerFiles(sectionId).length
  const downloadName = getAttachmentDownloadName(sectionTitle, 'answer', file.index, total, file.name)
  const accessUrl = file.url ? toAbsoluteUrl(file.url) : ''
  if (!accessUrl) return

  if (isDingTalk) {
    if (isPdf(file.name)) {
      window.open(accessUrl, '_blank')
    } else if (isImageFile(file.name)) {
      window.open(accessUrl, '_blank')
    } else {
      openFileDownload(accessUrl, downloadName)
    }
    return
  }

  if (isPdf(file.name) || isImageFile(file.name)) {
    window.open(accessUrl, '_blank')
    return
  }
  openFileDownload(accessUrl, downloadName)
}

</script>

<style scoped>
.student-homework-page {
  min-height: 100vh;
  max-width: 860px;
  margin: 0 auto;
  padding: 22px 18px 78px;
  color: #263238;
  background: linear-gradient(180deg, #f4f8f6 0%, #eef4f7 100%);
}

.page-heading {
  margin-bottom: 18px;
}

.page-title {
  margin: 0;
  color: #17324d;
  font-size: 26px;
}

.page-heading p {
  margin: 6px 0 0;
  color: #687681;
  font-size: 14px;
}

.btn-primary,
.btn-secondary {
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 700;
}

.btn-primary {
  background: #2563eb;
  color: white;
  padding: 10px 18px;
  box-shadow: 0 8px 18px rgba(37, 99, 235, 0.18);
}

.btn-primary:disabled {
  background: #b9c3cf;
  box-shadow: none;
  cursor: not-allowed;
}

.btn-secondary {
  background: #eef2f7;
  color: #375266;
  padding: 9px 16px;
}

.section-card {
  position: relative;
  overflow: hidden;
  background: #fffefa;
  border: 1px solid #dfe9e5;
  border-radius: 8px;
  padding: 18px 20px 18px 28px;
  box-shadow: 0 10px 28px rgba(42, 62, 79, 0.08);
  margin-bottom: 16px;
}

.section-card::before {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 8px;
  background: linear-gradient(180deg, #2563eb, #16a085);
}

.section-header {
  border-bottom: 1px dashed #d6e1dc;
  padding-bottom: 10px;
  margin-bottom: 14px;
}

.section-header h3 {
  margin: 0;
  font-size: 17px;
  color: #17324d;
}

.section-empty {
  text-align: center;
  padding: 18px 0;
  color: #7b8790;
}

.assignment-detail {
  padding: 0;
}

.assignment-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
}

.assignment-header h4 {
  margin: 0;
  color: #22313f;
  font-size: 18px;
}

.status-badge,
.submitted-hint {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.status-badge.draft { background: #eef2f7; color: #607080; }
.status-badge.published { background: #e8f2ff; color: #2563eb; }
.status-badge.closed { background: #fff4df; color: #a16207; }

.desc {
  color: #566573;
  line-height: 1.65;
  margin: 0 0 12px;
}

.question-files {
  margin: 16px 0;
  padding: 12px;
  background: #f7fbf9;
  border: 1px solid #dfe9e5;
  border-radius: 8px;
}

.question-files h4 {
  margin: 0 0 10px;
  color: #40515f;
  font-size: 14px;
}

.question-files-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.question-file {
  display: inline-flex;
}

.question-image {
  width: 120px;
  height: 120px;
  object-fit: cover;
  border: 1px solid #d6e1dc;
  border-radius: 6px;
  cursor: pointer;
}

.pdf-link,
.file-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 120px;
  height: 64px;
  background: #eef5ff;
  color: #2563eb;
  border: 1px solid #c7dcff;
  border-radius: 6px;
  text-decoration: none;
  font-weight: 700;
  font-size: 12px;
  cursor: pointer;
  padding: 6px 8px;
  appearance: none;
  box-sizing: border-box;
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
  line-height: 1.25;
  text-align: center;
  overflow: hidden;
}

.meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 13px;
  color: #687681;
  margin-bottom: 16px;
}

.overdue-hint {
  color: #b42318;
  background: #fff1ee;
  border-radius: 999px;
  padding: 3px 9px;
  font-weight: 700;
}

.submitted-hint {
  background: #e7f6ef;
  color: #166154;
}

.submitted-hint.late {
  background: #fee8e7;
  color: #b42318;
}

.submit-section {
  display: flex;
  gap: 8px;
  margin-top: 16px;
}

.my-submission {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px dashed #d6e1dc;
}

.submission-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.submission-head h4 {
  margin: 0;
  color: #17324d;
}

.report-toggle {
  flex: 0 0 auto;
}

.attachment-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 14px;
  margin: 16px 0;
}

.attachment-group {
  padding-top: 12px;
  border-top: 1px solid #dfe9e5;
}

.attachment-group h4 {
  margin: 0 0 10px;
  color: #40515f;
  font-size: 14px;
}

.submission-images,
.preview-images {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 14px;
}

.preview {
  width: 96px;
  height: 96px;
  object-fit: cover;
  border: 1px solid #d6e1dc;
  border-radius: 6px;
  cursor: pointer;
}

.report-accordion {
  margin-top: 6px;
}

.report-summary-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.report-summary-text {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  color: #17324d;
  font-weight: 700;
}

.report-pill {
  display: inline-flex;
  align-items: center;
  padding: 3px 9px;
  border-radius: 999px;
  background: #e8f7ef;
  color: #15803d;
  font-size: 12px;
  font-weight: 700;
}

.report-score {
  margin-left: 8px;
  font-size: 13px;
  font-weight: 700;
  color: #1e40af;
}

.report-accuracy {
  margin-left: 8px;
  font-size: 12px;
  color: #6b7280;
}

.report-counts {
  margin-left: 8px;
  font-size: 12px;
  display: inline-flex;
  gap: 6px;
}

.count-correct {
  color: #15803d;
}

.count-wrong {
  color: #dc2626;
}

.report-body {
  padding-top: 12px;
}

.report-note {
  margin: 10px 0 0;
  padding: 12px 14px;
  border: 1px solid #cfe1f3;
  border-radius: 8px;
  background: #f6fbff;
  color: #38526b;
  font-size: 13px;
  line-height: 1.7;
}

.feedback {
  margin-top: 0;
  color: #40515f;
  line-height: 1.6;
}

.pending {
  color: #a16207;
  font-weight: 700;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(20, 32, 43, 0.48);
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 20px;
  z-index: 1000;
}

.modal {
  background: #fffefa;
  border-radius: 8px;
  padding: 24px;
  width: min(500px, 100%);
  max-height: 84vh;
  overflow-y: auto;
  box-shadow: 0 18px 44px rgba(15, 23, 42, 0.22);
}

.modal h3 {
  margin: 0 0 18px;
  color: #17324d;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-weight: 700;
  color: #2f3c48;
}

.form-group input[type="file"] {
  width: 100%;
  padding: 10px;
  border: 1px dashed #cfdce3;
  border-radius: 6px;
  background: #ffffff;
}

.drop-zone {
  border: 2px dashed #c4d4e0;
  border-radius: 8px;
  padding: 32px 16px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
  background: #fafcfd;
}

.drop-zone:hover {
  border-color: #2563eb;
  background: #f0f7ff;
}

.drop-zone--dragging {
  border-color: #2563eb;
  background: #e8f2ff;
}

.drop-zone-text {
  display: block;
  font-weight: 700;
  color: #374b5c;
  margin-bottom: 4px;
}

.drop-zone-hint {
  font-size: 12px;
  color: #8a9aa8;
}

.file-list {
  margin-top: 12px;
  border: 1px solid #e4edf0;
  border-radius: 8px;
  overflow: hidden;
}

.file-list-header {
  padding: 8px 12px;
  background: #f5f9fb;
  font-size: 13px;
  font-weight: 600;
  color: #4a6274;
  border-bottom: 1px solid #e4edf0;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-bottom: 1px solid #eff3f5;
  transition: background 0.15s;
}

.file-item:last-child {
  border-bottom: none;
}

.file-thumb {
  width: 44px;
  height: 44px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid #dce6eb;
  flex-shrink: 0;
}

.file-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.file-name {
  font-size: 13px;
  color: #263238;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-size {
  font-size: 11px;
  color: #8899a6;
}

.file-status {
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
}

.file-status.pending { color: #8899a6; }

.file-status.uploading { color: #2563eb; }

.file-status.done { color: #15803d; }

.file-status.failed { color: #b42318; }

.retry-btn {
  margin-left: 4px;
  border: none;
  background: transparent;
  color: #2563eb;
  font-weight: 700;
  font-size: 12px;
  cursor: pointer;
  text-decoration: underline;
  padding: 0;
}

.retry-btn:hover {
  color: #1d4ed8;
}

.remove-btn {
  border: none;
  background: transparent;
  color: #9aabb8;
  font-size: 18px;
  cursor: pointer;
  padding: 0 2px;
  line-height: 1;
  flex-shrink: 0;
  transition: color 0.15s;
}

.remove-btn:hover {
  color: #b42318;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}

.loading,
.empty {
  text-align: center;
  padding: 40px;
  color: #7b8790;
}

.bottom-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  background: #ffffff;
  display: flex;
  border-top: 1px solid #dfe9e5;
  box-shadow: 0 -8px 24px rgba(42, 62, 79, 0.08);
}

.nav-item {
  flex: 1;
  text-align: center;
  padding: 13px;
  color: #607080;
  text-decoration: none;
  font-weight: 700;
}

.nav-item.router-link-exact-active {
  color: #2563eb;
}

@media (max-width: 640px) {
  .student-homework-page {
    padding: 18px 12px 78px;
  }

  .assignment-header {
    flex-direction: column;
  }

  .submission-head,
  .report-summary-row {
    flex-direction: column;
    align-items: flex-start;
  }

  .attachment-grid {
    grid-template-columns: 1fr;
  }

}

.returned-notice {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fff7e6;
  border: 1px solid #ffd591;
  border-radius: 8px;
}
.returned-header {
  font-weight: 700;
  color: #d46b08;
  font-size: 15px;
  margin-bottom: 4px;
}
.returned-reason {
  color: #d46b08;
  font-size: 13px;
  margin-bottom: 4px;
}
.returned-hint {
  color: #999;
  font-size: 12px;
}
.failed-notice {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fff4f4;
  border: 1px solid #f3c7c7;
  border-radius: 8px;
}
.failed-header {
  font-weight: 700;
  color: #c41d1d;
  font-size: 15px;
  margin-bottom: 4px;
}
.failed-reason,
.failed-hint {
  color: #c41d1d;
  font-size: 13px;
  margin-bottom: 4px;
  word-break: break-word;
}
.returned-warning {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fff7e6;
  border: 1px solid #ffd591;
  border-radius: 8px;
  font-size: 13px;
  color: #d46b08;
}
.returned-warning strong {
  display: block;
  margin-bottom: 4px;
}
</style>
