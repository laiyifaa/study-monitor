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
-->
<template>
  <div class="ops-panel">
    <!-- ====== 顶部状态栏 ====== -->
    <div class="ops-header">
      <div class="oh-left">
        <button class="oh-back" @click="$router.back()">&larr; 返回</button>
        <span class="oh-badge" :class="alerts.length > 0 ? 'badge-err' : 'badge-ok'">
          {{ alerts.length > 0 ? alerts.length + ' 告警' : '全部正常' }}
        </span>
      </div>
      <div class="oh-right">
        <span class="oh-time">{{ currentTime }}</span>
        <button class="oh-refresh" @click="manualRefresh" :class="{ spinning: refreshing }" title="手动刷新">&#8635;</button>
      </div>
    </div>

    <!-- ====== 告警横幅 ====== -->
    <div v-if="alerts.length > 0" class="alert-banner">
      <div class="ab-icon">&#9888;</div>
      <div class="ab-list">
        <div v-for="(a, i) in alerts" :key="i" class="ab-item">{{ a.message }}</div>
      </div>
    </div>

    <!-- ====== 服务器资源 — 环形进度条 ====== -->
    <div class="section">
      <div class="sec-head"><span class="sec-icon">&#9881;</span> 服务器资源</div>
      <div class="ring-row">
        <RingGauge label="CPU" :percent="data.server.cpu_percent" :alert="data.server.cpu_alert === 'warning'" :info="data.server.cpu_count + ' 核'" color="#1890ff" />
        <RingGauge label="内存" :percent="data.server.memory_percent" :alert="data.server.memory_alert === 'warning'" :info="data.server.memory_used_human + ' / ' + data.server.memory_total_human" color="#722ed1" />
        <RingGauge label="交换分区" :percent="data.server.swap_percent" :alert="data.server.swap_percent > 90" :info="'Swap'" color="#fa8c16" />
      </div>
      <div class="mini-card-row">
        <MiniCard emoji="&#8593;" label="上行" :value="data.server.net_upload_mbps" unit="Mbps" :max="480" />
        <MiniCard emoji="&#8595;" label="下行" :value="data.server.net_download_mbps" unit="Mbps" :max="400" />
        <MiniCard emoji="&#8592;" label="磁盘读" :value="data.server.disk_io_read_mbs" unit="MB/s" :max="170" />
        <MiniCard emoji="&#8594;" label="磁盘写" :value="data.server.disk_io_write_mbs" unit="MB/s" :max="70" />
      </div>
    </div>

    <!-- ====== 服务容器 ====== -->
    <div class="section">
      <div class="sec-head"><span class="sec-icon">&#9783;</span> 服务容器</div>
      <div class="container-grid">
        <div
          v-for="c in data.containers.containers"
          :key="c.name"
          class="ctr-card"
          :class="{ 'ctr-ok': c.state === 'running', 'ctr-err': c.state !== 'running' }"
        >
          <div class="ctr-top">
            <span class="ctr-dot" :class="c.state === 'running' ? 'dot-g' : 'dot-r'"></span>
            <span class="ctr-name">{{ formatContainerName(c.name) }}</span>
          </div>
          <div class="ctr-status">{{ c.status }}</div>
          <div class="ctr-img">{{ c.image }}</div>
          <div v-if="c.ports" class="ctr-ports">&#127760; {{ c.ports }}</div>
        </div>
      </div>
    </div>

    <!-- ====== 服务健康 ====== -->
    <div class="section">
      <div class="sec-head"><span class="sec-icon">&#9733;</span> 服务健康</div>
      <div class="svc-row">
        <SvcCard name="FastAPI" :ok="data.services.api.status === 'ok'" :detail="data.services.api.version ? 'v' + data.services.api.version : '-'" />
        <SvcCard name="Redis" :ok="data.services.redis.status === 'ok'" :detail="data.services.redis.used_memory_human || '-'" />
        <SvcCard name="MySQL" :ok="data.services.mysql.status === 'ok'" :detail="data.services.mysql.version || '-'" />
      </div>
      <div class="svc-detail-row">
        <div class="svc-detail">MySQL {{ data.services.mysql.connections || 0 }} 连接 &middot; {{ data.services.mysql.database_size_human || '0B' }}</div>
        <div class="svc-detail">Redis {{ data.services.redis.connected_clients || 0 }} 客户端</div>
      </div>
    </div>

    <!-- ====== 业务数据 ====== -->
    <div class="section">
      <div class="sec-head"><span class="sec-icon">&#9782;</span> 业务数据</div>
      <div class="biz-card-row">
        <BizCard label="在线教师" :value="data.business.online_teachers" color="#52c41a" icon="&#128100;" />
        <BizCard label="在线学生" :value="data.business.online_students" color="#1890ff" icon="&#128101;" />
        <BizCard label="活跃会话" :value="data.business.active_sessions" color="#722ed1" icon="&#9654;" />
        <BizCard label="视频播放" :value="data.business.active_videos" color="#fa8c16" icon="&#127909;" />
      </div>
      <div class="biz-card-row">
        <BizCard label="心跳QPS" :value="data.business.heartbeat_qps" color="#13c2c2" icon="&#9829;" unit="/s" />
        <BizCard label="今日学习人次" :value="data.business.today_study_users" color="#eb2f96" icon="&#128200;" />
        <BizCard label="今日有效时长" :value="data.business.today_effective_minutes" color="#2f54eb" icon="&#9202;" unit="min" />
      </div>
    </div>

    <!-- ====== 存储信息 ====== -->
    <div class="section">
      <div class="sec-head"><span class="sec-icon">&#128190;</span> 存储信息</div>
      <div class="storage-row">
        <div class="sto-card">
          <div class="sto-label">视频文件</div>
          <div class="sto-value">{{ data.storage.video_total_human }}</div>
          <div class="sto-sub">{{ data.storage.video_count }} 个文件</div>
        </div>
        <div class="sto-card">
          <div class="sto-label">MySQL</div>
          <div class="sto-value">{{ data.storage.mysql_size_human || '-' }}</div>
          <div class="sto-sub">数据库大小</div>
        </div>
      </div>
      <!-- 磁盘使用率进度条 -->
      <div class="disk-section">
        <div class="disk-header">
          <span>磁盘使用率</span>
          <span class="disk-pct" :class="{ 'pct-warn': data.storage.disk_percent > 90 }">{{ data.storage.disk_percent }}%</span>
        </div>
        <div class="disk-track">
          <div class="disk-fill" :class="{ 'fill-warn': data.storage.disk_percent > 90 }" :style="{ width: data.storage.disk_percent + '%' }"></div>
        </div>
        <div class="disk-info">
          已用 {{ data.storage.disk_used_human }} / 总共 {{ data.storage.disk_total_human }} &middot; 剩余 {{ data.storage.disk_free_human }}
        </div>
      </div>
    </div>

    <!-- 底部刷新提示 -->
    <div class="ops-footer">每 5 秒自动刷新 &middot; 上次更新 {{ lastUpdateTime }}</div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed, h } from 'vue'
