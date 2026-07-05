<!--
  @模块：UserGuide.vue — 使用文档（v4.0 新增）
  @页面用途：根据用户角色展示对应的操作指引，帮助新用户快速上手
-->
<template>
  <div class="guide-page">
    <div class="back-nav">
      <a href="javascript:void(0)" @click="$router.back()" class="back-link">&larr; 返回</a>
    </div>
    <h2>使用指南</h2>

      <!-- 下载按钮 -->
    <div class="download-bar">
      <span class="download-label">离线版本：</span>
      <a class="download-btn pdf" href="/docs/使用指南.pdf" download="在线学习平台使用指南.pdf">
        <svg class="download-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        下载 PDF
      </a>
      <a class="download-btn word" href="/docs/使用指南.docx" download="在线学习平台使用指南.docx">
        <svg class="download-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        下载 Word
      </a>
      <a class="download-btn skill" href="/docs/在线学习平台助手技能.zip" download="在线学习平台助手技能.zip">
        <svg class="download-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        下载智能体技能包
      </a>
    </div>

    <!-- 角色切换标签 -->
    <div class="role-tabs">
      <button :class="['tab', { active: activeRole === 'student' }]" @click="activeRole = 'student'">学生</button>
      <button :class="['tab', { active: activeRole === 'teacher' }]" @click="activeRole = 'teacher'">教师</button>
      <button :class="['tab', { active: activeRole === 'admin' }]" @click="activeRole = 'admin'">管理员</button>
    </div>

    <!-- 学生指南 -->
    <div v-if="activeRole === 'student'" class="guide-content">
      <section class="guide-section">
        <h3>如何进入学习</h3>
        <ol>
          <li>在钉钉中打开「在线学习平台」H5 应用，自动登录</li>
          <li>在首页课程列表中选择一门课程</li>
          <li>点击课程进入详情页，查看所有小节</li>
          <li>点击小节进入学习页面，视频自动开始计时</li>
          <li>保持页面在前台且视频播放状态，系统每 30 秒记录一次有效学习时间</li>
        </ol>
        <div class="tip">注意：暂停视频或切换到其他应用/标签页时，学习时间不会被计入。</div>
      </section>

      <section class="guide-section">
        <h3>小节开播时间</h3>
        <p>部分小节设有"开播时间"，未到开播时间时无法进入学习，页面会显示锁定状态和倒计时。开播时间过后可随时进入（包括复习）。</p>
      </section>

      <section class="guide-section">
        <h3>查看我的进度</h3>
        <p>点击底部导航「我的进度」可查看各课程的有效学习时长、学习百分比和完成状态。</p>
      </section>

      <section class="guide-section">
        <h3>提交作业</h3>
        <ol>
          <li>在课程详情页点击「作业」按钮进入作业页面</li>
          <li>每个小节可能有一份作业，点击进入可查看题目要求</li>
          <li>拍照或选择图片上传，点击提交</li>
          <li>截至日期前可多次提交，系统以最新版本为准</li>
        </ol>
        <div class="tip">迟交：截止时间后仍可提交，但会标记为「迟交」，教师可看到。</div>
      </section>

      <section class="guide-section">
        <h3>签到日历</h3>
        <p>点击顶栏「签到」可查看本月学习签到日历，每天有有效学习记录即标记为已签到。</p>
      </section>

      <section class="guide-section">
        <h3>学习报告</h3>
        <p>点击顶栏「报告」查看个人学习总结报告，包括总学习时长、各课程进度和推荐学习建议。</p>
      </section>

      <section class="guide-section">
        <h3>小节评价</h3>
        <p>学完每节课后可以对小节进行评分（1-5 星）和文字评价，帮助教师改进课程。</p>
      </section>
    </div>

    <!-- 教师指南 -->
    <div v-if="activeRole === 'teacher'" class="guide-content">
      <section class="guide-section">
        <h3>创建和管理课程</h3>
        <ol>
          <li>登录后在首页点击「创建课程」按钮</li>
          <li>填写课程标题、描述、要求学习时长等基本信息</li>
          <li>在课程编辑页添加小节，每个小节可设置独立视频</li>
          <li>视频支持两种方式：外部链接（B站/腾讯视频）或本地上传（MP4文件）</li>
          <li>可为每个小节设置「开播时间」，控制学生何时可以开始学习</li>
        </ol>
      </section>

      <section class="guide-section">
        <h3>发布作业</h3>
        <ol>
          <li>在课程详情页点击「作业管理」</li>
          <li>每个小节可创建一份作业，填写标题、题目描述和截止时间</li>
          <li>支持上传题目图片，设置评分标准</li>
          <li>发布后学生即可看到作业并提交</li>
        </ol>
      </section>

      <section class="guide-section">
        <h3>查看学习统计</h3>
        <p>点击顶栏头像旁「学习统计」进入教师仪表盘，可查看：</p>
        <ul>
          <li>各课程的学习人数、平均学习时长</li>
          <li>学生完成率排名</li>
          <li>班级维度统计</li>
        </ul>
      </section>

      <section class="guide-section">
        <h3>发布公告</h3>
        <ol>
          <li>点击顶栏「公告」进入公告列表</li>
          <li>点击「发布公告」撰写新公告</li>
          <li>可选择关联某门课程（仅该课程学生可见）或全平台公告</li>
          <li>设置优先级：普通/重要/紧急，紧急公告会醒目展示</li>
        </ol>
      </section>

      <section class="guide-section">
        <h3>学习排行榜</h3>
        <p>在课程详情页点击「排行榜」查看该课程学生学习时长排名，按有效学习时长从高到低排列。</p>
      </section>

      <section class="guide-section">
        <h3>学习报告</h3>
        <p>教师可查看班级维度的学习报告，了解全班学习进度、未完成学生名单和建议关注的学生。</p>
      </section>

      <section class="guide-section">
        <h3>智能体技能接入</h3>
        <p>平台提供「在线学习平台助手」智能体技能（Skill），支持通过 AI 智能体自动执行教学管理操作，无需手动逐项操作。</p>

        <div class="skill-card">
          <div class="skill-card-header">
            <span class="skill-badge">Skill</span>
            <span class="skill-name">在线学习平台助手</span>
          </div>
          <p class="skill-desc">对接本平台 API，让 AI 智能体代为执行课程管理、视频上传、进度查询、统计汇总、提醒推送、报表导出等操作。</p>
        </div>

        <h4 style="margin:12px 0 6px;font-size:14px;color:#333;">支持的操作</h4>
        <div class="skill-grid">
          <div class="skill-item">
            <span class="skill-item-icon">&#128218;</span>
            <span>课程创建与编辑</span>
          </div>
          <div class="skill-item">
            <span class="skill-item-icon">&#127909;</span>
            <span>视频上传与管理</span>
          </div>
          <div class="skill-item">
            <span class="skill-item-icon">&#128200;</span>
            <span>学习进度查询统计</span>
          </div>
          <div class="skill-item">
            <span class="skill-item-icon">&#128227;</span>
            <span>发送学习提醒</span>
          </div>
          <div class="skill-item">
            <span class="skill-item-icon">&#128196;</span>
            <span>导出学习报表</span>
          </div>
          <div class="skill-item">
            <span class="skill-item-icon">&#128101;</span>
            <span>学生完成情况汇总</span>
          </div>
        </div>

        <h4 style="margin:12px 0 6px;font-size:14px;color:#333;">接入步骤</h4>
        <ol>
          <li>在本平台生成 API Key：管理后台 → 找到你的用户 → 点击「生成 API Key」</li>
          <li>点击页面上方「下载智能体技能包」，获取技能配置文件</li>
          <li>将技能包导入你的 AI 智能体（如星辰超级智能体）</li>
          <li>在智能体对话中提供服务器地址和 API Key 即可开始使用</li>
        </ol>

        <h4 style="margin:12px 0 6px;font-size:14px;color:#333;">使用示例</h4>
        <div class="chat-demo">
          <div class="chat-bubble user">帮我看看学生学得怎么样</div>
          <div class="chat-bubble bot">📊 高中数学必修一 - 集合与函数（要求60分钟）<br>&nbsp;&nbsp;完成率: 60% (3/5人)<br>&nbsp;&nbsp;✅ 已完成: 王小明(62分), 李小红(90分), 陈思思(90分)<br>&nbsp;&nbsp;⚠️ 未完成: 刘大伟(55分/差5分), 赵天宇(10分/差50分)</div>
        </div>
        <div class="chat-demo">
          <div class="chat-bubble user">帮我建个新课"初高中衔接化学"，传视频上去</div>
          <div class="chat-bubble bot">✅ 已创建课程「初高中衔接化学」(ID=18)<br>✅ 已上传第1讲 视频 (80MB)<br>✅ 已上传第2讲 视频 (118MB)<br>... 共12个章节全部上传完成</div>
        </div>

        <div class="tip" style="margin-top:12px;">提示：技能包内含 SKILL.md（技能定义）和 API 参考文档，技术细节请参阅附件。Teacher 和 Admin 角色均可使用，仅「删除课程」和「用户管理」限定 Admin。</div>
      </section>

      <section class="guide-section">
        <h3>管理用户</h3>
        <p>在「管理后台」（教师/管理员可见）可查看所有用户列表、修改用户角色、分配班级、生成 API Key。</p>
      </section>
    </div>

    <!-- 管理员指南 -->
    <div v-if="activeRole === 'admin'" class="guide-content">
      <section class="guide-section">
        <h3>管理后台</h3>
        <p>管理员拥有教师全部权限，额外可：</p>
        <ul>
          <li>查看和管理所有用户（学生/教师）</li>
          <li>修改任意用户角色</li>
          <li>删除用户</li>
          <li>分配和调整班级</li>
          <li>生成/重置 API Key</li>
        </ul>
      </section>

      <section class="guide-section">
        <h3>API Key 使用</h3>
        <p>API Key 用于让智能体或其他程序调用平台接口，无需通过浏览器登录。</p>
        <ol>
          <li>在管理后台找到目标用户，点击「生成 API Key」</li>
          <li>复制生成的 Key（格式：sk_xxxx），只显示一次</li>
          <li>调用 API 时在请求头加入 <code>X-API-Key: sk_xxxx</code></li>
          <li>所有需要认证的 API 都支持 JWT 和 API Key 两种认证方式</li>
        </ol>
      </section>

      <section class="guide-section">
        <h3>全平台报告</h3>
        <p>管理员可查看全平台维度的学习报告，包括总用户数、活跃用户数、各课程完成率等全局数据。</p>
      </section>

      <section class="guide-section">
        <h3>运维监控面板</h3>
        <p>点击顶栏「运维」进入监控面板，可查看：</p>
        <ul>
          <li>系统健康状态（API 响应时间、数据库连接等）</li>
          <li>在线用户实时统计</li>
          <li>学习会话活跃度</li>
          <li>服务器资源使用情况</li>
        </ul>
      </section>

      <section class="guide-section">
        <h3>系统架构</h3>
        <table class="info-table">
          <tr><td class="label">技术栈</td><td>Python FastAPI + MySQL + Redis + Nginx</td></tr>
          <tr><td class="label">前端</td><td>Vue3 + Vite + DingTalk JSAPI（H5微应用）</td></tr>
          <tr><td class="label">部署</td><td>Docker Compose，服务器 115.223.38.90:1001</td></tr>
          <tr><td class="label">容器</td><td>study-monitor-backend / frontend / mysql / redis</td></tr>
          <tr><td class="label">数据库</td><td>MySQL 8.0，数据库名 study_monitor</td></tr>
        </table>
      </section>

      <section class="guide-section">
        <h3>常用运维命令</h3>
        <div class="code-block">
          <pre># 查看容器状态
