"""
DataTutor 限流器（独立模块，避免循环导入）
如果 flask_limiter 未安装，降级为空操作模式
"""
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    _HAS_LIMITER = True
except ImportError:
    _HAS_LIMITER = False


class _NoopLimiter:
    """无操作限流器：未安装 flask-limiter 时使用"""
    def init_app(self, *args, **kwargs):
        pass

    def limit(self, *args, **kwargs):
        def decorator(f):
            return f
        return decorator


if _HAS_LIMITER:
    limiter = Limiter(key_func=get_remote_address, default_limits=[])
else:
    limiter = _NoopLimiter()