import api from '../utils/api'

// ==================== 子组件 ====================

/** 环形进度条 — 用于 CPU/内存等百分比指标 */
const RingGauge = {
  props: {
    label: String,
    percent: Number,
    alert: Boolean,
    info: String,
    color: { type: String, default: '#1890ff' }
  },
  setup(props) {
    return () => {
      const r = 36
      const c = 2 * Math.PI * r
      const offset = c - (Math.min(props.percent, 100) / 100) * c
      const strokeColor = props.alert ? '#ff4d4f' : props.color
      return h('div', { class: 'ring-wrap' }, [
        h('div', { class: 'ring-box' }, [
          h('svg', { viewBox: '0 0 80 80', class: 'ring-svg' }, [
            h('circle', { cx: 40, cy: 40, r, fill: 'none', stroke: '#f0f0f0', 'stroke-width': 6 }),
            h('circle', {
              cx: 40, cy: 40, r, fill: 'none', stroke: strokeColor, 'stroke-width': 6,
              'stroke-linecap': 'round', 'stroke-dasharray': c, 'stroke-dashoffset': offset,
              transform: 'rotate(-90 40 40)', class: 'ring-arc'
            })
          ]),
          h('div', { class: 'ring-inner' }, [
            h('div', { class: 'ring-pct', style: { color: strokeColor } }, Math.round(props.percent) + '%'),
          ])
        ]),
        h('div', { class: 'ring-label' }, props.label),
        props.info ? h('div', { class: 'ring-info' }, props.info) : null,
        props.alert ? h('div', { class: 'ring-alert' }, '⚠ 超阈值') : null,
      ])
    }
  }
}

