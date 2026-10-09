"""
Docker Engine API 轻量客户端 —— 只用标准库，通过 /var/run/docker.sock 直连守护进程。

为什么不用 `docker` 命令行或 docker-py：
  - app 运行在容器里，镜像**没有** docker CLI（终端页报「本机未安装 Docker」的根因）
  - 容器内也没有 docker-py；即使 pip 装上，镜像一旦重建就丢失
  - 而 /var/run/docker.sock 已由 restart_app.sh 挂载、进程是 root → 直接走 HTTP-over-Unix-Socket，
    零依赖、零维护，重建镜像/重启容器都不受影响

对外接口：
  available()                       -> bool
  ping()                           -> (ok, detail)
  find_container(name)             -> dict | None（含 State/Status）
  inspect(name)                    -> dict | None
  exists(name) / is_running(name)  -> bool
  start(name) / stop(name)         -> (ok, err)
  run(image, name, port, volumes, restart_policy) -> (ok, container_id_or_err)
"""
import http.client
import json
import os
import socket

SOCKET_PATH = os.getenv('DOCKER_SOCKET', '/var/run/docker.sock')
API_VERSION = os.getenv('DOCKER_API_VERSION', '')  # 留空 = 由守护进程协商


class _UnixHTTPConnection(http.client.HTTPConnection):
    """把 HTTP 连接建到 Unix domain socket 上。"""

    def __init__(self, path, timeout=10):
        super().__init__('localhost', timeout=timeout)
        self._unix_path = path

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self._unix_path)
        self.sock = sock


