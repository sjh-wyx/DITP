"""Doris 行为日志模块 — 学生操作事件写入"""
import pymysql
import os
import threading
from datetime import datetime


class DorisClient:
    """线程安全的 Doris 连接（每个线程独立连接）"""
    def __init__(self):
        self._local = threading.local()

    def _get_conn(self):
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            host = os.getenv('DORIS_HOST', '127.0.0.1')
            port = int(os.getenv('DORIS_PORT', '9030'))
            user = os.getenv('DORIS_USER', 'root')
            password = os.getenv('DORIS_PASSWORD', '')
            db = os.getenv('DORIS_DB', 'datatutor_analytics')
            self._local.conn = pymysql.connect(
                host=host, port=port, user=user, password=password,
                database=db, charset='utf8mb4', connect_timeout=3
            )
        return self._local.conn

    def execute(self, sql, params=None):
        """执行写入（INSERT）— Doris 已弃用，直接返回，避免连接超时阻塞终端"""
        return

    def query(self, sql, params=None):
        """执行查询（SELECT）"""
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute(sql, params)
            result = cur.fetchall()
            cur.close()
            return result
        except Exception:
            return []


# 全局单例
doris = DorisClient()


# ── 便捷写入函数 ──

def log_terminal_event(student_id, course_id, subtask_id, vm_name, data, direction):
    """记录终端 I/O 事件"""
    doris.execute(
        'INSERT INTO terminal_events (student_id, course_id, subtask_id, vm_name, data, direction) VALUES (%s,%s,%s,%s,%s,%s)',
        (student_id, course_id, subtask_id, vm_name, str(data)[:500], direction)
    )


def log_chat_event(student_id, course_id, subtask_id, role, content):
    """记录 AI 对话事件"""
    doris.execute(
        'INSERT INTO chat_events (student_id, course_id, subtask_id, msg_role, msg_length) VALUES (%s,%s,%s,%s,%s)',
        (student_id, course_id, subtask_id, role, len(content) if content else 0)
    )


def log_task_completion(student_id, course_id, subtask_id, duration_seconds, grade=''):
    """记录子任务完成事件"""
    doris.execute(
        'INSERT INTO task_completions (student_id, course_id, subtask_id, duration_seconds, grade_level) VALUES (%s,%s,%s,%s,%s)',
        (student_id, course_id, subtask_id, duration_seconds or 0, grade)
    )


def log_page_view(student_id, page, duration_seconds=0):
    """记录页面访问"""
    doris.execute(
        'INSERT INTO page_views (student_id, page, duration_seconds) VALUES (%s,%s,%s)',
        (student_id, page, duration_seconds)
    )


# ── 学情报表查询 ──

def get_student_analytics(student_id):
    """查询单个学生的学情分析"""
    result = {'terminal_count': 0, 'chat_count': 0, 'total_tasks': 0, 'avg_duration': 0,
              'top_commands': [], 'recent_events': []}

    rows = doris.query(
        'SELECT COUNT(*) FROM terminal_events WHERE student_id=%s', (student_id,))
    if rows:
        result['terminal_count'] = rows[0][0]

    rows = doris.query(
        'SELECT COUNT(*) FROM chat_events WHERE student_id=%s', (student_id,))
    if rows:
        result['chat_count'] = rows[0][0]

    rows = doris.query(
        'SELECT COUNT(*), AVG(duration_seconds) FROM task_completions WHERE student_id=%s', (student_id,))
    if rows and rows[0][0]:
        result['total_tasks'] = rows[0][0]
        result['avg_duration'] = round(rows[0][1] or 0)

    # 最近 10 条事件
    rows = doris.query(
        'SELECT event_time, direction, LEFT(data,60) FROM terminal_events WHERE student_id=%s ORDER BY event_time DESC LIMIT 10',
        (student_id,))
    result['recent_events'] = [{'time': str(r[0]), 'dir': r[1], 'data': r[2]} for r in rows]

    return result


def get_class_analytics(course_id):
    """查询课程整体学情"""
    result = {}
    rows = doris.query(
        'SELECT student_id, COUNT(*) as cnt, AVG(duration_seconds) as avg_dur FROM task_completions WHERE course_id=%s GROUP BY student_id',
        (course_id,))
    result['students'] = [{'student_id': r[0], 'tasks': r[1], 'avg_sec': round(r[2] or 0)} for r in rows]
    return result


# ── 以下为成员E 新增函数 ──

def get_course_ranking(course_id):
    """学生排行：终端命令数 TOP5 + 对话最多 TOP5 + 耗时最长 TOP5"""
    result = {}
    rows = doris.query(
        'SELECT student_id, COUNT(*) as cnt FROM terminal_events WHERE course_id=%s GROUP BY student_id ORDER BY cnt DESC LIMIT 5',
        (course_id,))
    result['terminal_top5'] = [{'student_id': r[0], 'count': r[1]} for r in rows]
    rows = doris.query(
        'SELECT student_id, COUNT(*) as cnt FROM chat_events WHERE course_id=%s GROUP BY student_id ORDER BY cnt DESC LIMIT 5',
        (course_id,))
    result['chat_top5'] = [{'student_id': r[0], 'count': r[1]} for r in rows]
    rows = doris.query(
        'SELECT student_id, SUM(duration_seconds) as total FROM task_completions WHERE course_id=%s GROUP BY student_id ORDER BY total DESC LIMIT 5',
        (course_id,))
    result['duration_top5'] = [{'student_id': r[0], 'seconds': int(r[1])} for r in rows]
    return result


def get_trend(course_id, days=7):
    """学习趋势：最近 N 天每日活跃数 + 任务完成数"""
    result = {'days': [], 'active': [], 'tasks': []}
    rows_active = doris.query(
        'SELECT DATE(event_time) as d, COUNT(DISTINCT student_id) FROM terminal_events '
        'WHERE course_id=%s AND event_time >= DATE_SUB(NOW(), INTERVAL %s DAY) GROUP BY d ORDER BY d',
        (course_id, days))
    rows_tasks = doris.query(
        'SELECT DATE(event_time) as d, COUNT(*) FROM task_completions '
        'WHERE course_id=%s AND event_time >= DATE_SUB(NOW(), INTERVAL %s DAY) GROUP BY d ORDER BY d',
        (course_id, days))
    date_map = {}
    for r in rows_active:
        date_map[str(r[0])] = {'active': r[1], 'tasks': 0}
    for r in rows_tasks:
        key = str(r[0])
        if key in date_map:
            date_map[key]['tasks'] = r[1]
        else:
            date_map[key] = {'active': 0, 'tasks': r[1]}
    for d in sorted(date_map.keys()):
        result['days'].append(d)
        result['active'].append(date_map[d]['active'])
        result['tasks'].append(date_map[d]['tasks'])
    return result
