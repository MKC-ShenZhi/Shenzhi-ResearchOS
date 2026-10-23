# 知识库搜索论文图片

搜索链路：知识底座 `image_id` → Knowledge Adapter → FastAPI `PaperSearchResult.imageId`
→ Web BFF / Knowledge Client → `ResultCard` → `getPaperThumbnailUrl(imageId)`
→ 同源 `/api/paper-images/[...path]` → 服务端 HTTP fetch 知识底座 Nginx `/images/`
→ 现有 `PaperThumbnail`。
`paper_id` / `id` 仍是不透明标识，不再用于推断图片名称。

搜索字段缺失或 `null`、开关关闭、非法路径均使用原有兜底；加载失败继续由
`PaperThumbnail.onError` 处理，放大预览不变。浏览历史转换为搜索卡片时明确使用
`imageId: null`，不从详情推断图片。首页 300 篇快照继续使用 `thumbnail_url` 和
`public/paper-thumbnails/`，不受此开关影响。

2026-10-23 对任务指定上游进行只读抽样：检索 `FlowDIS` 返回
`paper:2605.05077v2` 和 `/images/CVPR_2026/2605.05077v2.png`；
同一篇论文的 `GET /api/kg/paper?paperId=paper:2605.05077v2` 响应未提供 `image_id`。
因此本次不扩展详情图片契约；该抽样不代表所有上游记录均有图片。

## 配置与部署

本地默认保留 `NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED=false`，不发起知识库图片请求。
不需要本地图片文件、共享文件系统、服务器软链接或 Docker 图片目录挂载。

图片代理复用知识底座已有的 `KNOWLEDGE_BASE_API_URL`，不增加图片专用 Base URL。
Web 通过已有 `config/env.ts` 的 `optionalEnv()` 在服务端运行时读取配置：

```ini
# 同时注入 Web 和 FastAPI 服务端进程；不使用 NEXT_PUBLIC_ 前缀。
KNOWLEDGE_BASE_API_URL=http://158.247.231.197:18088/
# 同名复用后端超时配置，默认 30 秒；覆盖响应头及 body 读取。
KNOWLEDGE_BASE_TIMEOUT_SEC=30
# 本地默认关闭；生产启用需在构建环境设为 true 后重新构建。
NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED=false
```

Web 和 FastAPI 是独立进程，配置在 `apps/backend/.env` 中不会自动传给 Next.js。
本地 Web 可使用 `apps/web/.env.local`；standalone、Docker 或进程管理器应显式注入
运行时配置。两端的 `KNOWLEDGE_BASE_API_URL` 必须保持一致，末尾有无 `/` 均可。
该地址仅用于服务端请求，不进入浏览器 URL，也不返回上游 Location、Server 等响应头。
未配置或配置非法时图片代理返回空的 503，应用仍可正常启动。

生产启用步骤：

1. 部署 FastAPI 的可空 `imageId` 契约。
2. 给 Web 服务端注入与 FastAPI 相同的 `KNOWLEDGE_BASE_API_URL`，确认 Web 到知识底座的网络可达。
3. 构建时设置 `NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED=true`，重新构建、部署并重启 Web。
4. 检查搜索响应包含真实 `imageId`；缺失、null、代理错误继续显示兜底。

`NEXT_PUBLIC_` 开关在构建时内联，单独更改运行时环境变量不能启用已有 bundle。
地址或超时是服务端运行时配置，修改后重启进程即可，无需因此重新构建。

非 Docker，在 `apps/web` 中执行：

```bash
NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED=true pnpm build
```

Dockerfile 保留默认 false 的同名 build arg：

```bash
docker build -f infra/docker/web.Dockerfile \
  --build-arg NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED=true \
  -t shenzhi-web:paper-images .
```

运行容器时注入同名服务端配置（无需图片 volumes）：

```yaml
services:
  web:
    environment:
      KNOWLEDGE_BASE_API_URL: http://158.247.231.197:18088/
      KNOWLEDGE_BASE_TIMEOUT_SEC: "30"
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

先在 Web 所在机器或容器确认上游网络：

```bash
curl -I 'http://158.247.231.197:18088/images/CVPR_2026/2605.05077v2.png'
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

## 相比文件系统方案的调整

| 文件 | 本轮变化 |
| --- | --- |
| `apps/web/app/api/paper-images/[...path]/route.ts` | 文件读取改为固定来源的 HTTP 代理；增加超时、重定向/MIME 校验和上游缓存协商。 |
| `apps/web/config/knowledge.ts` | 沿用已有环境变量读取器，读取同名知识底座地址和超时。 |
| `apps/web/lib/paper-images.server.ts` | 删除上一轮的文件系统目录定位助手。 |
| `apps/web/tests/knowledge/paper-images.test.ts` | 文件系统模拟改为 fetch 模拟，覆盖路径、来源、缓存、MIME、重定向及超时。 |
| `apps/web/.env.example` | 移除 PAPER_IMAGES_DIR，说明同名服务端配置和默认关闭开关。 |
| `.gitignore` | 撤回上一轮新增的本地图片目录忽略规则。 |
| `docs/knowledge/PAPER-IMAGES.md` | 替换软链接、挂载、文件权限及旧验收说明。 |

此前的真实字段贯通、类型定义、URL 解析、UI、开关、兜底、预览和首页相关代码不在本轮重构。
Dockerfile 的默认 false 构建参数继续保留；不新增 Docker 挂载，也不改真实服务器配置。

## 自动化验证

在 `apps/web` 执行仓库已有脚本：

```bash
pnpm test
pnpm typecheck
pnpm lint
NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED=false pnpm build
```

代理测试用 fetch 替身验证请求来源、头部、重定向策略、超时、图片字节/MIME 和缓存，
不依赖本地文件或真实上游。上一轮的字段、Client、功能开关、组件错误回调和首页静态资源测试继续保留。

本轮验证记录（2026-10-23）：

- `pnpm --config.verify-deps-before-run=false test`：343/343 通过；最终超时边界调整后，7 项代理测试再次通过。
- 同样的 pnpm 选项执行 `typecheck`、`lint`：类型检查通过；lint 0 错误，仅保留两处未修改文件的既有 Hook 警告。
- `NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED=false pnpm --config.verify-deps-before-run=false build`：生产构建通过。
- 实际上游 HEAD 返回 PNG 200、`Cache-Control: max-age=604800` 和 ETag。
- 构建后的 standalone 在本机通过同名环境变量连接真实 Nginx，实际 HTTP 获得 289,798 字节 PNG，
  缓存头/ETag 保留，条件请求 304；缺失图片、双重编码和编码斜杠均为 404，客户端 URL 查询参数不能改变来源。
  临时进程已停止，未部署或修改真实服务器。
- `git diff --check` 通过。字段贯通、UI、首页静态图片和预览代码没有在本轮继续改动。

尚未在正式部署环境或实际浏览器验收；仍需检查部署进程的环境变量、出站网络以及图片优化/预览实际表现。
