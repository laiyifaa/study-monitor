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
                <img v-if="isImageFile(file)" :src="getMediaUrl(file)" :title="getAttachmentDisplayName(section.title, 'homework', i, getAssignment(section.id).question_files.length)" class="question-thumb" @click="previewImage(getMediaUrl(file))" />
                <button v-else type="button" class="file-link" :title="getAttachmentDisplayName(section.title, 'homework', i, getAssignment(section.id).question_files.length)" @click="openQuestionFile(section.title, file, i, getAssignment(section.id).question_files.length)">{{ getAttachmentDisplayName(section.title, 'homework', i, getAssignment(section.id).question_files.length) }}</button>
              </div>
            </div>
          </div>

          <div v-if="getAssignment(section.id).answer_files?.length" class="question-files-preview card-preview">
            <h4>答案附件</h4>
            <div class="question-files-list">
              <div v-for="(file, i) in getAssignment(section.id).answer_files" :key="`af-${i}`" class="question-file-item">
                <img v-if="isImageFile(file)" :src="getMediaUrl(file)" :title="getAttachmentDisplayName(section.title, 'answer', i, getAssignment(section.id).answer_files.length)" class="question-thumb" @click="openTeacherAnswerFile(section.title, file, i, getAssignment(section.id).answer_files.length)" />
                <button v-else type="button" class="file-link" :title="getAttachmentDisplayName(section.title, 'answer', i, getAssignment(section.id).answer_files.length)" @click="openTeacherAnswerFile(section.title, file, i, getAssignment(section.id).answer_files.length)">{{ getAttachmentDisplayName(section.title, 'answer', i, getAssignment(section.id).answer_files.length) }}</button>
              </div>
            </div>
          </div>

          <div class="assignment-actions">
            <button class="btn-sm" @click="openEditForSection(section)">编辑</button>
            <button class="btn-sm answer-action" @click="openAnswerForSection(section)">答案管理</button>
            <button v-if="getAssignment(section.id).status === 'draft'" class="btn-sm primary" @click="publishAssignment(section.id)">发布</button>
            <button class="btn-sm" @click="loadSubmissions(section.id, { reset: true, openModal: true })">查看提交</button>
            <button class="btn-sm" @click="openStudentLookup(section.id)">查询学生</button>
            <button class="btn-sm" @click="openUnsubmittedModal(section.id)">未交名单</button>
            <button class="btn-sm" @click="openLateModal(section.id)">迟交名单</button>
            <button
              v-if="getAssignment(section.id).status === 'published' && getAssignment(section.id).grading_mode !== 'manual'"
              class="btn-sm ai-grade-btn"
              :disabled="triggeringSection === section.id"
              @click="triggerAiGrading(section.id)"
            >
              {{ triggeringSection === section.id ? '批改中...' : '触发智能批改' }}
            </button>
          </div>
          <div v-if="triggeringSection === section.id && triggerStatus" class="trigger-progress">
            <span class="progress-text">
              批改进度：{{ triggerStatus.graded + triggerStatus.failed }} / {{ triggerStatus.total }}
              <span v-if="triggerStatus.processing > 0">（处理中 {{ triggerStatus.processing }}）</span>
              <span v-if="triggerStatus.failed > 0" class="fail-count">失败 {{ triggerStatus.failed }}</span>
            </span>
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
          <label>题目文件（图片/PDF/Word）</label>
          <input type="file" multiple accept="image/*,.pdf,.doc,.docx" @change="handleQuestionFileSelect" />
          <div v-if="form.question_files.length > 0" class="question-files-preview">
            <div v-for="(file, i) in form.question_files" :key="i" class="question-file-item">
              <img v-if="isImageFile(file)" :src="getMediaUrl(file)" :title="getAttachmentDisplayName(currentSection?.title, 'homework', i, form.question_files.length)" class="question-thumb" />
              <button v-else type="button" class="file-link" :title="getAttachmentDisplayName(currentSection?.title, 'homework', i, form.question_files.length)" @click="openQuestionFile(currentSection?.title, file, i, form.question_files.length)">{{ getAttachmentDisplayName(currentSection?.title, 'homework', i, form.question_files.length) }}</button>
              <button type="button" class="remove-btn" @click="removeQuestionFile(i)">x</button>
            </div>
          </div>
        </div>

        <div class="form-group answer-module">
            <div class="answer-header">
              <label>答案模块</label>
              <div class="answer-actions">
                <button type="button" class="btn-sm" @click="addAnswerItem">添加一题</button>
                <button type="button" class="btn-sm batch-action" @click="openBatchAnswerModal">批量新增</button>
                <label class="btn-sm file-button">
                  上传答案附件
                  <input type="file" multiple accept="image/*,.pdf,.doc,.docx" @change="handleAnswerAttachmentSelect" />
                </label>
                <label class="btn-sm file-button">
                  {{ answerParsing ? '解析中...' : '解析答案文件' }}
                  <input type="file" accept=".pdf,.doc,.docx" :disabled="answerParsing" @change="handleAnswerFileSelect" />
                </label>
              </div>
            </div>
          <div v-if="form.answer_files.length > 0" class="question-files-preview answer-files-preview">
            <div v-for="(file, i) in form.answer_files" :key="`answer-file-${i}`" class="question-file-item">
              <img v-if="isImageFile(file)" :src="getMediaUrl(file)" :title="getAttachmentDisplayName(currentSection?.title, 'answer', i, form.answer_files.length)" class="question-thumb" @click="openTeacherAnswerFile(currentSection?.title, file, i, form.answer_files.length)" />
              <button v-else type="button" class="file-link" :title="getAttachmentDisplayName(currentSection?.title, 'answer', i, form.answer_files.length)" @click="openTeacherAnswerFile(currentSection?.title, file, i, form.answer_files.length)">{{ getAttachmentDisplayName(currentSection?.title, 'answer', i, form.answer_files.length) }}</button>
              <button type="button" class="remove-btn" @click="removeAnswerFile(i)">x</button>
            </div>
          </div>
          <div v-if="form.answer_items.length === 0" class="empty small">暂无答案</div>
          <table v-else class="answer-table">
            <thead>
              <tr>
                <th>题号</th>
                <th>题型</th>
                <th>答案</th>
                <th>分数</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in form.answer_items" :key="index">
                <td><input v-model="item.no" placeholder="1" /></td>
                <td>
                  <select v-model="item.type">
                    <option value="option_letter">选项字母</option>
                    <option value="true_false">判断题</option>
                    <option value="fill_blank">填空题</option>
                  </select>
                </td>
                <td>
                  <textarea v-if="item.type === 'fill_blank'" v-model="item.answer" class="answer-textarea" rows="2" placeholder="标准答案"></textarea>
                  <input v-else v-model="item.answer" placeholder="标准答案" />
                </td>
                <td><input v-model.number="item.score" type="number" min="0" step="1" placeholder="分数" /></td>
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
          <label>截止时间（学生提交截止）</label>
          <input v-model="form.deadline" type="datetime-local" />
        </div>
        <div v-if="form.grading_mode !== 'manual'" class="form-group">
          <label>自动批改时间</label>
          <input v-model="form.auto_grade_at" type="datetime-local" />
          <p class="form-hint">不设置则在截止时间到后立即触发智能体批改</p>
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
              <label>标准答案 <span class="answer-count" v-if="form.answer_items.length > 0">{{ form.answer_items.length }} 题</span></label>
              <div class="answer-actions">
                <button type="button" class="btn-sm" @click="addAnswerItem">添加一题</button>
                <button type="button" class="btn-sm batch-action" @click="openBatchAnswerModal">批量新增</button>
                <button v-if="form.answer_items.length > 0" type="button" class="btn-sm ghost-action" @click="showAnswerPreview = !showAnswerPreview">{{ showAnswerPreview ? '收起预览' : '查看预览' }}</button>
                <label class="btn-sm file-button">
                  上传答案附件
                  <input type="file" multiple accept="image/*,.pdf,.doc,.docx" @change="handleAnswerAttachmentSelect" />
                </label>
                <label class="btn-sm file-button">
                  {{ answerParsing ? '解析中...' : '解析答案文件' }}
                  <input type="file" accept=".pdf,.doc,.docx" :disabled="answerParsing" @change="handleAnswerFileSelect" />
                </label>
              </div>
            </div>
            <div v-if="form.answer_files.length > 0" class="question-files-preview answer-files-preview">
              <div v-for="(file, i) in form.answer_files" :key="`answer-file-standalone-${i}`" class="question-file-item">
                <img v-if="isImageFile(file)" :src="getMediaUrl(file)" :title="getAttachmentDisplayName(currentSection?.title, 'answer', i, form.answer_files.length)" class="question-thumb" @click="openTeacherAnswerFile(currentSection?.title, file, i, form.answer_files.length)" />
                <button v-else type="button" class="file-link" :title="getAttachmentDisplayName(currentSection?.title, 'answer', i, form.answer_files.length)" @click="openTeacherAnswerFile(currentSection?.title, file, i, form.answer_files.length)">{{ getAttachmentDisplayName(currentSection?.title, 'answer', i, form.answer_files.length) }}</button>
                <button type="button" class="remove-btn" @click="removeAnswerFile(i)">x</button>
              </div>
            </div>
            <div v-if="form.answer_items.length === 0" class="empty small">暂无答案</div>
            <table v-else class="answer-table">
            <thead>
              <tr>
                <th>题号</th>
                <th>题型</th>
                <th>答案</th>
                <th>分数</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in form.answer_items" :key="index">
                <td><input v-model="item.no" placeholder="1" /></td>
                <td>
                  <select v-model="item.type">
                    <option value="option_letter">选项字母</option>
                    <option value="true_false">判断题</option>
                    <option value="fill_blank">填空题</option>
                  </select>
                </td>
                <td>
                  <textarea v-if="item.type === 'fill_blank'" v-model="item.answer" class="answer-textarea" rows="2" placeholder="标准答案"></textarea>
                  <input v-else v-model="item.answer" placeholder="标准答案" />
                </td>
                <td><input v-model.number="item.score" type="number" min="0" step="1" placeholder="分数" /></td>
                <td><button type="button" class="remove-btn" @click="removeAnswerItem(index)">移除</button></td>
              </tr>
            </tbody>
          </table>
          <div ref="quickAnswerBarRef" class="answer-quick-entry">
            <div class="quick-entry-header">
              <strong>快速录入</strong>
              <span class="quick-entry-hint">题号自动递增；选择/判断题按 Enter 追加，填空题按 Ctrl+Enter 追加</span>
            </div>
            <div class="quick-entry-grid">
              <div class="quick-entry-field quick-entry-no">
                <label>题号</label>
                <input v-model="quickAnswerItem.no" @keydown="handleQuickAnswerKeydown" placeholder="1" />
              </div>
              <div class="quick-entry-field quick-entry-type">
                <label>题型</label>
                <select v-model="quickAnswerItem.type" @keydown="handleQuickAnswerKeydown">
                  <option value="option_letter">选项字母</option>
                  <option value="true_false">判断题</option>
                  <option value="fill_blank">填空题</option>
                </select>
              </div>
              <div class="quick-entry-field quick-entry-answer">
                <label>答案</label>
                <textarea
                  v-if="quickAnswerItem.type === 'fill_blank'"
                  ref="quickAnswerFieldRef"
                  v-model="quickAnswerItem.answer"
                  class="answer-textarea quick-answer-textarea"
                  rows="2"
                  placeholder="标准答案"
                  @keydown="handleQuickAnswerKeydown"
                />
                <input
                  v-else
                  ref="quickAnswerFieldRef"
                  v-model="quickAnswerItem.answer"
                  placeholder="标准答案"
                  @keydown="handleQuickAnswerKeydown"
                />
              </div>
              <div class="quick-entry-field quick-entry-score">
                <label>分数</label>
                <input v-model.number="quickAnswerItem.score" type="number" min="0" step="1" placeholder="分数" @keydown="handleQuickAnswerKeydown" />
              </div>
              <div class="quick-entry-submit">
                <button type="button" class="btn-primary quick-entry-button" @click="appendQuickAnswer">追加一题</button>
              </div>
            </div>
          </div>
          <pre v-if="form.answer_items.length > 0 && showAnswerPreview" class="answer-json answer-json-collapsible">{{ answerJsonPreview }}</pre>
        </div>
        <div class="modal-actions">
          <button class="btn-secondary" @click="closeAnswerModal">取消</button>
          <button class="btn-primary" @click="saveAnswer">保存答案</button>
        </div>
      </div>
    </div>

    <div v-if="showBatchAnswerModal" class="modal-overlay" @click.self="closeBatchAnswerModal">
      <div class="modal modal-lg batch-answer-modal">
        <h3>批量新增答案</h3>
        <div class="batch-hint">逐行填写题号、题型、答案和分数，确认后会追加到当前答案列表。</div>
        <div class="batch-actions-bar">
          <button type="button" class="btn-sm" @click="addBatchAnswerRow">添加一行</button>
          <button type="button" class="btn-sm" @click="resetBatchAnswerRows">清空</button>
        </div>
        <table class="answer-table batch-answer-table">
          <thead>
            <tr>
              <th>题号</th>
              <th>题型</th>
              <th>答案</th>
              <th>分数</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in batchAnswerRows" :key="`batch-${index}`">
              <td><input v-model="item.no" placeholder="13(1)" /></td>
              <td>
                <select v-model="item.type">
                  <option value="option_letter">选项字母</option>
                  <option value="true_false">判断题</option>
                  <option value="fill_blank">填空题</option>
                </select>
              </td>
              <td>
                <textarea v-if="item.type === 'fill_blank'" v-model="item.answer" class="answer-textarea" rows="2" placeholder="标准答案"></textarea>
                <input v-else v-model="item.answer" placeholder="标准答案" />
              </td>
              <td><input v-model.number="item.score" type="number" min="0" step="1" placeholder="分数" /></td>
              <td><button type="button" class="remove-btn" @click="removeBatchAnswerRow(index)">移除</button></td>
            </tr>
          </tbody>
        </table>
        <div class="modal-actions">
          <button class="btn-secondary" @click="closeBatchAnswerModal">取消</button>
          <button class="btn-primary" @click="appendBatchAnswers">追加到答案</button>
        </div>
      </div>
    </div>

    <div v-if="showSubmissionsModal" class="modal-overlay" @click.self="showSubmissionsModal = false">
      <div class="modal modal-lg">
        <h3>提交列表</h3>
        <div class="list-toolbar">
          <div class="list-search">
            <div class="search-input-wrap">
              <span class="search-icon">🔍</span>
              <input v-model="submissionsSearch" type="text" placeholder="按学生姓名查询" @keydown.enter.prevent="searchSubmissionsByName" />
              <button v-if="submissionsSearch" class="search-clear" @click="resetSubmissionsSearch" title="清空">✕</button>
            </div>
            <button class="btn-sm primary search-go" @click="searchSubmissionsByName">查询</button>
          </div>
          <div class="list-summary">共 {{ submissionsTotal }} 条</div>
        </div>
        <div v-if="submissionsLoading" class="loading">加载中...</div>
        <div v-else-if="submissions.length === 0" class="empty">暂无提交</div>
        <div v-else class="submissions-list">
          <div v-for="s in submissions" :key="s.id" class="submission-item">
            <div class="submission-header">
              <span class="student-name">{{ s.user?.name }}</span>
              <div class="status-group">
                <span v-if="s.is_late" class="status-badge late">迟交<button class="unlate-btn" title="取消迟交标签" @click.stop="unlateSubmission(s)">✕</button></span>
                <span class="status-badge" :class="s.status">{{ submissionStatusText(s) }}</span>
                <span v-if="s.task" class="task-badge" :class="s.task.status">{{ taskStatusText(s.task.status) }}</span>
              </div>
            </div>
            <div class="submission-images">
              <img v-for="(img, i) in s.images" :key="i" :src="getMediaUrl(img)" class="thumb" @click="previewImage(getMediaUrl(img))" />
            </div>
            <div v-if="s.report" class="report-preview">
              <div class="score">
                分数：{{ s.report.score ?? '--' }}<span v-if="s.report.full_score"> / {{ s.report.full_score }}</span>
                <span v-if="s.report.status" class="status-tag" :class="s.report.status">{{ reportStatusText(s.report.status) }}</span>
              </div>
              <div v-if="s.report.accuracy != null" class="report-meta">正确率：{{ formatAccuracy(s.report.accuracy) }} &nbsp; 对{{ s.report.correct_count ?? 0 }} / 错{{ s.report.wrong_count ?? 0 }}</div>
              <div class="feedback">{{ s.report.feedback }}</div>
            </div>
            <div v-if="s.status === 'returned' && s.return_reason" class="return-reason">
              <span class="return-label">打回原因：</span>{{ s.return_reason }}
            </div>
            <div v-if="s.task && s.task.status === 'failed'" class="task-error">
              <span class="error-label">批改失败：</span>{{ s.task.error_message || '未知错误' }}
              <span v-if="s.task.retry_count > 0" class="retry-info">(已重试 {{ s.task.retry_count }} 次)</span>
            </div>
            <div v-if="s.task && s.task.status === 'sent'" class="task-info">智能体批改中...</div>
            <div v-if="s.task && s.task.status === 'pending'" class="task-info">等待批改...</div>
            <div class="submission-actions">
              <button v-if="s.report || s.status === 'graded'" class="btn-sm" @click="openReportModal(s)">查看报告</button>
              <button v-if="canRegradeSubmission(s)" class="btn-sm" :disabled="regradingSubmissionId === s.id" @click="regradeSubmission(s)">
                {{ regradingSubmissionId === s.id ? '重批中...' : '重新智能批改' }}
              </button>
              <button v-if="s.status === 'pending'" class="btn-sm primary" @click="openGradeModal(s)">批改</button>
              <button v-if="s.status !== 'returned'" class="btn-sm danger" @click="openReturnModal(s)">打回重交</button>
            </div>
            <div class="submission-time">{{ formatDate(s.submitted_at) }}</div>
          </div>
        </div>
        <div class="modal-actions modal-actions-between">
          <div v-if="submissionsTotal > 0" class="list-pagination">
            <span class="list-pagination-meta">{{ pageRangeText(submissionsTotal, submissionsPage) }}</span>
            <div class="list-pagination-actions">
              <button class="btn-sm" :disabled="submissionsPage <= 1 || submissionsLoading" @click="changeSubmissionsPage(submissionsPage - 1)">上一页</button>
              <span>第 {{ submissionsPage }} / {{ totalPages(submissionsTotal) }} 页</span>
              <button class="btn-sm" :disabled="submissionsPage >= totalPages(submissionsTotal) || submissionsLoading" @click="changeSubmissionsPage(submissionsPage + 1)">下一页</button>
            </div>
          </div>
          <button class="btn-secondary" @click="showSubmissionsModal = false">关闭</button>
        </div>
      </div>
    </div>

    <div v-if="showReportModal" class="modal-overlay" @click.self="closeReportModal">
      <div class="modal modal-lg report-detail-modal">
        <div class="report-modal-header">
          <div>
            <h3>批改报告 - {{ reportSubmission?.user?.name || '学生' }}</h3>
            <div class="report-subtitle">提交时间：{{ formatDate(reportSubmission?.submitted_at) }}</div>
          </div>
          <span v-if="reportDetail?.status" class="status-tag" :class="reportDetail.status">{{ reportStatusText(reportDetail.status) }}</span>
        </div>

        <div v-if="reportLoading" class="loading report-loading">加载中...</div>
        <div v-else-if="reportError" class="task-error report-error">{{ reportError }}</div>
        <template v-else-if="reportDetail">
          <div class="report-summary-grid">
            <div class="report-summary-item">
              <span class="report-summary-label">总分</span>
              <strong class="report-summary-value">{{ reportDetail.score }}</strong>
            </div>
            <div class="report-summary-item">
              <span class="report-summary-label">满分</span>
              <strong class="report-summary-value">{{ reportDetail.full_score }}</strong>
            </div>
            <div class="report-summary-item">
              <span class="report-summary-label">正确率</span>
              <strong class="report-summary-value">{{ formatAccuracy(reportDetail.accuracy) }}</strong>
            </div>
            <div class="report-summary-item">
              <span class="report-summary-label">对错题数</span>
              <strong class="report-summary-value">对{{ reportDetail.correct_count }} / 错{{ reportDetail.wrong_count }}</strong>
            </div>
            <div class="report-summary-item">
              <span class="report-summary-label">生成方式</span>
              <strong class="report-summary-value">{{ reportDetail.generated_by || '未知' }}</strong>
            </div>
            <div class="report-summary-item">
              <span class="report-summary-label">生成时间</span>
              <strong class="report-summary-value">{{ formatDate(reportDetail.created_at) }}</strong>
            </div>
          </div>

          <div class="report-section">
            <div class="report-section-title">智能体反馈</div>
            <div class="report-feedback-block">{{ reportDetail.feedback || '暂无评语' }}</div>
          </div>

          <div v-if="getReportReviewQuestions(reportDetail).length" class="report-section">
            <div class="report-section-title">需复核题号</div>
            <div class="report-review-list">
              <span v-for="item in getReportReviewQuestions(reportDetail)" :key="`review-${item}`" class="review-chip">{{ item }}</span>
            </div>
          </div>

          <div v-if="getReportIssues(reportDetail).length" class="report-section">
            <div class="report-section-title">补充信息</div>
            <ul class="report-issues-list">
              <li v-for="(issue, index) in getReportIssues(reportDetail)" :key="`issue-${index}`">{{ issue }}</li>
            </ul>
          </div>

          <div v-if="getReportQuestions(reportDetail)?.length" class="report-section">
            <div class="report-section-title">逐题明细</div>
            <div class="report-question-list">
              <div v-for="question in getReportQuestions(reportDetail)" :key="question.key" class="report-question-item">
                <div class="report-question-head">
                  <span class="report-question-index">第{{ question.index }}题</span>
                  <span class="report-question-score">
                    <template v-if="hasDisplayValue(question.score)">{{ question.score }}</template>
                    <template v-else>--</template>
                    <template v-if="hasDisplayValue(question.maxScore)"> / {{ question.maxScore }}</template>
                  </span>
                  <span class="report-question-status" :class="questionStatusClass(question)">{{ questionStatusText(question) }}</span>
                </div>
                <div v-if="question.expectedAnswer" class="report-question-line">标准答案：{{ question.expectedAnswer }}</div>
                <div v-if="question.answer" class="report-question-line">识别答案：{{ question.answer }}</div>
                <div v-if="question.comment" class="report-question-line">说明：{{ question.comment }}</div>
              </div>
            </div>
          </div>

          <div v-else-if="formatReportDetailJson(reportDetail)" class="report-section">
            <div class="report-section-title">原始明细</div>
            <pre class="report-raw-json">{{ formatReportDetailJson(reportDetail) }}</pre>
          </div>
        </template>
        <div v-else class="empty report-empty">暂无批改报告</div>

        <div class="modal-actions">
          <button class="btn-secondary" @click="closeReportModal">关闭</button>
        </div>
      </div>
    </div>

    <div v-if="showUnsubmittedModal" class="modal-overlay" @click.self="showUnsubmittedModal = false">
      <div class="modal modal-lg">
        <h3>未交名单{{ currentViewSectionId ? ` - ${getSectionTitle(currentViewSectionId)}` : '' }}</h3>
        <div class="list-toolbar">
          <div class="list-search">
            <div class="search-input-wrap">
              <span class="search-icon">🔍</span>
              <input v-model="unsubmittedSearch" type="text" placeholder="按学生姓名查询" @keydown.enter.prevent="searchUnsubmittedByName" />
              <button v-if="unsubmittedSearch" class="search-clear" @click="resetUnsubmittedSearch" title="清空">✕</button>
            </div>
            <button class="btn-sm primary search-go" @click="searchUnsubmittedByName">查询</button>
          </div>
          <div class="list-summary">共 {{ unsubmittedTotal }} 人</div>
        </div>
        <div v-if="unsubmittedLoading" class="loading">加载中...</div>
        <div v-else-if="unsubmittedStudents.length === 0" class="empty">暂无未交学生</div>
        <div v-else class="submissions-list">
          <div v-for="u in unsubmittedStudents" :key="u.id" class="submission-item">
            <div class="submission-header">
              <span class="student-name">{{ u.name }}</span>
              <span>{{ u.class_name || '未分配班级' }}</span>
            </div>
          </div>
        </div>
        <div class="modal-actions modal-actions-between">
          <div v-if="unsubmittedTotal > 0" class="list-pagination">
            <span class="list-pagination-meta">{{ pageRangeText(unsubmittedTotal, unsubmittedPage) }}</span>
            <div class="list-pagination-actions">
              <button class="btn-sm" :disabled="unsubmittedPage <= 1 || unsubmittedLoading" @click="changeUnsubmittedPage(unsubmittedPage - 1)">上一页</button>
              <span>第 {{ unsubmittedPage }} / {{ totalPages(unsubmittedTotal) }} 页</span>
              <button class="btn-sm" :disabled="unsubmittedPage >= totalPages(unsubmittedTotal) || unsubmittedLoading" @click="changeUnsubmittedPage(unsubmittedPage + 1)">下一页</button>
            </div>
          </div>
          <button class="btn-secondary" @click="showUnsubmittedModal = false">关闭</button>
        </div>
      </div>
    </div>

    <div v-if="showLateModal" class="modal-overlay" @click.self="showLateModal = false">
      <div class="modal modal-lg">
        <h3>迟交名单{{ currentViewSectionId ? ` - ${getSectionTitle(currentViewSectionId)}` : '' }}</h3>
        <div class="list-toolbar">
          <div class="list-search">
            <div class="search-input-wrap">
              <span class="search-icon">🔍</span>
              <input v-model="lateSearch" type="text" placeholder="按学生姓名查询" @keydown.enter.prevent="searchLateByName" />
              <button v-if="lateSearch" class="search-clear" @click="resetLateSearch" title="清空">✕</button>
            </div>
            <button class="btn-sm primary search-go" @click="searchLateByName">查询</button>
          </div>
          <div class="list-summary">共 {{ lateTotal }} 条</div>
        </div>
        <div v-if="lateLoading" class="loading">加载中...</div>
        <div v-else-if="lateSubmissions.length === 0" class="empty">暂无迟交学生</div>
        <div v-else class="submissions-list">
          <div v-for="s in lateSubmissions" :key="s.id" class="submission-item">
            <div class="submission-header">
              <span class="student-name">{{ s.user?.name }}</span>
              <div class="status-group">
                <span class="status-badge late">迟交<button class="unlate-btn" title="取消迟交标签" @click.stop="unlateSubmission(s)">✕</button></span>
                <span class="status-badge" :class="s.status">{{ s.status === 'graded' ? '已批改' : '待批改' }}</span>
              </div>
            </div>
            <div class="submission-meta">
              <span>{{ s.user?.class_name || '未分配班级' }}</span>
              <span>提交时间：{{ formatDate(s.submitted_at) }}</span>
            </div>
          </div>
        </div>
        <div class="modal-actions modal-actions-between">
          <div v-if="lateTotal > 0" class="list-pagination">
            <span class="list-pagination-meta">{{ pageRangeText(lateTotal, latePage) }}</span>
            <div class="list-pagination-actions">
              <button class="btn-sm" :disabled="latePage <= 1 || lateLoading" @click="changeLatePage(latePage - 1)">上一页</button>
              <span>第 {{ latePage }} / {{ totalPages(lateTotal) }} 页</span>
              <button class="btn-sm" :disabled="latePage >= totalPages(lateTotal) || lateLoading" @click="changeLatePage(latePage + 1)">下一页</button>
            </div>
          </div>
          <button class="btn-secondary" @click="showLateModal = false">关闭</button>
        </div>
      </div>
    </div>

    <div v-if="showStudentLookupModal" class="modal-overlay" @click.self="showStudentLookupModal = false">
      <div class="modal modal-lg">
        <h3>查询学生 - {{ getSectionTitle(studentLookupSectionId) }}</h3>
        <div class="form-group" style="margin-bottom: 16px;">
          <input v-model="studentSearchQuery" type="text" placeholder="输入学生姓名或账号搜索..." @input="debouncedSearchStudent" />
          <span v-if="searchingStudent" class="loading" style="display:inline;margin-left:8px;">搜索中...</span>
        </div>
        <div v-if="selectedStudent && !studentSubmissionsLoading" class="selected-student-info" style="margin-bottom:12px;padding:8px 12px;background:#f0f5ff;border-radius:6px;">
          已选择：<strong>{{ selectedStudent.name }}</strong>
          <span v-if="selectedStudent.class_name">（{{ selectedStudent.class_name }}）</span>
          <button class="btn-sm" style="margin-left:12px;" @click="selectedStudent = null; studentSearchQuery = ''; searchResults = []; studentSubmissions = []">更换学生</button>
        </div>
        <div v-if="!selectedStudent && searchResults.length > 0" class="student-search-results" style="max-height:200px;overflow-y:auto;margin-bottom:12px;">
          <div v-for="u in searchResults" :key="u.id" class="submission-item" style="cursor:pointer;" @click="selectStudent(u)">
            <div class="submission-header">
              <span class="student-name">{{ u.name }}</span>
              <span>{{ u.class_name || '未分配班级' }}</span>
            </div>
          </div>
        </div>
        <div v-if="selectedStudent && studentSubmissionsLoading" class="loading">加载提交记录中...</div>
        <div v-else-if="selectedStudent && studentSubmissions.length === 0" class="empty">该学生暂无提交记录</div>
        <div v-else-if="studentSubmissions.length > 0" class="submissions-list">
          <div v-for="s in studentSubmissions" :key="s.id" class="submission-item">
            <div class="submission-header">
              <span class="student-name">{{ s.user?.name }} <span v-if="studentSubmissions.length > 1" class="version-badge">v{{ s.version }}{{ s.is_latest ? ' (最新)' : '' }}</span></span>
              <div class="status-group">
                <span v-if="s.is_late" class="status-badge late">迟交<button class="unlate-btn" title="取消迟交标签" @click.stop="unlateSubmission(s)">✕</button></span>
                <span class="status-badge" :class="s.status">{{ s.status === 'graded' ? '已批改' : '待批改' }}</span>
                <span v-if="s.task" class="task-badge" :class="s.task.status">{{ taskStatusText(s.task.status) }}</span>
              </div>
            </div>
            <div class="submission-images">
              <img v-for="(img, i) in s.images" :key="i" :src="getMediaUrl(img)" class="thumb" @click="previewImage(getMediaUrl(img))" />
            </div>
            <div v-if="s.report" class="report-preview">
              <div class="score">
                分数：{{ s.report.score ?? '--' }}<span v-if="s.report.full_score"> / {{ s.report.full_score }}</span>
                <span v-if="s.report.status" class="status-tag" :class="s.report.status">{{ reportStatusText(s.report.status) }}</span>
              </div>
              <div v-if="s.report.accuracy != null" class="report-meta">正确率：{{ formatAccuracy(s.report.accuracy) }} &nbsp; 对{{ s.report.correct_count ?? 0 }} / 错{{ s.report.wrong_count ?? 0 }}</div>
              <div class="feedback">{{ s.report.feedback }}</div>
            </div>
            <div v-if="s.task && s.task.status === 'failed'" class="task-error">
              <span class="error-label">批改失败：</span>{{ s.task.error_message || '未知错误' }}
              <span v-if="s.task.retry_count > 0" class="retry-info">(已重试 {{ s.task.retry_count }} 次)</span>
            </div>
            <div v-if="s.task && s.task.status === 'sent'" class="task-info">智能体批改中...</div>
            <div v-if="s.task && s.task.status === 'pending'" class="task-info">等待批改...</div>
            <div class="submission-actions">
              <button v-if="s.report || s.status === 'graded'" class="btn-sm" @click="openReportModal(s)">查看报告</button>
              <button v-if="canRegradeSubmission(s)" class="btn-sm" :disabled="regradingSubmissionId === s.id" @click="regradeSubmission(s)">
                {{ regradingSubmissionId === s.id ? '重批中...' : '重新智能批改' }}
              </button>
              <button v-if="s.status === 'pending'" class="btn-sm primary" @click="openGradeModal(s)">批改</button>
            </div>
            <div class="submission-time">{{ formatDate(s.submitted_at) }}</div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn-secondary" @click="showStudentLookupModal = false">关闭</button>
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

    <div v-if="showReturnModal" class="modal-overlay" @click.self="showReturnModal = false">
      <div class="modal">
        <h3>打回重交 - {{ returnSubmission?.user?.name }}</h3>
        <div class="form-group">
          <label>打回原因</label>
          <textarea v-model="returnReason" placeholder="请说明打回原因，学生将看到此原因并重新提交" rows="4"></textarea>
        </div>
        <div v-if="returnSubmitting" class="loading">提交中...</div>
        <div class="modal-actions">
          <button class="btn-secondary" @click="showReturnModal = false">取消</button>
          <button class="btn-primary danger" :disabled="returnSubmitting" @click="submitReturn">确认打回</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useDingTalk } from '../composables/useDingTalk.js'
