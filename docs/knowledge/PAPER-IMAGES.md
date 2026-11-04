# 知识库搜索论文图片

搜索链路：知识底座 `image_id` → Knowledge Adapter → FastAPI `PaperSearchResult.imageId`
→ Web BFF / Knowledge Client → `KnowledgeResultCard`（`features/knowledge/search/components/result-card.tsx`）→ `getPaperThumbnailUrl(imageId)`
→ 同源 `/api/paper-images/[...path]` → 服务端 HTTP fetch 知识底座 Nginx `/images/`
→ 现有 `PaperThumbnail`。
`paper_id` / `id` 仍是不透明标识，不再用于推断图片名称。

搜索字段缺失或 `null`、开关关闭、非法路径均使用原有兜底；加载失败继续由
`PaperThumbnail.onError` 处理，放大预览不变。浏览历史转换为搜索卡片时明确使用
`imageId: null`，不从详情推断图片。

首页（匿名与登录 Feed）：`daily`、`trending`、`personal` 数据源的论文都只携带 `image_id`，
`mapDiscoveryPaper` 用 `getPaperThumbnailUrl(image_id)` 解析，因此受此开关控制；只有兜底快照
（`fallback`）中的论文带 `thumbnail_url`（同时也带 `image_id`），Web 优先使用 `public/paper-thumbnails/`
静态图，不受开关和底座图片服务影响。所有首页数据源的论文都要通过统一准入检查，只接受本代理能处理的 png/jpg/webp 路径（底座的 SVG 图不收录）。底座原图中位数约 180 KB、约两成超过
500 KB；`PaperThumbnail` 经 `next/image` 按卡片宽度输出压缩后的 webp，原图只在
「查看原图」时加载。底座的 `/images/...` 图片接口目前不在其接口手册中，是按实际返回的
`image_id`（形如 `/images/CVPR_2026/2604.26488v1.png`）验证可用的。

知识底座只在检索结果中提供 `image_id`；详情接口 `GET /api/kg/paper` 不提供该字段，
因此详情契约不包含图片。并非所有上游记录都有图片。

## 配置与部署

本地默认保留 `NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED=false`，不发起知识库图片请求。
不需要本地图片文件、共享文件系统、服务器软链接或图片目录挂载。

图片代理复用知识底座已有的 `KNOWLEDGE_BASE_API_URL`，不增加图片专用 Base URL。
Web 通过已有 `config/env.ts` 的 `optionalEnv()` 在服务端运行时读取配置：

```ini
# 同时注入 Web 和 FastAPI 服务端进程；不使用 NEXT_PUBLIC_ 前缀。
KNOWLEDGE_BASE_API_URL=<KNOWLEDGE_BASE_API_URL>
# 同名复用后端超时配置，默认 30 秒；覆盖响应头及 body 读取。
KNOWLEDGE_BASE_TIMEOUT_SEC=30
# 本地默认关闭；生产启用需在构建环境设为 true 后重新构建。
NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED=false
```

Web 和 FastAPI 是独立进程，配置在 `apps/backend/.env` 中不会自动传给 Next.js。
本地 Web 可使用 `apps/web/.env.local`；部署环境需显式为 Web 服务端注入运行时配置。两端的 `KNOWLEDGE_BASE_API_URL` 必须保持一致，末尾有无 `/` 均可。
该地址仅用于服务端请求，不进入浏览器 URL，也不返回上游 Location、Server 等响应头。
未配置或配置非法时图片代理返回空的 503，应用仍可正常启动。

生产启用步骤：

1. 部署 FastAPI 的可空 `imageId` 契约。
2. 给 Web 服务端注入与 FastAPI 相同的 `KNOWLEDGE_BASE_API_URL`，确认 Web 到知识底座的网络可达。
3. 构建时设置 `NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED=true`，重新构建、部署并重启 Web。
4. 检查搜索响应包含真实 `imageId`；缺失、null、代理错误继续显示兜底。

