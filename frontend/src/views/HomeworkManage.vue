<template>
  <div class="homework-manage-page">
    <div class="page-header">
      <div class="title-block">
        <h2>作业管理</h2>
        <p>按小节整理题目、标准答案与学生提交</p>
      </div>
      <router-link to="/teacher" class="btn-secondary">返回统计看板</router-link>
    </div>

    <div v-if="loading" class="loading">加载中...</div>

    <template v-else>
      <div v-for="section in sections" :key="section.id" class="section-card">
        <div class="section-header">
          <h3>{{ section.title }}</h3>
        </div>

        <div v-if="!getAssignment(section.id)" class="section-empty">
          <p>该小节暂无作业</p>
          <button class="btn-primary" @click="openCreateForSection(section)">发布作业</button>
        </div>

        <div v-else class="assignment-detail">
          <div class="assignment-header">
            <h4>{{ getAssignment(section.id).title }}</h4>
            <div class="status-group">
              <span class="status-badge" :class="getAssignment(section.id).status">{{ statusText(getAssignment(section.id).status) }}</span>
              <span class="status-badge grading" :class="getAssignment(section.id).grading_status">{{ gradingStatusText(getAssignment(section.id).grading_status) }}</span>
            </div>
          </div>

          <p class="desc">{{ getAssignment(section.id).description || '暂无描述' }}</p>
          <div class="meta">
            <span v-if="getAssignment(section.id).deadline">截止时间：{{ formatDate(getAssignment(section.id).deadline) }}</span>
            <span class="answer-state" :class="{ ready: hasAnswer(getAssignment(section.id)) }">答案：{{ hasAnswer(getAssignment(section.id)) ? '已录入' : '未录入' }}</span>
          </div>

          <div v-if="getAssignment(section.id).question_files?.length" class="question-files-preview card-preview">
            <h4>题目文件</h4>
            <div class="question-files-list">
              <div v-for="(file, i) in getAssignment(section.id).question_files" :key="`qf-${i}`" class="question-file-item">
                <img v-if="!isPdf(file)" :src="getMediaUrl(file)" class="question-thumb" @click="previewImage(getMediaUrl(file))" />
                <a v-else :href="getMediaUrl(file)" target="_blank" class="pdf-link">查看 PDF</a>
              </div>
            </div>
          </div>

          <div class="assignment-actions">
            <button class="btn-sm" @click="openEditForSection(section)">编辑</button>
            <button class="btn-sm answer-action" @click="openAnswerForSection(section)">答案管理</button>
            <button v-if="getAssignment(section.id).status === 'draft'" class="btn-sm primary" @click="publishAssignment(section.id)">发布</button>
            <button class="btn-sm" @click="loadSubmissions(section.id)">查看提交</button>
            <button class="btn-sm" @click="openUnsubmittedModal">未交名单</button>
          </div>
        </div>
      </div>

      <div v-if="sections.length === 0" class="empty">暂无小节数据</div>
    </template>

    <div v-if="showCreateModal || showEditModal" class="modal-overlay" @click.self="closeModal">
      <div class="modal modal-lg">
        <h3>{{ showEditModal ? '编辑作业' : '创建作业' }}</h3>
        <div class="form-group">
          <label>所属小节</label>
          <input :value="currentSection?.title" disabled />
        </div>
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
              <span v-if="isPdf(file)" class="file-icon">PDF</span>
              <img v-else :src="getMediaUrl(file)" class="question-thumb" />
              <button type="button" class="remove-btn" @click="removeQuestionFile(i)">x</button>
            </div>
          </div>
        </div>

        <div class="form-group answer-module">
          <div class="answer-header">
            <label>答案模块</label>
            <div class="answer-actions">
            <button type="button" class="btn-sm" @click="addAnswerItem">添加一题</button>
              <label class="btn-sm file-button">
                {{ answerParsing ? '解析中...' : '上传答案文件' }}
                <input type="file" accept=".pdf,.doc,.docx" :disabled="answerParsing" @change="handleAnswerFileSelect" />
              </label>
            </div>
          </div>
          <div v-if="form.answer_items.length === 0" class="empty small">暂无答案</div>
          <table v-else class="answer-table">
            <thead>
              <tr>
                <th>题号</th>
                <th>题型</th>
                <th>答案</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in form.answer_items" :key="index">
                <td><input v-model="item.no" placeholder="1" /></td>
                <td>
                  <select v-model="item.type">
                    <option value="choice">选择题</option>
                    <option value="fill">填空题</option>
                    <option value="judge">判断题</option>
                  </select>
                </td>
                <td><input v-model="item.answer" placeholder="标准答案" /></td>
                <td><button type="button" class="remove-btn" @click="removeAnswerItem(index)">移除</button></td>
              </tr>
            </tbody>
          </table>
          <pre v-if="form.answer_items.length > 0" class="answer-json">{{ answerJsonPreview }}</pre>
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

    <div v-if="showAnswerModal" class="modal-overlay" @click.self="closeAnswerModal">
      <div class="modal modal-lg answer-manage-modal">
        <h3>答案管理 - {{ currentSection?.title }}</h3>
        <div class="answer-module standalone">
          <div class="answer-header">
            <label>标准答案</label>
            <div class="answer-actions">
              <button type="button" class="btn-sm" @click="addAnswerItem">添加一题</button>
              <label class="btn-sm file-button">
                {{ answerParsing ? '解析中...' : '上传答案文件' }}
                <input type="file" accept=".pdf,.doc,.docx" :disabled="answerParsing" @change="handleAnswerFileSelect" />
              </label>
            </div>
          </div>
          <div v-if="form.answer_items.length === 0" class="empty small">暂无答案</div>
          <table v-else class="answer-table">
            <thead>
              <tr>
                <th>题号</th>
                <th>题型</th>
                <th>答案</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in form.answer_items" :key="index">
                <td><input v-model="item.no" placeholder="1" /></td>
                <td>
                  <select v-model="item.type">
                    <option value="choice">选择题</option>
                    <option value="fill">填空题</option>
                    <option value="judge">判断题</option>
                  </select>
                </td>
                <td><input v-model="item.answer" placeholder="标准答案" /></td>
                <td><button type="button" class="remove-btn" @click="removeAnswerItem(index)">移除</button></td>
              </tr>
            </tbody>
          </table>
          <pre v-if="form.answer_items.length > 0" class="answer-json">{{ answerJsonPreview }}</pre>
        </div>
        <div class="modal-actions">
          <button class="btn-secondary" @click="closeAnswerModal">取消</button>
          <button class="btn-primary" @click="saveAnswer">保存答案</button>
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
              <div class="status-group">
                <span v-if="s.is_late" class="status-badge late">迟交</span>
                <span class="status-badge" :class="s.status">{{ s.status === 'graded' ? '已批改' : '待批改' }}</span>
                <span v-if="s.task" class="task-badge" :class="s.task.status">{{ taskStatusText(s.task.status) }}</span>
              </div>
            </div>
            <div class="submission-images">
              <img v-for="(img, i) in s.images" :key="i" :src="getMediaUrl(img)" class="thumb" @click="previewImage(getMediaUrl(img))" />
            </div>
            <div v-if="s.report" class="report-preview">
              <div class="score">分数：{{ s.report.score }}</div>
              <div class="feedback">{{ s.report.feedback }}</div>
            </div>
            <div v-if="s.task && s.task.status === 'failed'" class="task-error">
              <span class="error-label">批改失败：</span>{{ s.task.error_message || '未知错误' }}
              <span v-if="s.task.retry_count > 0" class="retry-info">(已重试 {{ s.task.retry_count }} 次)</span>
            </div>
            <div v-if="s.task && s.task.status === 'sent'" class="task-info">已发送给智能体，等待回调...</div>
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

    <div v-if="showUnsubmittedModal" class="modal-overlay" @click.self="showUnsubmittedModal = false">
      <div class="modal modal-lg">
        <h3>未交名单</h3>
        <div v-if="unsubmittedStudents.length === 0" class="empty">暂无未交学生</div>
        <div v-else class="submissions-list">
          <div v-for="u in unsubmittedStudents" :key="u.id" class="submission-item">
            <div class="submission-header">
              <span class="student-name">{{ u.name }}</span>
              <span>{{ u.class_name || '未分配班级' }}</span>
            </div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn-secondary" @click="showUnsubmittedModal = false">关闭</button>
        </div>
      </div>
    </div>

    <div v-if="showGradeModal" class="modal-overlay" @click.self="showGradeModal = false">
      <div class="modal">
        <h3>手动批改 - {{ gradingSubmission?.user?.name }}</h3>
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
import { computed, ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../utils/api.js'

const route = useRoute()
const courseId = route.params.courseId

const loading = ref(false)
const sections = ref([])
const assignmentMap = ref({})
const submissions = ref([])
const unsubmittedStudents = ref([])
const showCreateModal = ref(false)
const showEditModal = ref(false)
const showAnswerModal = ref(false)
const showSubmissionsModal = ref(false)
const showUnsubmittedModal = ref(false)
const showGradeModal = ref(false)
const gradingSubmission = ref(null)
const gradeForm = ref({ score: '', feedback: '' })
const gradeSubmitting = ref(false)
const answerParsing = ref(false)
const currentSection = ref(null)
const currentViewSectionId = ref(null)

function emptyForm() {
  return {
    title: '',
    description: '',
    question_files: [],
    grading_prompt: '',
    grading_mode: 'auto',
    deadline: '',
    section_id: null,
    answer_items: [],
  }
}

const form = ref(emptyForm())

const answerJsonPreview = computed(() => JSON.stringify(buildAnswerObject(), null, 2))

onMounted(() => {
  loadData()
})

function getAssignment(sectionId) {
  return assignmentMap.value[sectionId]
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

function parseAnswerItems(raw) {
  if (!raw) return []
  try {
    const obj = typeof raw === 'string' ? JSON.parse(raw) : raw
    return Array.isArray(obj.items)
      ? obj.items.map(item => ({
        no: String(item.no || ''),
        type: item.type || 'choice',
        answer: String(item.answer ?? ''),
      }))
      : []
  } catch {
    return []
  }
}

function buildAnswerItems() {
  return form.value.answer_items
    .map(item => ({
      no: String(item.no || '').trim(),
      type: item.type || 'choice',
      answer: String(item.answer || '').trim(),
    }))
    .filter(item => item.no && item.answer)
}

function buildAnswerObject() {
  return { version: 1, items: buildAnswerItems() }
}

function buildAnswerJson() {
  const items = buildAnswerItems()
  return items.length ? JSON.stringify({ version: 1, items }) : ''
}

function hasAnswer(assignment) {
  return parseAnswerItems(assignment?.reference_answer).length > 0
}

function addAnswerItem() {
  form.value.answer_items.push({ no: String(form.value.answer_items.length + 1), type: 'choice', answer: '' })
}

function removeAnswerItem(index) {
  form.value.answer_items.splice(index, 1)
}

async function loadData() {
  loading.value = true
  try {
    const [sectionsRes, assignmentsRes] = await Promise.all([
      api.get('/sections', { params: { course_id: courseId } }),
      api.get(`/homework/course/${courseId}`),
    ])
    sections.value = sectionsRes.data.data || []
    const map = {}
    for (const assignment of assignmentsRes.data.data || []) {
      map[assignment.section_id] = assignment
    }
    assignmentMap.value = map
  } catch (e) {
    alert('加载失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

function openCreateForSection(section) {
  currentSection.value = section
  form.value = {
    ...emptyForm(),
    title: `${section.title} 作业`,
    section_id: section.id,
  }
  showCreateModal.value = true
}

function openEditForSection(section) {
  const assignment = assignmentMap.value[section.id]
  if (!assignment) return
  currentSection.value = section
  form.value = {
    title: assignment.title || '',
    description: assignment.description || '',
    question_files: assignment.question_files ? [...assignment.question_files] : [],
    grading_prompt: assignment.grading_prompt || '',
    grading_mode: assignment.grading_mode || 'auto',
    deadline: assignment.deadline ? assignment.deadline.slice(0, 16) : '',
    section_id: section.id,
    answer_items: parseAnswerItems(assignment.reference_answer),
  }
  showEditModal.value = true
}

function openAnswerForSection(section) {
  const assignment = assignmentMap.value[section.id]
  if (!assignment) return
  currentSection.value = section
  form.value = {
    ...emptyForm(),
    section_id: section.id,
    answer_items: parseAnswerItems(assignment.reference_answer),
  }
  showAnswerModal.value = true
}

async function saveAssignment() {
  if (!form.value.title.trim()) {
    alert('请输入作业标题')
    return
  }
  const payload = {
    title: form.value.title.trim(),
    description: form.value.description,
    question_files: form.value.question_files,
    grading_prompt: form.value.grading_prompt,
    reference_answer: buildAnswerJson(),
    grading_mode: form.value.grading_mode,
    deadline: form.value.deadline || null,
  }
  try {
    if (showEditModal.value) {
      await api.put(`/homework/assignments/${form.value.section_id}`, payload)
    } else {
      await api.post(`/homework/assignments/${form.value.section_id}`, payload)
    }
    closeModal()
    await loadData()
  } catch (e) {
    alert('保存失败：' + (e.response?.data?.detail || e.message))
  }
}

async function publishAssignment(sectionId) {
  if (!confirm('确认发布此作业？')) return
  try {
    await api.put(`/homework/assignments/${sectionId}`, { status: 'published' })
    await loadData()
  } catch (e) {
    alert('发布失败：' + (e.response?.data?.detail || e.message))
  }
}

function closeModal() {
  showCreateModal.value = false
  showEditModal.value = false
  currentSection.value = null
  form.value = emptyForm()
}

function closeAnswerModal() {
  showAnswerModal.value = false
  currentSection.value = null
  form.value = emptyForm()
}

async function saveAnswer() {
  if (!form.value.section_id) return
  try {
    await api.put(`/homework/assignments/${form.value.section_id}/answer`, {
      answer: buildAnswerJson() || '',
    })
    closeAnswerModal()
    await loadData()
  } catch (e) {
    alert('保存答案失败：' + (e.response?.data?.detail || e.message))
  }
}

async function handleQuestionFileSelect(e) {
  const files = Array.from(e.target.files || [])
  for (const file of files) {
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await api.post('/homework/upload-question', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      form.value.question_files.push(res.data.data.url)
    } catch (err) {
      alert('上传失败：' + (err.response?.data?.detail || err.message))
    }
  }
  e.target.value = ''
}

async function handleAnswerFileSelect(e) {
  const file = e.target.files?.[0]
  if (!file) return
  answerParsing.value = true
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await api.post('/homework/answer/parse', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    form.value.answer_items = parseAnswerItems(res.data.data.answer)
  } catch (err) {
    alert('答案解析失败：' + (err.response?.data?.detail || err.message))
  } finally {
    answerParsing.value = false
    e.target.value = ''
  }
}

function removeQuestionFile(index) {
  form.value.question_files.splice(index, 1)
}

async function loadSubmissions(sectionId) {
  currentViewSectionId.value = sectionId
  try {
    const res = await api.get(`/homework/assignments/${sectionId}/submissions`)
    submissions.value = res.data.data || []
    showSubmissionsModal.value = true
  } catch (e) {
    alert('加载失败：' + (e.response?.data?.detail || e.message))
  }
}

async function openUnsubmittedModal() {
  try {
    const res = await api.get(`/homework/assignments/${courseId}/submissions-summary`)
    unsubmittedStudents.value = res.data.data?.unsubmitted_students || []
  } catch {
    unsubmittedStudents.value = []
  }
  showUnsubmittedModal.value = true
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
    if (currentViewSectionId.value) await loadSubmissions(currentViewSectionId.value)
  } catch (e) {
    alert('批改失败：' + (e.response?.data?.detail || e.message))
  } finally {
    gradeSubmitting.value = false
  }
}
</script>

<style scoped>
.homework-manage-page {
  min-height: 100vh;
  max-width: 1040px;
  margin: 0 auto;
  padding: 24px;
  color: #263238;
  background: linear-gradient(180deg, #f4f8f6 0%, #eef4f7 100%);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
  margin-bottom: 20px;
}

.title-block h2 {
  margin: 0;
  font-size: 26px;
  color: #17324d;
}

.title-block p {
  margin: 6px 0 0;
  color: #687681;
  font-size: 14px;
}

.btn-primary,
.btn-secondary,
.btn-sm {
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
  transition: transform 0.15s, box-shadow 0.15s, background 0.15s;
}

.btn-primary:hover,
.btn-secondary:hover,
.btn-sm:hover {
  transform: translateY(-1px);
}

.btn-primary {
  background: #2563eb;
  color: white;
  padding: 9px 18px;
  box-shadow: 0 6px 14px rgba(37, 99, 235, 0.18);
}

.btn-secondary {
  background: #ffffff;
  color: #375266;
  border: 1px solid #d9e4ea;
  padding: 9px 16px;
  text-decoration: none;
}

.btn-sm {
  background: #edf6f3;
  color: #166154;
  border: 1px solid #c8ded7;
  padding: 6px 12px;
  margin: 0;
}

.btn-sm.primary {
  background: #2563eb;
  color: white;
  border-color: #2563eb;
}

.btn-sm.answer-action {
  background: #fff4df;
  border-color: #f8ddb0;
  color: #a16207;
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
  background: linear-gradient(180deg, #16a085, #f59e0b);
}

.section-header {
  display: flex;
  align-items: center;
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
  padding: 22px 0;
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
  font-size: 18px;
  color: #22313f;
}

.status-group {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.status-badge,
.task-badge,
.answer-state {
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
.status-badge.pending { background: #fff4df; color: #a16207; }
.status-badge.graded { background: #e8f7ef; color: #15803d; }
.status-badge.late { background: #fee8e7; color: #b42318; }
.status-badge.grading { border: 1px solid rgba(0, 0, 0, 0.04); }

.task-badge.pending { background: #eef2f7; color: #607080; }
.task-badge.sent { background: #e8f2ff; color: #2563eb; }
.task-badge.graded { background: #e8f7ef; color: #15803d; }
.task-badge.failed { background: #fee8e7; color: #b42318; }

.desc {
  color: #566573;
  line-height: 1.65;
  margin: 0 0 10px;
}

.meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
  font-size: 13px;
  color: #687681;
  margin-bottom: 12px;
}

.answer-state {
  color: #b42318;
  background: #fff1ee;
}

.answer-state.ready {
  color: #166154;
  background: #e7f6ef;
}

.assignment-actions,
.answer-actions,
.modal-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.assignment-actions {
  margin-top: 16px;
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

.modal-lg {
  width: min(780px, 100%);
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

.form-group input,
.form-group textarea,
.form-group select {
  width: 100%;
  box-sizing: border-box;
  padding: 10px 11px;
  border: 1px solid #cfdce3;
  border-radius: 6px;
  background: #ffffff;
  color: #263238;
  font-size: 14px;
}

.form-group input:focus,
.form-group textarea:focus,
.form-group select:focus {
  border-color: #16a085;
  box-shadow: 0 0 0 3px rgba(22, 160, 133, 0.12);
  outline: none;
}

.form-group textarea {
  min-height: 92px;
  resize: vertical;
}

.question-files-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 10px;
}

.question-files-preview h4 {
  flex-basis: 100%;
  margin: 0;
  color: #40515f;
  font-size: 14px;
}

.question-file-item {
  position: relative;
  width: 88px;
  height: 88px;
  border: 1px solid #d6e1dc;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #ffffff;
}

.question-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 6px;
  cursor: pointer;
}

.pdf-link,
.file-icon {
  display: flex;
  width: 100%;
  height: 100%;
  align-items: center;
  justify-content: center;
  background: #eef5ff;
  color: #2563eb;
  text-decoration: none;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 700;
}

.remove-btn {
  position: absolute;
  top: -8px;
  right: -8px;
  min-width: 22px;
  height: 22px;
  border-radius: 999px;
  background: #b42318;
  color: white;
  border: none;
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
}

.modal-actions {
  justify-content: flex-end;
  margin-top: 18px;
}

.answer-module {
  border: 1px solid #d6e1dc;
  border-radius: 8px;
  padding: 14px;
  background: linear-gradient(180deg, #ffffff 0%, #f7fbf9 100%);
}

.answer-manage-modal .answer-module.standalone {
  margin-top: 4px;
}

.answer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.file-button {
  display: inline-flex;
  align-items: center;
  cursor: pointer;
}

.file-button input {
  display: none;
}

.answer-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0 8px;
  table-layout: fixed;
}

.answer-table th {
  color: #657582;
  font-size: 12px;
  text-align: left;
  padding: 0 8px;
}

.answer-table td {
  background: #ffffff;
  border-top: 1px solid #dfe9e5;
  border-bottom: 1px solid #dfe9e5;
  padding: 8px;
}

.answer-table td:first-child {
  border-left: 1px solid #dfe9e5;
  border-radius: 6px 0 0 6px;
}

.answer-table td:last-child {
  border-right: 1px solid #dfe9e5;
  border-radius: 0 6px 6px 0;
}

.answer-table input,
.answer-table select {
  width: 100%;
  box-sizing: border-box;
}

.answer-table .remove-btn {
  position: static;
  width: auto;
  height: auto;
  border-radius: 6px;
  padding: 7px 10px;
}

.answer-json {
  background: #182734;
  color: #dce8ea;
  border-radius: 6px;
  padding: 10px;
  overflow-x: auto;
  font-size: 12px;
  line-height: 1.5;
}

.submissions-list {
  max-height: 440px;
  overflow-y: auto;
}

.submission-item {
  border: 1px solid #dfe9e5;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 10px;
  background: #ffffff;
}

.submission-header {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.student-name {
  font-weight: 700;
  color: #17324d;
}

.submission-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.thumb {
  width: 64px;
  height: 64px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid #dfe9e5;
  cursor: pointer;
}

.report-preview {
  background: #edf9f1;
  border: 1px solid #c8ecd4;
  padding: 10px;
  border-radius: 6px;
  margin-bottom: 8px;
}

.score {
  font-weight: 800;
  color: #15803d;
}

.feedback {
  margin-top: 4px;
  font-size: 13px;
  color: #40515f;
}

.task-error,
.task-info {
  padding: 9px 10px;
  border-radius: 6px;
  margin: 8px 0;
  font-size: 13px;
}

.task-error {
  background: #fff1ee;
  border: 1px solid #fecaca;
  color: #b42318;
}

.task-info {
  background: #eef5ff;
  color: #2563eb;
}

.error-label {
  font-weight: 700;
}

.retry-info,
.submission-time {
  color: #7b8790;
  font-size: 12px;
}

.submission-actions {
  margin-top: 8px;
}

.loading,
.empty {
  text-align: center;
  padding: 40px;
  color: #7b8790;
}

.empty.small {
  padding: 14px;
  background: #ffffff;
  border: 1px dashed #cfdce3;
  border-radius: 6px;
}

@media (max-width: 720px) {
  .homework-manage-page {
    padding: 16px;
  }

  .page-header,
  .assignment-header,
  .answer-header {
    align-items: stretch;
    flex-direction: column;
  }

  .status-group {
    justify-content: flex-start;
  }

  .answer-table {
    min-width: 560px;
  }

  .answer-module {
    overflow-x: auto;
  }
}
</style>