import api from '../utils/api.js'
import {
  getAttachmentDisplayName,
  getAttachmentDownloadName,
  getAbsoluteMediaUrl,
  getMediaUrl,
  isDocumentFile,
  isImageFile,
  isPdf,
  toAbsoluteUrl,
  openFileDownload,
} from '../utils/homeworkFiles.js'

const route = useRoute()
const courseId = route.params.courseId
const { isDingTalk, previewFile } = useDingTalk()
const LIST_PAGE_SIZE = 20

const loading = ref(false)
const sections = ref([])
const assignmentMap = ref({})
const submissions = ref([])
const submissionsTotal = ref(0)
const submissionsPage = ref(1)
const submissionsSearch = ref('')
const submissionsLoading = ref(false)
const unsubmittedStudents = ref([])
const unsubmittedTotal = ref(0)
const unsubmittedPage = ref(1)
const unsubmittedSearch = ref('')
const unsubmittedLoading = ref(false)
const lateSubmissions = ref([])
const lateTotal = ref(0)
const latePage = ref(1)
const lateSearch = ref('')
const lateLoading = ref(false)
const ANSWER_TYPE_DEFAULT_SCORE = {
  option_letter: 2,
  true_false: 1,
  fill_blank: 2,
}
const showCreateModal = ref(false)
const showEditModal = ref(false)
const showAnswerModal = ref(false)
const showBatchAnswerModal = ref(false)
const showSubmissionsModal = ref(false)
const showUnsubmittedModal = ref(false)
const showLateModal = ref(false)
const showGradeModal = ref(false)
const showReportModal = ref(false)
const gradingSubmission = ref(null)
const reportSubmission = ref(null)
const reportDetail = ref(null)
const reportLoading = ref(false)
const reportError = ref('')
const gradeForm = ref({ score: '', feedback: '' })
const gradeSubmitting = ref(false)
const answerParsing = ref(false)
const batchAnswerRows = ref([])
const currentSection = ref(null)
const currentViewSectionId = ref(null)
const triggeringSection = ref(null)
const triggerStatus = ref(null)
const regradingSubmissionId = ref(null)
const showAnswerPreview = ref(false)
const quickAnswerFieldRef = ref(null)
const quickAnswerBarRef = ref(null)
const showStudentLookupModal = ref(false)
const studentSearchQuery = ref('')
const searchResults = ref([])
const searchingStudent = ref(false)
const selectedStudent = ref(null)
const studentLookupSectionId = ref(null)
const studentSubmissions = ref([])
const studentSubmissionsLoading = ref(false)
const showReturnModal = ref(false)
const returnSubmission = ref(null)
const returnReason = ref('')
const returnSubmitting = ref(false)
let pollTimer = null
let regradeTimer = null
let studentSearchTimer = null

