"""Docker 初始化 — MySQL 用户 + Doris 表"""
import pymysql, os, time
from werkzeug.security import generate_password_hash

# 连接参数可用环境变量覆盖（compose 下 MySQL 走宿主机 127.0.0.1:3307）
_MYSQL_HOST = os.getenv('MYSQL_HOST', 'mysql')
_MYSQL_PORT = int(os.getenv('MYSQL_PORT', '3306'))
_MYSQL_PWD = os.getenv('MYSQL_PASSWORD', 'datatutor123')

print('Waiting for MySQL...')
for i in range(30):
    try:
        conn = pymysql.connect(host=_MYSQL_HOST, user='root', password=_MYSQL_PWD, port=_MYSQL_PORT, connect_timeout=2)
        conn.close()
        break
    except:
        time.sleep(2)

# 1. MySQL 种子用户
conn = pymysql.connect(host=_MYSQL_HOST, user='root', password=_MYSQL_PWD, port=_MYSQL_PORT, database='datatutor')
cur = conn.cursor()

# 1.1 管理员账号（幂等：无论 users 表是否为空都会确保存在）
#     默认 admin / admin123 —— 首次登录后请立即修改密码
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')
cur.execute('SELECT id FROM users WHERE username=%s', (ADMIN_USERNAME,))
admin_row = cur.fetchone()
if admin_row is None:
    cur.execute(
        'INSERT INTO users (username, password_hash, role, display_name) VALUES (%s,%s,%s,%s)',
        (ADMIN_USERNAME, generate_password_hash(ADMIN_PASSWORD), 'admin', ADMIN_USERNAME)
    )
    conn.commit()
    print(f'Admin created: {ADMIN_USERNAME}')
else:
    print(f'Admin exists: {ADMIN_USERNAME} (id={admin_row[0]})')

# 1.2 演示用种子账号（仅在空库时创建，避免污染既有数据）
cur.execute('SELECT COUNT(*) FROM users')
if cur.fetchone()[0] <= 1:
    users = [
        ('tanwei', generate_password_hash('tanwei'), 'teacher', 'TW'),
        ('student1', generate_password_hash('123456'), 'student', 'student1'),
        ('stu001', generate_password_hash('123456'), 'student', 'stu001'),
        ('student2', generate_password_hash('123456'), 'student', 'student2'),
    ]
    for u in users:
        cur.execute('INSERT INTO users (username, password_hash, role, display_name) VALUES (%s,%s,%s,%s)', u)
    conn.commit()
    print('MySQL demo users created')
cur.close(); conn.close()

# 2. Doris 表（可选组件：未部署时用 SKIP_DORIS=1 跳过，或连接失败自动跳过）
if os.getenv('SKIP_DORIS') == '1':
    print('SKIP_DORIS=1，跳过 Doris 建表')
    print('Init complete')
    raise SystemExit(0)

_DORIS_HOST = os.getenv('DORIS_HOST', 'doris')
_DORIS_PORT = int(os.getenv('DORIS_PORT', '9030'))

print('Waiting for Doris...')
_doris_ok = False
for i in range(30):
    try:
        conn = pymysql.connect(host=_DORIS_HOST, user='root', password='', port=_DORIS_PORT, connect_timeout=2)
        cur = conn.cursor()
        cur.execute('SHOW DATABASES')
        cur.close(); conn.close()
        _doris_ok = True
        break
    except:
        time.sleep(3)

if not _doris_ok:
    # Doris 是可选的分析库，未部署不影响 MySQL 账号与平台主功能
    print(f'Doris ({_DORIS_HOST}:{_DORIS_PORT}) 未就绪，跳过分析库建表')
    print('Init complete')
    raise SystemExit(0)

conn = pymysql.connect(host=_DORIS_HOST, user='root', password='', port=_DORIS_PORT)
cur = conn.cursor()
cur.execute('CREATE DATABASE IF NOT EXISTS datatutor_analytics')
cur.execute('USE datatutor_analytics')

tables = [
    'CREATE TABLE IF NOT EXISTS terminal_events (student_id INT, event_time DATETIME DEFAULT CURRENT_TIMESTAMP, course_id INT, subtask_id INT, vm_name VARCHAR(50), data STRING, direction VARCHAR(10)) DUPLICATE KEY(student_id, event_time) DISTRIBUTED BY HASH(student_id) BUCKETS 2 PROPERTIES("replication_num"="1")',
    'CREATE TABLE IF NOT EXISTS chat_events (student_id INT, event_time DATETIME DEFAULT CURRENT_TIMESTAMP, course_id INT, subtask_id INT, msg_role VARCHAR(10), msg_length INT) DUPLICATE KEY(student_id, event_time) DISTRIBUTED BY HASH(student_id) BUCKETS 2 PROPERTIES("replication_num"="1")',
    'CREATE TABLE IF NOT EXISTS task_completions (student_id INT, event_time DATETIME DEFAULT CURRENT_TIMESTAMP, course_id INT, subtask_id INT, duration_seconds INT, grade_level VARCHAR(2)) DUPLICATE KEY(student_id, event_time) DISTRIBUTED BY HASH(student_id) BUCKETS 2 PROPERTIES("replication_num"="1")',
    'CREATE TABLE IF NOT EXISTS page_views (student_id INT, event_time DATETIME DEFAULT CURRENT_TIMESTAMP, page VARCHAR(100), duration_seconds INT) DUPLICATE KEY(student_id, event_time) DISTRIBUTED BY HASH(student_id) BUCKETS 2 PROPERTIES("replication_num"="1")',
]
for sql in tables:
    try:
        cur.execute(sql)
    except Exception as e:
        print(f'Doris warn: {str(e)[:60]}')
conn.commit()
cur.close(); conn.close()
print('Doris tables created')
print('Init complete')
