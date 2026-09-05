"""Vercel Serverless 入口。

Vercel Python Runtime 会加载本文件中名为 ``app`` 的 ASGI 应用，
所有请求经 vercel.json 的 rewrites 转发至此函数。
"""

from app.main import app

__all__ = ["app"]
