# 论文图片验收记录

> 从 [PAPER-IMAGES.md](../../../knowledge/PAPER-IMAGES.md) 拆出的历史记录，只反映记录当时的状态；当前约定以原文档为准。

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
