<!--
  @模块：CourseEdit.vue — 课程编辑页（新建/编辑双模式 + 小节管理）
  @页面用途：教师创建新课程或编辑已有课程，管理课程下的小节（章节），每个小节独立设置视频。
  @数据流：
    1. 路由参数 courseId > 0 → 编辑模式，挂载时加载课程 + 小节列表
    2. 路由参数 courseId = 0 → 新建模式，先创建课程再管理小节
    3. 保存课程信息（标题/描述/时长等）和小节信息（增删改排序）独立操作
    4. 小节视频：每个小节独立上传，支持外部链接和本地上传
  @后端API：
    - GET /courses/:courseId：获取课程详情
    - POST /courses：创建新课程
    - PUT /courses/:courseId：更新课程信息
    - GET /sections?course_id=x：获取小节列表
    - POST /sections：创建小节
    - PUT /sections/:id：更新小节
    - DELETE /sections/:id：删除小节
    - POST /sections/:id/upload-video：上传小节视频
  @依赖：
    - vue-router：获取路由参数、编程式导航
    - utils/api：封装了 axios 的请求工具
-->
<template>
  <div class="course-edit-page">
    <!-- 返回导航 -->
    <div class="back-nav">
      <a href="javascript:void(0)" @click="$router.back()" class="back-link">&larr; 返回</a>
    </div>
    <!-- 页面标题 -->
    <h2 class="page-title">{{ isEdit ? '编辑课程' : '创建课程' }}</h2>

    <!-- ==================== 课程基本信息表单 ==================== -->
    <div class="form-card">
      <div class="form-group">
        <label>课程标题<span class="required">*</span></label>
        <input v-model="form.title" placeholder="如：高中数学必修一 - 集合与函数" />
      </div>

      <div class="form-group">
        <label>课程描述</label>
        <textarea v-model="form.description" rows="3" placeholder="简述课程内容"></textarea>
      </div>

      <div class="form-group">
        <label>要求学习时长（分钟）</label>
        <input v-model.number="form.require_minutes" type="number" min="1" />
      </div>

      <div class="form-group">
        <label>截止日期</label>
        <input v-model="form.end_date" type="date" />
      </div>

      <!-- 保存课程信息按钮 -->
      <div class="form-actions">
        <button class="btn primary" @click="onSaveCourse()" :disabled="saving">
          {{ saving ? '保存中...' : '保存课程信息' }}
        </button>
        <span v-if="saveMsg" class="save-msg" :class="saveMsgType">{{ saveMsg }}</span>
      </div>
    </div>

    <!-- ==================== 小节管理区域（仅编辑模式显示） ==================== -->
    <div v-if="isEdit" class="sections-card">
      <div class="section-header">
        <h3>课程小节（{{ sections.length }}）</h3>
        <button class="btn primary btn-sm" @click="onAddSection()">+ 添加小节</button>
      </div>

      <!-- 小节列表：按 sort_order 排序显示 -->
      <div v-if="sections.length === 0" class="empty-hint">
        暂无小节，点击"添加小节"开始创建
      </div>

      <div v-for="(sec, idx) in sections" :key="sec.id" class="section-item">
        <!-- 小节头部：序号 + 标题 + 操作按钮 -->
        <div class="section-item-header">
          <span class="section-index">{{ idx + 1 }}</span>
          <input
            v-model="sec.title"
            class="section-title-input"
            placeholder="小节标题"
            @blur="onUpdateSection(sec)"
          />
          <div class="section-actions">
            <!-- 上移/下移排序按钮 -->
            <button class="btn-icon" @click="onMoveSection(idx, -1)" :disabled="idx === 0" title="上移">&#9650;</button>
            <button class="btn-icon" @click="onMoveSection(idx, 1)" :disabled="idx === sections.length - 1" title="下移">&#9660;</button>
            <!-- 删除小节 -->
            <button class="btn-icon btn-danger" @click="onDeleteSection(sec, idx)" title="删除">&#10005;</button>
          </div>
        </div>

        <!-- 小节视频设置 -->
        <div class="section-video-settings">
          <!-- v4.0: 开播时间设置 -->
          <div class="open-time-setting">
            <label class="open-time-label">开播时间</label>
            <input
              v-model="sec.open_time"
              type="datetime-local"
              class="open-time-input"
              @blur="onUpdateSection(sec)"
            />
            <button v-if="sec.open_time" class="btn-text" @click="sec.open_time = ''; onUpdateSection(sec)">清除</button>
            <span v-else class="hint">不设则随时可学</span>
          </div>
          <!-- 模式切换 -->
          <div class="video-mode-tabs">
            <button :class="['tab', sec.video_type === 'url' ? 'active' : '']" @click="sec.video_type = 'url'">
              外部链接
            </button>
            <button :class="['tab', sec.video_type === 'local' ? 'active' : '']" @click="sec.video_type = 'local'">
              本地上传
            </button>
          </div>

          <!-- 外部链接模式 -->
          <div v-if="sec.video_type === 'url'" class="video-mode-content">
            <input
              v-model="sec.video_url"
              placeholder="粘贴视频播放页链接（如B站、腾讯视频等）"
              @blur="onUpdateSection(sec)"
            />
          </div>

          <!-- 本地上传模式 -->
          <div v-if="sec.video_type === 'local'" class="video-mode-content">
            <!-- 上传中 -->
            <div v-if="sec._uploading" class="upload-progress">
              <div class="progress-bar">
                <div class="progress-fill" :style="{ width: (sec._uploadProgress || 0) + '%' }"></div>
              </div>
              <span>{{ sec._uploadProgress || 0 }}%</span>
            </div>
            <!-- 已上传视频 -->
            <div v-else-if="sec.video_url && isLocalFile(sec.video_url)" class="current-video">
              <span>已上传: {{ sec.video_url }}</span>
              <button class="btn-text" @click="sec.video_url = ''">重新上传</button>
            </div>
            <!-- 上传区域 -->
            <div v-else class="upload-area" @click="triggerFileSelect(sec.id)">
              <span class="upload-icon">+</span>
              <span>点击选择视频文件</span>
              <span class="hint">支持 MP4/WebM/OGG/MOV，最大 500MB</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 新建模式提示：先保存课程才能管理小节 -->
    <div v-else class="sections-card">
      <div class="empty-hint">请先保存课程信息，然后即可添加小节</div>
    </div>

    <!-- 隐藏的文件输入框（每个小节共用，通过 currentUploadSection 区分） -->
    <input
      ref="fileInput"
      type="file"
      accept="video/mp4,video/webm,video/ogg,video/quicktime"
      @change="onFileSelect"
      style="display:none"
    />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../utils/api'

