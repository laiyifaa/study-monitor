"""
修复 announcements 表创建失败的问题
MySQL strict mode 下 TEXT 类型不能设 DEFAULT ''
"""
import paramiko

HOST = "115.223.38.172"
PORT = 1000
USER = "root"
PASS = "3MgZ)mhs"

def run_cmd(client, cmd, timeout=30):
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    if out.strip():
        print(out.strip()[-2000:])
    if err.strip() and 'Warning' not in err:
        print(f"[STDERR] {err.strip()[-500:]}")
    return stdout.channel.recv_exit_status(), out, err

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, port=PORT, username=USER, password=PASS, timeout=30)

try:
    # 检查 announcements 是否已存在
    rc, out, err = run_cmd(client,
        '''docker exec study-monitor-mysql mysql -u root -p'Sm2026Root_Secure_Prod' study_monitor -e "SHOW TABLES LIKE 'announcements';"''')
    
    if 'announcements' not in out:
        print("\nannouncements 表不存在，创建中...")
        # TEXT 列不设 DEFAULT，content 用 NULLABLE
        rc, out, err = run_cmd(client,
            """docker exec study-monitor-mysql mysql -u root -p'Sm2026Root_Secure_Prod' study_monitor -e "
            CREATE TABLE IF NOT EXISTS announcements (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                course_id BIGINT DEFAULT NULL COMMENT '关联课程ID',
                title VARCHAR(200) NOT NULL COMMENT '公告标题',
                content TEXT COMMENT '公告正文',
                priority ENUM('normal', 'important', 'urgent') NOT NULL DEFAULT 'normal' COMMENT '优先级',
                created_by BIGINT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX ix_announcements_course_id (course_id),
                CONSTRAINT fk_announcements_course FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE SET NULL,
                CONSTRAINT fk_announcements_creator FOREIGN KEY (created_by) REFERENCES users(id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='公告表';
            \" """, timeout=30)
        if rc == 0:
            print("announcements 表创建成功！")
    else:
        print("announcements 表已存在，跳过")
    
    # 检查 grading_tasks 的 error_message 列是否有默认值问题
    print("\n--- 检查 grading_tasks 列定义 ---")
    rc, out, err = run_cmd(client,
        """docker exec study-monitor-mysql mysql -u root -p'Sm2026Root_Secure_Prod' study_monitor -e "SHOW COLUMNS FROM grading_tasks LIKE 'error_message';" """)
    
    print("\n--- 最终表列表 ---")
    run_cmd(client,
        """docker exec study-monitor-mysql mysql -u root -p'Sm2026Root_Secure_Prod' study_monitor -e "SHOW TABLES;" """)
    
    print("\n--- submissions 列检查（确认 is_late 存在）---")
    run_cmd(client,
        """docker exec study-monitor-mysql mysql -u root -p'Sm2026Root_Secure_Prod' study_monitor -e "SHOW COLUMNS FROM submissions LIKE 'is_late';" """)

finally:
    client.close()
    print("\n修复完毕。")
