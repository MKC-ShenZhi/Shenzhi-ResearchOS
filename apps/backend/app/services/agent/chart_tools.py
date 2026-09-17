"""配图工具：`draw_chart`（从被引数字渲图）与 `image_search`（取权威原图）。

移植 SZDR 的 `src/tools/draw-chart.tool.ts` 与 `image-search.tool.ts`，按本基座的能力裁剪：

- **draw_chart**：只用调用方**逐字给出**的数字渲染柱/折线/饼图，至少 2 个可比数据点参与比较；
  含中文时由 `cjkFont` 指定可用字体（否则图上中文是方框）。产物写入工作区，
  返回 markdown 图片行（指向图床端点），供报告直接引用。
- **image_search**：走 Exa（`EXA_API_KEY`）找图，取回后**缓存进工作区**再以图床 URL 返回——
  直接引用外链会因防盗链/失效而碎图。单张取不到不影响其余结果。

两个工具都需要工作区根（产物落盘 + 图床路径）；工作区未挂载时不注册（不宣称做不到的能力）。
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from app.core.errors import BusinessError
from app.services.agent.netguard import (
    BlockedUrlError, assert_public_http_url, read_bytes_capped, safe_get,
)
from app.services.agent.tools import Tool, ToolOutput, tool

IMAGE_DIR = 'images'                    # 工作区内的图目录
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGES = 10
EXA_ENDPOINT = 'https://api.exa.ai/search'
TIMEOUT_S = 45.0
# 中文标题/标签在图上的字体候选（matplotlib 找不到就退回默认，此时中文会显示为方框）
_CJK_FONTS = ('Microsoft YaHei', 'SimHei', 'PingFang SC', 'Noto Sans CJK SC',
              'Source Han Sans SC', 'WenQuanYi Zen Hei')
_IMAGE_EXT = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'image/gif': 'gif'}


def _has_cjk(text: str) -> bool:
    return bool(re.search(r'[\u4e00-\u9fff]', text))


def _asset_url(session_id: str | None, relative: str) -> str:
    """图床地址：会话工作区文件端点（image_search/draw_chart 的产物都在工作区里）。"""
    path = f'{IMAGE_DIR}/{relative}'
    if session_id:
        return f'/api/v1/agent/assets/{session_id}/{path}'
    return f'/api/v1/agent/session/_/file?path={path}'


class ChartArgs(BaseModel):
    kind: str = Field(description='bar（柱）/ line（折线）/ pie（饼）')
    title: str = Field(default='', description='图题')
    values: list[float | str] = Field(description='数值；必须逐字来自被引来源，不得推算或估计')
    x_labels: list[str] = Field(default_factory=list, description='与 values 一一对应的标签')
    series_name: str = Field(default='', description='系列名（单系列时的图例文字）')


def render_chart(args: ChartArgs) -> bytes:
    """渲染图表为 PNG 字节；数据不合法（点数不足/长度不匹配）直接报错，不画半成品。"""
    try:
        import matplotlib
        matplotlib.use('Agg')                     # 服务端无显示环境
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
    except ImportError as exc:  # pragma: no cover - 依赖缺失时给出明确指引
        raise BusinessError(20004, f'绘图依赖未安装（matplotlib）：{exc}') from exc

    kind = args.kind.strip().lower()
    if kind not in ('bar', 'line', 'pie'):
        raise BusinessError(20001, f'draw_chart 只支持 bar / line / pie，收到 {args.kind!r}')
    labels = list(args.x_labels)
    # 允许 values 里混入纯数字字符串（模型常把表格里的数字原样搬过来）
    values: list[float] = []
    for item in args.values:
        try:
            values.append(float(str(item).replace(',', '').replace('%', '')))
        except ValueError as exc:
            raise BusinessError(20001, f'values 里有非数字项: {item!r}') from exc
    if len(values) < 2:
        raise BusinessError(20001, '至少需要 2 个可比数据点才成图（1 个点没有比较意义）')
    if labels and len(labels) != len(values):
        raise BusinessError(20001, f'x_labels（{len(labels)}）与 values（{len(values)}）数量必须一致')
    if not labels:
        labels = [str(index + 1) for index in range(len(values))]

    if _has_cjk(args.title) or any(_has_cjk(item) for item in labels):
        available = {font.name for font in font_manager.fontManager.ttflist}
        picked = next((name for name in _CJK_FONTS if name in available), None)
        if picked:
            plt.rcParams['font.sans-serif'] = [picked, *plt.rcParams['font.sans-serif']]
        plt.rcParams['axes.unicode_minus'] = False

    figure, axes = plt.subplots(figsize=(8, 4.8), dpi=140)
    try:
        if kind == 'pie':
            axes.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
            axes.axis('equal')
        elif kind == 'line':
            axes.plot(labels, values, marker='o', linewidth=2)
            axes.grid(True, alpha=0.3)
        else:
            axes.bar(labels, values)
            axes.grid(True, axis='y', alpha=0.3)
        if args.title:
            axes.set_title(args.title)
        if kind != 'pie' and args.series_name:
            axes.set_ylabel(args.series_name)
        if kind == 'bar' and max(len(str(item)) for item in labels) > 12:
            figure.autofmt_xdate(rotation=30)
        figure.tight_layout()
        import io
        buffer = io.BytesIO()
        figure.savefig(buffer, format='png', bbox_inches='tight')
        return buffer.getvalue()
    finally:
        plt.close(figure)


def chart_tool(*, workspace_root: Path | None, session_id: str | None = None,
               transport: httpx.BaseTransport | None = None) -> Tool:
    """工厂：产物落进工作区；未挂工作区时由组合根不注册本工具。"""

    @tool(name='draw_chart',
          description='用**调用方给定的**数字渲染柱/折线/饼图并返回图片 markdown。'
                      '数字必须逐字来自被引来源，不得推算、估计或补全；至少 2 个可比数据点。',
          params=ChartArgs, timeout_s=180.0)
    async def draw_chart(args: ChartArgs) -> str | ToolOutput:
        import json as _json

        png = await asyncio.to_thread(render_chart, args)     # 绘图是 CPU 活，别阻塞事件循环
        if workspace_root is None:
            raise BusinessError(20004, '未挂载工作区，无法保存图表产物')
        target_dir = Path(workspace_root) / IMAGE_DIR
        target_dir.mkdir(parents=True, exist_ok=True)
        name = f'chart-{uuid.uuid4().hex[:12]}.png'
        (target_dir / name).write_bytes(png)
        url = _asset_url(session_id, name)
        caption = args.title or args.series_name or '图表'
        return _json.dumps({
            'path': f'{IMAGE_DIR}/{name}',
            'url': url,
            'markdown': f'![{caption}]({url})',
            'caption': caption,
            'data_points': len(args.values),
            'note': '图上的数字逐字来自给定 values；请在被引来源旁标注 [n]。',
        }, ensure_ascii=False)

    return draw_chart


class ImageSearchArgs(BaseModel):
    query: str
    limit: int = Field(default=5, description='返回张数（1-10）')


def _exa_images(body: Any) -> list[dict[str, str]]:
    """从 Exa 响应里抽出 (title, imageUrl, sourceUrl)；字段名在不同版本间有差异。"""
    images: list[dict[str, str]] = []
    for item in (body or {}).get('results') or []:
        if not isinstance(item, dict):
            continue
        candidates = [
            *(item.get('richImageLinks') or []),
            *(item.get('imageLinks') or []),
            *((item.get('extras') or {}).get('richImageLinks') or []),
        ]
        for entry in candidates:
            url = entry.get('url') if isinstance(entry, dict) else None
            if not isinstance(url, str) or not url.startswith(('http://', 'https://')):
                continue
            images.append({
                'title': str(item.get('title') or '').strip(),
                'imageUrl': url,
                'sourceUrl': str(item.get('url') or ''),
            })
    return images


def image_search_tool(*, workspace_root: Path | None, session_id: str | None = None,
                      transport: httpx.BaseTransport | None = None) -> Tool:
    """工厂：Exa 找图 → 取回缓存进工作区 → 返回图床 URL（外链会碎图，所以必须落盘）。"""

    @tool(name='image_search',
          description='按关键词找权威配图（Exa 检索），取回后缓存并返回图片 markdown。'
                      '优先政府/国际组织/学术机构/官方数据库的原始图。',
          params=ImageSearchArgs, timeout_s=180.0)
    async def image_search(args: ImageSearchArgs) -> str | ToolOutput:
        import json as _json
        import os

        api_key = os.getenv('EXA_API_KEY', '').strip()
        if not api_key:
            raise BusinessError(20004, '图片检索未配置（EXA_API_KEY）')
        if workspace_root is None:
            raise BusinessError(20004, '未挂载工作区，无法缓存图片')
        limit = max(1, min(args.limit, MAX_IMAGES))
        payload = {'query': args.query, 'type': 'neural', 'numResults': limit,
                   'contents': {'richImageLinks': True}}
        async with httpx.AsyncClient(timeout=TIMEOUT_S, transport=transport) as client:
            try:
                response = await client.post(EXA_ENDPOINT, json=payload,
                                             headers={'content-type': 'application/json',
                                                      'x-api-key': api_key})
            except httpx.HTTPError as exc:
                raise BusinessError(20004, f'图片检索失败：{exc}') from exc
            if response.status_code >= 400:
                raise BusinessError(20004,
                                    f'图片检索失败（Exa {response.status_code}）：{response.text[:200]}')

            target_dir = Path(workspace_root) / IMAGE_DIR
            target_dir.mkdir(parents=True, exist_ok=True)
            cached: list[dict[str, str]] = []
            with httpx.Client(timeout=TIMEOUT_S, transport=transport) as fetch_client:
                for item in _exa_images(response.json())[:limit]:
                    saved = await asyncio.to_thread(
                        _cache_image, fetch_client, target_dir, item, session_id)
                    if saved:
                        cached.append(saved)
        if not cached:
            # 渠道有响应但拿不到图（当前 Exa /search 不返回图片字段，只抽文本）：
            # 这是**能力不可用**而不是查询错误——如实声明，让技能退回 draw_chart。
            return ToolOutput(
                content=json.dumps({
                    'provider': 'Exa',
                    'images': [],
                    'unavailable': 'image_search',
                    'note': '当前图片检索渠道没有返回任何可用图片（Exa /search 只抽文本内容，'
                            '不提供图片链接）。改用 draw_chart 用来源里的数字自行渲图，'
                            '或不要配图。',
                }, ensure_ascii=False),
                unavailable=('image_search',))
        return _json.dumps({
            'provider': 'Exa',
            'query': args.query,
            'images': cached,
            'markdown': '\n\n'.join(item['markdown'] for item in cached),
            'note': '图片已缓存到工作区；报告里请在图注中标明来源页。',
        }, ensure_ascii=False)

    return image_search


def _cache_image(client: httpx.Client, target_dir: Path, item: dict[str, str],
                 session_id: str | None) -> dict[str, str] | None:
    """取回单张图并落盘；任何失败返回 None（一张图不可达不该让整次检索失败）。"""
    try:
        assert_public_http_url(item['imageUrl'])          # 逐跳 SSRF 防护
        response = safe_get(client, item['imageUrl'])
        if response.status_code >= 400:
            return None
        content_type = response.headers.get('content-type', '').split(';')[0].strip().lower()
        extension = _IMAGE_EXT.get(content_type)
        if extension is None:
            return None                                    # 非图片内容一律丢弃
        data = read_bytes_capped(response, MAX_IMAGE_BYTES)
        if not data:
            return None
        name = f'image-{uuid.uuid4().hex[:12]}.{extension}'
        (target_dir / name).write_bytes(data)
        url = _asset_url(session_id, name)
        caption = item.get('title') or urlparse(item['imageUrl']).netloc
        return {'title': caption, 'image_url': url, 'source_url': item.get('sourceUrl', ''),
                'markdown': f'![{caption}]({url})'}
    except (BlockedUrlError, ValueError, httpx.HTTPError, OSError):
        return None