const route = useRoute()
const router = useRouter()

/** 课程ID：0 表示新建模式 */
const courseId = computed(() => parseInt(route.params.courseId) || 0)

/** 是否为编辑模式 */
const isEdit = computed(() => courseId.value > 0)

/** 课程基本信息表单 */
const form = ref({
  title: '',
  description: '',
  require_minutes: 60,
  end_date: '',
  status: 'active',
})

/** 小节列表（含前端临时状态 _uploading / _uploadProgress） */
const sections = ref([])

const saving = ref(false)
const saveMsg = ref('')
const saveMsgType = ref('success')

/** 当前正在上传视频的小节ID */
const currentUploadSection = ref(null)

/** 文件输入框模板引用 */
const fileInput = ref(null)

/**
 * 判断文件名是否为本地视频（非 http 链接）
 */
function isLocalFile(url) {
  return url && !url.startsWith('http')
}

/**
 * 组件挂载：编辑模式下加载课程和小节数据
 */
onMounted(async () => {
  if (isEdit.value) {
    try {
      // 并行请求课程详情和小节列表
      const [courseRes, sectionsRes] = await Promise.all([
        api.get(`/courses/${courseId.value}`),
        api.get('/sections', { params: { course_id: courseId.value } }),
      ])
      if (courseRes.data.code === 0) {
        const c = courseRes.data.data
        form.value = {
          title: c.title,
          description: c.description,
          require_minutes: c.require_minutes,
          end_date: c.end_date ? c.end_date.split(' ')[0] : '',
          status: c.status,
        }
      }
      if (sectionsRes.data.code === 0) {
        // 给每个小节加前端临时字段
        sections.value = sectionsRes.data.data.map(s => ({
          ...s,
          // v4.0: 格式化 open_time 用于 datetime-local input
          open_time: s.open_time ? s.open_time.slice(0, 16) : '',
          _uploading: false,
          _uploadProgress: 0,
        }))
      }
    } catch (e) {
      console.error('加载课程数据失败:', e)
    }
  }
})

/**
 * 保存课程基本信息
 */
const onSaveCourse = async () => {
  if (!form.value.title) {
    alert('请填写课程标题')
    return
  }

  saving.value = true
  saveMsg.value = ''
  try {
    const payload = {
      title: form.value.title,
      description: form.value.description,
      require_minutes: form.value.require_minutes,
      end_date: form.value.end_date || null,
    }

    if (isEdit.value) {
      const res = await api.put(`/courses/${courseId.value}`, payload)
      if (res.data.code === 0) {
        saveMsg.value = '保存成功'
        saveMsgType.value = 'success'
        setTimeout(() => { saveMsg.value = '' }, 3000)
      } else {
        saveMsg.value = res.data.msg || '保存失败'
        saveMsgType.value = 'error'
      }
    } else {
      // 新建：创建课程后跳转到编辑页，以便管理小节
      const res = await api.post('/courses', payload)
      if (res.data.code === 0) {
        router.replace(`/course-edit/${res.data.data.id}`)
        return
      } else {
        saveMsg.value = res.data.msg || '创建失败'
        saveMsgType.value = 'error'
      }
    }
  } catch (e) {
    saveMsg.value = '保存失败: ' + (e.response?.data?.detail || e.message)
    saveMsgType.value = 'error'
  } finally {
    saving.value = false
  }
}

