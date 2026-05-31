<!--
  @模块：CourseEdit.vue — 课程编辑页（新建/编辑双模式）
  @页面用途：教师创建新课程或编辑已有课程，支持双模式视频源（外部链接/本地上传）
  @数据流：
    1. 路由参数 courseId > 0 → 编辑模式，挂载时调用 GET /courses/:courseId 填充表单
    2. 路由参数 courseId = 0 → 新建模式，表单为空默认值
    3. 保存：
       - 编辑模式 → PUT /courses/:courseId 更新课程
       - 新建模式 → POST /courses 创建课程 → 跳转到编辑页（方便上传视频）
    4. 视频上传：
       - 新建课程时先自动保存课程再上传视频（POST /courses/:courseId/upload-video）
       - axios onUploadProgress 实时更新上传进度条
  @后端API：
    - GET /courses/:courseId：获取课程详情（编辑模式回填表单）
    - POST /courses：创建新课程
    - PUT /courses/:courseId：更新课程信息
    - POST /courses/:courseId/upload-video：上传视频文件（multipart/form-data）
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
    <!-- 页面标题：根据 isEdit 动态切换"编辑课程"/"创建课程" -->
    <h2 class="page-title">{{ isEdit ? '编辑课程' : '创建课程' }}</h2>

    <div class="form-card">
      <!-- 课程标题：必填项 -->
      <div class="form-group">
        <label>课程标题<span class="required">*</span></label>
        <input v-model="form.title" placeholder="如：高中数学必修一 - 集合与函数" />
      </div>

      <!-- 课程描述：选填 -->
      <div class="form-group">
        <label>课程描述</label>
        <textarea v-model="form.description" rows="3" placeholder="简述课程内容"></textarea>
      </div>

      <!-- 要求学习时长：数字输入，默认60分钟 -->
      <div class="form-group">
        <label>要求学习时长（分钟）</label>
        <input v-model.number="form.require_minutes" type="number" min="1" />
      </div>

      <!-- 截止日期：日期选择器 -->
      <div class="form-group">
        <label>截止日期</label>
        <input v-model="form.end_date" type="date" />
      </div>

      <!-- ==================== 视频设置：双模式切换 ==================== -->
      <div class="form-group">
        <label>课程视频</label>
        <!-- 模式切换标签页：点击切换 form.video_type -->
        <div class="video-mode-tabs">
          <button :class="['tab', form.video_type === 'url' ? 'active' : '']" @click="form.video_type = 'url'">
            外部链接
          </button>
          <button :class="['tab', form.video_type === 'local' ? 'active' : '']" @click="form.video_type = 'local'">
            本地上传
          </button>
        </div>

        <!-- 外部链接模式：粘贴视频播放页 URL -->
        <div v-if="form.video_type === 'url'" class="video-mode-content">
          <input v-model="form.video_url" placeholder="粘贴视频播放页链接（如B站、腾讯视频等）" />
          <p class="hint">支持B站、腾讯视频、优酷等平台的播放页链接</p>
        </div>

        <!-- 本地上传模式：文件选择 + 上传进度 + 已上传状态 -->
        <div v-if="form.video_type === 'local'" class="video-mode-content">
          <!-- 上传中：显示进度条 -->
          <div v-if="uploading" class="upload-progress">
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: uploadProgress + '%' }"></div>
            </div>
            <span>{{ uploadProgress }}%</span>
          </div>
          <!-- 编辑模式下已有本地视频：显示文件名和"重新上传"按钮 -->
          <!-- 条件：video_url 非空 + 编辑模式 + video_url 看起来是本地文件（非 http 开头） -->
          <div v-else-if="form.video_url && isEdit && isLocalVideo" class="current-video">
            <span>已上传: {{ form.video_url }}</span>
            <!-- 点击重新上传：清空 video_url 触发显示上传区域 -->
            <button class="btn-text" @click="form.video_url = ''">重新上传</button>
          </div>
          <!-- 无视频/新建模式：显示上传区域 -->
          <!-- 用 div + ref 触发文件选择，避免 label+hidden 在部分浏览器不弹出文件对话框 -->
          <div v-else class="upload-area" @click="triggerFileSelect">
            <input ref="fileInput" type="file" accept="video/mp4,video/webm,video/ogg,video/quicktime" @change="onFileSelect" style="display:none" />
            <span class="upload-icon">+</span>
            <span>点击选择视频文件</span>
            <span class="hint">支持 MP4/WebM/OGG/MOV，最大 500MB</span>
          </div>
        </div>
      </div>

      <!-- ==================== 表单操作按钮 ==================== -->
      <div class="form-actions">
        <!-- 保存按钮：保存中时禁用防止重复提交 -->
        <button class="btn primary" @click="onSave()" :disabled="saving">
          {{ saving ? '保存中...' : '保存' }}
        </button>
        <!-- 保存成功/失败的即时反馈 -->
        <span v-if="saveMsg" class="save-msg" :class="saveMsgType">{{ saveMsg }}</span>
        <!-- 取消按钮：返回上一页 -->
        <button class="btn" @click="$router.back()">取消</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../utils/api'