docker ps --filter name=study-monitor

# 重启后端容器（代码更新后）
cd /data/study-monitor && docker compose up -d --build backend frontend

# 查看后端日志
docker logs study-monitor-backend --tail 100 -f

# 进入 MySQL 容器
docker exec -it study-monitor-mysql mysql -u root -p

# 健康检查
curl http://127.0.0.1:8001/api/health</pre>
        </div>
      </section>

      <section class="guide-section">
        <h3>代码更新部署流程</h3>
        <ol>
          <li>本地提交代码并 push 到 GitHub</li>
          <li>SSH 到服务器，cd /data/study-monitor</li>
          <li>git pull（需要代理：https_proxy=http://127.0.0.1:7890）</li>
          <li>如有数据库变更，先执行迁移 SQL</li>
          <li>docker compose up -d --build backend frontend</li>
          <li>curl http://127.0.0.1:1001/ 验证首页可访问</li>
        </ol>
      </section>

      <section class="guide-section">
        <h3>数据备份</h3>
        <div class="code-block">
          <pre># 导出数据库备份
docker exec study-monitor-mysql mysqldump -u root -p'Sm2026Root_Secure_Prod' study_monitor > backup_$(date +%Y%m%d).sql

# 恢复备份
docker exec -i study-monitor-mysql mysql -u root -p'Sm2026Root_Secure_Prod' study_monitor &lt; backup_20260621.sql</pre>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '../utils/auth'

