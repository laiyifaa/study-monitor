"""
服务器部署脚本：git pull + DB迁移 + Docker重建
"""
import paramiko
import sys
import time

HOST = "115.223.38.172"
PORT = 1000
USER = "root"
PASS = "3MgZ)mhs"

# v4 迁移 SQL（从本地文件读取后传输）
MIGRATION_SQL_PATH = "/Users/sh/Desktop/Agent Workspace/TeleClaw/study-monitor/.temp/v4_migration.sql"

def create_client():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=PASS, timeout=30)
    return client

def run_cmd(client, cmd, timeout=120):
    """执行远程命令，返回 stdout + stderr"""
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    exit_code = stdout.channel.recv_exit_status()
    if out.strip():
        print(out.strip()[-2000:])  # 限制输出长度
    if err.strip():
        print(f"[STDERR] {err.strip()[-1000:]}")
    return exit_code, out, err

def main():
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    client = create_client()
    
    try:
        if step in ("pull", "all"):
            print("=" * 60)
            print("步骤1: Git Pull 拉取最新代码")
            print("=" * 60)
            rc, out, err = run_cmd(client, 
                "cd /data/study-monitor && https_proxy=http://127.0.0.1:7890 http_proxy=http://127.0.0.1:7890 git pull")
            if rc != 0:
                print("git pull 失败！")
                if step == "all":
                    return
        
        if step in ("migrate", "all"):
            print("\n" + "=" * 60)
            print("步骤2: 数据库迁移")
            print("=" * 60)
            
            # 先检查当前数据库表结构
            print("\n--- 检查现有表结构 ---")
            run_cmd(client,
                'docker exec study-monitor-mysql mysql -u root -p\'Sm2026Root_Secure_Prod\' study_monitor -e "SHOW TABLES;"')
            
            # 上传迁移 SQL
            print("\n--- 上传迁移脚本 ---")
            sftp = client.open_sftp()
            sftp.put(MIGRATION_SQL_PATH, '/tmp/v4_migration.sql')
            sftp.close()
            print("迁移脚本已上传到 /tmp/v4_migration.sql")
            
            # 拷贝到 MySQL 容器内
            print("\n--- 拷贝SQL到MySQL容器 ---")
            run_cmd(client,
                'docker cp /tmp/v4_migration.sql study-monitor-mysql:/tmp/v4_migration.sql')
            
            # 执行迁移
            print("\n--- 执行迁移 ---")
            rc, out, err = run_cmd(client,
                'docker exec study-monitor-mysql mysql -u root -p\'Sm2026Root_Secure_Prod\' study_monitor -e "source /tmp/v4_migration.sql"',
                timeout=60)
            if rc != 0:
                print("迁移执行失败，尝试逐条执行...")
                # 读取迁移SQL逐条执行
                with open(MIGRATION_SQL_PATH, 'r') as f:
                    sql_content = f.read()
                # 按分号分割，跳过注释和空行
                statements = []
                for line in sql_content.split('\n'):
                    stripped = line.strip()
                    if stripped and not stripped.startswith('--'):
                        statements.append(line)
                full_sql = '\n'.join(statements)
                for stmt in full_sql.split(';'):
                    stmt = stmt.strip()
                    if stmt:
                        print(f"  执行: {stmt[:80]}...")
                        rc2, _, _ = run_cmd(client,
                            f'docker exec study-monitor-mysql mysql -u root -p\'Sm2026Root_Secure_Prod\' study_monitor -e "{stmt}"',
                            timeout=30)
                        if rc2 != 0:
                            print(f"  ⚠️ 语句可能已执行或出错（如列已存在），继续...")
            
            print("\n--- 验证迁移结果 ---")
            run_cmd(client,
                'docker exec study-monitor-mysql mysql -u root -p\'Sm2026Root_Secure_Prod\' study_monitor -e "DESCRIBE users;"')
            run_cmd(client,
                'docker exec study-monitor-mysql mysql -u root -p\'Sm2026Root_Secure_Prod\' study_monitor -e "DESCRIBE sections;"')
            run_cmd(client,
                'docker exec study-monitor-mysql mysql -u root -p\'Sm2026Root_Secure_Prod\' study_monitor -e "SHOW TABLES;"')
        
        if step in ("rebuild", "all"):
            print("\n" + "=" * 60)
            print("步骤3: Docker 重建容器")
            print("=" * 60)
            rc, out, err = run_cmd(client,
                "cd /data/study-monitor && docker compose up -d --build backend frontend",
                timeout=300)
            print("重建完成，等待5秒让容器启动...")
            time.sleep(5)
            
            # 检查容器状态
            print("\n--- 容器状态 ---")
            run_cmd(client, "docker ps --filter name=study-monitor --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'")
        
        if step in ("verify", "all"):
            print("\n" + "=" * 60)
            print("步骤4: 健康检查 + API 冒烟测试")
            print("=" * 60)
            
            # 后端健康检查
            print("\n--- 后端健康检查 ---")
            run_cmd(client, "curl -s http://127.0.0.1:8001/api/health | head -c 500")
            
            # 检查新路由是否注册
            print("\n--- 检查API路由列表 ---")
            run_cmd(client, "curl -s http://127.0.0.1:8001/openapi.json | python3 -c \"import sys,json; paths=json.load(sys.stdin)['paths']; [print(p) for p in sorted(paths.keys()) if 'announcement' in p or 'feedback' in p or 'leaderboard' in p or 'checkin' in p or 'report' in p]\" 2>/dev/null || echo 'openapi解析失败'")
            
            # 前端检查
            print("\n--- 前端页面检查 ---")
            run_cmd(client, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/")
            
            # Nginx 端口检查
            print("\n--- Nginx 1001端口检查 ---")
            run_cmd(client, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:1001/")

    finally:
        client.close()
        print("\n部署脚本执行完毕。")

if __name__ == "__main__":
    main()
