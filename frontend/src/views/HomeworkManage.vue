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
          <span class="status-badge" :class="assignment.status">{{ statusText(assignment.status) }}</span>
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
      <div class="modal">
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
          <label>评分标准（传给智能体）</label>
          <textarea v-model="form.grading_prompt" placeholder="请输入评分标准/批改提示词"></textarea>
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
            </div>
            <div class="submission-images">
              <img v-for="(img, i) in s.images" :key="i" :src="img" class="thumb" @click="previewImage(img)" />
            </div>
            <div v-if="s.report" class="report-preview">
              <div class="score">分数：{{ s.report.score }}</div>
              <div class="feedback">{{ s.report.feedback }}</div>
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
  grading_prompt: '',
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
        grading_prompt: form.value.grading_prompt,
        deadline: form.value.deadline || null,
      })
    } else {
      await api.post(`/homework/assignments/${courseId}`, {
        title: form.value.title,
        description: form.value.description,
        grading_prompt: form.value.grading_prompt,
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
  form.value = { title: '', description: '', grading_prompt: '', deadline: '' }
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
