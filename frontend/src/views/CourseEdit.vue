<template>
  <div class="course-edit-page">
    <h2 class="page-title">{{ isEdit ? '编辑课程' : '创建课程' }}</h2>

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

      <!-- 视频设置：双模式 -->
      <div class="form-group">
        <label>课程视频</label>
        <div class="video-mode-tabs">
          <button :class="['tab', form.video_type === 'url' ? 'active' : '']" @click="form.video_type = 'url'">
            外部链接
          </button>
          <button :class="['tab', form.video_type === 'local' ? 'active' : '']" @click="form.video_type = 'local'">
            本地上传
          </button>
        </div>

        <!-- 外部链接模式 -->
        <div v-if="form.video_type === 'url'" class="video-mode-content">
          <input v-model="form.video_url" placeholder="粘贴视频播放页链接（如B站、腾讯视频等）" />
          <p class="hint">支持B站、腾讯视频、优酷等平台的播放页链接</p>
        </div>

        <!-- 本地上传模式 -->
        <div v-if="form.video_type === 'local'" class="video-mode-content">
          <div v-if="uploading" class="upload-progress">
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: uploadProgress + '%' }"></div>
            </div>
            <span>{{ uploadProgress }}%</span>
          </div>
          <div v-else-if="form.video_url && isEdit" class="current-video">
            <span>已上传: {{ form.video_url }}</span>
            <button class="btn-text" @click="form.video_url = ''">重新上传</button>
          </div>
          <label v-else class="upload-area">
            <input type="file" accept="video/mp4,video/webm,video/ogg,video/quicktime" @change="onFileSelect" hidden />
            <span class="upload-icon">+</span>
            <span>点击选择视频文件</span>
            <span class="hint">支持 MP4/WebM/OGG/MOV，最大 500MB</span>
          </label>
        </div>
      </div>

      <div class="form-actions">
        <button class="btn primary" @click="onSave" :disabled="saving">
          {{ saving ? '保存中...' : '保存' }}
        </button>
        <button class="btn" @click="$router.back()">取消</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../utils/api'

const route = useRoute()
const router = useRouter()
const courseId = computed(() => parseInt(route.params.courseId) || 0)
const isEdit = computed(() => courseId.value > 0)

const form = ref({
  title: '',
  description: '',
  video_type: 'url',
  video_url: '',
  require_minutes: 60,
  end_date: '',
  status: 'active',
})

const saving = ref(false)
const uploading = ref(false)
const uploadProgress = ref(0)

onMounted(async () => {
  if (isEdit.value) {
    try {
      const res = await api.get(`/courses/${courseId.value}`)
      if (res.data.code === 0) {
        const c = res.data.data
        form.value = {
          title: c.title,
          description: c.description,
          video_type: c.video_type || 'url',
          video_url: c.video_url || '',
          require_minutes: c.require_minutes,
          end_date: c.end_date ? c.end_date.split(' ')[0] : '',
          status: c.status,
        }
      }
    } catch (e) {
      console.error('获取课程失败:', e)
    }
  }
})

const onFileSelect = async (event) => {
  const file = event.target.files[0]
  if (!file) return

  // 检查大小
  if (file.size > 500 * 1024 * 1024) {
    alert('视频文件不能超过500MB')
    return
  }

  uploading.value = true
  uploadProgress.value = 0

  try {
    const formData = new FormData()
    formData.append('file', file)

    // 如果是新建课程，先创建课程再上传
    if (!isEdit.value) {
      // 先保存基本课程信息
      form.value.video_url = ''
      await onSave(true)
    }

    const res = await api.post(`/courses/${courseId.value}/upload-video`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => {
        uploadProgress.value = Math.round((e.loaded / e.total) * 100)
      },
    })

    if (res.data.code === 0) {
      form.value.video_type = 'local'
      form.value.video_url = res.data.data.video_url
      alert('视频上传成功')
    }
  } catch (e) {
    alert('上传失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    uploading.value = false
    uploadProgress.value = 0
  }
}

const onSave = async (silent = false) => {
  if (!form.value.title) {
    alert('请填写课程标题')
    return
  }

  saving.value = true
  try {
    const payload = {
      title: form.value.title,
      description: form.value.description,
      video_type: form.value.video_type,
      video_url: form.value.video_type === 'url' ? form.value.video_url : form.value.video_url,
      require_minutes: form.value.require_minutes,
      end_date: form.value.end_date || null,
    }

    if (isEdit.value) {
      await api.put(`/courses/${courseId.value}`, payload)
    } else {
      const res = await api.post('/courses', payload)
      if (res.data.code === 0 && !isEdit.value) {
        // 新建成功后跳转到编辑页，方便上传视频
        router.replace(`/course-edit/${res.data.data.id}`)
        return
      }
    }

    if (!silent) {
      alert('保存成功')
      router.back()
    }
  } catch (e) {
    alert('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.course-edit-page { padding: 16px; max-width: 640px; margin: 0 auto; }
.page-title { font-size: 20px; margin-bottom: 16px; }
.form-card { background: #fff; border-radius: 10px; padding: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
.form-group { margin-bottom: 16px; }
.form-group label { display: block; font-size: 14px; font-weight: 500; margin-bottom: 6px; color: #333; }
.required { color: #ff4d4f; }
.form-group input, .form-group textarea {
  width: 100%; padding: 10px 12px; border: 1px solid #d9d9d9; border-radius: 6px;
  font-size: 14px; box-sizing: border-box;
}
.form-group input:focus, .form-group textarea:focus { border-color: #1890ff; outline: none; }

.video-mode-tabs { display: flex; gap: 8px; margin-bottom: 8px; }
.tab {
  padding: 6px 16px; border: 1px solid #d9d9d9; border-radius: 6px; cursor: pointer;
  font-size: 13px; background: #fff; color: #666;
}
.tab.active { border-color: #1890ff; color: #1890ff; background: #e6f7ff; }

.video-mode-content { margin-top: 4px; }
.hint { font-size: 12px; color: #999; margin-top: 4px; }

.upload-area {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  border: 2px dashed #d9d9d9; border-radius: 8px; padding: 30px; cursor: pointer;
  color: #999; transition: border-color 0.2s;
}
.upload-area:hover { border-color: #1890ff; }
.upload-icon { font-size: 28px; margin-bottom: 6px; }

.upload-progress { display: flex; align-items: center; gap: 10px; }
.progress-bar { flex: 1; height: 8px; background: #f0f0f0; border-radius: 4px; overflow: hidden; }
.progress-fill { height: 100%; background: #1890ff; border-radius: 4px; transition: width 0.3s; }

.current-video { display: flex; align-items: center; gap: 10px; padding: 12px; background: #f6ffed; border-radius: 6px; font-size: 13px; }
.btn-text { background: none; border: none; color: #1890ff; font-size: 13px; cursor: pointer; text-decoration: underline; }

.form-actions { display: flex; gap: 10px; margin-top: 20px; }
.btn {
  padding: 10px 24px; border: 1px solid #d9d9d9; border-radius: 6px;
  background: #fff; font-size: 14px; cursor: pointer;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn.primary { background: #1890ff; color: #fff; border-color: #1890ff; }
</style>
