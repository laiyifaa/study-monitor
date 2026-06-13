<!--
  @模块：OpsPanel.vue — 运维监控面板
  @页面用途：展示系统实时运行状态，包括服务器资源、容器健康、业务数据、存储信息等。
            面向运维人员（ops）和管理员（admin），10秒自动刷新。
  @数据流：
    1. 组件挂载 → 调用 GET /ops/overview 获取全量数据
    2. 定时器每10秒刷新
    3. 告警项实时标红
  @依赖：
    - utils/api：封装了 axios 的请求工具
    - utils/auth：获取当前用户角色
-->
<template>
  <div class="ops-panel">
    <!-- 返回导航 -->
    <div class="back-nav-bar">
      <a href="javascript:void(0)" @click="$router.back()" class="back-link">&larr; 返回</a>
      <span class="page-title">运维监控面板</span>
      <span class="refresh-info">自动刷新: {{ countdown }}s</span>
    </div>

    <!-- ==================== 告警横幅 ==================== -->
    <div v-if="alerts.length > 0" class="alert-banner">
      <div class="alert-icon">!</div>
      <div class="alert-content">
        <div v-for="(a, i) in alerts" :key="i" class="alert-item">{{ a.message }}</div>
      </div>
    </div>

    <!-- ==================== 服务器资源 ==================== -->
    <div class="section-title">服务器资源</div>
    <div class="card-grid cols-4">
      <MetricCard label="CPU" :value="data.server.cpu_percent + '%'" :sub="data.server.cpu_count + ' 核'" :alert="data.server.cpu_alert" icon="cpu" />
      <MetricCard label="内存" :value="data.server.memory_percent + '%'" :sub="data.server.memory_used_human + ' / ' + data.server.memory_total_human" :alert="data.server.memory_alert" icon="mem" />
      <MetricCard label="磁盘读" :value="data.server.disk_io_read_mbs + ' MB/s'" sub="实时速率" icon="disk" />
      <MetricCard label="磁盘写" :value="data.server.disk_io_write_mbs + ' MB/s'" sub="实时速率" icon="disk" />
    </div>
    <div class="card-grid cols-4">
      <MetricCard label="上行带宽" :value="data.server.net_upload_mbps + ' Mbps'" sub="服务器出口" icon="net" />
      <MetricCard label="下行带宽" :value="data.server.net_download_mbps + ' Mbps'" sub="服务器入口" icon="net" />
      <MetricCard label="交换分区" :value="data.server.swap_percent + '%'" sub="Swap 使用率" icon="mem" />
      <div class="metric-card"><div class="mc-label">系统时间</div><div class="mc-value time">{{ currentTime }}</div></div>
    </div>

    <!-- ==================== Docker 容器 ==================== -->
    <div class="section-title">服务容器</div>
    <div class="container-grid">
      <div
        v-for="c in data.containers.containers"
        :key="c.name"
        class="container-card"
        :class="{ 'container-warning': c.state !== 'running' }"
      >
        <div class="cc-name">{{ formatContainerName(c.name) }}</div>
        <div class="cc-status">
          <span class="cc-dot" :class="c.state === 'running' ? 'dot-ok' : 'dot-err'"></span>
          {{ c.state }}
        </div>
        <div class="cc-image">{{ c.image }}</div>
        <div v-if="c.health" class="cc-health">健康: {{ c.health }}</div>
      </div>
    </div>

    <!-- ==================== 服务健康 ==================== -->
    <div class="section-title">服务健康</div>
    <div class="card-grid cols-3">
      <ServiceCard name="FastAPI" :status="data.services.api.status" :detail="'v' + data.services.api.version" />
      <ServiceCard name="Redis" :status="data.services.redis.status" :detail="data.services.redis.used_memory_human || ''" />
      <ServiceCard name="MySQL" :status="data.services.mysql.status" :detail="data.services.mysql.version || ''" />
    </div>
    <div class="card-grid cols-3" v-if="data.services.mysql.connections || data.services.redis.connected_clients">
      <MetricCard label="MySQL 连接数" :value="String(data.services.mysql.connections || 0)" icon="db" />
      <MetricCard label="Redis 客户端" :value="String(data.services.redis.connected_clients || 0)" icon="db" />
      <MetricCard label="MySQL 大小" :value="data.services.mysql.database_size_human || '0B'" icon="disk" />
    </div>

    <!-- ==================== 业务数据 ==================== -->
    <div class="section-title">业务数据</div>
    <div class="card-grid cols-4">
      <MetricCard label="在线教师" :value="String(data.business.online_teachers)" sub="近2分钟活跃" icon="user" />
      <MetricCard label="在线学生" :value="String(data.business.online_students)" sub="近2分钟活跃" icon="user" />
      <MetricCard label="活跃会话" :value="String(data.business.active_sessions)" sub="正在学习中" icon="play" />
      <MetricCard label="视频播放" :value="String(data.business.active_videos)" sub="正在播放视频" icon="video" />
    </div>
    <div class="card-grid cols-3">
      <MetricCard label="心跳 QPS" :value="String(data.business.heartbeat_qps)" sub="每秒心跳数" icon="pulse" />
      <MetricCard label="今日学习人次" :value="String(data.business.today_study_users)" icon="chart" />
      <MetricCard label="今日有效时长" :value="data.business.today_effective_minutes + ' 分钟'" icon="clock" />
    </div>

    <!-- ==================== 存储信息 ==================== -->
    <div class="section-title">存储信息</div>
    <div class="card-grid cols-4">
      <MetricCard label="视频文件" :value="data.storage.video_total_human" :sub="data.storage.video_count + ' 个文件'" icon="disk" />
      <MetricCard label="磁盘已用" :value="data.storage.disk_used_human" :sub="data.storage.disk_percent + '%'" :alert="data.storage.disk_alert" icon="disk" />
      <MetricCard label="磁盘剩余" :value="data.storage.disk_free_human" :sub="'总 ' + data.storage.disk_total_human" icon="disk" />
      <MetricCard label="MySQL 大小" :value="data.storage.mysql_size_human || '-'" icon="db" />
    </div>

    <!-- 磁盘使用率进度条 -->
    <div class="disk-bar">
      <div class="disk-bar-label">磁盘使用率</div>
      <div class="disk-bar-track">
        <div class="disk-bar-fill" :class="{ 'bar-warning': data.storage.disk_percent > 90 }" :style="{ width: data.storage.disk_percent + '%' }"></div>
      </div>
      <div class="disk-bar-text">{{ data.storage.disk_percent }}%</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed, h } from 'vue'
