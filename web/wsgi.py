#!/usr/bin/env python3
"""
Gunicorn WSGI 入口。

生产环境示例：
  python3 scripts/run_gunicorn.py
"""

try:
    from web.server import app
except ModuleNotFoundError:
    from server import app
