-- study_monitor backup generated before schema migration
-- database: study_monitor
-- generated_at: 2026-07-01 12:10:34.087179

SET FOREIGN_KEY_CHECKS=0;

DROP TABLE IF EXISTS `announcement_reads`;
CREATE TABLE `announcement_reads` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `announcement_id` bigint NOT NULL COMMENT '公告ID',
  `user_id` bigint NOT NULL COMMENT '用户ID',
  `read_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '已读时间',
  PRIMARY KEY (`id`),
  KEY `ix_announcement_reads_announcement_id` (`announcement_id`),
  KEY `ix_announcement_reads_user_id` (`user_id`),
  CONSTRAINT `announcement_reads_ibfk_1` FOREIGN KEY (`announcement_id`) REFERENCES `announcements` (`id`),
  CONSTRAINT `announcement_reads_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

DROP TABLE IF EXISTS `announcements`;
CREATE TABLE `announcements` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `course_id` bigint DEFAULT NULL COMMENT '关联课程ID(null=全平台公告)',
  `title` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '公告标题',
  `content` text COLLATE utf8mb4_unicode_ci COMMENT '公告正文',
  `priority` enum('normal','important','urgent') COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '优先级',
  `created_by` bigint NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `created_by` (`created_by`),
  KEY `ix_announcements_course_id` (`course_id`),
  CONSTRAINT `announcements_ibfk_1` FOREIGN KEY (`course_id`) REFERENCES `courses` (`id`),
  CONSTRAINT `announcements_ibfk_2` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `assignments`;
CREATE TABLE `assignments` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `course_id` bigint NOT NULL,
  `title` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text COLLATE utf8mb4_unicode_ci,
  `grading_prompt` text COLLATE utf8mb4_unicode_ci COMMENT '评分标准/批改提示词',
  `deadline` datetime DEFAULT NULL,
  `status` enum('draft','published','closed') COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `grading_status` enum('pending','graded') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending' COMMENT '批改状态',
  `grading_triggered` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否已触发智能体批改',
  `question_files` text COLLATE utf8mb4_unicode_ci COMMENT '题目文件URL数组(JSON)',
  `grading_mode` enum('auto','manual','hybrid') COLLATE utf8mb4_unicode_ci DEFAULT 'auto' COMMENT '批改模式',
  PRIMARY KEY (`id`),
  KEY `ix_assignments_course_id` (`course_id`),
  CONSTRAINT `assignments_ibfk_1` FOREIGN KEY (`course_id`) REFERENCES `courses` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `courses`;
