<template>
  <div class="homework-manage-page">
    <div class="page-header">
      <h2>作业管理</h2>
      <router-link :to="`/teacher`" class="btn-secondary">← 返回统计看板</router-link>
    </div>

    <div v-if="loading" class="loading">加载中...</div>

    <template v-else>
      <div v-if="!assignment" class="empty">
        <p>该课程暂无作业</p>
        <button class="btn-primary" @click="showCreateModal = true">创建作业</button>
      </div>

      <div v-else class="assignment-detail">
        <div class="assignment-header">
          <h3>{{ assignment.title }}</h3>
          <div class="status-group">
            <span class="status-badge" :class="assignment.status">{{ statusText(assignment.status) }}</span>
            <span class="status-badge" :class="assignment.grading_status">{{ gradingStatusText(assignment.grading_status) }}</span>
          </div>
        </div>
        <p class="desc">{{ assignment.description || '暂无描述' }}</p>
        <div class="meta">
          <span v-if="assignment.deadline">截止：{{ formatDate(assignment.deadline) }}</span>
        </div>
        <div class="assignment-actions">
          <button class="btn-sm" @click="showEditModal = true">编辑</button>
          <button v-if="assignment.status === 'draft'" class="btn-sm primary" @click="publishAssignment">发布</button>
          <button class="btn-sm" @click="loadSubmissions">查看提交 ({{ submissions.length }})</button>
        </div>
      </div>
    </template>

    <div v-if="showCreateModal || showEditModal" class="modal-overlay" @click.self="closeModal">
      <div class="modal modal-lg">
        <h3>{{ showEditModal ? '编辑作业' : '创建作业' }}</h3>
        <div class="form-group">
          <label>作业标题</label>
          <input v-model="form.title" type="text" placeholder="请输入作业标题" />
        </div>
        <div class="form-group">
          <label>题目描述</label>
          <textarea v-model="form.description" placeholder="请输入题目描述"></textarea>
        </div>
        <div class="form-group">
          <label>题目文件（图片/PDF）</label>
          <input type="file" multiple accept="image/*,.pdf" @change="handleQuestionFileSelect" />
          <div v-if="form.question_files.length > 0" class="question-files-preview">
            <div v-for="(file, i) in form.question_files" :key="i" class="question-file-item">
              <span v-if="file.endsWith('.pdf')" class="file-icon">📄</span>
              <img v-else :src="file" class="question-thumb" />
              <button class="remove-btn" @click="removeQuestionFile(i)">×</button>
            </div>
          </div>
        </div>
        <div class="form-group">
          <label>评分标准（传给智能体）</label>
          <textarea v-model="form.grading_prompt" placeholder="请输入评分标准/批改提示词"></textarea>
        </div>
        <div class="form-group">
          <label>批改模式</label>
          <select v-model="form.grading_mode">
            <option value="auto">自动批改（智能体）</option>
            <option value="manual">人工批改</option>
            <option value="hybrid">混合模式（智能体+人工复核）</option>
          </select>
        </div>
        <div class="form-group">
          <label>截止时间</label>
          <input v-model="form.deadline" type="datetime-local" />
        </div>
        <div class="modal-actions">
          <button class="btn-secondary" @click="closeModal">取消</button>
          <button class="btn-primary" @click="saveAssignment">{{ showEditModal ? '保存' : '创建' }}</button>
        </div>
      </div>
    </div>

    <div v-if="showSubmissionsModal" class="modal-overlay" @click.self="showSubmissionsModal = false">
      <div class="modal modal-lg">
        <h3>提交列表</h3>
        <div v-if="submissions.length === 0" class="empty">暂无提交</div>
        <div v-else class="submissions-list">
          <div v-for="s in submissions" :key="s.id" class="submission-item">
            <div class="submission-header">
              <span class="student-name">{{ s.user?.name }}</span>
              <span class="status-badge" :class="s.status">{{ s.status === 'graded' ? '已批改' : '待批改' }}</span>
              <span v-if="s.task" class="task-badge" :class="s.task.status">{{ taskStatusText(s.task.status) }}</span>
            </div>
            <div class="submission-images">
              <img v-for="(img, i) in s.images" :key="i" :src="img" class="thumb" @click="previewImage(img)" />
            </div>
            <div v-if="s.report" class="report-preview">
              <div class="score">分数：{{ s.report.score }}</div>
              <div v-if="getConfidence(s.report)" class="confidence">
                置信度：{{ (getConfidence(s.report) * 100).toFixed(0) }}%
                <span v-if="getConfidence(s.report) < 0.8" class="low-confidence">（较低）</span>
              </div>
              <div v-if="getQuestions(s.report)" class="questions-detail">
                <div v-for="q in getQuestions(s.report)" :key="q.index" class="question-item">
                  <span class="q-index">第{{ q.index }}题</span>
                  <span class="q-score" :class="{ correct: q.correct }">{{ q.score }}/{{ q.max_score }}</span>
                  <span class="q-status">{{ q.correct ? '✓' : '✗' }}</span>
                </div>
              </div>
              <div v-if="getIssues(s.report)" class="issues-list">
                <span class="issues-label">问题：</span>
                <span v-for="(issue, i) in getIssues(s.report)" :key="i">{{ issue }}{{ i < getIssues(s.report).length - 1 ? '；' : '' }}</span>
              </div>
              <div class="feedback">{{ s.report.feedback }}</div>
            </div>
            <div v-if="s.task && s.task.status === 'failed'" class="task-error">
              <span class="error-label">批改失败：</span>{{ s.task.error_message || '未知错误' }}
              <span v-if="s.task.retry_count > 0" class="retry-info">(已重试 {{ s.task.retry_count }} 次)</span>
            </div>
            <div v-if="s.task && s.task.status === 'sent'" class="task-info">
              已发送给智能体，等待回调...
            </div>
            <div class="submission-actions">
              <button v-if="s.status === 'pending'" class="btn-sm primary" @click="openGradeModal(s)">批改</button>
            </div>
            <div class="submission-time">{{ formatDate(s.submitted_at) }}</div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn-secondary" @click="showSubmissionsModal = false">关闭</button>
        </div>
      </div>
    </div>

    <div v-if="showGradeModal" class="modal-overlay" @click.self="showGradeModal = false">
      <div class="modal">
        <h3>手动批改 — {{ gradingSubmission?.user?.name }}</h3>
        <div class="form-group">
          <label>分数（0-100）</label>
          <input v-model.number="gradeForm.score" type="number" min="0" max="100" placeholder="请输入分数" />
        </div>
        <div class="form-group">
          <label>评语</label>
          <textarea v-model="gradeForm.feedback" placeholder="请输入评语"></textarea>
        </div>
        <div v-if="gradeSubmitting" class="loading">提交中...</div>
        <div class="modal-actions">
          <button class="btn-secondary" @click="showGradeModal = false">取消</button>
          <button class="btn-primary" :disabled="gradeSubmitting" @click="submitGrade">确认批改</button>
        </div>
      </div>
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
const submissions = ref([])
const showCreateModal = ref(false)
const showEditModal = ref(false)
const showSubmissionsModal = ref(false)
const showGradeModal = ref(false)
const gradingSubmission = ref(null)
const gradeForm = ref({ score: '', feedback: '' })
const gradeSubmitting = ref(false)