import api from '../utils/api'
import { getAuth } from '../utils/auth'

// ==================== 子组件 ====================

/**
 * 指标卡片 — 显示单个数值指标
 * Props: label, value, sub, alert('ok'/'warning'), icon
 */
const MetricCard = {
  props: { label: String, value: String, sub: String, alert: String, icon: String },
  setup(props) {
    return () => h('div', {
      class: ['metric-card', props.alert === 'warning' ? 'card-warning' : '']
    }, [
      h('div', { class: 'mc-label' }, props.label),
      h('div', { class: 'mc-value' }, props.value),
      props.sub ? h('div', { class: 'mc-sub' }, props.sub) : null,
    ])
  }
}

/**
 * 服务状态卡片 — 显示服务健康检查结果
 * Props: name, status('ok'/'error'), detail
 */
const ServiceCard = {
  props: { name: String, status: String, detail: String },
  setup(props) {
    return () => h('div', {
      class: ['metric-card', 'service-card', props.status !== 'ok' ? 'card-error' : '']
    }, [
      h('div', { class: 'mc-label' }, props.name),
      h('div', { class: 'mc-row' }, [
        h('span', { class: ['sc-dot', props.status === 'ok' ? 'dot-ok' : 'dot-err'] }),
        h('span', { class: 'sc-status' }, props.status === 'ok' ? '正常' : '异常'),
      ]),
      props.detail ? h('div', { class: 'mc-sub' }, props.detail) : null,
    ])
  }
}

// ==================== 数据与状态 ====================

// 全量数据默认值
const defaultData = {
  server: { cpu_percent: 0, cpu_count: 0, memory_total: 0, memory_total_human: '-', memory_used: 0, memory_used_human: '-', memory_percent: 0, swap_percent: 0, disk_io_read_mbs: 0, disk_io_write_mbs: 0, net_upload_mbps: 0, net_download_mbps: 0, cpu_alert: 'ok', memory_alert: 'ok' },
  containers: { containers: [], alerts: [] },
  services: { api: { status: 'error', version: '' }, redis: { status: 'error' }, mysql: { status: 'error' } },
  business: { online_teachers: 0, online_students: 0, active_sessions: 0, active_videos: 0, heartbeat_qps: 0, today_study_users: 0, today_effective_minutes: 0 },
  storage: { video_total_size: 0, video_total_human: '-', video_count: 0, disk_total: 0, disk_total_human: '-', disk_used: 0, disk_used_human: '-', disk_free: 0, disk_free_human: '-', disk_percent: 0, disk_alert: 'ok', mysql_size: 0, mysql_size_human: '-' },
  all_alerts: [],
  alert_count: 0,
  timestamp: '',
}

const data = ref(defaultData)
const countdown = ref(10)
const currentTime = ref('')
let timer = null
let countdownTimer = null

// 合并所有告警
const alerts = computed(() => data.value.all_alerts || [])

// ==================== 数据刷新 ====================