/** 迷你数据卡片 — 带彩色进度条（有 max 时启用） */
const MiniCard = {
  props: {
    emoji: String,
    label: String,
    value: [Number, String],
    unit: String,
    max: { type: Number, default: 0 },   // 0 = 无进度条
  },
  setup(props) {
    return () => {
      const numVal = typeof props.value === 'number' ? props.value : 0
      // 有 max 时算比率与颜色
      const hasMax = props.max > 0
      const ratio = hasMax ? Math.min(numVal / props.max, 1.5) : 0   // 上限1.5避免溢出
      const pct = Math.min(ratio * 100, 100)                          // 进度条宽度封顶100%
      let barColor = '#52c41a'                                         // 绿色：正常
      let valColor = '#333'
      if (hasMax) {
        if (numVal > props.max) { barColor = '#ff4d4f'; valColor = '#ff4d4f' }        // 红：超限
        else if (numVal > props.max * 0.8) { barColor = '#faad14'; valColor = '#d48806' } // 黄：接近
      }

      return h('div', { class: 'mini-card' }, [
        h('div', { class: 'mc-top' }, [
          h('span', { class: 'mc-emoji' }, props.emoji),
          h('span', { class: 'mc-label' }, props.label),
        ]),
        h('div', { class: 'mc-body' }, [
          h('span', { class: 'mc-val', style: { color: valColor } }, numVal.toFixed(2)),
          h('span', { class: 'mc-slash' }, '/'),
          h('span', { class: 'mc-max' }, props.max),
          h('span', { class: 'mc-unit' }, ' ' + props.unit),
        ]),
        hasMax
          ? h('div', { class: 'mc-bar-track' }, [
              h('div', {
                class: 'mc-bar-fill',
                style: { width: pct + '%', background: barColor },
              }),
            ])
          : null,
      ])
    }
  }
}

/** 服务健康卡片 */
const SvcCard = {
  props: { name: String, ok: Boolean, detail: String },
  setup(props) {
    return () => h('div', { class: ['svc-card', props.ok ? 'svc-ok' : 'svc-fail'] }, [
      h('div', { class: 'svc-dot' }, props.ok ? '✓' : '✗'),
      h('div', { class: 'svc-name' }, props.name),
      h('div', { class: 'svc-detail' }, props.detail),
    ])
  }
}

/** 业务数据卡片 */
const BizCard = {
  props: { label: String, value: [Number, String], unit: String, color: String, icon: String },
  setup(props) {
    return () => h('div', { class: 'biz-card' }, [
      h('div', { class: 'bc-icon', style: { background: props.color + '15', color: props.color } }, props.icon),
      h('div', { class: 'bc-body' }, [
        h('div', { class: 'bc-val', style: { color: props.color } }, props.value + (props.unit || '')),
        h('div', { class: 'bc-label' }, props.label),
      ]),
    ])
  }
}

// ==================== 数据与状态 ====================

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
const currentTime = ref('')
const lastUpdateTime = ref('-')
const refreshing = ref(false)
let timer = null
let clockTimer = null

const alerts = computed(() => data.value.all_alerts || [])

// ==================== 数据刷新 ====================

async function fetchData() {
  try {
    const res = await api.get('/ops/overview')
    if (res.data.code === 0) {
      data.value = res.data.data
      lastUpdateTime.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    }
  } catch (e) {
    console.error('获取运维数据失败:', e)
  }
}

async function manualRefresh() {
  if (refreshing.value) return
  refreshing.value = true
  await fetchData()
  setTimeout(() => { refreshing.value = false }, 600)
}

function updateTime() {
  currentTime.value = new Date().toLocaleString('zh-CN', { hour12: false })
}

function formatContainerName(name) {
  return name.replace(/^study-monitor-/, '')
}