const form = ref({
  title: '',
  description: '',
  question_files: [],
  grading_prompt: '',
  grading_mode: 'auto',
  deadline: '',
})

onMounted(() => {
  loadAssignment()
})

async function loadAssignment() {
  loading.value = true
  try {
    const res = await api.get(`/homework/assignments/${courseId}`)
    assignment.value = res.data.data
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function loadSubmissions() {
  try {
    const res = await api.get(`/homework/assignments/${courseId}/submissions`)
    submissions.value = res.data.data || []
    showSubmissionsModal.value = true
  } catch (e) {
    alert('加载失败')
  }
}

async function saveAssignment() {
  if (!form.value.title) {
    alert('请输入作业标题')
    return
  }
  try {
    if (showEditModal.value) {
      await api.put(`/homework/assignments/${courseId}`, {
        title: form.value.title,
        description: form.value.description,
        question_files: form.value.question_files,
        grading_prompt: form.value.grading_prompt,
        grading_mode: form.value.grading_mode,
        deadline: form.value.deadline || null,
      })
    } else {
      await api.post(`/homework/assignments/${courseId}`, {
        title: form.value.title,
        description: form.value.description,
        question_files: form.value.question_files,
        grading_prompt: form.value.grading_prompt,
        grading_mode: form.value.grading_mode,
        deadline: form.value.deadline || null,
      })
    }
    closeModal()
    loadAssignment()
  } catch (e) {
    alert('保存失败：' + (e.response?.data?.detail || e.message))
  }
}

async function publishAssignment() {
  if (!confirm('确认发布此作业？')) return
  try {
    await api.put(`/homework/assignments/${courseId}`, { status: 'published' })
    loadAssignment()
  } catch (e) {
    alert('发布失败')
  }
}

function closeModal() {
  showCreateModal.value = false
  showEditModal.value = false
  form.value = { title: '', description: '', question_files: [], grading_prompt: '', grading_mode: 'auto', deadline: '' }
}

async function handleQuestionFileSelect(e) {
  const files = Array.from(e.target.files)
  for (const file of files) {
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await api.post('/homework/upload-question', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      form.value.question_files.push(res.data.data.url)
    } catch (err) {
      alert('上传失败：' + err.message)
    }
  }
}

function removeQuestionFile(index) {
  form.value.question_files.splice(index, 1)
}

function statusText(status) {
  return { draft: '草稿', published: '已发布', closed: '已关闭' }[status] || status
}

function gradingStatusText(status) {
  return { pending: '待批改', graded: '已批改' }[status] || status
}

function taskStatusText(status) {
  return { pending: '待发送', sent: '已发送', graded: '已批改', failed: '失败' }[status] || status
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

function getConfidence(report) {
  if (!report?.detail) return null
  try {
    const detail = typeof report.detail === 'string' ? JSON.parse(report.detail) : report.detail
    return detail.confidence || null
  } catch {
    return null
  }
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString('zh-CN')
}

function previewImage(url) {
  window.open(url, '_blank')
}

function openGradeModal(submission) {
  gradingSubmission.value = submission
  gradeForm.value = { score: '', feedback: '' }
  showGradeModal.value = true
}

async function submitGrade() {
  if (gradeForm.value.score === '' || gradeForm.value.score < 0 || gradeForm.value.score > 100) {
    alert('请输入 0-100 的分数')
    return
  }
  gradeSubmitting.value = true
  try {
    await api.post(`/homework/manual-grade/${gradingSubmission.value.id}`, {
      score: gradeForm.value.score,
      feedback: gradeForm.value.feedback,
    })
    showGradeModal.value = false
    loadSubmissions()
  } catch (e) {
    alert('批改失败：' + (e.response?.data?.detail || e.message))
  } finally {
    gradeSubmitting.value = false
  }
}
</script>

<style scoped>
.homework-manage-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
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

.btn-secondary {
  background: #f0f0f0;
  color: #333;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  text-decoration: none;
}

.btn-sm {
  background: #e6f7ff;
  color: #1890ff;
  border: 1px solid #91d5ff;
  padding: 4px 12px;
  border-radius: 4px;
  cursor: pointer;
  margin-right: 8px;
}

.btn-sm.primary {
  background: #1890ff;
  color: white;
  border-color: #1890ff;
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
.status-badge.pending { background: #fff7e6; color: #fa8c16; }
.status-badge.graded { background: #f6ffed; color: #52c41a; }

.status-group {
  display: flex;
  gap: 6px;
}

.task-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  margin-left: 6px;
}

.task-badge.pending { background: #f0f0f0; color: #666; }
.task-badge.sent { background: #e6f7ff; color: #1890ff; }
.task-badge.graded { background: #f6ffed; color: #52c41a; }
.task-badge.failed { background: #fff1f0; color: #ff4d4f; }

.task-error {
  background: #fff1f0;
  border: 1px solid #ffa39e;
  padding: 8px;
  border-radius: 4px;
  margin: 8px 0;
  font-size: 13px;
  color: #ff4d4f;
}

.error-label {
  font-weight: 500;
}

.retry-info {
  color: #999;
  font-size: 12px;
  margin-left: 8px;
}

.task-info {
  background: #e6f7ff;
  padding: 8px;
  border-radius: 4px;
  margin: 8px 0;
  font-size: 13px;
  color: #1890ff;
}

.desc {
  color: #666;
  margin-bottom: 8px;
}

.meta {
  font-size: 12px;
  color: #999;
  margin-bottom: 12px;
}

.assignment-actions {
  margin-top: 16px;
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

.modal-lg {
  width: 700px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 4px;
  font-weight: 500;
}

.form-group input,
.form-group textarea {
  width: 100%;
  padding: 8px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
}

.form-group textarea {
  min-height: 80px;
}

.form-group select {
  width: 100%;
  padding: 8px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
}

.form-group input[type="file"] {
  padding: 4px;
}

.question-files-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.question-file-item {
  position: relative;
  width: 80px;
  height: 80px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.question-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 4px;
}

.file-icon {
  font-size: 32px;
}

.remove-btn {
  position: absolute;
  top: -8px;
  right: -8px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #ff4d4f;
  color: white;
  border: none;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}

.submissions-list {
  max-height: 400px;
  overflow-y: auto;
}

.submission-item {
  border-bottom: 1px solid #f0f0f0;
  padding: 12px 0;
}

.submission-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.student-name {
  font-weight: 500;
}

.submission-images {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.thumb {
  width: 60px;
  height: 60px;
  object-fit: cover;
  border-radius: 4px;
  cursor: pointer;
}

.report-preview {
  background: #f6ffed;
  padding: 8px;
  border-radius: 4px;
  margin-bottom: 8px;
}

.confidence {
  font-size: 12px;
  color: #666;
  margin-bottom: 4px;
}

.low-confidence {
  color: #fa8c16;
  font-weight: 500;
}

.questions-detail {
  margin: 8px 0;
  padding: 8px;
  background: white;
  border-radius: 4px;
  font-size: 13px;
}

.question-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}

.q-index {
  font-weight: 500;
  min-width: 40px;
}

.q-score {
  min-width: 50px;
  color: #ff4d4f;
}

.q-score.correct {
  color: #52c41a;
}

.q-status {
  font-size: 14px;
}

.issues-list {
  margin: 8px 0;
  font-size: 12px;
  color: #fa8c16;
}

.issues-label {
  font-weight: 500;
}

.score {
  font-weight: 500;
  color: #52c41a;
}

.feedback {
  margin-top: 4px;
  font-size: 13px;
}

.submission-actions {
  margin-top: 8px;
}

.submission-time {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}

.loading, .empty {
  text-align: center;
  padding: 40px;
  color: #999;
}
</style>
