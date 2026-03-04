#!/usr/bin/env python3
"""
DeepVision Gunicorn 生产配置。

可通过环境变量覆盖：
- GUNICORN_WORKERS
- GUNICORN_THREADS
- GUNICORN_TIMEOUT
- GUNICORN_GRACEFUL_TIMEOUT
- GUNICORN_KEEPALIVE
- GUNICORN_WORKER_CLASS
- GUNICORN_LOG_LEVEL
- GUNICORN_ACCESSLOG
- GUNICORN_ERRORLOG
- GUNICORN_PRELOAD_APP
"""

import multiprocessing
import os


def _env_int(name: str, default: int, min_value: int = 1) -> int:
    try:
        value = int(str(os.getenv(name, default)).strip())
    except Exception:
        value = default
    return max(min_value, value)


def _env_bool(name: str, default: bool = False) -> bool:
    value = str(os.getenv(name, str(default))).strip().lower()
    if value in {"1", "true", "yes", "on", "y"}:
        return True
    if value in {"0", "false", "no", "off", "n"}:
        return False
    return default


_cpu_count = multiprocessing.cpu_count() or 2
_default_workers = max(2, _cpu_count * 2 + 1)

host = str(os.getenv("SERVER_HOST", "0.0.0.0")).strip() or "0.0.0.0"
port = _env_int("SERVER_PORT", 5001, min_value=1)
bind = f"{host}:{port}"

workers = _env_int("GUNICORN_WORKERS", _default_workers, min_value=1)
threads = _env_int("GUNICORN_THREADS", 2, min_value=1)
worker_class = str(os.getenv("GUNICORN_WORKER_CLASS", "gthread")).strip() or "gthread"

timeout = _env_int("GUNICORN_TIMEOUT", 120, min_value=30)
graceful_timeout = _env_int("GUNICORN_GRACEFUL_TIMEOUT", 30, min_value=5)
keepalive = _env_int("GUNICORN_KEEPALIVE", 5, min_value=1)

accesslog = str(os.getenv("GUNICORN_ACCESSLOG", "-")).strip() or "-"
errorlog = str(os.getenv("GUNICORN_ERRORLOG", "-")).strip() or "-"
loglevel = str(os.getenv("GUNICORN_LOG_LEVEL", "info")).strip() or "info"

preload_app = _env_bool("GUNICORN_PRELOAD_APP", False)
capture_output = True
reuse_port = True

