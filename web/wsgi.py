#!/usr/bin/env python3
"""
Gunicorn WSGI 入口。

生产环境示例：
  uv run --with gunicorn gunicorn -c web/gunicorn.conf.py web.wsgi:app
"""

from server import app

