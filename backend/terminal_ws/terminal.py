"""
xterm.js 终端后端 — paramiko SSH 连接本地虚拟机 + Doris 行为日志
"""
import paramiko
import os
import threading
import time
from flask_socketio import emit, disconnect, join_room, leave_room
from db_doris import log_terminal_event
from docker_api import (available as docker_available, find_container, start as docker_start,
                        run as docker_run, remove as docker_remove,
                        cleanup_completed, flush_pending, course_completed)

# {session_key: {'ssh': SSHClient, 'channel': Channel, 'sandbox_dir': str, 'io_buffer': list}}
# session_key = f"{student_id}:{session_id}"
active_sessions = {}

# 终端 I/O 缓冲区: {student_id: [{'vm': '主终端', 'data': 'xxx', 'direction': 'in'|'out'}, ...]}
# 每个学生最多保留 200 条 I/O 记录
terminal_buffers = {}
MAX_BUFFER = 200


def record_terminal_io(student_id, vm_name, data, direction):
    """记录终端 I/O：direction = 'in'（用户输入） 或 'out'（VM 输出）"""
    key = str(student_id)
    if key not in terminal_buffers:
        terminal_buffers[key] = []
    buf = terminal_buffers[key]
    buf.append({'vm': vm_name, 'data': data, 'direction': direction})
    if len(buf) > MAX_BUFFER:
        buf[:] = buf[-MAX_BUFFER:]


def get_terminal_context(student_id):
    """获取学生的终端上下文，用于拼入 AI 消息中"""
    import re
    buf = terminal_buffers.get(str(student_id), [])
    if not buf:
        return ''
    # 过滤 ANSI 转义序列
    ansi_re = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\][0-9;]*[^\x07]*\x07|\r')
    lines = []
    for item in buf[-50:]:
        if item['direction'] == 'in':
            text = item['data'].strip()
            if text and len(text) < 200:
                lines.append(f"[{item['vm']}] $ {text}")
        else:
            text = ansi_re.sub('', item['data']).strip()
            # 只保留有意义的行（至少 2 个可见字符，非纯控制字符）
            if text and len(text) >= 2 and not text.startswith('\x1b'):
                # 截断过长的输出行
                for line in text.split('\n')[:5]:
                    line = line.strip()
                    if line and len(line) >= 2:
                        lines.append(line[:200])
    return '\n'.join(lines[-30:])


def close_session(session_key):
    """安全关闭终端会话；若该生容器处于「待回收」状态，断开后补删。"""
    session = active_sessions.pop(session_key, None)
    if session:
        try:
            session['channel'].close()
        except Exception:
            pass
        try:
            session['ssh'].close()
        except Exception:
            pass
        # 课程已完成但当时还有会话 → 现在补删（flush_pending 内部已做异常兜底）
        try:
            flush_pending(session.get('student_id'))
        except Exception as exc:
            print(f'[TERM] flush_pending 异常: {exc}', flush=True)


def _start_reading(session_key, socketio):
    """后台线程持续读取 SSH channel 输出并推送到前端"""
    session = active_sessions.get(session_key)
    if not session:
        return

    channel = session['channel']

    def read_loop():
        retry = 0
        while session_key in active_sessions:
            try:
                data_received = False
                if channel.recv_ready():
                    data = channel.recv(4096).decode('utf-8', errors='replace')
                    socketio.emit('terminal_output', {'output': data, 'session_id': session_key.split(':')[1]}, room=session_key)
                    record_terminal_io(session_key.split(':')[0], f'VM{session_key.split(":")[1]}', data, 'out')
                    log_terminal_event(session_key.split(':')[0], 0, 0, f'VM{session_key.split(":")[1]}', data[:200], 'out')
                    data_received = True
                if channel.recv_stderr_ready():
                    data = channel.recv_stderr(4096).decode('utf-8', errors='replace')
                    socketio.emit('terminal_output', {'output': data, 'session_id': session_key.split(':')[1]}, room=session_key)
                    record_terminal_io(session_key.split(':')[0], f'VM{session_key.split(":")[1]}', data, 'out')
                    log_terminal_event(session_key.split(':')[0], 0, 0, f'VM{session_key.split(":")[1]}', data[:200], 'out')
                    data_received = True

                if not data_received:
                    time.sleep(0.03)

                retry = 0

            except Exception:
                retry += 1
                if retry > 3:
                    break
                time.sleep(0.5)

        if session_key in active_sessions:
            socketio.emit('terminal_output', {
                'output': '\r\n\x1b[31m[连接已断开] 请点击重连按钮\x1b[0m\r\n',
                'session_id': session_key.split(':')[1]
            }, room=session_key)
            close_session(session_key)

    t = threading.Thread(target=read_loop, daemon=True)
    t.start()
    session['thread'] = t