function getNextAnswerNo(rows = form.value?.answer_items || []) {
  const numericNos = rows
    .map(item => String(item?.no ?? '').trim())
    .filter(no => /^\d+$/.test(no))
    .map(no => Number(no))

  if (!numericNos.length) {
    return rows.length ? String(rows.length + 1) : '1'
  }
  return String(Math.max(...numericNos) + 1)
}

function emptyForm() {
  return {
    title: '',
    description: '',
    question_files: [],
    answer_files: [],
    grading_prompt: '',
    grading_mode: 'auto',
    deadline: '',
    auto_grade_at: '',
    section_id: null,
    answer_items: [],
  }
}

const form = ref(emptyForm())
const quickAnswerItem = ref(createAnswerItem({ no: '1' }))

const answerJsonPreview = computed(() => JSON.stringify(serializeAnswerItems(collectAnswerItems(form.value.answer_items).items), null, 2))

onMounted(() => {
  loadData()
})

onUnmounted(() => {
  stopPolling()
  stopRegradePolling()
})

function getAssignment(sectionId) {
  return assignmentMap.value[sectionId]
}

function normalizeAnswerType(type) {
  const normalized = String(type ?? '').trim().toLowerCase()
  if (['choice', 'single_choice', 'multiple_choice', 'option_letter'].includes(normalized)) return 'option_letter'
  if (['judge', 'true_false'].includes(normalized)) return 'true_false'
  if (['fill', 'fill_blank'].includes(normalized)) return 'fill_blank'
  return 'option_letter'
}