def _request(method, endpoint, body=None, timeout=15):
    """返回 (status, decoded_json_or_text)。任何异常都转成 (0, 错误串)。"""
    conn = None
    try:
        conn = _UnixHTTPConnection(SOCKET_PATH, timeout=timeout)
        headers = {'Host': 'localhost'}
        payload = None
        if body is not None:
            payload = json.dumps(body).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        conn.request(method, endpoint, body=payload, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        text = raw.decode('utf-8', 'replace')
        try:
            return resp.status, json.loads(text)
        except Exception:
            return resp.status, text
    except FileNotFoundError:
        return 0, 'docker socket 不存在: %s' % SOCKET_PATH
    except PermissionError:
        return 0, '无权访问 docker socket: %s' % SOCKET_PATH
    except Exception as exc:
        return 0, '%s: %s' % (type(exc).__name__, exc)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _version():
    return ('/v%s' % API_VERSION) if API_VERSION else ''


def available():
    return os.path.exists(SOCKET_PATH)


def ping():
    status, data = _request('GET', _version() + '/_ping', timeout=5)
    if status == 200:
        return True, 'ok'
    return False, str(data)[:200]


def find_container(name):
    """按名字精确匹配（Docker 的 name 过滤是子串匹配，这里再精确比对一次）。"""
    status, data = _request('GET', _version() + '/containers/json?all=1')
    if status != 200 or not isinstance(data, list):
        return None
    for item in data:
        for nm in item.get('Names') or []:
            if nm.lstrip('/') == name:
                return item
    return None


def inspect(name):
    status, data = _request('GET', _version() + '/containers/%s/json' % name)
    return data if status == 200 and isinstance(data, dict) else None


def exists(name):
    return find_container(name) is not None


def is_running(name):
    item = find_container(name)
    return bool(item) and item.get('State') == 'running'


def start(name):
    status, data = _request('POST', _version() + '/containers/%s/start' % name, timeout=20)
    if status in (204, 304):
        return True, ''
    return False, str(data)[:200]


def stop(name, timeout=5):
    """停止容器。已停止（304）也算成功。"""
    status, data = _request('POST', _version() + '/containers/%s/stop?t=%d' % (name, timeout), timeout=30)
    if status in (204, 304):
        return True, ''
    return False, str(data)[:200]


def remove(name, force=True):
    """删除容器。force=True 时运行中也会停掉再删；v=1 同时删除匿名卷。"""
    status, data = _request('DELETE', _version() + '/containers/%s?force=%d&v=1' % (name, 1 if force else 0),
                            timeout=30)
    if status in (204, 200):
        return True, ''
    if status == 404:
        return True, ''      # 本来就不存在，视为已完成
    return False, str(data)[:200]


# ---------- 学生容器生命周期（课程完成即回收） ----------

# 课程完成时若仍有活动 SSH 会话，先挂起，等断开后再删
_pending_removal = {}


def active_session_exists(student_id):
    """该生是否还有活动终端会话。有则不能硬删容器，否则终端当场断掉。"""
    try:
        from terminal_ws.terminal import active_sessions
    except Exception:
        return False
    key = str(student_id)
    for session_key, sess in list(active_sessions.items()):
        try:
            if str(sess.get('student_id')) == key:
                return True
        except Exception:
            continue
    return False


def container_name_for(student_id):
    return 'dts-student%s' % student_id


def remove_when_idle(student_id, container_name=None):
    """删除学生容器；若有活动会话则挂起，返回 (已删除?, 挂起?, 说明)。

    绝不让容器操作影响主流程 —— 所有异常都在这里消化。
    """
    name = container_name or container_name_for(student_id)
    try:
        if not available():
            return False, False, 'docker socket 不可用'
        if active_session_exists(student_id):
            _pending_removal[str(student_id)] = name
            return False, True, '终端会话仍在使用，已在断开后回收'
        if not exists(name):
            _pending_removal.pop(str(student_id), None)
            return False, False, '容器不存在'
        ok, err = remove(name)
        if ok:
            _pending_removal.pop(str(student_id), None)
            print('[DOCKER] 已回收学生容器 %s' % name, flush=True)
            return True, False, ''
        print('[DOCKER] 回收 %s 失败: %s' % (name, err), flush=True)
        return False, False, '删除失败: %s' % err
    except Exception as exc:
        print('[DOCKER] remove_when_idle 异常: %s' % exc, flush=True)
        return False, False, str(exc)


def flush_pending(student_id):
    """会话断开后调用：把挂起的删除补上。"""
    name = _pending_removal.get(str(student_id))
    if not name:
        return False
    if active_session_exists(student_id):
        return False
    return remove_when_idle(student_id, name)[0]


def course_completed(student_id, course_id):
    """该生在该课程下的子任务是否已全部完成。查不到课程/子任务时返回 False。"""
    try:
        from models import Subtask, TaskProgress
        subtask_ids = [s.id for s in Subtask.query.filter_by(course_id=course_id).all()]
        if not subtask_ids:
            return False
        done = (TaskProgress.query
                .filter(TaskProgress.student_id == student_id,
                        TaskProgress.subtask_id.in_(subtask_ids),
                        TaskProgress.status == 'completed')
                .count())
        return done >= len(subtask_ids)
    except Exception as exc:
        print('[DOCKER] course_completed 查询异常: %s' % exc, flush=True)
        return False


def cleanup_completed(student_id, course_id):
    """课程全部完成 → 回收该生容器。返回 (已删除?, 是否为完成态, 提示文案)。"""
    try:
        if not course_completed(student_id, course_id):
            return False, False, ''
        removed, pending, note = remove_when_idle(student_id)
        if removed:
            return True, True, '本课程已全部完成，实训容器已自动回收。重新开始本课程会为你重新分配干净环境。'
        if pending:
            return False, True, '本课程已全部完成，实训容器将在终端断开后自动回收。'
        return False, True, '本课程已全部完成。'
    except Exception as exc:
        print('[DOCKER] cleanup_completed 异常: %s' % exc, flush=True)
        return False, False, ''


def run(image, name, port, volumes=None, restart_policy='unless-stopped'):
    """创建并启动容器。port = 宿主端口（绑 127.0.0.1），容器内固定 22。"""
    host_config = {
        'PortBindings': {'22/tcp': [{'HostIp': '127.0.0.1', 'HostPort': str(port)}]},
        'RestartPolicy': {'Name': restart_policy},
        'Binds': list(volumes or []),
    }
    payload = {
        'Image': image,
        'HostConfig': host_config,
        'ExposedPorts': {'22/tcp': {}},
    }
    status, data = _request('POST', _version() + '/containers/create?name=%s' % name,
                            body=payload, timeout=30)
    if status not in (201, 200):
        return False, 'create 失败(%s): %s' % (status, str(data)[:200])
    cid = (data or {}).get('Id', '')[:12] if isinstance(data, dict) else ''
    status, data = _request('POST', _version() + '/containers/%s/start' % name, timeout=30)
    if status not in (204, 304):
        return False, 'start 失败(%s): %s' % (status, str(data)[:200])
    return True, cid