const auth = useAuthStore()
const activeRole = ref('student')

onMounted(() => {
  // 默认显示当前用户角色对应的指南
  const role = auth.user.value?.role
  if (role === 'teacher' || role === 'admin') {
    activeRole.value = role
  }
})
</script>

<style scoped>
.guide-page {
  max-width: 800px;
  margin: 0 auto;
  padding: 16px;
  min-height: calc(100vh - 48px);
}

.back-nav {
  margin-bottom: 12px;
}

.back-link {
  color: #1890ff;
  text-decoration: none;
  font-size: 14px;
}

.guide-page h2 {
  font-size: 20px;
  color: #333;
  margin-bottom: 12px;
}

/* 下载按钮区域 */
.download-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
  padding: 10px 14px;
  background: #f9f9fb;
  border-radius: 8px;
  border: 1px solid #eef0f3;
}

.download-label {
  font-size: 13px;
  color: #999;
  white-space: nowrap;
}

.download-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.download-btn .download-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.download-btn.pdf {
  background: #fff1f0;
  color: #cf1322;
  border-color: #ffa39e;
}
.download-btn.pdf:hover {
  background: #ff7875;
  color: #fff;
}

.download-btn.word {
  background: #e6f7ff;
  color: #096dd9;
  border-color: #91d5ff;
}
.download-btn.word:hover {
  background: #1890ff;
  color: #fff;
}

