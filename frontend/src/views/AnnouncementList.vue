<!--
  @模块：AnnouncementList.vue — 通知公告列表（v4.0 新增）
  @页面用途：学生/教师/管理员查看公告通知，按时间倒序展示
-->
<template>
  <div class="announcement-page">
    <div class="back-nav">
      <a href="javascript:void(0)" @click="$router.back()" class="back-link">&larr; 返回</a>
    </div>
    <div class="page-header">
      <h2>通知公告</h2>
      <router-link v-if="isTeacherOrAdmin" to="/announcement-create" class="btn primary btn-sm">发布公告</router-link>
    </div>

    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="list.length === 0" class="empty">暂无公告</div>
    <div v-else class="announcement-list">
      <div v-for="a in list" :key="a.id" class="announcement-card" @click="viewDetail(a)">
        <div class="ac-header">
          <span v-if="a.priority === 'urgent'" class="priority-tag urgent">紧急</span>
          <span v-else-if="a.priority === 'important'" class="priority-tag important">重要</span>
          <span class="ac-title">{{ a.title }}</span>
        </div>
        <div class="ac-meta">
          <span v-if="a.course_id" class="ac-course">课程公告</span>
          <span v-else class="ac-global">全平台公告</span>
          <span v-if="a.popup" class="popup-tag">强制弹窗</span>
          <span>{{ a.created_by_name }}</span>
          <span>{{ formatTime(a.created_at) }}</span>
        </div>
        <div class="ac-content">{{ a.content.slice(0, 100) }}{{ a.content.length > 100 ? '...' : '' }}</div>
        <div v-if="a.image_urls && a.image_urls.length > 0" class="ac-images">
          <img v-for="(url, idx) in a.image_urls.slice(0, 3)" :key="idx" :src="getImageUrl(url)" class="ac-thumb" />
          <span v-if="a.image_urls.length > 3" class="ac-more-images">+{{ a.image_urls.length - 3 }}</span>
        </div>
      </div>
    </div>

    <!-- 公告详情弹窗 -->
    <div v-if="detailVisible" class="modal-overlay" @click.self="detailVisible = false">
      <div class="modal-card">
        <div class="modal-header">
          <h3>{{ detailData.title }}</h3>
          <span v-if="detailData.priority === 'urgent'" class="priority-tag urgent">紧急</span>
          <span v-else-if="detailData.priority === 'important'" class="priority-tag important">重要</span>
        </div>
        <div class="modal-meta">
          <span>{{ detailData.created_by_name }}</span>
          <span>{{ formatTime(detailData.created_at) }}</span>
        </div>
        <div class="modal-body">
          <div v-if="detailData.content" class="modal-text">{{ detailData.content }}</div>
          <div v-if="detailData.image_urls && detailData.image_urls.length > 0" class="modal-images">
            <img v-for="(url, idx) in detailData.image_urls" :key="idx" :src="getImageUrl(url)" class="modal-image" />
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn-sm" @click="detailVisible = false">关闭</button>
          <button v-if="isTeacherOrAdmin" class="btn-sm danger" @click="deleteAnnouncement(detailData.id)">删除</button>
        </div>
      </div>
    </div>

    <!-- 自定义确认弹窗（替代原生 confirm，兼容钉钉 WebView）-->
    <div v-if="confirmVisible" class="modal-overlay confirm-overlay" @click.self="confirmCancel">
      <div class="modal-card" style="max-width: 360px; text-align: center;">
        <div style="font-size: 15px; margin-bottom: 20px;">{{ confirmMsg }}</div>
        <div class="modal-actions" style="justify-content: center;">
          <button class="btn-sm" @click="confirmCancel">取消</button>
          <button class="btn-sm danger" @click="confirmOk">确定</button>
        </div>
      </div>
    </div>

    <!-- 自定义提示弹窗（替代原生 alert，兼容钉钉 WebView）-->
    <div v-if="toastVisible" class="modal-overlay confirm-overlay" @click.self="toastVisible = false">
      <div class="modal-card" style="max-width: 360px; text-align: center;">
        <div style="font-size: 15px; margin-bottom: 20px;">{{ toastMsg }}</div>
        <div class="modal-actions" style="justify-content: center;">
          <button class="btn-sm primary" @click="toastVisible = false">知道了</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../utils/api'
import { useAuthStore } from '../utils/auth'
import { getMediaUrl } from '../utils/homeworkFiles'

const auth = useAuthStore()
const isTeacherOrAdmin = computed(() => ['teacher', 'admin'].includes(auth.user.value?.role))

function getImageUrl(url) {
  return getMediaUrl(url)
}

const list = ref([])
const loading = ref(true)
const detailVisible = ref(false)
const detailData = ref({})

// 自定义确认弹窗状态（替代原生 confirm，兼容钉钉 WebView）
const confirmVisible = ref(false)
const confirmMsg = ref('')
let confirmResolver = null