function normalizeAnswerText(type, value) {
  const text = String(value ?? '')
  if (type === 'option_letter') {
    return text.replace(/[\s,，、]+/g, '').toUpperCase()
  }
  if (type === 'true_false') {
    const cleaned = text.trim().toUpperCase()
    if (['T', 'TRUE', '1', 'Y', 'YES', '对', '正确', '√'].includes(cleaned)) return 'T'
    if (['F', 'FALSE', '0', 'N', 'NO', '错', '错误', '×'].includes(cleaned)) return 'F'
    return cleaned
  }
  return text.replace(/\r\n/g, '\n').trim()
}

function normalizeAnswerScore(type, value) {
  if (value === null || value === undefined || value === '') {
    return ANSWER_TYPE_DEFAULT_SCORE[type] ?? 2
  }
  const normalized = Number(value)
  if (!Number.isFinite(normalized) || normalized < 0) {
    return ANSWER_TYPE_DEFAULT_SCORE[type] ?? 2
  }
  return Math.trunc(normalized)
}

function createAnswerItem(overrides = {}) {
  const type = normalizeAnswerType(overrides.type)
  return {
    no: String(overrides.no ?? '').trim(),
    type,
    answer: normalizeAnswerText(type, overrides.answer),
    score: normalizeAnswerScore(type, overrides.score),
  }
}