/* 角色标签切换 */
.role-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
  border-bottom: 2px solid #f0f0f0;
  padding-bottom: 8px;
}

.role-tabs .tab {
  padding: 6px 16px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: #fff;
  color: #666;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.role-tabs .tab.active {
  background: #1890ff;
  color: #fff;
  border-color: #1890ff;
}

/* 指南内容 */
.guide-content {
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.guide-section {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

.guide-section h3 {
  font-size: 16px;
  color: #1890ff;
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid #f0f0f0;
}

.guide-section p {
  font-size: 14px;
  color: #555;
  line-height: 1.6;
  margin-bottom: 8px;
}

.guide-section ol,
.guide-section ul {
  padding-left: 20px;
  font-size: 14px;
  color: #555;
  line-height: 1.8;
}

.tip {
  background: #fffbe6;
  border: 1px solid #ffe58f;
  border-radius: 4px;
  padding: 8px 12px;
  font-size: 13px;
  color: #ad6800;
  margin-top: 8px;
}

code {
  background: #f5f5f5;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Menlo', 'Consolas', monospace;
  font-size: 13px;
  color: #d46b08;
}

.info-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.info-table td {
  padding: 8px 12px;
  border-bottom: 1px solid #f0f0f0;
}

.info-table .label {
  color: #999;
  width: 80px;
  white-space: nowrap;
}

.code-block {
  background: #1e1e1e;
  border-radius: 6px;
  padding: 12px;
  overflow-x: auto;
}

.code-block pre {
  color: #d4d4d4;
  font-family: 'Menlo', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}

/* 下载按钮 - 技能包 */
.download-btn.skill {
  background: #f6ffed;
  color: #389e0d;
  border-color: #b7eb8f;
}
.download-btn.skill:hover {
  background: #52c41a;
  color: #fff;
}

/* 技能卡片 */
.skill-card {
  background: linear-gradient(135deg, #f0f5ff 0%, #e6fffb 100%);
  border: 1px solid #d6e4ff;
  border-radius: 10px;
  padding: 14px 16px;
  margin: 10px 0;
}

.skill-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.skill-badge {
  display: inline-block;
  background: linear-gradient(135deg, #1890ff, #722ed1);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  letter-spacing: 0.5px;
}

.skill-name {
  font-size: 15px;
  font-weight: 600;
  color: #1a1a1a;
}

.skill-desc {
  font-size: 13px;
  color: #666;
  margin: 0;
  line-height: 1.5;
}

/* 技能功能网格 */
.skill-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.skill-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  background: #fafafa;
  border-radius: 6px;
  border: 1px solid #f0f0f0;
  font-size: 13px;
  color: #444;
}

.skill-item-icon {
  font-size: 16px;
  flex-shrink: 0;
}

/* 对话示例 */
.chat-demo {
  margin-bottom: 8px;
}

.chat-bubble {
  max-width: 85%;
  padding: 8px 12px;
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.5;
  margin-bottom: 6px;
}

.chat-bubble.user {
  background: #1890ff;
  color: #fff;
  margin-left: auto;
  border-bottom-right-radius: 2px;
  text-align: right;
}

.chat-bubble.bot {
  background: #f5f5f5;
  color: #333;
  margin-right: auto;
  border-bottom-left-radius: 2px;
}
</style>
