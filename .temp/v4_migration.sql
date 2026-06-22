-- ============================================================
-- v4.0 数据库迁移脚本
-- 从 v3.0 升级到 v4.0，包含以下变更：
--   1. users 表新增 real_name、phone 字段
--   2. sections 表新增 open_time 字段
--   3. assignments 表从 course_id(唯一) 迁移到 section_id(唯一)
--   4. submissions 表新增 is_late 字段
--   5. 新建 announcements 表
--   6. 新建 section_feedbacks 表
--
-- 执行方式：
--   mysql -u root -p study_monitor < v4_migration.sql
--
-- 注意事项：
--   - 执行前请备份数据库
--   - assignments 表迁移需要先把已有作业匹配到对应小节
--   - 如果旧 assignments 表没有数据，可直接执行
-- ============================================================

-- 1. users 表新增实名信息字段
ALTER TABLE users ADD COLUMN real_name VARCHAR(50) DEFAULT '' COMMENT '真实姓名（钉钉通讯录获取）';
ALTER TABLE users ADD COLUMN phone VARCHAR(20) DEFAULT '' COMMENT '手机号（钉钉通讯录获取）';

-- 2. sections 表新增开播时间字段
ALTER TABLE sections ADD COLUMN open_time DATETIME DEFAULT NULL COMMENT '开播时间（未到不可进入学习，null=不限制）';

-- 3. assignments 表从 course_id 迁移到 section_id
-- 3a. 新增 section_id 列（暂时允许 NULL）
ALTER TABLE assignments ADD COLUMN section_id BIGINT DEFAULT NULL COMMENT '所属小节ID';

-- 3b. 如果旧 assignments 有数据，尝试根据 course_id 匹配到该课程下的第一个小节
--     如果没有 section 数据，先设为 NULL，后续手动处理
UPDATE assignments a
JOIN (
    SELECT MIN(s.id) AS min_section_id, s.course_id
    FROM sections s
    GROUP BY s.course_id
) sec ON a.course_id = sec.course_id
SET a.section_id = sec.min_section_id;

-- 3c. 将 section_id 设为 NOT NULL（确认所有记录都已填充后再执行）
-- ALTER TABLE assignments MODIFY COLUMN section_id BIGINT NOT NULL;

-- 3d. 添加 section_id 的外键约束和唯一约束
-- 注意：如果旧数据 course_id 有重复的唯一约束，需要先删除旧的唯一约束
-- 先删除旧的 course_id 唯一约束（如果存在）
-- MySQL 无法直接 DROP INDEX IF EXISTS，需要先查询索引名
-- 可通过 SHOW INDEX FROM assignments 查看现有索引
-- 假设旧唯一约束名为 uq_assignments_course_id：
-- ALTER TABLE assignments DROP INDEX uq_assignments_course_id;

-- 添加新的唯一约束
-- ALTER TABLE assignments ADD UNIQUE INDEX uq_assignments_section_id (section_id);

-- 3e. 确保 course_id 不再有唯一约束（保留为普通索引，方便按课程查询）
ALTER TABLE assignments ADD INDEX ix_assignments_course_id (course_id);

-- 4. submissions 表新增 is_late 字段
ALTER TABLE submissions ADD COLUMN is_late BOOLEAN DEFAULT FALSE COMMENT '是否迟交（截止时间后提交）';

-- 5. 新建 announcements 表
CREATE TABLE IF NOT EXISTS announcements (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    course_id BIGINT DEFAULT NULL COMMENT '关联课程ID(null=全平台公告)',
    title VARCHAR(200) NOT NULL COMMENT '公告标题',
    content TEXT DEFAULT '' COMMENT '公告正文',
    priority ENUM('normal', 'important', 'urgent') NOT NULL DEFAULT 'normal' COMMENT '优先级',
    created_by BIGINT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX ix_announcements_course_id (course_id),
    CONSTRAINT fk_announcements_course FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE SET NULL,
    CONSTRAINT fk_announcements_creator FOREIGN KEY (created_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='公告表';

-- 6. 新建 section_feedbacks 表
CREATE TABLE IF NOT EXISTS section_feedbacks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    section_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    rating INT DEFAULT 5 COMMENT '评分1-5星',
    comment VARCHAR(500) DEFAULT '' COMMENT '文字评价',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_feedback_section_id (section_id),
    INDEX ix_feedback_user_id (user_id),
    CONSTRAINT fk_feedback_section FOREIGN KEY (section_id) REFERENCES sections(id) ON DELETE CASCADE,
    CONSTRAINT fk_feedback_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE INDEX uq_feedback_section_user (section_id, user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='小节评价表';

-- 7. 新建 grading_tasks 表（v4.0 新增）
CREATE TABLE IF NOT EXISTS grading_tasks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    submission_id BIGINT NOT NULL COMMENT '关联提交ID',
    stitched_image_url VARCHAR(500) DEFAULT '' COMMENT '拼接后的长图URL',
    agent_task_id VARCHAR(100) DEFAULT '' COMMENT '智能体任务ID',
    status ENUM('pending', 'sent', 'graded', 'failed') NOT NULL DEFAULT 'pending' COMMENT '任务状态',
    retry_count INT DEFAULT 0 COMMENT '已重试次数',
    error_message TEXT DEFAULT '' COMMENT '错误信息',
    sent_at DATETIME DEFAULT NULL COMMENT '发送时间',
    graded_at DATETIME DEFAULT NULL COMMENT '批改完成时间',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_grading_tasks_submission_id (submission_id),
    CONSTRAINT fk_grading_task_submission FOREIGN KEY (submission_id) REFERENCES submissions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='批改任务表';

-- 完成提示
SELECT 'v4.0 migration completed successfully' AS status;