// ==================== 生命周期 ====================

onMounted(() => {
  fetchData()
  updateTime()
  timer = setInterval(fetchData, 5000)
  clockTimer = setInterval(updateTime, 1000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  if (clockTimer) clearInterval(clockTimer)
})
</script>

<style scoped>
.ops-panel {
  min-height: 100vh;
  background: #f0f2f5;
  padding-bottom: 50px;
}

/* ====== 顶部状态栏 ====== */
.ops-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px;
  background: linear-gradient(135deg, #0d1b3e 0%, #1a237e 100%);
  color: #fff;
  position: sticky; top: 0; z-index: 10;
}
.oh-left, .oh-right { display: flex; align-items: center; gap: 10px; }
.oh-back {
  width: 28px; height: 28px; border-radius: 6px; border: none;
  background: rgba(255,255,255,0.15); color: #fff; font-size: 16px;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
}
.oh-title { font-size: 16px; font-weight: 600; }
.oh-badge {
  font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 500;
}
.badge-ok { background: rgba(82,196,26,0.25); color: #b7eb8f; }
.badge-err { background: rgba(255,77,79,0.3); color: #ffa39e; }
.oh-time { font-size: 12px; opacity: 0.7; font-variant-numeric: tabular-nums; }
.oh-refresh {
  width: 28px; height: 28px; border-radius: 50%; border: none;
  background: rgba(255,255,255,0.15); color: #fff; font-size: 16px;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: transform 0.3s;
}
.oh-refresh.spinning { animation: spin 0.6s linear; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

/* ====== 告警横幅 ====== */
.alert-banner {
  display: flex; align-items: flex-start; gap: 10px;
  margin: 10px 16px; padding: 12px 14px;
  background: linear-gradient(135deg, #fff2f0 0%, #fff1f0 100%);
  border: 1px solid #ffccc7; border-radius: 10px;
}
.ab-icon { font-size: 20px; line-height: 1; flex-shrink: 0; }
.ab-list { flex: 1; }
.ab-item { font-size: 13px; color: #cf1322; line-height: 1.8; }

/* ====== 分区 ====== */
.section {
  margin: 12px 16px 0;
  background: #fff;
  border-radius: 12px;
  padding: 14px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}
.sec-head {
  font-size: 14px; font-weight: 600; color: #333;
  margin-bottom: 12px; display: flex; align-items: center; gap: 6px;
}
.sec-icon { font-size: 16px; }

/* ====== 环形进度条 ====== */
.ring-row {
  display: flex; justify-content: space-around; gap: 8px; margin-bottom: 14px;
}
.ring-wrap { text-align: center; flex: 1; }
.ring-box { position: relative; width: 68px; height: 68px; margin: 0 auto 4px; }
.ring-svg { width: 68px; height: 68px; }
.ring-arc { transition: stroke-dashoffset 0.8s ease; }
.ring-inner {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  text-align: center;
}
.ring-pct { font-size: 15px; font-weight: 700; font-variant-numeric: tabular-nums; }
.ring-label { font-size: 13px; color: #666; font-weight: 500; }
.ring-info { font-size: 11px; color: #999; margin-top: 2px; }
.ring-alert { font-size: 11px; color: #ff4d4f; margin-top: 2px; font-weight: 500; }

/* PC 宽屏下环形图再缩小 */
@media (min-width: 768px) {
  .ring-box { width: 54px; height: 54px; }
  .ring-svg { width: 54px; height: 54px; }
  .ring-pct { font-size: 13px; }
}

/* ====== 迷你卡片行 ====== */
.mini-card-row {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;
}
.mini-card {
  background: #fafafa; border-radius: 8px; padding: 10px 8px;
}
.mc-top {
  display: flex; align-items: center; gap: 4px; margin-bottom: 4px;
}
.mc-emoji { font-size: 14px; }
.mc-label { font-size: 11px; color: #999; }
.mc-body {
  display: flex; align-items: baseline; gap: 2px; margin-bottom: 5px;
}
.mc-val { font-size: 16px; font-weight: 700; font-variant-numeric: tabular-nums; }
.mc-slash { font-size: 12px; color: #bbb; margin: 0 1px; }
.mc-max { font-size: 12px; color: #999; font-weight: 500; font-variant-numeric: tabular-nums; }
.mc-unit { font-size: 11px; color: #999; }
.mc-bar-track {
  height: 4px; background: #f0f0f0; border-radius: 2px; overflow: hidden;
}
.mc-bar-fill {
  height: 100%; border-radius: 2px;
  transition: width 0.8s ease, background 0.4s ease;
}

/* ====== 容器卡片 ====== */
.container-grid {
  display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px;
}
.ctr-card {
  border-radius: 10px; padding: 12px; border: 1.5px solid #f0f0f0;
  transition: border-color 0.3s;
}
.ctr-ok { border-left: 3px solid #52c41a; background: #f6ffed; }
.ctr-err { border-left: 3px solid #ff4d4f; background: #fff2f0; }
.ctr-top { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.ctr-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot-g { background: #52c41a; box-shadow: 0 0 6px rgba(82,196,26,0.4); }
.dot-r { background: #ff4d4f; box-shadow: 0 0 6px rgba(255,77,79,0.4); }
.ctr-name { font-size: 15px; font-weight: 600; color: #333; }
.ctr-status { font-size: 12px; color: #666; margin-bottom: 2px; }
.ctr-img { font-size: 11px; color: #bbb; word-break: break-all; }
.ctr-ports { font-size: 11px; color: #8c8c8c; margin-top: 3px; }

/* ====== 服务健康 ====== */
.svc-row {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 8px;
}
.svc-card {
  border-radius: 10px; padding: 14px 10px; text-align: center;
  transition: all 0.3s;
}
.svc-ok { background: linear-gradient(135deg, #f6ffed 0%, #fcffe6 100%); border: 1px solid #d9f7be; }
.svc-fail { background: linear-gradient(135deg, #fff2f0 0%, #fff1f0 100%); border: 1px solid #ffccc7; }
.svc-dot { font-size: 22px; margin-bottom: 4px; }
.svc-ok .svc-dot { color: #52c41a; }
.svc-fail .svc-dot { color: #ff4d4f; }
.svc-name { font-size: 14px; font-weight: 600; color: #333; }
.svc-detail { font-size: 11px; color: #999; margin-top: 2px; }
.svc-detail-row {
  display: flex; justify-content: space-around;
}
.svc-detail { font-size: 11px; color: #bbb; }

/* ====== 业务数据 ====== */
.biz-card-row {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 8px;
}
.biz-card-row:last-child {
  grid-template-columns: repeat(3, 1fr);
}
.biz-card {
  display: flex; align-items: center; gap: 10px;
  padding: 10px; border-radius: 8px; background: #fafafa;
}
.bc-icon {
  width: 36px; height: 36px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; flex-shrink: 0;
}
.bc-body { flex: 1; }
.bc-val { font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; }
.bc-label { font-size: 11px; color: #999; }

/* ====== 存储信息 ====== */
.storage-row {
  display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 12px;
}
.sto-card {
  background: #fafafa; border-radius: 8px; padding: 14px; text-align: center;
}
.sto-label { font-size: 12px; color: #999; margin-bottom: 4px; }
.sto-value { font-size: 22px; font-weight: 700; color: #333; font-variant-numeric: tabular-nums; }
.sto-sub { font-size: 11px; color: #bbb; margin-top: 2px; }

/* 磁盘进度条 */
.disk-section { padding: 0 2px; }
.disk-header {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 13px; color: #666; margin-bottom: 6px;
}
.disk-pct { font-weight: 700; color: #333; }
.pct-warn { color: #ff4d4f; }
.disk-track {
  height: 10px; background: #f0f0f0; border-radius: 5px; overflow: hidden;
}
.disk-fill {
  height: 100%; border-radius: 5px;
  background: linear-gradient(90deg, #1890ff, #52c41a);
  transition: width 0.8s ease;
}
.fill-warn { background: linear-gradient(90deg, #faad14, #ff4d4f); }
.disk-info { font-size: 11px; color: #bbb; margin-top: 4px; }

/* ====== 底部 ====== */
.ops-footer {
  text-align: center; font-size: 12px; color: #bbb;
  padding: 16px 0 8px;
}
</style>