/**
 * 添加小节
 */
const onAddSection = async () => {
  try {
    const res = await api.post('/sections', {
      course_id: courseId.value,
      title: `小节 ${sections.value.length + 1}`,
      sort_order: sections.value.length + 1,
      video_type: 'url',
      video_url: '',
    })
    if (res.data.code === 0) {
      sections.value.push({
        id: res.data.data.id,
        course_id: courseId.value,
        title: res.data.data.title,
        sort_order: sections.value.length + 1,
        video_type: 'url',
        video_url: '',
        video_cdn_url: '',
        duration_seconds: 0,
        _uploading: false,
        _uploadProgress: 0,
      })
    }
  } catch (e) {
    alert('添加小节失败: ' + (e.response?.data?.detail || e.message))
  }
}

/**
 * 更新小节信息（标题/视频类型/视频URL等）
 */
const onUpdateSection = async (sec) => {
  try {
    const payload = {
      title: sec.title,
      video_type: sec.video_type,
      video_url: sec.video_type === 'url' ? (sec.video_url || '') : sec.video_url,
    }
    // v4.0: 传递开播时间
    if (sec.open_time) {
      payload.open_time = sec.open_time
    }
    await api.put(`/sections/${sec.id}`, payload)
  } catch (e) {
    console.warn('更新小节失败:', e)
  }
}

/**
 * 移动小节排序（direction: -1=上移, 1=下移）
 */
const onMoveSection = async (idx, direction) => {
  const targetIdx = idx + direction
  if (targetIdx < 0 || targetIdx >= sections.value.length) return

  // 前端交换位置
  const list = [...sections.value]
  ;[list[idx], list[targetIdx]] = [list[targetIdx], list[idx]]

  // 更新 sort_order 并批量保存到后端
  const updates = list.map((s, i) => {
    s.sort_order = i + 1
    return api.put(`/sections/${s.id}`, { sort_order: s.sort_order })
  })

  sections.value = list
  try {
    await Promise.all(updates)
  } catch (e) {
    console.warn('排序更新失败:', e)
  }
}

/**
 * 删除小节
 */