/** 路由实例 */
const route = useRoute()
/** 路由导航实例 */
const router = useRouter()

/** 课程ID：从路由参数获取，0 表示新建模式 */
const courseId = computed(() => parseInt(route.params.courseId) || 0)

/** 是否为编辑模式：courseId > 0 即为编辑已有课程 */
const isEdit = computed(() => courseId.value > 0)

/**
 * 当前的 video_url 是否是本地视频文件（而非外部链接）
 * 判断依据：本地文件名不以 http 开头（如 "3_a1b2c3d4.mp4"）
 * 外部链接以 http/https 开头（如 "https://www.bilibili.com/..."）
 */
const isLocalVideo = computed(() => {
  return form.value.video_url && !form.value.video_url.startsWith('http')
})

/** 表单数据对象，包含课程的所有可编辑字段 */
const form = ref({
  title: '',
  description: '',
  video_type: 'url',      // 视频类型：'url'（外部链接）或 'local'（本地上传）
  video_url: '',           // 视频地址：url模式为链接，local模式为服务器文件名
  require_minutes: 60,     // 默认要求学习60分钟
  end_date: '',
  status: 'active',        // 课程状态，新建默认活跃
})

/** 保存中状态标识，防止重复提交 */
const saving = ref(false)

/** 视频上传中状态标识 */
const uploading = ref(false)

/** 视频上传进度百分比（0-100） */
const uploadProgress = ref(0)

/** 文件输入框的模板引用，用于 ref 方式触发文件选择对话框 */
const fileInput = ref(null)

/** 保存反馈消息 */
const saveMsg = ref('')
/** 反馈消息类型：success / error */
const saveMsgType = ref('success')

/**
 * 组件挂载：编辑模式下回填课程数据
 * 流程：获取课程详情 → 将后端字段映射到表单 → 日期字段只取日期部分（去掉时分秒）
 */
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

/**
 * 通过 ref 触发文件选择对话框
 * 替代 <label> + hidden <input> 方案：
 * - hidden 属性在部分浏览器（尤其是移动端 WebView）会阻止文件对话框弹出
 * - 使用 ref + click() 方式在所有浏览器中表现一致
 */
function triggerFileSelect() {
  fileInput.value?.click()
}

/**
 * 视频文件选择处理
 * 流程：
 *   1. 校验文件大小（不超过500MB）
 *   2. 新建模式下先自动保存课程（获取 courseId）
 *   3. 上传视频文件，实时更新进度条
 *   4. 上传成功后更新表单的 video_type 和 video_url
 *
 * @param {Event} event - 文件选择事件
 */
const onFileSelect = async (event) => {
  const file = event.target.files?.[0]
  if (!file) return

  // 检查文件大小上限 500MB
  if (file.size > 500 * 1024 * 1024) {
    alert('视频文件不能超过500MB')
    // 清空 input 值，允许重新选择同一文件
    event.target.value = ''
    return
  }

  uploading.value = true
  uploadProgress.value = 0

  try {
    const formData = new FormData()
    formData.append('file', file)

    // 新建课程时：必须先保存课程获取ID，再上传视频
    if (!isEdit.value) {
      form.value.video_url = ''
      await onSave(true)  // silent=true 静默保存，不弹提示
    }

    // 上传视频文件到服务器，携带 onUploadProgress 回调更新进度条
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
    // 清空 input 值，允许用户再次选择同一文件
    if (fileInput.value) fileInput.value.value = ''
  }
}

/**
 * 保存课程（新建或更新）
 * 流程：
 *   1. 校验标题必填
 *   2. 构建 payload 发送请求
 *   3. 新建成功后跳转到编辑页（方便继续上传视频）
 *   4. 编辑成功后返回上一页
 *
 * @param {boolean} silent - 静默模式，不弹提示不跳转（用于视频上传前的自动保存）
 */