async function fetchData() {
  try {
    const res = await api.get('/ops/overview')
    if (res.data.code === 0) {
      data.value = res.data.data
    }
  } catch (e) {
    console.error('获取运维数据失败:', e)
  }
}

function updateTime() {
  currentTime.value = new Date().toLocaleString('zh-CN', { hour12: false })
}

function formatContainerName(name) {
  // 去掉 "study-monitor-" 前缀，使显示更简洁
  return name.replace(/^study-monitor-/, '')
}

// ==================== 生命周期 ====================

onMounted(() => {
  fetchData()
  updateTime()
  // 每10秒刷新数据
  timer = setInterval(() => {
    fetchData()
    countdown.value = 10
  }, 10000)
  // 倒计时 + 时钟
  countdownTimer = setInterval(() => {
    countdown.value = Math.max(0, countdown.value - 1)
    updateTime()
  }, 1000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  if (countdownTimer) clearInterval(countdownTimer)
})
</script>

<style scoped>
.ops-panel {
  min-height: 100vh;
  background: #f5f7fa;
  padding-bottom: 30px;
}

/* 返回导航栏 */
.back-nav-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; background: #fff; border-bottom: 1px solid #e8e8e8;
}
.page-title { font-size: 16px; font-weight: 600; color: #333; }
.refresh-info { font-size: 12px; color: #999; }
.back-link { color: #1890ff; font-size: 14px; text-decoration: none; cursor: pointer; }

/* 告警横幅 */
.alert-banner {
  display: flex; align-items: flex-start; gap: 10px;
  margin: 12px 16px; padding: 12px 16px;
  background: #fff2f0; border: 1px solid #ffccc7; border-radius: 8px;
}
.alert-icon {
  width: 24px; height: 24px; border-radius: 50%; background: #ff4d4f;
  color: #fff; display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 14px; flex-shrink: 0;
}
.alert-content { flex: 1; }
.alert-item { font-size: 13px; color: #cf1322; line-height: 1.8; }

/* 分区标题 */
.section-title {
  font-size: 14px; font-weight: 600; color: #666;
  margin: 16px 16px 8px; padding-left: 8px;
  border-left: 3px solid #1890ff;
}

/* 卡片网格 */
.card-grid { display: grid; gap: 8px; padding: 0 16px; margin-bottom: 8px; }
.cols-3 { grid-template-columns: repeat(3, 1fr); }
.cols-4 { grid-template-columns: repeat(4, 1fr); }

/* 指标卡片 */
.metric-card {
  background: #fff; border-radius: 8px; padding: 12px;
  border: 1px solid #f0f0f0;
  transition: border-color 0.3s;
}
.card-warning { border-color: #faad14; background: #fffbe6; }
.card-error { border-color: #ff4d4f; background: #fff2f0; }
.mc-label { font-size: 12px; color: #999; margin-bottom: 4px; }
.mc-value { font-size: 20px; font-weight: 700; color: #333; font-variant-numeric: tabular-nums; }
.mc-value.time { font-size: 15px; font-weight: 500; }
.mc-sub { font-size: 11px; color: #bbb; margin-top: 2px; }
.mc-row { display: flex; align-items: center; gap: 6px; }

/* 状态圆点 */
.dot-ok, .dot-err { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot-ok { background: #52c41a; }
.dot-err { background: #ff4d4f; }
.sc-status { font-size: 16px; font-weight: 600; }
.sc-dot { flex-shrink: 0; }

/* 容器卡片网格 */
.container-grid {
  display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; padding: 0 16px; margin-bottom: 8px;
}
.container-card {
  background: #fff; border-radius: 8px; padding: 12px;
  border: 1px solid #f0f0f0;
}
.container-warning { border-color: #ff4d4f; background: #fff2f0; }
.cc-name { font-size: 15px; font-weight: 600; color: #333; margin-bottom: 6px; }
.cc-status { display: flex; align-items: center; gap: 6px; font-size: 13px; color: #666; }
.cc-image { font-size: 11px; color: #bbb; margin-top: 4px; word-break: break-all; }
.cc-health { font-size: 11px; color: #52c41a; margin-top: 2px; }

/* 磁盘进度条 */
.disk-bar {
  display: flex; align-items: center; gap: 10px;
  padding: 0 16px; margin: 4px 0 16px;
}
.disk-bar-label { font-size: 12px; color: #999; white-space: nowrap; }
.disk-bar-track {
  flex: 1; height: 8px; background: #f0f0f0; border-radius: 4px; overflow: hidden;
}
.disk-bar-fill {
  height: 100%; background: linear-gradient(90deg, #1890ff, #52c41a);
  border-radius: 4px; transition: width 0.5s;
}
.bar-warning { background: linear-gradient(90deg, #faad14, #ff4d4f); }
.disk-bar-text { font-size: 13px; font-weight: 600; color: #333; min-width: 36px; }
</style>