const onDeleteSection = async (sec, idx) => {
  if (!confirm(`确定删除小节"${sec.title}"？`)) return
  try {
    await api.delete(`/sections/${sec.id}`)
    sections.value.splice(idx, 1)
    // 重新编号 sort_order
    sections.value.forEach((s, i) => { s.sort_order = i + 1 })
  } catch (e) {
    alert('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

/**
 * 触发文件选择
 */
function triggerFileSelect(sectionId) {
  currentUploadSection.value = sectionId
  fileInput.value?.click()
}

/**
 * 视频文件选择处理：上传到对应小节
 */
const onFileSelect = async (event) => {
  const file = event.target.files?.[0]
  if (!file) return

  if (file.size > 500 * 1024 * 1024) {
    alert('视频文件不能超过500MB')
    event.target.value = ''
    return
  }

  const secId = currentUploadSection.value
  const sec = sections.value.find(s => s.id === secId)
  if (!sec) return

  sec._uploading = true
  sec._uploadProgress = 0

  try {
    const formData = new FormData()
    formData.append('file', file)

    const res = await api.post(`/sections/${secId}/upload-video`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => {
        sec._uploadProgress = Math.round((e.loaded / e.total) * 100)
      },
    })

    if (res.data.code === 0) {
      sec.video_type = 'local'
      sec.video_url = res.data.data.video_url
      alert('视频上传成功')
    }
  } catch (e) {
    alert('上传失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    sec._uploading = false
    sec._uploadProgress = 0
    if (fileInput.value) fileInput.value.value = ''
    currentUploadSection.value = null
  }
}
</script>

<style scoped>
/* 页面整体 */
.course-edit-page { padding: 16px; max-width: 640px; margin: 0 auto; }
.page-title { font-size: 20px; margin-bottom: 16px; }

/* 表单卡片 */
.form-card { background: #fff; border-radius: 10px; padding: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); margin-bottom: 16px; }
.form-group { margin-bottom: 16px; }
.form-group label { display: block; font-size: 14px; font-weight: 500; margin-bottom: 6px; color: #333; }
.required { color: #ff4d4f; }
.form-group input, .form-group textarea {
  width: 100%; padding: 10px 12px; border: 1px solid #d9d9d9; border-radius: 6px;
  font-size: 14px; box-sizing: border-box;
}
.form-group input:focus, .form-group textarea:focus { border-color: #1890ff; outline: none; }

/* 小节管理卡片 */
.sections-card { background: #fff; border-radius: 10px; padding: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }

/* 小节管理头部 */
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.section-header h3 { font-size: 16px; margin: 0; }

/* 空状态提示 */
.empty-hint { text-align: center; color: #999; padding: 20px 0; font-size: 14px; }

/* 单个小节卡片 */
.section-item {
  border: 1px solid #e8e8e8; border-radius: 8px; padding: 12px; margin-bottom: 12px;
  background: #fafafa;
}
.section-item-header {
  display: flex; align-items: center; gap: 8px; margin-bottom: 8px;
}
.section-index {
  display: inline-flex; align-items: center; justify-content: center;
  width: 24px; height: 24px; border-radius: 50%; background: #1890ff; color: #fff;
  font-size: 12px; font-weight: 600; flex-shrink: 0;
}
.section-title-input {
  flex: 1; border: none; border-bottom: 1px solid #d9d9d9; padding: 4px 2px;
  font-size: 14px; background: transparent; outline: none;
}
.section-title-input:focus { border-bottom-color: #1890ff; }

/* 小节操作按钮组 */
.section-actions { display: flex; gap: 4px; flex-shrink: 0; }
.btn-icon {
  width: 28px; height: 28px; border: 1px solid #d9d9d9; border-radius: 4px;
  background: #fff; cursor: pointer; font-size: 12px; display: flex;
  align-items: center; justify-content: center; color: #666;
}
.btn-icon:disabled { opacity: 0.3; cursor: not-allowed; }
.btn-icon.btn-danger { color: #ff4d4f; border-color: #ffccc7; }
.btn-icon.btn-danger:hover { background: #fff1f0; }

/* 小节视频设置区域 */
.section-video-settings { padding-left: 32px; }

/* v4.0: 开播时间设置 */
.open-time-setting {
  display: flex; align-items: center; gap: 8px; margin-bottom: 8px;
}
.open-time-label { font-size: 12px; color: #666; white-space: nowrap; }
.open-time-input {
  padding: 4px 8px; border: 1px solid #d9d9d9; border-radius: 4px;
  font-size: 12px; color: #333;
}
.open-time-input:focus { border-color: #1890ff; outline: none; }

/* 视频模式切换标签 */
.video-mode-tabs { display: flex; gap: 8px; margin-bottom: 8px; }
.tab {
  padding: 4px 12px; border: 1px solid #d9d9d9; border-radius: 4px; cursor: pointer;
  font-size: 12px; background: #fff; color: #666;
}
.tab.active { border-color: #1890ff; color: #1890ff; background: #e6f7ff; }

.video-mode-content { margin-top: 4px; }
.video-mode-content input {
  width: 100%; padding: 8px 10px; border: 1px solid #d9d9d9; border-radius: 4px;
  font-size: 13px; box-sizing: border-box;
}
.hint { font-size: 12px; color: #999; margin-top: 4px; }

/* 上传区域 */
.upload-area {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  border: 2px dashed #d9d9d9; border-radius: 8px; padding: 20px; cursor: pointer;
  color: #999; transition: border-color 0.2s;
}
.upload-area:hover { border-color: #1890ff; }
.upload-icon { font-size: 24px; margin-bottom: 4px; }

/* 上传进度条 */
.upload-progress { display: flex; align-items: center; gap: 10px; }
.progress-bar { flex: 1; height: 6px; background: #f0f0f0; border-radius: 3px; overflow: hidden; }
.progress-fill { height: 100%; background: #1890ff; border-radius: 3px; transition: width 0.3s; }

/* 已上传视频提示 */
.current-video { display: flex; align-items: center; gap: 10px; padding: 8px 12px; background: #f6ffed; border-radius: 4px; font-size: 12px; }
.btn-text { background: none; border: none; color: #1890ff; font-size: 12px; cursor: pointer; text-decoration: underline; }

/* 表单操作按钮 */
.form-actions { display: flex; gap: 10px; margin-top: 16px; align-items: center; }
.save-msg { font-size: 13px; animation: fadeIn 0.3s; }
.save-msg.success { color: #52c41a; }
.save-msg.error { color: #ff4d4f; }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

/* 通用按钮 */
.btn {
  padding: 8px 20px; border: 1px solid #d9d9d9; border-radius: 6px;
  background: #fff; font-size: 14px; cursor: pointer;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn.primary { background: #1890ff; color: #fff; border-color: #1890ff; }
.btn-sm { padding: 6px 14px; font-size: 13px; }

/* 返回导航 */
.back-nav { margin-bottom: 12px; }
.back-link { color: #1890ff; font-size: 14px; text-decoration: none; cursor: pointer; }
.back-link:hover { text-decoration: underline; }
</style>