const onSave = async (silent = false) => {
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
      video_type: form.value.video_type,
      video_url: form.value.video_type === 'url' ? form.value.video_url : form.value.video_url,
      require_minutes: form.value.require_minutes,
      end_date: form.value.end_date || null,
    }

    if (isEdit.value) {
      // 编辑模式：PUT 更新已有课程
      const res = await api.put(`/courses/${courseId.value}`, payload)
      if (res.data.code === 0) {
        if (!silent) {
          // 内联成功提示，3秒后自动消失，不跳走（用户可能还要继续编辑）
          saveMsg.value = '保存成功'
          saveMsgType.value = 'success'
          setTimeout(() => { saveMsg.value = '' }, 3000)
        }
      } else {
        if (!silent) {
          saveMsg.value = res.data.msg || '保存失败'
          saveMsgType.value = 'error'
        }
      }
    } else {
      // 新建模式：POST 创建课程
      const res = await api.post('/courses', payload)
      if (res.data.code === 0) {
        // 新建成功后跳转到编辑页，方便上传视频
        router.replace(`/course-edit/${res.data.data.id}`)
        return
      } else {
        saveMsg.value = res.data.msg || '创建失败'
        saveMsgType.value = 'error'
      }
    }
  } catch (e) {
    if (!silent) {
      saveMsg.value = '保存失败: ' + (e.response?.data?.detail || e.message)
      saveMsgType.value = 'error'
    }
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
/* 页面整体：左右留内边距，最大宽度640px居中（表单页不适合太宽） */
.course-edit-page { padding: 16px; max-width: 640px; margin: 0 auto; }
.page-title { font-size: 20px; margin-bottom: 16px; }

/* 表单卡片容器 */
.form-card { background: #fff; border-radius: 10px; padding: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }

/* 表单行间距 */
.form-group { margin-bottom: 16px; }
.form-group label { display: block; font-size: 14px; font-weight: 500; margin-bottom: 6px; color: #333; }

/* 必填标识：红色星号 */
.required { color: #ff4d4f; }

/* 输入框统一样式 */
.form-group input, .form-group textarea {
  width: 100%; padding: 10px 12px; border: 1px solid #d9d9d9; border-radius: 6px;
  font-size: 14px; box-sizing: border-box;
}
/* 输入框聚焦：蓝色边框高亮 */
.form-group input:focus, .form-group textarea:focus { border-color: #1890ff; outline: none; }

/* 视频模式切换标签页 */
.video-mode-tabs { display: flex; gap: 8px; margin-bottom: 8px; }
.tab {
  padding: 6px 16px; border: 1px solid #d9d9d9; border-radius: 6px; cursor: pointer;
  font-size: 13px; background: #fff; color: #666;
}
/* 激活态标签：蓝色边框+浅蓝背景 */
.tab.active { border-color: #1890ff; color: #1890ff; background: #e6f7ff; }

.video-mode-content { margin-top: 4px; }
.hint { font-size: 12px; color: #999; margin-top: 4px; }

/* 上传区域：虚线边框，hover时蓝色高亮，引导用户点击选择文件 */
.upload-area {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  border: 2px dashed #d9d9d9; border-radius: 8px; padding: 30px; cursor: pointer;
  color: #999; transition: border-color 0.2s;
}
.upload-area:hover { border-color: #1890ff; }
.upload-icon { font-size: 28px; margin-bottom: 6px; }

/* 上传进度条 */
.upload-progress { display: flex; align-items: center; gap: 10px; }
.progress-bar { flex: 1; height: 8px; background: #f0f0f0; border-radius: 4px; overflow: hidden; }
.progress-fill { height: 100%; background: #1890ff; border-radius: 4px; transition: width 0.3s; }

/* 已上传视频提示：浅绿背景 */
.current-video { display: flex; align-items: center; gap: 10px; padding: 12px; background: #f6ffed; border-radius: 6px; font-size: 13px; }
.btn-text { background: none; border: none; color: #1890ff; font-size: 13px; cursor: pointer; text-decoration: underline; }

/* 表单操作按钮区域 */
.form-actions { display: flex; gap: 10px; margin-top: 20px; align-items: center; }

/* 保存反馈消息 */
.save-msg { font-size: 13px; animation: fadeIn 0.3s; }
.save-msg.success { color: #52c41a; }
.save-msg.error { color: #ff4d4f; }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

/* 通用按钮样式 */
.btn {
  padding: 10px 24px; border: 1px solid #d9d9d9; border-radius: 6px;
  background: #fff; font-size: 14px; cursor: pointer;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn.primary { background: #1890ff; color: #fff; border-color: #1890ff; }

/* 返回导航 */
.back-nav { margin-bottom: 12px; }
.back-link { color: #1890ff; font-size: 14px; text-decoration: none; cursor: pointer; }
.back-link:hover { text-decoration: underline; }
</style>