function showConfirm(msg) {
  return new Promise(resolve => {
    confirmMsg.value = msg
    confirmVisible.value = true
    confirmResolver = resolve
  })
}

function confirmOk() {
  confirmVisible.value = false
  if (confirmResolver) confirmResolver(true)
  confirmResolver = null
}

function confirmCancel() {
  confirmVisible.value = false
  if (confirmResolver) confirmResolver(false)
  confirmResolver = null
}

// 自定义提示弹窗状态（替代原生 alert，兼容钉钉 WebView）
const toastVisible = ref(false)
const toastMsg = ref('')

function showToast(msg) {
  toastMsg.value = msg
  toastVisible.value = true
  // 3秒后自动关闭
  setTimeout(() => { toastVisible.value = false }, 3000)
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}

function viewDetail(a) {
  detailData.value = a
  detailVisible.value = true
}

async function deleteAnnouncement(id) {
  // 先关闭详情弹窗，避免确认弹窗被遮挡
  const wasDetailOpen = detailVisible.value
  detailVisible.value = false

  if (!(await showConfirm('确定删除该公告？'))) {
    // 取消删除，恢复详情弹窗
    if (wasDetailOpen) detailVisible.value = true
    return
  }
  try {
    await api.delete(`/announcements/${id}`)
    list.value = list.value.filter(a => a.id !== id)
    showToast('删除成功')
  } catch (e) {
    showToast('删除失败: ' + (e.response?.data?.detail || e.message))
    // 删除失败也恢复详情弹窗
    if (wasDetailOpen) detailVisible.value = true
  }
}

onMounted(async () => {
  try {
    const res = await api.get('/announcements')
    if (res.data.code === 0) list.value = res.data.data
    // 打开公告页即标记全部已读，使红点消失
    api.post('/announcements/mark-all-read').catch(() => {})
  } catch (e) {
    console.error('获取公告失败:', e)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.announcement-page { padding: 16px; max-width: 768px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { font-size: 20px; }
.back-nav { margin-bottom: 12px; }
.back-link { color: #1890ff; font-size: 14px; text-decoration: none; cursor: pointer; }
.loading, .empty { text-align: center; padding: 40px; color: #999; }

.announcement-card {
  background: #fff; border-radius: 8px; padding: 14px; margin-bottom: 10px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06); cursor: pointer;
}
.announcement-card:active { background: #f9f9f9; }

.ac-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.ac-title { font-size: 15px; font-weight: 500; }

.priority-tag { font-size: 11px; padding: 1px 6px; border-radius: 4px; font-weight: 500; }
.priority-tag.urgent { background: #fff1f0; color: #ff4d4f; }
.priority-tag.important { background: #fff7e6; color: #fa8c16; }

.ac-meta { font-size: 12px; color: #999; display: flex; gap: 10px; margin-bottom: 6px; flex-wrap: wrap; }
.ac-course { color: #1890ff; }
.ac-global { color: #52c41a; }
.popup-tag { color: #fa8c16; background: #fff7e6; padding: 0 4px; border-radius: 3px; font-size: 11px; }
.ac-content { font-size: 13px; color: #666; line-height: 1.5; }
.ac-images { display: flex; gap: 6px; margin-top: 8px; align-items: center; }
.ac-thumb { width: 48px; height: 48px; object-fit: cover; border-radius: 4px; border: 1px solid #e8e8e8; }
.ac-more-images { font-size: 12px; color: #999; }

.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 200; }
.confirm-overlay { z-index: 300; }
.modal-card { background: #fff; border-radius: 12px; padding: 24px; width: 90%; max-width: 500px; max-height: 80vh; overflow-y: auto; }
.modal-header { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.modal-header h3 { font-size: 17px; }
.modal-meta { font-size: 12px; color: #999; display: flex; gap: 10px; margin-bottom: 14px; }
.modal-body { font-size: 14px; line-height: 1.8; }
.modal-text { white-space: pre-wrap; margin-bottom: 12px; }
.modal-images { display: flex; flex-direction: column; gap: 10px; }
.modal-image { width: 100%; border-radius: 6px; }
.modal-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 16px; }

.btn-sm { padding: 6px 16px; border: 1px solid #d9d9d9; border-radius: 4px; background: #fff; font-size: 13px; cursor: pointer; }
.btn-sm.primary { background: #1890ff; color: #fff; border-color: #1890ff; }
.btn-sm.danger { color: #ff4d4f; border-color: #ffccc7; }
.btn.primary { background: #1890ff; color: #fff; border-color: #1890ff; }
.btn { padding: 6px 16px; border: 1px solid #d9d9d9; border-radius: 6px; background: #fff; font-size: 13px; cursor: pointer; text-decoration: none; display: inline-block; }
</style>
