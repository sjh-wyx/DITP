"""端到端验证 DataTutor 学生终端链路。
流程：登录学生账号 -> socketio terminal_connect -> 收 terminal_connected / 输出。
"""
import socketio, requests, time, sys, re

BASE = 'http://127.0.0.1'

# 1. 找一个学生用户（先调 init 列表接口或用默认账号）
# 走登录接口拿 cookie；不知道密码，先用 init_users 创建默认学生
s = requests.Session()

# 试试 README 默认学生账号 student/123456
login = s.post(f'{BASE}/api/auth/login', json={'username': 'student1', 'password': '123456'}, timeout=5)
print('login status:', login.status_code, login.text[:200])

data = login.json()
token = data.get('token') or data.get('access_token')
user = data.get('user') or data
print('user:', user)
uid = user.get('id') or user.get('user_id') or 2

# 2. socketio 连接（带 auth header）
sio = socketio.Client(reconnection=False)
out_buf = []

@sio.on('terminal_output')
def _(d):
    out_buf.append(d.get('output', ''))
    sys.stdout.write('[OUT] ' + repr(d.get('output', '')[:80]) + '\n')
    sys.stdout.flush()

@sio.on('terminal_connected')
def _(d):
    print('[CONNECTED]', d)

@sio.on('terminal_error')
def _(d):
    print('[ERROR]', d, flush=True)

@sio.on('connect')
def _():
    print('[socket connected]', flush=True)

@sio.on('connect_error')
def _(e):
    print('[connect_error]', e, flush=True)

try:
    sio.connect(BASE, headers={'Authorization': f'Bearer {token}'} if token else {}, transports=['websocket', 'polling'])
except Exception as e:
    print('socket connect failed:', e)
    sys.exit(1)

time.sleep(0.5)
print('emit terminal_connect for student_id=', uid)
sio.emit('terminal_connect', {'student_id': uid, 'session_id': 0, 'cols': 80, 'rows': 24})

# 等容器创建 + SSH 起来
deadline = time.time() + 120
while time.time() < deadline and not out_buf:
    sio.sleep(0.5)

# 再等几秒看 banner
time.sleep(2)
print('total output chunks:', len(out_buf))
joined = ''.join(out_buf)
ansi_re = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\][0-9;]*[^\x07]*\x07|\r')
clean = ansi_re.sub('', joined)
print('=== first 800 chars of terminal output ===')
print(clean[:800])
print('=== end ===')

# 试着发一条命令
sio.emit('terminal_input', {'student_id': uid, 'session_id': 0, 'command': 'echo HELLO_FROM_TEST\n'})
time.sleep(2)
clean2 = ansi_re.sub('', ''.join(out_buf))
if 'HELLO_FROM_TEST' in clean2:
    print('[OK] terminal echo command worked')
else:
    print('[WARN] echo not seen in output')

sio.disconnect()