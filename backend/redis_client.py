"""Redis 缓存 + 在线 + 黑名单模块（成员B）
说明：在成员B原版基础上增加了 fail-safe 容错——当 Redis 服务未启动/不可达时，
各函数返回安全默认值（None / 0 / False）并静默跳过，保证登录、AI 接口不会因
Redis 缺失而崩溃。docker-compose 部署中 Redis 正常运行时，缓存/在线/黑名单全部生效。
"""
import redis
import os
import hashlib
import json
import time

REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))

try:
    _pool = redis.ConnectionPool(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
except Exception:
    _pool = None


def get_redis():
    """返回 Redis 客户端；若 Redis 不可用（未安装/未启动）返回 None（降级为不缓存）。"""
    if _pool is None:
        return None
    return redis.Redis(connection_pool=_pool)


# ---- 1. AI 回复缓存 ----
def cache_ai_reply(student_id, subtask_id, question, reply, ttl=3600):
    r = get_redis()
    if r is None:
        return
    try:
        key = f'ai:cache:{student_id}:{subtask_id}:{hashlib.md5(question.encode()).hexdigest()[:12]}'
        r.setex(key, ttl, json.dumps({'reply': reply}, ensure_ascii=False))
    except Exception:
        return


def get_cached_ai_reply(student_id, subtask_id, question):
    r = get_redis()
    if r is None:
        return None
    try:
        key = f'ai:cache:{student_id}:{subtask_id}:{hashlib.md5(question.encode()).hexdigest()[:12]}'
        val = r.get(key)
        return json.loads(val).get('reply') if val else None
    except Exception:
        return None


# ---- 2. 在线人数 ----
def set_user_online(user_id, display_name, ttl=600):
    r = get_redis()
    if r is None:
        return
    try:
        r.setex(f'online:{user_id}', ttl, display_name)
    except Exception:
        return


def get_online_count():
    r = get_redis()
    if r is None:
        return 0
    try:
        return len(r.keys('online:*'))
    except Exception:
        return 0


def remove_user_online(user_id):
    r = get_redis()
    if r is None:
        return
    try:
        r.delete(f'online:{user_id}')
    except Exception:
        return


# ---- 3. JWT 黑名单 ----
def blacklist_token(jti, exp_timestamp):
    r = get_redis()
    if r is None:
        return
    try:
        ttl = max(1, int(exp_timestamp - time.time()))
        r.setex(f'blacklist:{jti}', ttl, '1')
    except Exception:
        return


def is_token_blacklisted(jti):
    r = get_redis()
    if r is None:
        return False
    try:
        return r.exists(f'blacklist:{jti}') > 0
    except Exception:
        return False


# ---- 4. 终端记录 ----
def push_terminal_io(student_id, data, direction):
    r = get_redis()
    if r is None:
        return
    try:
        r.rpush(f'term:{student_id}', json.dumps({'data': data[:200], 'direction': direction}, ensure_ascii=False))
        r.ltrim(f'term:{student_id}', -200, -1)
    except Exception:
        return
