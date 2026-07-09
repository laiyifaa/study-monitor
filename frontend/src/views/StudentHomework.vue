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
              {{ isSubmissionLocked(section.id) ? '已批改，不可再提交' : (mySubmissionMap[section.id] ? '修改提交' : '提交作业') }}
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
                  <span v-if="hasQuestionStats(mySubmissionMap[section.id].report)" class="report-counts">
                    对{{ mySubmissionMap[section.id].report.correct_count ?? 0 }}题 / 错{{ mySubmissionMap[section.id].report.wrong_count ?? 0 }}题
                  </span>
                </div>
              </div>
              <div v-if="isReportExpanded(section.id)" class="report-body">
                <div class="feedback">总评：{{ mySubmissionMap[section.id].report.feedback || '暂无评语' }}</div>
                <div v-if="getQuestions(mySubmissionMap[section.id].report)" class="questions-detail">
                  <div v-for="q in getQuestions(mySubmissionMap[section.id].report)" :key="q.index" class="question-item">
                    <span class="q-index">第{{ q.index }}题</span>
                    <span class="q-status" :class="q.correct ? 'correct' : 'wrong'">{{ q.correct ? '正确' : '错误' }}</span>
                  </div>
                </div>
              </div>
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
  triggerBrowserDownload,
} from '../utils/homeworkFiles.js'

const route = useRoute()
const courseId = route.params.courseId
const { isDingTalk, previewFile } = useDingTalk()

const loading = ref(false)
const sections = ref([])
const assignmentMap = ref({})
const mySubmissionMap = ref({})
const expandedReports = ref({})
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

function isSubmissionLocked(sectionId) {
  return Boolean(mySubmissionMap.value[sectionId]?.report)
}

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

  if (isPdf(file)) {
    if (isDingTalk) {
      previewFile(getAbsoluteMediaUrl(file), downloadName)
      return
    }
    window.open(mediaUrl, '_blank')
    return
  }

  if (isDocumentFile(file)) {
    if (isDingTalk) {
      previewFile(getAbsoluteMediaUrl(file), downloadName)
      return
    }
    triggerBrowserDownload(mediaUrl, downloadName)
    return
  }

  window.open(mediaUrl, '_blank')
}

async function requestAnswerFileAccessUrl(sectionId, fileIndex) {
  const res = await api.post('/homework/answer-files/access', {
    section_id: sectionId,
    file_index: fileIndex,
  })
  return toAbsoluteUrl(res.data.data?.url || '')
}

async function openStudentAnswerFile(sectionId, file) {
  try {
    const accessUrl = await requestAnswerFileAccessUrl(sectionId, file.index)
    if (!accessUrl) return
    const sectionTitle = getSectionTitle(sectionId)
    const total = getAnswerFiles(sectionId).length
    const downloadName = getAttachmentDownloadName(sectionTitle, 'answer', file.index, total, file.name)

    if (isPdf(file.name)) {
      if (isDingTalk) {
        previewFile(accessUrl, downloadName)
        return
      }
      window.open(accessUrl, '_blank')
      return
    }

    if (isDocumentFile(file.name)) {
      if (isDingTalk) {
        previewFile(accessUrl, downloadName)
        return
      }
      triggerBrowserDownload(accessUrl, downloadName)
      return
    }

    window.open(accessUrl, '_blank')
  } catch (e) {
    alert('打开答案附件失败：' + (e.response?.data?.detail || e.message))
  }
}

function getQuestions(report) {
  if (Array.isArray(report?.questions) && report.questions.length > 0) {
    return report.questions.map(item => ({
      index: item.index,
      correct: item.correct === true,
    }))
  }

  if (!report?.detail) return null
  try {
    const detail = typeof report.detail === 'string' ? JSON.parse(report.detail) : report.detail
    if (Array.isArray(detail.questions) && detail.questions.length > 0) return detail.questions
    if (Array.isArray(detail.details) && detail.details.length > 0) {
      return detail.details.map(d => ({
        index: d.qid,
        correct: d.ok,
      }))
    }
    if (Array.isArray(detail.result?.details) && detail.result.details.length > 0) {
      return detail.result.details.map(d => ({
        index: d.question_id ?? d.qid,
        correct: typeof d.is_correct === 'boolean' ? d.is_correct : d.ok,
      }))
    }
    return null
  } catch {
    return null
  }
}

function hasQuestionStats(report) {
  return typeof report?.correct_count === 'number' || typeof report?.wrong_count === 'number'
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

.questions-detail {
  margin: 12px 0 0;
  border-top: 1px solid #dfe9e5;
}

.question-item {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid #edf2f0;
}

.question-item:last-child {
  border-bottom: none;
}

.q-index {
  font-weight: 700;
  color: #40515f;
}

.q-status {
  font-size: 12px;
  font-weight: 700;
  padding: 4px 10px;
  border-radius: 999px;
}

.q-status.correct {
  background: #e8f7ef;
  color: #15803d;
}

.q-status.wrong {
  background: #fee8e7;
  color: #b42318;
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

.report-counts {
  color: #607080;
  font-size: 13px;
  font-weight: 600;
}

.report-body {
  padding-top: 12px;
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

.uploading {
  color: #2563eb;
  font-weight: 700;
  margin-bottom: 16px;
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

  .question-item {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
