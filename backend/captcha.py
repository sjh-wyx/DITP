"""
DataTutor 验证码模块
自绘4位数字验证码，Pillow + Redis 存储
带 Redis 不可用时的内存降级方案（开发/单机测试用）
"""
import io
import base64
import random
import string
import uuid
import threading
import time
import redis_client
from PIL import Image, ImageDraw


# 内存降级存储（Redis 不可用时使用）{captcha_id: (code, expire_at)}
_fallback_store = {}
_fallback_lock = threading.Lock()
FALLBACK_TTL = 300  # 5 分钟


def _fallback_set(captcha_id, code, ttl=FALLBACK_TTL):
    with _fallback_lock:
        _fallback_store[captcha_id] = (code, time.time() + ttl)
        # 顺手清理过期项
        now = time.time()
        for k in list(_fallback_store.keys()):
            if _fallback_store[k][1] < now:
                del _fallback_store[k]


def _fallback_get(captcha_id):
    with _fallback_lock:
        item = _fallback_store.get(captcha_id)
        if not item:
            return None
        code, exp = item
        if exp < time.time():
            del _fallback_store[captcha_id]
            return None
        return code


def _fallback_delete(captcha_id):
    with _fallback_lock:
        _fallback_store.pop(captcha_id, None)


def _store_captcha(captcha_id, code):
    """优先存 Redis，失败则降级到内存"""
    r = redis_client.get_redis()
    if r is not None:
        try:
            r.setex(f'captcha:{captcha_id}', FALLBACK_TTL, code)
            return  # 成功
        except Exception:
            pass  # 降级
    _fallback_set(captcha_id, code)


def _fetch_captcha(captcha_id):
    """优先从 Redis 取，失败则从内存取"""
    r = redis_client.get_redis()
    if r is not None:
        try:
            stored = r.get(f'captcha:{captcha_id}')
            if stored is not None:
                return stored.decode('utf-8') if isinstance(stored, bytes) else stored
        except Exception:
            pass
    return _fallback_get(captcha_id)


def _delete_captcha(captcha_id):
    r = redis_client.get_redis()
    if r is not None:
        try:
            r.delete(f'captcha:{captcha_id}')
            return
        except Exception:
            pass
    _fallback_delete(captcha_id)


def generate_captcha():
    """生成验证码图片，返回 (captcha_id, base64_image)"""
    # 4位随机数字
    code = ''.join(random.choices(string.digits, k=4))
    captcha_id = str(uuid.uuid4())

    # 存验证码（Redis 优先，失败降级内存）
    _store_captcha(captcha_id, code)

    # 绘制图片
    width, height = 120, 44
    img = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 随机背景颜色块
    for i in range(20):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = x1 + random.randint(4, 12)
        y2 = y1 + random.randint(4, 12)
        color = (random.randint(200, 255), random.randint(200, 255), random.randint(200, 255))
        draw.rectangle([x1, y1, x2, y2], fill=color)

    # 干扰线
    for _ in range(3):
        x1 = random.randint(0, width // 3)
        y1 = random.randint(0, height)
        x2 = random.randint(width * 2 // 3, width)
        y2 = random.randint(0, height)
        color = (random.randint(100, 200), random.randint(100, 200), random.randint(100, 200))
        draw.line([x1, y1, x2, y2], fill=color, width=1)

    # 噪点
    for _ in range(30):
        x = random.randint(0, width)
        y = random.randint(0, height)
        color = (random.randint(100, 200), random.randint(100, 200), random.randint(100, 200))
        draw.point((x, y), fill=color)

    # 绘制数字
    for i, ch in enumerate(code):
        x = 15 + i * 24 + random.randint(-3, 3)
        y = random.randint(4, 12)
        color = (
            random.randint(0, 80),
            random.randint(80, 160),
            random.randint(160, 220)
        )
        draw.text((x, y), ch, fill=color)

    # 输出 base64
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

    return captcha_id, f'data:image/png;base64,{b64}'


def verify_captcha(captcha_id, captcha_code):
    """校验验证码，成功返回 True 并删除存储项，失败返回 False"""
    if not captcha_id or not captcha_code:
        return False
    stored_str = _fetch_captcha(captcha_id)
    if stored_str is None:
        return False
    if str(stored_str).strip().lower() == str(captcha_code).strip().lower():
        _delete_captcha(captcha_id)  # 一次性验证码
        return True
    return False