function resetQuickAnswerItem(overrides = {}) {
  quickAnswerItem.value = createAnswerItem({
    no: getNextAnswerNo(),
    type: overrides.type ?? quickAnswerItem.value?.type ?? 'option_letter',
    score: overrides.score ?? quickAnswerItem.value?.score ?? ANSWER_TYPE_DEFAULT_SCORE.option_letter,
    answer: '',
  })
}

async function focusQuickAnswerField() {
  await nextTick()
  quickAnswerBarRef.value?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  quickAnswerFieldRef.value?.focus?.()
  quickAnswerFieldRef.value?.select?.()
}

function extractAnswerEntries(raw) {
  if (Array.isArray(raw)) {
    return raw.map(item => [item?.no, item]).filter(([, item]) => item && typeof item === 'object')
  }
  if (!raw || typeof raw !== 'object') return []
  if (Array.isArray(raw.items)) {
    return raw.items.map(item => [item?.no, item]).filter(([, item]) => item && typeof item === 'object')
  }
  return Object.entries(raw).filter(([key]) => key !== 'version' && key !== 'items')
}

function parseAnswerItems(raw) {
  if (!raw) return []
  try {
    const obj = typeof raw === 'string' ? JSON.parse(raw) : raw
    return extractAnswerEntries(obj)
      .map(([no, item]) => {
        const source = item && typeof item === 'object' ? item : {}
        const type = normalizeAnswerType(source.type ?? source.question_type)
        return createAnswerItem({
          no: String(no ?? source.no ?? '').trim(),
          type,
          answer: source.answer,
          score: source.score,
        })
      })
      .filter(item => item.no || item.answer)
  } catch {
    return []
  }
}

function collectAnswerItems(rows) {
  const items = []
  const errors = []
  const seenNos = new Set()

  rows.forEach((item, index) => {
    const no = String(item.no ?? '').trim()
    const type = normalizeAnswerType(item.type)
    const rawAnswer = String(item.answer ?? '')
    const answer = normalizeAnswerText(type, rawAnswer)
    const hasContent = no || rawAnswer.trim()

    if (!hasContent) {
      return
    }

    if (!no) {
      errors.push(`第 ${index + 1} 行缺少题号`)
      return
    }

    if (!rawAnswer.trim()) {
      errors.push(`第 ${index + 1} 行缺少答案`)
      return
    }

    if (seenNos.has(no)) {
      errors.push(`第 ${index + 1} 行题号 ${no} 重复`)
      return
    }

    if (type === 'option_letter' && !/^[A-Z]+$/.test(answer)) {
      errors.push(`第 ${index + 1} 行选项字母答案格式无效`)
      return
    }

    if (type === 'true_false' && !['T', 'F'].includes(answer)) {
      errors.push(`第 ${index + 1} 行判断题答案只能是 T 或 F`)
      return
    }

    items.push({
      no,
      type,
      answer,
      score: normalizeAnswerScore(type, item.score),
    })
    seenNos.add(no)
  })

  return { items, errors }
}

function serializeAnswerItems(items) {
  return items.reduce((acc, item) => {
    acc[item.no] = {
      answer: item.answer,
      type: item.type,
      score: item.score,
    }
    return acc
  }, {})
}

function buildAnswerObject(rows = form.value.answer_items) {
  return serializeAnswerItems(collectAnswerItems(rows).items)
}

function buildAnswerJson(rows = form.value.answer_items) {
  const { items } = collectAnswerItems(rows)
  const payload = serializeAnswerItems(items)
  return Object.keys(payload).length ? JSON.stringify(payload) : ''
}

function hasAnswer(assignment) {
  return parseAnswerItems(assignment?.reference_answer).length > 0
}

function addAnswerItem() {
  const lastItem = form.value.answer_items.at(-1)
  form.value.answer_items.push(createAnswerItem({
    no: getNextAnswerNo(),
    type: lastItem?.type ?? quickAnswerItem.value.type,
    score: lastItem?.score ?? quickAnswerItem.value.score,
  }))
  resetQuickAnswerItem({
    type: lastItem?.type ?? quickAnswerItem.value.type,
    score: lastItem?.score ?? quickAnswerItem.value.score,
  })
}

function removeAnswerItem(index) {
  form.value.answer_items.splice(index, 1)
  resetQuickAnswerItem()
}

function appendQuickAnswer() {
  const candidate = createAnswerItem(quickAnswerItem.value)
  const existingNos = new Set(form.value.answer_items.map(item => String(item.no ?? '').trim()).filter(Boolean))

  if (existingNos.has(candidate.no)) {
    alert(`题号 ${candidate.no} 已存在，请修改后再追加`)
    return
  }

  const { items, errors } = collectAnswerItems([candidate])
  if (errors.length) {
    alert(errors[0].replace('第 1 行', '快速录入'))
    return
  }

  form.value.answer_items.push(items[0])
  resetQuickAnswerItem({ type: candidate.type, score: candidate.score })
  focusQuickAnswerField()
}

function handleQuickAnswerKeydown(event) {
  if (event.isComposing || event.key !== 'Enter') return
  if (
    quickAnswerItem.value.type === 'fill_blank'
    && event.target?.tagName === 'TEXTAREA'
    && !(event.ctrlKey || event.metaKey)
  ) return
  event.preventDefault()
  appendQuickAnswer()
}

function resetBatchAnswerRows(count = 3) {
  batchAnswerRows.value = Array.from({ length: count }, () => createAnswerItem())
}

function openBatchAnswerModal() {
  resetBatchAnswerRows()
  showBatchAnswerModal.value = true
}

function closeBatchAnswerModal() {
  showBatchAnswerModal.value = false
  batchAnswerRows.value = []
}

function addBatchAnswerRow() {
  batchAnswerRows.value.push(createAnswerItem())
}

function removeBatchAnswerRow(index) {
  batchAnswerRows.value.splice(index, 1)
}