`NEXT_PUBLIC_` 开关在构建时内联，单独更改运行时环境变量不能启用已有 bundle。
地址或超时是服务端运行时配置，修改后重启进程即可，无需因此重新构建。

在 `apps/web` 中执行：

```bash
NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED=true pnpm build
```

## 代理安全、错误与缓存

- 复用现有路径校验，只允许安全 ASCII 片段及 PNG/JPG/JPEG/WebP 扩展名。
  拒绝 `..`、百分号、编码斜杠、反斜杠、协议、查询串等片段，不二次解码。
- 目标只由服务端配置和 `images/<安全路径>` 构成；客户端 URL、Host、查询参数不能改变来源。
  Base URL 仅允许 HTTP(S)，拒绝内嵌账号密码、查询串及 fragment。
- `redirect: manual`，所有重定向均拒绝，包括指向其他域或内网地址的 Location。
  不转发浏览器 Cookie、Authorization、Range 等非必要请求头。
- 上游 200 的 MIME 必须匹配文件扩展名；HTML、SVG、缺失 MIME、其他格式均拒绝。
- 设置超时，完整读取 body 成功后才返回，响应读取错误也不会中断或泄漏上游错误页面。
- 浏览器和原图预览始终访问深知同源路由，HTTPS 页面不会直接加载上游 HTTP 图片。

| 情况 | 响应 |
| --- | --- |
| 合法图片 | 200，原始字节及正确 Content-Type |
| 条件请求命中上游缓存 | 304，空 body |
| 非法路径、上游 404/410 | 404，空 body |
| Base URL 缺失或非法 | 503，空 body |
| 请求或 body 超时 | 504，空 body |
| 网络失败、重定向、其他上游异常、非法 MIME | 502，空 body |

错误响应使用 `Cache-Control: no-store`。成功响应转发上游 `Cache-Control`、`ETag` 和
`Last-Modified`；未提供 Cache-Control 时沿用 `public, max-age=3600, must-revalidate`。
将浏览器 `If-None-Match`、`If-Modified-Since` 传给上游，由 Nginx 判断 304。
上游无条件返回的 304 视为异常；不转发 Set-Cookie、Location、Content-Encoding 等头。
代理 fetch 使用 `cache: no-store`，不叠加 Next.js fetch 数据缓存；浏览器和现有
`next/image` 图片优化仍按原有机制工作。

## curl 验收

先在 Web 服务端所在运行环境确认上游网络：

```bash
curl -I '<KNOWLEDGE_BASE_API_URL>/images/CVPR_2026/2605.05077v2.png'
```

将 `https://你的深知域名` 替换为正式地址，使用实际存在的图片：

```bash
curl -sS -D /tmp/shenzhi-paper-headers -o /tmp/shenzhi-paper.png \
  'https://你的深知域名/api/paper-images/CVPR_2026/2605.05077v2.png'
cat /tmp/shenzhi-paper-headers
file /tmp/shenzhi-paper.png
etag=$(sed -n 's/^[Ee][Tt][Aa][Gg]:[[:space:]]*//p' /tmp/shenzhi-paper-headers | tr -d '\r')
curl -i -H "If-None-Match: $etag" \
  'https://你的深知域名/api/paper-images/CVPR_2026/2605.05077v2.png'
curl -i 'https://你的深知域名/api/paper-images/CVPR_2026/missing.png'
curl --path-as-is -i \
  'https://你的深知域名/api/paper-images/%252e%252e/secret.png'
```

预期依次为 PNG 的 200、空 body 的 304、404、404。资源接口可独立验证，
功能开关仅控制搜索卡片是否请求图片。浏览器网络面板应只有深知同源图片请求。

历史验收与变更记录见 [PAPER-IMAGES-validation.md](../dev/records/knowledge/PAPER-IMAGES-validation.md)。
