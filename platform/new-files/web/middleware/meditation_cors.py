# -*- coding: utf-8 -*-
"""
冥想室对外接口的跨域放行。

为什么需要
----------
同学预约页面托管在**委托人的子域名**上，接口在 **SMUPA 平台域名**上，
两者不同源。浏览器的同源策略会拦住这个请求，除非平台在响应里明确声明
「允许该来源调用我」—— 这就是 CORS。

只加响应头还不够：浏览器对 `Content-Type: application/json` 的请求会
**先发一个 OPTIONS 预检**，预检通过了才发真实请求。
现有的 /meditation/api/* 视图没有处理 OPTIONS，Django 会回 405，
预检失败 → **真实请求根本不会发出**。所以这里必须自己处理 OPTIONS。

设计取舍
--------
1. **只作用于 `/meditation/api/`** —— 把影响面锁死在冥想室模块，
   不碰平台其它任何接口。
2. **白名单为空 = 不开放** —— 默认安全；必须由管理员在 .env 里显式填来源。
   绝不使用 `*`（那等于任何网站都能调）。
3. **Vary: Origin** —— 避免 CDN/缓存把一个来源的响应错误地喂给另一个来源。
4. 不设 `Access-Control-Allow-Credentials`：这些接口不依赖 Cookie
   （视图是 @csrf_exempt，身份靠手机号或小程序 token），无需带凭据。
"""

from django.conf import settings
from django.http import HttpResponse


class MeditationCorsMiddleware(object):

    #: 只管这个前缀，其它路径一律原样放行
    PATH_PREFIX = '/meditation/api/'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info or ''
        if not path.startswith(self.PATH_PREFIX):
            return self.get_response(request)

        origin = request.META.get('HTTP_ORIGIN', '')
        allowed = self._is_allowed(origin)

        # 预检请求：直接回 204，不进视图
        if request.method == 'OPTIONS':
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)

        if allowed:
            self._apply_headers(response, origin)
        return response

    # ------------------------------------------------------------------
    @staticmethod
    def _is_allowed(origin):
        """来源是否在白名单里。未配置或来源为空一律不放行。"""
        if not origin:
            return False
        allowed = getattr(settings, 'MEDITATION_CORS_ORIGINS', None) or []
        return origin in allowed

    @staticmethod
    def _apply_headers(response, origin):
        # 回显具体来源而不是 *，这样将来若需要带凭据也能用
        response['Access-Control-Allow-Origin'] = origin
        response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, X-Med-Openid, X-Med-Token'
        # 预检结果缓存 24 小时，减少 OPTIONS 往返
        response['Access-Control-Max-Age'] = '86400'
        # 同一 URL 对不同来源的响应不同，必须声明，否则缓存会串
        response['Vary'] = 'Origin'
        return response