function appendBatchAnswers() {
  const { items, errors } = collectAnswerItems(batchAnswerRows.value)
  if (errors.length) {
    alert(errors[0])
    return
  }
  if (items.length === 0) {
    alert('请至少填写一行完整答案')
    return
  }

  const existingNos = new Set(form.value.answer_items.map(item => String(item.no ?? '').trim()).filter(Boolean))
  for (const item of items) {
    if (existingNos.has(item.no)) {
      alert(`题号 ${item.no} 已存在，请先修改后再追加`)
      return
    }
    existingNos.add(item.no)
  }

  form.value.answer_items.push(...items.map(createAnswerItem))
  closeBatchAnswerModal()
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
    await restoreGradingProgress()
  } catch (e) {
    alert('加载失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

async function restoreGradingProgress() {
  if (triggeringSection.value) return

  stopPolling()
  triggeringSection.value = null
  triggerStatus.value = null

  for (const section of sections.value) {
    const assignment = assignmentMap.value[section.id]
    if (!assignment) continue
    if (assignment.status !== 'published' || assignment.grading_mode === 'manual') continue
    if (!assignment.grading_triggered || assignment.grading_status === 'graded') continue

    try {
      const res = await api.get(`/homework/trigger-status/${assignment.id}`)
      const status = res.data.data
      if (!status?.total || !status.task_count || status.done >= status.total) continue

      triggeringSection.value = section.id
      triggerStatus.value = status
      pollTimer = setInterval(() => pollGradingStatus(assignment.id), 3000)
      return
    } catch (e) {
      console.error('恢复批改进度失败', e)
    }
  }
}

function openCreateForSection(section) {
  currentSection.value = section
  form.value = {
    ...emptyForm(),
    title: `${section.title} 作业`,
    section_id: section.id,
  }
  showAnswerPreview.value = false
  resetQuickAnswerItem()
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
    answer_files: assignment.answer_files ? [...assignment.answer_files] : [],
    grading_prompt: assignment.grading_prompt || '',
    grading_mode: assignment.grading_mode || 'auto',
    deadline: assignment.deadline ? assignment.deadline.slice(0, 16) : '',
    auto_grade_at: assignment.auto_grade_at ? assignment.auto_grade_at.slice(0, 16) : '',
    section_id: section.id,
    answer_items: parseAnswerItems(assignment.reference_answer),
  }
  showAnswerPreview.value = false
  resetQuickAnswerItem()
  showEditModal.value = true
}

function openAnswerForSection(section) {
  const assignment = assignmentMap.value[section.id]
  if (!assignment) return
  currentSection.value = section
  form.value = {
    ...emptyForm(),
    section_id: section.id,
    answer_files: assignment.answer_files ? [...assignment.answer_files] : [],
    answer_items: parseAnswerItems(assignment.reference_answer),
  }
  showAnswerPreview.value = false
  resetQuickAnswerItem()
  showAnswerModal.value = true
  focusQuickAnswerField()
}

async function saveAssignment() {
  if (!form.value.title.trim()) {
    alert('请输入作业标题')
    return
  }
  const { items, errors } = collectAnswerItems(form.value.answer_items)
  if (errors.length) {
    alert(errors[0])
    return
  }
  const payload = {
    title: form.value.title.trim(),
    description: form.value.description,
    question_files: form.value.question_files,
    answer_files: form.value.answer_files,
    grading_prompt: form.value.grading_prompt,
    reference_answer: items.length ? JSON.stringify(serializeAnswerItems(items)) : '',
    grading_mode: form.value.grading_mode,
    deadline: form.value.deadline || null,
    auto_grade_at: form.value.auto_grade_at || null,
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
  showBatchAnswerModal.value = false
  showAnswerPreview.value = false
  currentSection.value = null
  form.value = emptyForm()
  resetQuickAnswerItem()
}

function closeAnswerModal() {
  showAnswerModal.value = false
  showBatchAnswerModal.value = false
  showAnswerPreview.value = false
  currentSection.value = null
  form.value = emptyForm()
  resetQuickAnswerItem()
}

async function saveAnswer() {
  if (!form.value.section_id) return
  const { items, errors } = collectAnswerItems(form.value.answer_items)
  if (errors.length) {
    alert(errors[0])
    return
  }
  try {
    await api.put(`/homework/assignments/${form.value.section_id}/answer`, {
      answer: items.length ? JSON.stringify(serializeAnswerItems(items)) : '',
      answer_files: form.value.answer_files,
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

async function handleAnswerAttachmentSelect(e) {
  const files = Array.from(e.target.files || [])
  for (const file of files) {
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await api.post('/homework/upload-answer', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      form.value.answer_files.push(res.data.data.url)
    } catch (err) {
      alert('答案附件上传失败：' + (err.response?.data?.detail || err.message))
    }
  }
  e.target.value = ''
}

function removeQuestionFile(index) {
  form.value.question_files.splice(index, 1)
}

function removeAnswerFile(index) {
  form.value.answer_files.splice(index, 1)
}

function buildPagedParams(page, search, extra = {}) {
  const params = { page, page_size: LIST_PAGE_SIZE, ...extra }
  const normalizedSearch = (search || '').trim()
  if (normalizedSearch) params.search = normalizedSearch
  return params
}

function totalPages(total) {
  return Math.max(1, Math.ceil((total || 0) / LIST_PAGE_SIZE))
}

function pageRangeText(total, page) {
  if (!total) return '0 / 0'
  const start = (page - 1) * LIST_PAGE_SIZE + 1
  const end = Math.min(page * LIST_PAGE_SIZE, total)
  return `${start}-${end} / ${total}`
}

async function loadSectionSubmissions(sectionId, page = submissionsPage.value) {
  currentViewSectionId.value = sectionId
  submissionsLoading.value = true
  try {
    const res = await api.get(`/homework/assignments/${sectionId}/submissions`, {
      params: buildPagedParams(page, submissionsSearch.value),
    })
    const data = res.data.data || {}
    const items = data.items || []
    const total = data.total || 0
    if (!items.length && total > 0 && page > 1) {
      return await loadSectionSubmissions(sectionId, page - 1)
    }
    submissions.value = items
    submissionsTotal.value = total
    submissionsPage.value = data.page || page
  } finally {
    submissionsLoading.value = false
  }
}

async function loadLateSectionSubmissions(sectionId, page = latePage.value) {
  currentViewSectionId.value = sectionId
  lateLoading.value = true
  try {
    const res = await api.get(`/homework/assignments/${sectionId}/submissions`, {
      params: buildPagedParams(page, lateSearch.value, { late_only: true }),
    })
    const data = res.data.data || {}
    const items = data.items || []
    const total = data.total || 0
    if (!items.length && total > 0 && page > 1) {
      return await loadLateSectionSubmissions(sectionId, page - 1)
    }
    lateSubmissions.value = items
    lateTotal.value = total
    latePage.value = data.page || page
  } finally {
    lateLoading.value = false
  }
}

async function loadUnsubmittedStudentsPage(sectionId, page = unsubmittedPage.value) {
  currentViewSectionId.value = sectionId
  unsubmittedLoading.value = true
  try {
    const res = await api.get(`/homework/assignments/${sectionId}/submissions-summary`, {
      params: buildPagedParams(page, unsubmittedSearch.value),
    })
    const data = res.data.data || {}
    const items = data.unsubmitted_students || []
    const total = data.total || 0
    if (!items.length && total > 0 && page > 1) {
      return await loadUnsubmittedStudentsPage(sectionId, page - 1)
    }
    unsubmittedStudents.value = items
    unsubmittedTotal.value = total
    unsubmittedPage.value = data.page || page
  } catch {
    unsubmittedStudents.value = []
    unsubmittedTotal.value = 0
  } finally {
    unsubmittedLoading.value = false
  }
}

async function loadSubmissions(sectionId, options = {}) {
  const { reset = false, openModal = true } = options
  if (reset) {
    submissionsSearch.value = ''
    submissionsPage.value = 1
  }
  try {
    await loadSectionSubmissions(sectionId, submissionsPage.value)
    if (openModal) {
      showSubmissionsModal.value = true
      showLateModal.value = false
    }
  } catch (e) {
    alert('加载失败：' + (e.response?.data?.detail || e.message))
  }
}

async function searchSubmissionsByName() {
  if (!currentViewSectionId.value) return
  submissionsPage.value = 1
  try {
    await loadSectionSubmissions(currentViewSectionId.value, 1)
  } catch (e) {
    alert('加载失败：' + (e.response?.data?.detail || e.message))
  }
}

async function resetSubmissionsSearch() {
  submissionsSearch.value = ''
  await searchSubmissionsByName()
}

async function changeSubmissionsPage(page) {
  if (!currentViewSectionId.value || page < 1 || page > totalPages(submissionsTotal.value)) return
  try {
    await loadSectionSubmissions(currentViewSectionId.value, page)
  } catch (e) {
    alert('加载失败：' + (e.response?.data?.detail || e.message))
  }
}

async function openLateModal(sectionId) {
  lateSearch.value = ''
  latePage.value = 1
  try {
    await loadLateSectionSubmissions(sectionId, 1)
    showLateModal.value = true
    showSubmissionsModal.value = false
  } catch (e) {
    alert('加载失败：' + (e.response?.data?.detail || e.message))
  }
}

async function searchLateByName() {
  if (!currentViewSectionId.value) return
  latePage.value = 1
  try {
    await loadLateSectionSubmissions(currentViewSectionId.value, 1)
  } catch (e) {
    alert('加载失败：' + (e.response?.data?.detail || e.message))
  }
}

async function resetLateSearch() {
  lateSearch.value = ''
  await searchLateByName()
}

async function changeLatePage(page) {
  if (!currentViewSectionId.value || page < 1 || page > totalPages(lateTotal.value)) return
  try {
    await loadLateSectionSubmissions(currentViewSectionId.value, page)
  } catch (e) {
    alert('加载失败：' + (e.response?.data?.detail || e.message))
  }
}

async function unlateSubmission(submission) {
  if (!confirm('确定取消该提交的「迟交」标签？')) return
  try {
    await api.patch(`/homework/submissions/${submission.id}/unlate`)
    if (showSubmissionsModal.value && currentViewSectionId.value) {
      await loadSectionSubmissions(currentViewSectionId.value, submissionsPage.value)
    }
    if (showLateModal.value && currentViewSectionId.value) {
      await loadLateSectionSubmissions(
        currentViewSectionId.value,
        lateSubmissions.value.length === 1 && latePage.value > 1 ? latePage.value - 1 : latePage.value,
      )
    }
    if (showStudentLookupModal.value && selectedStudent.value) {
      await selectStudent(selectedStudent.value)
    }
  } catch (e) {
    alert('操作失败：' + (e.response?.data?.detail || e.message))
  }
}

async function openUnsubmittedModal(sectionId) {
  unsubmittedSearch.value = ''
  unsubmittedPage.value = 1
  await loadUnsubmittedStudentsPage(sectionId, 1)
  showUnsubmittedModal.value = true
}

async function searchUnsubmittedByName() {
  if (!currentViewSectionId.value) return
  unsubmittedPage.value = 1
  await loadUnsubmittedStudentsPage(currentViewSectionId.value, 1)
}

async function resetUnsubmittedSearch() {
  unsubmittedSearch.value = ''
  await searchUnsubmittedByName()
}

async function changeUnsubmittedPage(page) {
  if (!currentViewSectionId.value || page < 1 || page > totalPages(unsubmittedTotal.value)) return
  await loadUnsubmittedStudentsPage(currentViewSectionId.value, page)
}

function openStudentLookup(sectionId) {
  studentLookupSectionId.value = sectionId
  studentSearchQuery.value = ''
  searchResults.value = []
  selectedStudent.value = null
  studentSubmissions.value = []
  showStudentLookupModal.value = true
}

function debouncedSearchStudent() {
  if (studentSearchTimer) clearTimeout(studentSearchTimer)
  const q = studentSearchQuery.value
  if (!q || q.length < 1) { searchResults.value = []; return }
  studentSearchTimer = setTimeout(async () => {
    searchingStudent.value = true
    try {
      const res = await api.get('/admin/users', { params: { role: 'student', search: q } })
      searchResults.value = res.data.data || []
    } catch {
      searchResults.value = []
    } finally {
      searchingStudent.value = false
    }
  }, 300)
}

async function selectStudent(user) {
  selectedStudent.value = user
  searchResults.value = []
  studentSearchQuery.value = user.name
  const sectionId = studentLookupSectionId.value
  if (!sectionId || !user?.id) return
  studentSubmissionsLoading.value = true
  try {
    const res = await api.get(`/homework/assignments/${sectionId}/student-submissions`, {
      params: { user_id: user.id }
    })
    studentSubmissions.value = res.data.data || []
  } catch (e) {
    alert('加载学生提交失败：' + (e.response?.data?.detail || e.message))
    studentSubmissions.value = []
  } finally {
    studentSubmissionsLoading.value = false
  }
}

function statusText(status) {
  return { draft: '草稿', published: '已发布', closed: '已关闭', returned: '已打回' }[status] || status
}

function submissionStatusText(s) {
  if (s.status === 'returned') return '已打回'
  if (s.status === 'graded') return '已批改'
  return '待批改'
}

function gradingStatusText(status) {
  return { pending: '待批改', graded: '已批改' }[status] || status
}

function getSectionTitle(sectionId) {
  return sections.value.find(section => section.id === sectionId)?.title || ''
}

function taskStatusText(status) {
  return { pending: '待发送', sent: '已发送', graded: '已批改', failed: '失败' }[status] || status
}

function reportStatusText(status) {
  return { success: '成功', partial: '部分成功', degraded: '降级', failed: '失败' }[status] || status || '未知'
}

function hasDisplayValue(value) {
  return value !== null && value !== undefined && value !== ''
}

function formatAccuracy(value) {
  if (value === null || value === undefined || value === '') return '--'
  const normalized = Number(value)
  if (!Number.isFinite(normalized)) return '--'
  return `${(normalized * 100).toFixed(0)}%`
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString('zh-CN')
}

function parseReportDetail(report) {
  if (!report?.detail) return null
  try {
    return typeof report.detail === 'string' ? JSON.parse(report.detail) : report.detail
  } catch {
    return null
  }
}

function normalizeReportQuestionRef(item) {
  if (item === null || item === undefined) return ''
  if (typeof item === 'object') {
    return String(item.question_id ?? item.qid ?? item.index ?? item.no ?? item.key ?? '').trim()
  }
  return String(item).trim()
}

function formatReportError(error) {
  if (!error) return ''
  if (typeof error === 'string') return error.trim()
  if (typeof error === 'object') {
    const code = String(error.code ?? '').trim()
    const message = String(error.message ?? error.detail ?? error.msg ?? '').trim()
    if (code && message) return `${code}: ${message}`
    if (message) return message
    try {
      return JSON.stringify(error)
    } catch {
      return ''
    }
  }
  return String(error).trim()
}

function getReportReviewQuestions(report) {
  const detail = parseReportDetail(report)
  const merged = [
    ...(Array.isArray(report?.review_questions) ? report.review_questions : []),
    ...(Array.isArray(detail?.review) ? detail.review : []),
    ...(Array.isArray(detail?.low_confidence_questions) ? detail.low_confidence_questions : []),
    ...(Array.isArray(detail?.result?.low_confidence_questions) ? detail.result.low_confidence_questions : []),
  ]
  return [...new Set(merged.map(normalizeReportQuestionRef).filter(Boolean))]
}

function getReportIssues(report) {
  const detail = parseReportDetail(report)
  if (!detail) return []

  const issues = []
  if (Array.isArray(detail.issues)) {
    issues.push(...detail.issues.map(item => String(item ?? '').trim()).filter(Boolean))
  }
  const errorText = formatReportError(detail.error ?? detail.result?.error)
  if (errorText) {
    issues.push(`批改异常：${errorText}`)
  }
  return issues
}

function getReportQuestions(report) {
  const detail = parseReportDetail(report)
  if (!detail) return null

  const source = [
    Array.isArray(detail.questions) && detail.questions.length ? detail.questions : null,
    Array.isArray(detail.details) && detail.details.length ? detail.details : null,
    Array.isArray(detail.result?.details) && detail.result.details.length ? detail.result.details : null,
  ].find(Boolean)

  if (!source?.length) return null

  return source.map((item, index) => ({
    key: `${item?.index ?? item?.qid ?? item?.question_id ?? item?.no ?? index + 1}-${index}`,
    index: item?.index ?? item?.qid ?? item?.question_id ?? item?.no ?? index + 1,
    correct: typeof item?.correct === 'boolean'
      ? item.correct
      : typeof item?.ok === 'boolean'
        ? item.ok
        : typeof item?.is_correct === 'boolean'
          ? item.is_correct
          : null,
    score: item?.score ?? item?.s ?? item?.obtained_score ?? item?.points ?? null,
    maxScore: item?.max_score ?? item?.fs ?? item?.full_score ?? item?.total_score ?? item?.fullScore ?? null,
    comment: item?.comment ?? item?.feedback ?? item?.reason ?? item?.analysis ?? '',
    answer: item?.answer ?? item?.student_answer ?? item?.studentAnswer ?? '',
    expectedAnswer: item?.expected_answer ?? item?.reference_answer ?? item?.correct_answer ?? item?.answer_key ?? '',
    matchStatus: item?.match_status ?? item?.status ?? '',
    confidence: item?.confidence ?? '',
  }))
}

function formatReportDetailJson(report) {
  const detail = parseReportDetail(report)
  if (!detail) return ''
  try {
    return JSON.stringify(detail, null, 2)
  } catch {
    return ''
  }
}

function questionStatusText(question) {
  if (question.correct === true) return '正确'
  if (question.correct === false) return '错误'
  return '待确认'
}

function questionStatusClass(question) {
  if (question.correct === true) return 'correct'
  if (question.correct === false) return 'wrong'
  return 'unknown'
}

function previewImage(url) {
  if (isDingTalk) {
    previewFile(getAbsoluteMediaUrl(url), '')
    return
  }
  window.open(url, '_blank')
}

function openTeacherAnswerFile(sectionTitle, file, index = 0, total = 1) {
  const downloadName = getAttachmentDownloadName(sectionTitle, 'answer', index, total, file)
  const accessUrl = getAbsoluteMediaUrl(file)
  if (!accessUrl) return

  if (isDingTalk) {
    if (isPdf(file) || isImageFile(file)) {
      window.open(accessUrl, '_blank')
    } else {
      openFileDownload(accessUrl, downloadName)
    }
    return
  }

  if (isPdf(file) || isImageFile(file)) {
    window.open(accessUrl, '_blank')
    return
  }
  openFileDownload(accessUrl, downloadName)
}

function openQuestionFile(sectionTitle, file, index = 0, total = 1) {
  const mediaUrl = getMediaUrl(file)
  if (!mediaUrl) return
  const downloadName = getAttachmentDownloadName(sectionTitle, 'homework', index, total, file)

  if (isDingTalk) {
    if (isPdf(file)) {
      window.open(getAbsoluteMediaUrl(file), '_blank')
    } else {
      openFileDownload(getAbsoluteMediaUrl(file), downloadName)
    }
    return
  }

  if (isPdf(file)) {
    window.open(mediaUrl, '_blank')
    return
  }

  openFileDownload(mediaUrl, downloadName)
}

async function openReportModal(submission) {
  reportSubmission.value = submission
  reportDetail.value = null
  reportError.value = ''
  reportLoading.value = true
  showReportModal.value = true

  try {
    const res = await api.get(`/homework/reports/${submission.id}`)
    reportDetail.value = res.data.data || null
  } catch (e) {
    reportError.value = e.response?.data?.detail || e.message || '加载报告失败'
  } finally {
    reportLoading.value = false
  }
}

function closeReportModal() {
  showReportModal.value = false
  reportSubmission.value = null
  reportDetail.value = null
  reportError.value = ''
  reportLoading.value = false
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
    if (currentViewSectionId.value) await loadSectionSubmissions(currentViewSectionId.value)
  } catch (e) {
    alert('批改失败：' + (e.response?.data?.detail || e.message))
  } finally {
    gradeSubmitting.value = false
  }
}

function openReturnModal(submission) {
  returnSubmission.value = submission
  returnReason.value = ''
  showReturnModal.value = true
}

async function submitReturn() {
  if (!returnReason.value.trim()) {
    alert('请输入打回原因')
    return
  }
  returnSubmitting.value = true
  try {
    await api.post(`/homework/return/${returnSubmission.value.id}`, {
      reason: returnReason.value,
    })
    showReturnModal.value = false
    if (currentViewSectionId.value) await loadSectionSubmissions(currentViewSectionId.value)
  } catch (e) {
    alert('打回失败：' + (e.response?.data?.detail || e.message))
  } finally {
    returnSubmitting.value = false
  }
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function stopRegradePolling() {
  if (regradeTimer) {
    clearInterval(regradeTimer)
    regradeTimer = null
  }
}

function canRegradeSubmission(submission) {
  if (submission?.task?.status === 'failed') return true
  const generatedBy = String(submission?.report?.generated_by || '').toLowerCase()
  if (!submission?.report) return false
  return !generatedBy.includes('teacher')
}

async function triggerAiGrading(sectionId) {
  const assignment = getAssignment(sectionId)
  if (!assignment) return

  stopPolling()
  stopRegradePolling()
  triggeringSection.value = sectionId
  triggerStatus.value = null

  try {
    const res = await api.post(`/homework/trigger-grading/${assignment.id}`)
    const data = res.data.data
    if (data.submission_count === 0) {
      alert('无待批改的提交')
      triggeringSection.value = null
      return
    }
    triggerStatus.value = {
      total: data.submission_count,
      pending: data.submission_count,
      processing: 0,
      graded: 0,
      failed: 0,
      done: 0,
    }
    pollTimer = setInterval(() => pollGradingStatus(assignment.id), 3000)
  } catch (e) {
    alert('触发失败：' + (e.response?.data?.detail || e.message))
    triggeringSection.value = null
  }
}

async function regradeSubmission(submission) {
  const sectionId = currentViewSectionId.value
  if (!sectionId) return

  const assignment = getAssignment(sectionId)
  if (!assignment) return

  if (!canRegradeSubmission(submission)) {
    alert('当前提交不支持重新智能批改')
    return
  }

  if (!confirm('确认重新触发智能批改？当前 AI 报告会在新结果返回后覆盖。')) return

  stopPolling()
  stopRegradePolling()
  regradingSubmissionId.value = submission.id

  try {
    await api.post(`/homework/regrade/${submission.id}`)
    regradeTimer = setInterval(() => pollRegradeStatus(submission.id, sectionId), 3000)
    await pollRegradeStatus(submission.id, sectionId)
  } catch (e) {
    alert('重新触发失败：' + (e.response?.data?.detail || e.message))
    regradingSubmissionId.value = null
  }
}

async function pollRegradeStatus(submissionId, sectionId) {
  try {
    const res = await api.get(`/homework/tasks/${submissionId}`)
    const task = res.data.data || {}
    if (task.status === 'graded' || task.status === 'failed') {
      stopRegradePolling()
      regradingSubmissionId.value = null
      await loadSubmissions(sectionId)
      if (reportSubmission.value?.id === submissionId) {
        const fullSubmission = submissions.value.find(s => s.id === submissionId)
        if (fullSubmission) {
          reportSubmission.value = fullSubmission
        }
        await openReportModal(fullSubmission || { id: submissionId })
      }
    }
  } catch (e) {
    console.error('重批轮询失败', e)
    stopRegradePolling()
    regradingSubmissionId.value = null
  }
}

async function pollGradingStatus(assignmentId) {
  try {
    const res = await api.get(`/homework/trigger-status/${assignmentId}`)
    triggerStatus.value = res.data.data

    if (triggerStatus.value.done >= triggerStatus.value.total) {
      stopPolling()
      triggeringSection.value = null
      triggerStatus.value = null
      await loadData()
      if (currentViewSectionId.value) await loadSectionSubmissions(currentViewSectionId.value)
    }
  } catch (e) {
    console.error('轮询失败', e)
    stopPolling()
    triggeringSection.value = null
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

.btn-sm.batch-action {
  background: #e8f2ff;
  border-color: #c9ddff;
  color: #1d4ed8;
}

.btn-sm.ai-grade-btn {
  background: #7c3aed;
  color: white;
  border-color: #7c3aed;
}

.btn-sm.ai-grade-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.trigger-progress {
  margin-top: 10px;
  padding: 8px 12px;
  background: #f0e7ff;
  border: 1px solid #d4c4f0;
  border-radius: 6px;
  font-size: 13px;
  color: #5b21b6;
}

.progress-text {
  display: flex;
  gap: 8px;
  align-items: center;
}

.fail-count {
  color: #b42318;
  font-weight: 700;
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

.form-hint {
  margin: 4px 0 0;
  font-size: 12px;
  color: #7b8790;
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
.file-link,
.file-icon {
  display: flex;
  width: 100%;
  height: 100%;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  background: #eef5ff;
  color: #2563eb;
  text-decoration: none;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 700;
  border: none;
  cursor: pointer;
  padding: 6px 4px;
  appearance: none;
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
  line-height: 1.2;
  text-align: center;
  overflow: hidden;
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

.answer-count {
  display: inline-flex;
  align-items: center;
  margin-left: 8px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #edf6ff;
  color: #245b9b;
  font-size: 12px;
  font-weight: 700;
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

.ghost-action {
  background: #f5f7fa;
  color: #415163;
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
  vertical-align: top;
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
.answer-table select,
.answer-table textarea {
  width: 100%;
  box-sizing: border-box;
}

.answer-table textarea {
  min-height: 62px;
  resize: vertical;
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

.answer-json-collapsible {
  margin-top: 12px;
}

.answer-quick-entry {
  margin-top: 14px;
  border: 1px solid #d7e4ea;
  border-radius: 8px;
  background: #f6fbfd;
  padding: 14px;
}

.quick-entry-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  color: #17324d;
}

.quick-entry-hint {
  font-size: 12px;
  color: #687681;
}

.quick-entry-grid {
  display: grid;
  grid-template-columns: 90px 150px minmax(220px, 1fr) 110px auto;
  gap: 10px;
  align-items: end;
}

.quick-entry-field label {
  display: block;
  margin-bottom: 6px;
  color: #556575;
  font-size: 12px;
  font-weight: 700;
}

.quick-entry-field input,
.quick-entry-field select,
.quick-entry-field textarea {
  width: 100%;
  box-sizing: border-box;
}

.quick-answer-textarea {
  min-height: 62px;
}

.quick-entry-submit {
  display: flex;
  align-items: stretch;
}

.quick-entry-button {
  width: 100%;
  min-width: 112px;
}

@media (max-width: 920px) {
  .quick-entry-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .quick-entry-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .quick-entry-answer,
  .quick-entry-submit {
    grid-column: 1 / -1;
  }
}

@media (max-width: 640px) {
  .quick-entry-grid {
    grid-template-columns: 1fr;
  }

  .quick-entry-answer,
  .quick-entry-submit {
    grid-column: auto;
  }
}

.batch-answer-modal {
  width: min(920px, 100%);
}

.batch-hint {
  margin: -6px 0 12px;
  color: #687681;
  font-size: 13px;
}

.batch-actions-bar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.batch-answer-table {
  margin-bottom: 8px;
}

.submissions-list {
  max-height: 440px;
  overflow-y: auto;
}

.list-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
  background: #f8fafc;
  border: 1px solid #e9eef3;
  border-radius: 10px;
  padding: 10px 14px;
}

.list-search {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.search-input-wrap {
  display: flex;
  align-items: center;
  background: #fff;
  border: 1px solid #d0dbe3;
  border-radius: 8px;
  padding: 0 4px 0 10px;
  width: min(280px, 100%);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.search-input-wrap:focus-within {
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

.search-icon {
  font-size: 14px;
  opacity: 0.5;
  margin-right: 6px;
  line-height: 1;
  flex-shrink: 0;
}

.search-input-wrap input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  padding: 8px 4px;
  font-size: 14px;
  color: #1a2b3c;
}

.search-input-wrap input::placeholder {
  color: #9aabba;
}

.search-clear {
  border: none;
  background: transparent;
  color: #9aabba;
  cursor: pointer;
  padding: 4px 6px;
  font-size: 14px;
  line-height: 1;
  border-radius: 4px;
  flex-shrink: 0;
  transition: color 0.15s, background 0.15s;
}

.search-clear:hover {
  color: #475569;
  background: #f1f5f9;
}

.search-go {
  flex-shrink: 0;
}

.list-summary {
  font-size: 12px;
  color: #607080;
}

.list-pagination {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.list-pagination-meta {
  font-size: 12px;
  color: #607080;
}

.list-pagination-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
  color: #40515f;
}

.modal-actions-between {
  justify-content: space-between;
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

.submission-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: #7b8790;
  font-size: 12px;
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
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.status-tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}

.status-tag.success { background: #e8f7ef; color: #15803d; }
.status-tag.partial { background: #fff4df; color: #a16207; }
.status-tag.degraded { background: #fff1ee; color: #b42318; }
.status-tag.failed { background: #fee8e7; color: #b42318; }

.report-meta {
  font-size: 12px;
  color: #607080;
  margin-top: 4px;
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
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.report-detail-modal {
  width: min(880px, 100%);
}

.report-modal-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.report-modal-header h3 {
  margin-bottom: 6px;
}

.report-subtitle {
  color: #6b7785;
  font-size: 13px;
}

.report-loading,
.report-empty,
.report-error {
  margin-bottom: 12px;
}

.report-summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 18px;
}

.report-summary-item {
  border: 1px solid #d9e5ec;
  border-radius: 6px;
  padding: 12px;
  background: #f8fbfd;
}

.report-summary-label {
  display: block;
  margin-bottom: 6px;
  color: #6b7785;
  font-size: 12px;
}

.report-summary-value {
  display: block;
  color: #17324d;
  font-size: 15px;
  line-height: 1.4;
}

.report-section {
  margin-bottom: 18px;
}

.report-section-title {
  margin-bottom: 8px;
  color: #17324d;
  font-size: 14px;
  font-weight: 700;
}

.report-feedback-block,
.report-raw-json {
  margin: 0;
  padding: 12px;
  border: 1px solid #d9e5ec;
  border-radius: 6px;
  background: #f8fbfd;
  color: #324252;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.report-review-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.review-chip {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  background: #fff4df;
  color: #a16207;
  font-size: 12px;
  font-weight: 700;
}

.report-issues-list {
  margin: 0;
  padding-left: 18px;
  color: #475569;
  font-size: 13px;
  line-height: 1.6;
}

.report-question-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.report-question-item {
  border: 1px solid #d9e5ec;
  border-radius: 6px;
  padding: 12px;
  background: #ffffff;
}

.report-question-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.report-question-index {
  color: #17324d;
  font-weight: 700;
}

.report-question-score {
  color: #475569;
  font-size: 13px;
}

.report-question-status {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.report-question-status.correct {
  background: #e8f7ef;
  color: #15803d;
}

.report-question-status.wrong {
  background: #fee8e7;
  color: #b42318;
}

.report-question-status.unknown {
  background: #eef5ff;
  color: #2563eb;
}

.report-question-line {
  margin-top: 4px;
  color: #475569;
  font-size: 13px;
  line-height: 1.5;
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

.status-badge.returned {
  background: #fff7e6;
  color: #d46b08;
  border-color: #ffd591;
}

.btn-sm.danger {
  color: #ff4d4f;
  border-color: #ffccc7;
}
.btn-sm.danger:hover {
  background: #fff2f0;
}

.btn-primary.danger {
  background: #ff4d4f;
  border-color: #ff4d4f;
  color: #fff;
}
.btn-primary.danger:hover {
  background: #ff7875;
}

.return-reason {
  margin: 8px 0;
  padding: 8px 12px;
  background: #fff7e6;
  border: 1px solid #ffd591;
  border-radius: 6px;
  font-size: 13px;
  color: #d46b08;
}
.return-label {
  font-weight: 600;
}

.unlate-btn {
  background: none;
  border: none;
  color: #ff4d4f;
  cursor: pointer;
  padding: 0 2px;
  font-size: 12px;
  line-height: 1;
  margin-left: 2px;
}
.unlate-btn:hover {
  color: #cf1322;
}

@media (max-width: 720px) {
  .homework-manage-page {
    padding: 16px;
  }

  .page-header,
  .assignment-header,
  .answer-header,
  .report-modal-header {
    align-items: stretch;
    flex-direction: column;
  }

  .status-group {
    justify-content: flex-start;
  }

  .answer-table {
    min-width: 560px;
  }

  .list-search {
    width: 100%;
  }

  .search-input-wrap {
    width: 100%;
    flex: 1;
  }

  .list-pagination,
  .modal-actions-between {
    width: 100%;
    flex-direction: column;
    align-items: stretch;
  }

  .list-pagination-actions {
    justify-content: space-between;
  }

  .report-summary-grid {
    grid-template-columns: 1fr;
  }

  .answer-module {
    overflow-x: auto;
  }
}
</style>
