"""Flask Prometheus 指标埋点（成员C：监控模块）"""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CollectorRegistry, CONTENT_TYPE_LATEST
from flask import Response
import os
import time
from functools import wraps

registry = CollectorRegistry()

# ========== API 层指标 ==========

# API 请求计数（按路径 + 方法）
api_requests = Counter(
    'datatutor_api_requests_total',
    'API 请求总数',
    ['method', 'endpoint'],
    registry=registry
)

# API 响应时间
api_latency = Histogram(
    'datatutor_api_latency_seconds',
    'API 响应时间（秒）',
    ['method', 'endpoint'],
    registry=registry
)

# API 错误计数
api_errors = Counter(
    'datatutor_api_errors_total',
    'API 错误总数',
    ['method', 'endpoint', 'status_code'],
    registry=registry
)

# ========== 业务层指标 ==========

# 在线用户数
online_users = Gauge(
    'datatutor_online_users',
    '实时在线学生数',
    registry=registry
)

# 终端连接数
terminal_connections = Gauge(
    'datatutor_terminal_connections',
    '活跃终端连接数',
    registry=registry
)

# 报告生成计数器
reports_generated = Counter(
    'datatutor_reports_total',
    '实训报告生成总数',
    registry=registry
)

# AI 调用计数器（按 Agent）
ai_calls = Counter(
    'datatutor_ai_calls_total',
    'AI Agent 调用次数',
    ['agent'],
    registry=registry
)

# ========== 基础设施指标 ==========

# Doris 连接状态（可选组件，未部署时恒为 0）
doris_connected = Gauge(
    'datatutor_doris_connected',
    'Doris 数据库连接状态（1=通，0=断）',
    registry=registry
)

# MySQL 连接状态
mysql_connected = Gauge(
    'datatutor_mysql_connected',
    'MySQL 数据库连接状态（1=通，0=断）',
    registry=registry
)


def check_infra_health():
    """后台检测基础设施连接状态 → 更新 Gauge 指标"""
    # Doris
    try:
        import pymysql
        host = os.getenv('DORIS_HOST', '127.0.0.1')
        port = int(os.getenv('DORIS_PORT', '9030'))
        user = os.getenv('DORIS_USER', 'root')
        password = os.getenv('DORIS_PASSWORD', '')
        conn = pymysql.connect(host=host, port=port, user=user, password=password,
                               charset='utf8mb4', connect_timeout=2)
        conn.ping()
        conn.close()
        doris_connected.set(1)
    except Exception:
        doris_connected.set(0)

    # MySQL
    try:
        import pymysql
        host = os.getenv('MYSQL_HOST', '127.0.0.1')
        port = int(os.getenv('MYSQL_PORT', '3306'))
        user = os.getenv('MYSQL_USER', 'root')
        password = os.getenv('MYSQL_PASSWORD', '')
        conn = pymysql.connect(host=host, port=port, user=user, password=password,
                               charset='utf8mb4', connect_timeout=2)
        conn.ping()
        conn.close()
        mysql_connected.set(1)
    except Exception:
        mysql_connected.set(0)


def metrics_endpoint():
    """返回 Prometheus 格式的指标数据（每次请求前刷新基础设施状态）"""
    check_infra_health()
    return Response(generate_latest(registry), mimetype=CONTENT_TYPE_LATEST)


# ========== 装饰器：自动记录 API 调用 ==========

def track_api(method, endpoint):
    """装饰器：自动记录 API 调用次数 + 响应时间"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            api_requests.labels(method=method, endpoint=endpoint).inc()
            start = time.time()
            try:
                result = f(*args, **kwargs)
                api_latency.labels(method=method, endpoint=endpoint).observe(time.time() - start)
                return result
            except Exception:
                api_errors.labels(method=method, endpoint=endpoint, status_code='500').inc()
                raise
        return wrapper
    return decorator