def register_terminal_handlers(socketio):
    """在 app.py 中调用，注册所有终端 Socket.IO 事件"""

    @socketio.on('terminal_connect')
    def handle_terminal_connect(data):
        student_id = str(data.get('student_id', ''))
        session_id = str(data.get('session_id', '0'))
        session_key = f'{student_id}:{session_id}'
        print(f'[TERM] connect student={student_id} session={session_id}', flush=True)

        if session_key in active_sessions:
            close_session(session_key)

        vm_host = data.get('host') or os.getenv('VM_HOST', '127.0.0.1')
        vm_port = int(data.get('port') or os.getenv('VM_PORT', '22'))

        # 检测角色：学生连自己的 Docker 容器，教师连宿主机
        from models import User
        student = User.query.get(int(student_id)) if student_id and student_id.isdigit() else None
        if student and student.role == 'student':
            vm_host = '127.0.0.1'
            vm_port = 2200 + int(student_id)
            vm_user = 'learner'
            vm_password = '123456'
            container_name = f'dts-student{student_id}'

            # 检查容器是否存在，不存在则自动创建
            # 走 Docker Engine API（/var/run/docker.sock），不用 docker 命令行：
            # app 跑在容器里，镜像里没有 docker CLI，subprocess 调 docker 必然失败
            if not docker_available():
                leave_room(session_key)
                emit('terminal_error', {'message': f'Docker 不可用：未找到 {os.getenv("DOCKER_SOCKET", "/var/run/docker.sock")}。'
                                                    f'请用 restart_app.sh 启动 app 容器（它会挂载 docker.sock），并确认学生容器 {container_name} 已创建。',
                                         'session_id': session_id})
                return

            item = find_container(container_name)

            # 兜底回收：该课程已全部完成却还留着容器（例如完成时终端还连着）→ 删掉换一个干净的
            course_id = data.get('course_id')
            if item is not None and course_id and course_completed(student_id, course_id):
                removed, _, note = cleanup_completed(student_id, course_id)
                if removed:
                    print(f'[TERM] 课程 {course_id} 已完成，回收旧容器 {container_name}', flush=True)
                    emit('terminal_notice', {'message': note, 'session_id': session_id})
                    item = None

            if item is None:
                print(f'[TERM] Auto-creating container {container_name} on port {vm_port}', flush=True)
                # 只读挂载的宿主路径按部署给，默认 VM（ECS 用环境变量覆盖）
                uploads_dir = os.getenv('STUDENT_UPLOADS_DIR', '/home/hadoop/datatutor/backend/uploads')
                packages_dir = os.getenv('STUDENT_PACKAGES_DIR', '/opt/packages')
                binds = [f'{uploads_dir}:/home/learner/course-data:ro',
                         f'{packages_dir}:/home/learner/packages:ro']
                # 注意：这里判不了宿主路径是否存在——app 在容器内，看到的不是宿主文件系统；
                # Docker 守护进程按**宿主**命名空间解析 bind 源，宿主路径缺失时容器会起不来。
                print(f'[TERM] bind 源: {binds[0].split(":")[0]} / {binds[1].split(":")[0]}（须存在于宿主机）', flush=True)
                ok, detail = docker_run(image=os.getenv('STUDENT_IMAGE', 'datatutor-student'),
                                        name=container_name, port=vm_port, volumes=binds)
                if not ok:
                    leave_room(session_key)
                    emit('terminal_error', {'message': f'学生容器 {container_name} 创建失败：{detail}',
                                            'session_id': session_id})
                    return
                print(f'[TERM] Created {container_name} id={detail}', flush=True)
            elif item.get('State') != 'running':
                print(f'[TERM] Starting existing container {container_name} (state={item.get("State")})', flush=True)
                ok, detail = docker_start(container_name)
                if not ok:
                    leave_room(session_key)
                    emit('terminal_error', {'message': f'学生容器 {container_name} 启动失败：{detail}',
                                            'session_id': session_id})
                    return

            print(f'[TERM] {student.username}(id={student_id}) -> {container_name}:{vm_port}', flush=True)
        else:
            vm_user = data.get('user') or os.getenv('VM_USER', 'root')
            vm_password = data.get('password') or os.getenv('VM_PASSWORD', '')
        sandbox = os.getenv('VM_SANDBOX_DIR', f'/home/{vm_user}/datatutor')

        if not vm_host or not vm_password:
            emit('terminal_error', {'message': '请填写虚拟机 IP、用户名和密码', 'session_id': session_id})
            return

        join_room(session_key)

        try:
            # 新创建的容器里 sshd 还没起来，首次连接会报 "Error reading SSH protocol banner"，
            # 因此这里做短重试，避免学生点进来看到一次失败
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            last_err = None
            for attempt in range(1, 6):
                try:
                    print(f'[TERM] SSH connecting to {vm_host}:{vm_port} as {vm_user}... (第{attempt}次)', flush=True)
                    ssh.connect(vm_host, port=vm_port, username=vm_user, password=vm_password, timeout=10)
                    last_err = None
                    break
                except Exception as exc:
                    last_err = exc
                    print(f'[TERM] SSH 第{attempt}次失败: {exc}', flush=True)
                    if attempt < 5:
                        time.sleep(1.5)
            if last_err is not None:
                raise last_err
            print(f'[TERM] SSH connected to {vm_host}', flush=True)

            cols = int(data.get('cols') or 80)
            rows = int(data.get('rows') or 24)
            channel = ssh.invoke_shell(term='xterm-256color', width=cols, height=rows)
            channel.settimeout(0)

            student_sandbox = f'{sandbox}/student_{student_id}_vm{session_id}'
            channel.send(f'mkdir -p {student_sandbox}\ncd {student_sandbox}\nclear\n')

            active_sessions[session_key] = {
                'ssh': ssh, 'channel': channel, 'sandbox_dir': student_sandbox,
                'student_id': student_id,
            }

            # Doris: 记录终端连接
            log_terminal_event(student_id, 0, 0, f'VM{session_id}', f'Connected to {vm_host}', 'connect')

            time.sleep(0.3)

            emit('terminal_connected', {
                'message': f'已连接 {vm_host}',
                'sandbox_dir': student_sandbox,
                'session_id': session_id
            })

            _start_reading(session_key, socketio)

        except paramiko.AuthenticationException:
            print(f'[TERM] Auth failed for {vm_host}', flush=True)
            leave_room(session_key)
            emit('terminal_error', {'message': 'VM 认证失败，请检查用户名/密码', 'session_id': session_id})
        except paramiko.SSHException as e:
            print(f'[TERM] SSH error: {e}', flush=True)
            leave_room(session_key)
            emit('terminal_error', {'message': f'SSH 连接失败: {str(e)}', 'session_id': session_id})
        except Exception as e:
            print(f'[TERM] Unexpected error: {e}', flush=True)
            leave_room(session_key)
            emit('terminal_error', {'message': f'连接异常: {str(e)}', 'session_id': session_id})

    @socketio.on('terminal_input')
    def handle_terminal_input(data):
        student_id = str(data.get('student_id', ''))
        session_id = str(data.get('session_id', '0'))
        session_key = f'{student_id}:{session_id}'
        # 记录用户输入
        command = data.get('command', '')
        if command and command.strip():
            record_terminal_io(student_id, f'VM{session_id}', command, 'in')
        session = active_sessions.get(session_key)
        if session:
            try:
                session['channel'].send(command)
            except Exception:
                pass

    @socketio.on('terminal_resize')
    def handle_terminal_resize(data):
        student_id = str(data.get('student_id', ''))
        session_id = str(data.get('session_id', '0'))
        session_key = f'{student_id}:{session_id}'
        session = active_sessions.get(session_key)
        if session:
            try:
                session['channel'].resize_pty(
                    width=data.get('cols', 120),
                    height=data.get('rows', 40),
                )
            except Exception:
                pass

    @socketio.on('terminal_disconnect')
    def handle_terminal_disconnect(data):
        student_id = str(data.get('student_id', ''))
        session_id = str(data.get('session_id', '0'))
        session_key = f'{student_id}:{session_id}'
        close_session(session_key)
        leave_room(session_key)
        emit('terminal_disconnected', {'message': '已断开', 'session_id': session_id})

    print('[TERM] terminal handlers registered', flush=True)