CREATE TABLE `courses` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `title` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `video_type` enum('url','local') COLLATE utf8mb4_unicode_ci NOT NULL,
  `video_url` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '视频地址：外部链接或本地路径',
  `wukong_url` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '钉钉悟空智能体接口预留(暂未使用)',
  `duration_seconds` int DEFAULT NULL COMMENT '课程总时长(秒)',
  `teacher_id` bigint NOT NULL,
  `require_minutes` int DEFAULT NULL COMMENT '要求学习时长(分钟)',
  `start_date` datetime DEFAULT NULL,
  `end_date` datetime DEFAULT NULL,
  `status` enum('active','ended','draft') COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `teacher_id` (`teacher_id`),
  CONSTRAINT `courses_ibfk_1` FOREIGN KEY (`teacher_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `grading_reports`;
CREATE TABLE `grading_reports` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `submission_id` bigint NOT NULL,
  `score` int DEFAULT NULL COMMENT '分数0-100',
  `feedback` text COLLATE utf8mb4_unicode_ci,
  `detail` text COLLATE utf8mb4_unicode_ci COMMENT '各题详细批改(JSON)',
  `generated_by` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '智能体标识',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `review_status` enum('pending_review','confirmed','modified') COLLATE utf8mb4_unicode_ci DEFAULT 'confirmed' COMMENT '复核状态',
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_grading_reports_submission_id` (`submission_id`),
  CONSTRAINT `grading_reports_ibfk_1` FOREIGN KEY (`submission_id`) REFERENCES `submissions` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `grading_tasks`;
CREATE TABLE `grading_tasks` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `submission_id` bigint NOT NULL,
  `stitched_image_url` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '拼接后的长图URL',
  `status` enum('pending','sent','graded','failed') COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '任务状态',
  `retry_count` int DEFAULT NULL COMMENT '已重试次数',
  `error_message` text COLLATE utf8mb4_unicode_ci COMMENT '错误信息',
  `sent_at` datetime DEFAULT NULL COMMENT '发送时间',
  `graded_at` datetime DEFAULT NULL COMMENT '批改完成时间',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `agent_task_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT '' COMMENT '智能体任务ID',
  PRIMARY KEY (`id`),
  KEY `ix_grading_tasks_submission_id` (`submission_id`),
  CONSTRAINT `grading_tasks_ibfk_1` FOREIGN KEY (`submission_id`) REFERENCES `submissions` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `heartbeat_logs`;
CREATE TABLE `heartbeat_logs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `session_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` bigint NOT NULL,
  `timestamp` datetime NOT NULL,
  `is_playing` tinyint(1) DEFAULT NULL,
  `is_page_visible` tinyint(1) DEFAULT NULL,
  `video_current_time` decimal(12,2) DEFAULT NULL COMMENT '当前播放秒数',
  `action` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'heartbeat/play/pause/seek/verify/end',
  PRIMARY KEY (`id`),
  KEY `ix_heartbeat_logs_session_id` (`session_id`),
  KEY `ix_heartbeat_logs_user_id` (`user_id`),
  CONSTRAINT `heartbeat_logs_ibfk_1` FOREIGN KEY (`session_id`) REFERENCES `study_sessions` (`session_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `section_feedbacks`;
CREATE TABLE `section_feedbacks` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `section_id` bigint NOT NULL,
  `user_id` bigint NOT NULL,
  `rating` int DEFAULT NULL COMMENT '评分1-5星',
  `comment` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '文字评价',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_section_feedbacks_section_id` (`section_id`),
  KEY `ix_section_feedbacks_user_id` (`user_id`),
  CONSTRAINT `section_feedbacks_ibfk_1` FOREIGN KEY (`section_id`) REFERENCES `sections` (`id`),
  CONSTRAINT `section_feedbacks_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `sections`;
CREATE TABLE `sections` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `course_id` bigint NOT NULL,
  `title` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '小节标题',
  `sort_order` int DEFAULT NULL COMMENT '排序序号（从小到大）',
  `video_type` enum('url','local') COLLATE utf8mb4_unicode_ci NOT NULL,
  `video_url` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '视频地址：外部链接或本地路径',
  `duration_seconds` int DEFAULT NULL COMMENT '小节视频时长(秒)',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_sections_course_id` (`course_id`),
  CONSTRAINT `sections_ibfk_1` FOREIGN KEY (`course_id`) REFERENCES `courses` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `study_sessions`;
CREATE TABLE `study_sessions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL,
  `course_id` bigint NOT NULL,
  `session_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `start_time` datetime NOT NULL,
  `last_heartbeat` datetime DEFAULT NULL,
  `effective_seconds` int DEFAULT NULL COMMENT '有效学习秒数',
  `video_progress` decimal(10,2) DEFAULT NULL COMMENT '视频播放进度0-100%',
  `is_active` tinyint(1) DEFAULT NULL,
  `end_time` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_study_sessions_session_id` (`session_id`),
  KEY `ix_study_sessions_course_id` (`course_id`),
  KEY `ix_study_sessions_user_id` (`user_id`),
  KEY `ix_study_sessions_is_active` (`is_active`),
  CONSTRAINT `study_sessions_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `study_sessions_ibfk_2` FOREIGN KEY (`course_id`) REFERENCES `courses` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `submissions`;
CREATE TABLE `submissions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `assignment_id` bigint NOT NULL,
  `user_id` bigint NOT NULL,
  `images` text COLLATE utf8mb4_unicode_ci COMMENT '图片URL数组(JSON)',
  `status` enum('pending','graded') COLLATE utf8mb4_unicode_ci NOT NULL,
  `submitted_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `version` int DEFAULT '1' COMMENT '提交版本号',
  `is_latest` tinyint(1) DEFAULT '1' COMMENT '是否最新版本',
  PRIMARY KEY (`id`),
  KEY `ix_submissions_assignment_id` (`assignment_id`),
  KEY `ix_submissions_user_id` (`user_id`),
  KEY `idx_is_latest` (`is_latest`),
  CONSTRAINT `submissions_ibfk_1` FOREIGN KEY (`assignment_id`) REFERENCES `assignments` (`id`),
  CONSTRAINT `submissions_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `dingtalk_user_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `role` enum('student','teacher','admin') COLLATE utf8mb4_unicode_ci NOT NULL,
  `class_name` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '班级名称',
  `class_id` bigint DEFAULT NULL COMMENT '班级ID',
  `avatar` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `password_hash` varchar(200) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '浏览器登录密码哈希(空=仅钉钉登录)',
  `api_key` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'API Key(空=未生成)',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_users_dingtalk_user_id` (`dingtalk_user_id`),
  UNIQUE KEY `api_key` (`api_key`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- data for assignments
INSERT INTO `assignments` (`id`, `course_id`, `title`, `description`, `grading_prompt`, `deadline`, `status`, `created_at`, `updated_at`, `grading_status`, `grading_triggered`, `question_files`, `grading_mode`) VALUES (1, 1, '信息技术作业', '请完成课后练习题', '请根据题目标准答案批改学生作业', '2026-06-22 12:32:08', 'published', '2026-06-15 20:32:07', '2026-06-30 15:47:00', 'graded', 1, '["/uploads/homework/questions/efa064252cef4ae1b7d0f9184055b9a1.pdf"]', 'auto');

-- data for courses
INSERT INTO `courses` (`id`, `title`, `description`, `video_type`, `video_url`, `wukong_url`, `duration_seconds`, `teacher_id`, `require_minutes`, `start_date`, `end_date`, `status`, `created_at`, `updated_at`) VALUES (1, '信息技术', '信息技术课程', 'url', '', '', 0, 1, 60, '2026-06-15 12:32:08', '2026-07-15 12:32:08', 'active', '2026-06-15 20:32:07', '2026-06-15 20:32:07');

-- data for grading_reports
INSERT INTO `grading_reports` (`id`, `submission_id`, `score`, `feedback`, `detail`, `generated_by`, `created_at`, `review_status`) VALUES (5, 1, 42, '得分42/52，正确率80.8%。整体表现优秀，基础概念扎实，选择题全部正确。编程题存在个别小错误，建议在变量命名规范上再多加注意，继续保持！', '{"questions": [{"index": "1", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "2", "score": 0, "max_score": 2, "comment": "答案为A，标准答案为B", "correct": false}, {"index": "3", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "4", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "5", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "6", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "7", "score": 0, "max_score": 2, "comment": "答案为B，标准答案为C", "correct": false}, {"index": "8", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "9", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "10", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "11", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "12", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "13. (1)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "13. (2)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "13. (3)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "13. (4)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "14. (1)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "14. (2) ①", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "14. (2) ②", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "14. (2) ③", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "14. (3)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "15. (1)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "15. (2) ①", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "15. (2) ②", "score": 0, "max_score": 2, "comment": "答案为A，标准答案为C", "correct": false}, {"index": "15. (3)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "15. (3) ①", "score": 0, "max_score": 2, "comment": "答案为OP = queinfo[k][i]，标准答案为op = queinfo[k][i]，变量名大小写错误", "correct": false}, {"index": "15. (3) ②", "score": 2, "max_score": 2, "comment": "正确", "correct": true}], "confidence": 0.92, "issues": ["第2题选择题答案错误", "第7题选择题答案错误", "第15.(2)②答案错误", "第15.(3)①变量名大小写错误"]}', '星辰智能体', '2026-06-18 14:43:16', 'confirmed');
INSERT INTO `grading_reports` (`id`, `submission_id`, `score`, `feedback`, `detail`, `generated_by`, `created_at`, `review_status`) VALUES (6, 2, 28, '得分28/52，正确率53.8%。选择题部分正确率尚可，但编程填空题失分较多，特别是循环和条件判断逻辑理解不够深入。建议重点复习Python控制流语句，多做编程练习巩固。', '{"questions": [{"index": "1", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "2", "score": 0, "max_score": 2, "comment": "答案为A，标准答案为B", "correct": false}, {"index": "3", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "4", "score": 0, "max_score": 2, "comment": "答案为C，标准答案为A", "correct": false}, {"index": "5", "score": 0, "max_score": 2, "comment": "答案为D，标准答案为B", "correct": false}, {"index": "6", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "7", "score": 0, "max_score": 2, "comment": "答案为B，标准答案为C", "correct": false}, {"index": "8", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "9", "score": 0, "max_score": 2, "comment": "答案为B，标准答案为A", "correct": false}, {"index": "10", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "11", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "12", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "13. (1)", "score": 0, "max_score": 2, "comment": "答案为B，标准答案为A", "correct": false}, {"index": "13. (2)", "score": 0, "max_score": 2, "comment": "答案为A，标准答案为C", "correct": false}, {"index": "13. (3)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "13. (4)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "14. (1)", "score": 0, "max_score": 2, "comment": "答案为D，标准答案为A", "correct": false}, {"index": "14. (2) ①", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "14. (2) ②", "score": 0, "max_score": 2, "comment": "答案为sm.t = sd，标准答案为sm.year = sd", "correct": false}, {"index": "14. (2) ③", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "14. (3)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "15. (1)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "15. (2) ①", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "15. (2) ②", "score": 0, "max_score": 2, "comment": "答案为A，标准答案为C", "correct": false}, {"index": "15. (3)", "score": 0, "max_score": 2, "comment": "空白，未作答", "correct": false}, {"index": "15. (3) ①", "score": 0, "max_score": 2, "comment": "空白，未作答", "correct": false}, {"index": "15. (3) ②", "score": 0, "max_score": 2, "comment": "空白，未作答", "correct": false}], "confidence": 0.85, "issues": ["第2题选择题答案错误", "第4题选择题答案错误", "第5题选择题答案错误", "第7题选择题答案错误", "第9题选择题答案错误", "第13.(1)题答案错误", "第13.(2)题答案错误", "第14.(1)题答案错误", "第14.(2)②属性名错误", "第15.(2)②答案错误", "第15.(3)题未作答", "第15.(3)①未作答", "第15.(3)②未作答"]}', '星辰智能体', '2026-06-18 14:43:18', 'confirmed');
INSERT INTO `grading_reports` (`id`, `submission_id`, `score`, `feedback`, `detail`, `generated_by`, `created_at`, `review_status`) VALUES (7, 3, 34, '得分34/52，正确率65.4%。选择题部分表现较好，基础概念掌握扎实；编程填空题存在多处细节错误，特别是变量命名大小写敏感问题突出。建议加强Python标识符规范训练，注意区分大小写，多进行代码调试练习。', '{"questions": [{"index": "1", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "2", "score": 0, "max_score": 2, "comment": "答案为A，标准答案为B", "correct": false}, {"index": "3", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "4", "score": 0, "max_score": 2, "comment": "答案为C，标准答案为A", "correct": false}, {"index": "5", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "6", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "7", "score": 0, "max_score": 2, "comment": "答案为B，标准答案为C", "correct": false}, {"index": "8", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "9", "score": 0, "max_score": 2, "comment": "答案为B，标准答案为A", "correct": false}, {"index": "10", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "11", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "12", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "13. (1)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "13. (2)", "score": 0, "max_score": 2, "comment": "答案为A，标准答案为C", "correct": false}, {"index": "13. (3)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "13. (4)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "14. (1)", "score": 0, "max_score": 2, "comment": "答案为D，标准答案为A", "correct": false}, {"index": "14. (2) ①", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "14. (2) ②", "score": 0, "max_score": 2, "comment": "答案为sm.t = sd，标准答案为sm.year = sd，属性名错误", "correct": false}, {"index": "14. (2) ③", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "14. (3)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "15. (1)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "15. (2) ①", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "15. (2) ②", "score": 0, "max_score": 2, "comment": "答案为A，标准答案为C", "correct": false}, {"index": "15. (3)", "score": 0, "max_score": 2, "comment": "答案为0 total = 0，标准答案为0，多余内容导致错误", "correct": false}, {"index": "15. (3) ①", "score": 0, "max_score": 2, "comment": "答案为OP = queinfo[k][i]，标准答案为op = queinfo[k][i]，变量名大小写错误，Python区分大小写", "correct": false}, {"index": "15. (3) ②", "score": 0, "max_score": 2, "comment": "答案为queinfo[k][0] = data[P][3]，标准答案为queinfo[k][0] = data[p][3]，变量P大小写错误", "correct": false}], "confidence": 0.88, "issues": ["第2题选择题答案错误", "第4题选择题答案错误", "第7题选择题答案错误", "第9题选择题答案错误", "第13.(2)题答案错误", "第14.(1)题答案错误", "第14.(2)②属性名错误", "第15.(2)②答案错误", "第15.(3)题多余内容", "第15.(3)①变量名大小写错误", "第15.(3)②变量名大小写错误"]}', '星辰智能体', '2026-06-18 14:43:21', 'confirmed');
INSERT INTO `grading_reports` (`id`, `submission_id`, `score`, `feedback`, `detail`, `generated_by`, `created_at`, `review_status`) VALUES (8, 4, 38, '得分38/52，正确率73.1%。整体表现良好，对基础概念理解比较到位。编程题中部分逻辑处理存在疏漏，建议针对列表操作和函数定义进行专项练习，争取下次取得更好成绩。', '{"questions": [{"index": "1", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "2", "score": 0, "max_score": 2, "comment": "答案为A，标准答案为B", "correct": false}, {"index": "3", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "4", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "5", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "6", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "7", "score": 0, "max_score": 2, "comment": "答案为B，标准答案为C", "correct": false}, {"index": "8", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "9", "score": 0, "max_score": 2, "comment": "答案为B，标准答案为A", "correct": false}, {"index": "10", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "11", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "12", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "13. (1)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "13. (2)", "score": 0, "max_score": 2, "comment": "答案为A，标准答案为C", "correct": false}, {"index": "13. (3)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "13. (4)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "14. (1)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "14. (2) ①", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "14. (2) ②", "score": 0, "max_score": 2, "comment": "答案为sm.t = sd，标准答案为sm.year = sd，属性名错误", "correct": false}, {"index": "14. (2) ③", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "14. (3)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "15. (1)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "15. (2) ①", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "15. (2) ②", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "15. (3)", "score": 2, "max_score": 2, "comment": "正确", "correct": true}, {"index": "15. (3) ①", "score": 0, "max_score": 2, "comment": "答案为OP = queinfo[k][i]，标准答案为op = queinfo[k][i]，变量名大小写错误", "correct": false}, {"index": "15. (3) ②", "score": 2, "max_score": 2, "comment": "正确", "correct": true}], "confidence": 0.9, "issues": ["第2题选择题答案错误", "第7题选择题答案错误", "第9题选择题答案错误", "第13.(2)题答案错误", "第14.(2)②属性名错误", "第15.(3)①变量名大小写错误"]}', '星辰智能体', '2026-06-18 14:43:23', 'confirmed');

-- data for submissions
INSERT INTO `submissions` (`id`, `assignment_id`, `user_id`, `images`, `status`, `submitted_at`, `version`, `is_latest`) VALUES (1, 1, 2, '["/uploads/homework/\\u4f5c\\u4e1a1.jpg"]', 'graded', '2026-06-15 20:32:07', 1, 1);
INSERT INTO `submissions` (`id`, `assignment_id`, `user_id`, `images`, `status`, `submitted_at`, `version`, `is_latest`) VALUES (2, 1, 3, '["/uploads/homework/\\u4f5c\\u4e1a2.jpg"]', 'graded', '2026-06-15 20:32:07', 1, 1);
INSERT INTO `submissions` (`id`, `assignment_id`, `user_id`, `images`, `status`, `submitted_at`, `version`, `is_latest`) VALUES (3, 1, 4, '["/uploads/homework/\\u4f5c\\u4e1a3.jpg"]', 'graded', '2026-06-15 20:32:07', 1, 1);
INSERT INTO `submissions` (`id`, `assignment_id`, `user_id`, `images`, `status`, `submitted_at`, `version`, `is_latest`) VALUES (4, 1, 5, '["/uploads/homework/\\u4f5c\\u4e1a4.jpg"]', 'graded', '2026-06-15 20:32:07', 1, 1);

-- data for users
INSERT INTO `users` (`id`, `dingtalk_user_id`, `name`, `role`, `class_name`, `class_id`, `avatar`, `password_hash`, `api_key`, `created_at`, `updated_at`) VALUES (1, '张老师_dt', '张老师', 'teacher', '高一1班', NULL, NULL, 'df9afb18dc488f6a:40216a66f0b86562c48a3c2704638b6bc9a9048e69777b1b0d07eb767ccde08a', 'sk_a289e915bee24eba9d05061f35fea7f1', '2026-06-08 15:20:57', '2026-06-08 15:20:57');
INSERT INTO `users` (`id`, `dingtalk_user_id`, `name`, `role`, `class_name`, `class_id`, `avatar`, `password_hash`, `api_key`, `created_at`, `updated_at`) VALUES (2, '王小明_dt', '王小明', 'student', '高一1班', NULL, NULL, 'df9afb18dc488f6a:40216a66f0b86562c48a3c2704638b6bc9a9048e69777b1b0d07eb767ccde08a', NULL, '2026-06-08 15:20:57', '2026-06-08 15:20:57');
INSERT INTO `users` (`id`, `dingtalk_user_id`, `name`, `role`, `class_name`, `class_id`, `avatar`, `password_hash`, `api_key`, `created_at`, `updated_at`) VALUES (3, '李小红_dt', '李小红', 'student', '高一1班', NULL, NULL, 'df9afb18dc488f6a:40216a66f0b86562c48a3c2704638b6bc9a9048e69777b1b0d07eb767ccde08a', NULL, '2026-06-08 15:20:57', '2026-06-08 15:20:57');
INSERT INTO `users` (`id`, `dingtalk_user_id`, `name`, `role`, `class_name`, `class_id`, `avatar`, `password_hash`, `api_key`, `created_at`, `updated_at`) VALUES (4, '刘大伟_dt', '刘大伟', 'student', '高一1班', NULL, NULL, 'df9afb18dc488f6a:40216a66f0b86562c48a3c2704638b6bc9a9048e69777b1b0d07eb767ccde08a', NULL, '2026-06-08 15:20:58', '2026-06-08 15:20:58');
INSERT INTO `users` (`id`, `dingtalk_user_id`, `name`, `role`, `class_name`, `class_id`, `avatar`, `password_hash`, `api_key`, `created_at`, `updated_at`) VALUES (5, '陈思思_dt', '陈思思', 'student', '高一2班', NULL, NULL, 'df9afb18dc488f6a:40216a66f0b86562c48a3c2704638b6bc9a9048e69777b1b0d07eb767ccde08a', NULL, '2026-06-08 15:20:58', '2026-06-08 15:20:58');
INSERT INTO `users` (`id`, `dingtalk_user_id`, `name`, `role`, `class_name`, `class_id`, `avatar`, `password_hash`, `api_key`, `created_at`, `updated_at`) VALUES (6, '赵天宇_dt', '赵天宇', 'student', '高一2班', NULL, NULL, 'df9afb18dc488f6a:40216a66f0b86562c48a3c2704638b6bc9a9048e69777b1b0d07eb767ccde08a', NULL, '2026-06-08 15:20:58', '2026-06-08 15:20:58');

SET FOREIGN_KEY_CHECKS=1;
