# 深知 ShenZhi V1 工程架构说明

> 本文描述 ShenZhi V1 当前统一采用的工程架构，用于指导代码开发、架构迁移、接口联调和后续维护。
>
> 本文以当前 `dev` 分支真实结构为准。新增代码原则上应遵循本文；已有实现如与本文存在差异，应结合当前代码状态逐步收敛，不因普通业务修改进行无关的大范围重构。

---

## 一、总体架构

ShenZhi V1 当前采用：

- Next.js 前端应用
- FastAPI 核心业务后端
- 模块化 Feature 业务组织
- 前后端核心业务分离
- 外部服务与科研能力通过 Client / Adapter / Service 隔离
- 后端 Python 依赖统一使用 `uv` 管理

整体调用关系：

```text
Frontend / Next.js
        ↓
Page / Feature
        ↓
Feature Service（按需）
        ↓
apps/web/clients/<capability>
        ↓
Next.js BFF（按需转发）
        ↓
ShenZhi FastAPI / Backend API
        ↓
Backend Service
        ↓
Backend Integration
        ↓
Database / External Research Service
```

核心原则：

```text
页面负责路由、展示与组合
业务逻辑进入 Feature
服务调用通过 Client / Adapter 隔离
核心业务由 FastAPI 承载
科研能力统一经 ShenZhi FastAPI 与 Backend Integration 接入
```

架构允许根据业务复杂度简化调用层级，但必须保持职责清晰，不为了形式机械增加空 Service、Hook、Client 或目录。

---

## 二、当前项目结构

```text
shenzhi/
├── apps/
│   ├── web/                     # Next.js 前端应用
│   │   ├── app/                 # 路由与页面入口
│   │   ├── features/            # 业务功能模块
│   │   ├── clients/             # 后端 / 外部服务调用封装
│   │   ├── components/          # 公共组件
│   │   ├── hooks/               # 全局 Hook
│   │   ├── lib/                 # Next.js / Web 框架级能力
│   │   ├── db/                  # 当前 Web 侧数据库相关实现
│   │   └── config/              # Web 配置
│   │
│   └── backend/                 # FastAPI 核心业务后端
│       ├── app/
│       │   ├── api/             # API 路由与请求边界；_support/ 放 HTTP transport helper
│       │   ├── schemas/         # 输入输出 Schema
│       │   ├── models/          # 持久化模型
│       │   ├── services/        # 按 agent、agent_sessions、identity、knowledge、library、home_feed、
│       │   │                    # discovery_pool、recommendation、topics、user 等领域组织业务逻辑
│       │   ├── integrations/    # 外部服务与科研能力接入边界
│       │   │   ├── knowledge/   # Knowledge Base Research Capability
│       │   │   ├── llm/         # 统一 Model Registry / Resolver
│       │   │   ├── web_search/  # 外部搜索 Provider
│       │   │   └── paper_resource/ # 外部 PDF 资源 Provider
│       │   ├── core/            # 配置、身份、错误、数据库、幂等与 Worker Lease 等基础能力
│       │   ├── data/            # 随包数据快照（会议截稿、首页兜底、主题目录）
│       │   └── main.py          # FastAPI 应用入口
│       ├── migrations/          # Alembic 数据库迁移
│       ├── skills/              # Agent Skill 提示词与参考资料
│       ├── evaluation/          # 推荐离线评估数据
│       ├── tests/
│       ├── pyproject.toml
│       └── uv.lock
│
├── data/                        # 离线数据源（首页兜底种子、会议截稿等）
├── docs/                        # 开发与产品文档
├── tests/                       # 视觉截图脚本
├── tools/
├── scripts/                     # 数据发布与本地辅助脚本
└── README.md
```

当前后端依赖管理以：

```text
pyproject.toml
uv.lock
```

为准，不重新引入 `requirements.txt` 作为主依赖管理方式。

---

## 三、Next.js 与 FastAPI 职责边界

### 1. Next.js

主要负责：

- 页面展示
- 用户交互
- App Router 路由
- 前端状态管理
- 页面与 Feature 组合
- 调用 FastAPI 及其他服务
- 与 Next.js / Web 框架强相关的能力
- 必要的 BFF / Server Route

`apps/web/app/api/` 主要用于与 Next.js 或 Web 层强相关的接口，不作为系统核心业务 API 的统一实现位置。

当前认证继续保持现有 Better Auth 方案及边界，不在普通业务开发中另建一套并行认证实现。

### 2. FastAPI

主要负责：

- 核心业务逻辑
- 业务校验与权限边界
- 数据处理
- AI 能力编排
- 科研能力集成
- 核心业务 API
- 数据持久化相关业务
- 统一错误与服务状态处理

后端推荐保持：

```text
API Route
   ↓
Schema / Validation
   ↓
Service
   ↓
Database / External Service / Research Service
```

其中：

```text
api/
```

负责 HTTP 请求与响应边界，不应承载大量核心业务逻辑。

```text
schemas/
```

负责输入输出结构和校验。

```text
services/
```

负责实际业务逻辑和能力编排。

```text
core/
```

负责配置、身份、错误处理等基础能力。

后端 Python 业务逻辑中的当前时间统一以 UTC 为基准，优先通过
`app.core.time.utc_now()` 获取。数据库持久化事实时间继续由数据库自身的
timezone-aware 时间逻辑负责，不与 Python 业务时钟强制合并。

### 3. 运行形态

后端按**长驻进程**设计。FastAPI `lifespan` 负责启动时的运行状态恢复与后台调度器，Agent 运行归属保存在进程内存，Agent workspace 写本地磁盘。部署到 Serverless 等非长驻环境时，这些能力不保证可用。当前部署形态与约束见 [部署与运行环境](deployment.md)。

---

## 四、页面与 Feature

`apps/web/app/` 主要表达：

- URL
- 页面层级
- Next.js Router
- 页面入口
- 页面组合

页面应尽量保持轻量：

```text
page.tsx
   ↓
Feature Component
   ↓
Feature Service / Client
```

不应在大型 `page.tsx` 中同时维护：

- 大量 UI
- API 请求
- 复杂状态
- 数据处理
- 核心业务逻辑

复杂业务进入：

```text
apps/web/features/{module}/
```

当前主要 Feature 包括：

```text
home            # 发现页入口
search          # 首页论文 Feed 与搜索组件；deep-search/ 为旧静态搜索原型
agent-chat      # 深知 AI（Agent）新对话页与会话页
papers          # 论文详情（PDF 阅读器 + 论文 Agent 问答）
knowledge       # 知识库：论文库、我的文献、学者、主题、基金、图谱等子功能
submit          # 会议DDL
settings / login / reset-password
deep-research / auto-research / projects   # 前端原型页，由 feature-availability 拦截
```

Agent 相关页面路由维护在 `app/agents` 体系下：`/agents` 由 `features/agent-chat` 承载，是当前唯一的对话链路；Deep Research、Auto Research 前端页面目前仍为原型。

旧 Deep Search 静态搜索结果原型统一归入 `features/search/deep-search`，不再建立平行业务实现。

Feature 内部可按实际需要组织：

```text
features/{module}/
├── components/
├── hooks/
├── services/
├── types.ts
└── constants.ts
```

不存在相应职责时，不要求机械创建完整目录。

---

## 五、Service 与 Client

推荐调用关系：

```text
Component
   ↓
Feature Service
   ↓
Client
   ↓
Backend API / External Service
```

### Feature Service

主要位于：

```text
features/{module}/services/
```

负责：

- 业务用例组织
- 参数整理
- 数据转换
- 返回结果适配
- 多个 Client 调用组合
- 当前 Feature 内部业务逻辑

如果只是一次简单服务调用，没有额外业务组织逻辑，可以直接：

```text
Component
   ↓
Client
   ↓
API
```

不需要机械增加只负责转发的 Service。

### Client

统一维护在：

```text
apps/web/clients/
```

其中：

```text
apps/web/clients/backend/
```

负责 ShenZhi Backend 的通用请求基础设施：

- HTTP / SSE 请求
- Header 与身份转发边界
- Next.js BFF 转发
- 通用 Backend Error
- 请求路径、协议等基础设施

依赖方向保持为：

```text
Feature Service
   ↓
clients/backend/{module}
   ↓
clients/backend
   ↓
Backend API
```

`clients/backend` 根目录是基础层，不得反向依赖 `profile`、`settings`
等具体模块。模块 Client 只负责请求、协议封装和错误转换；模型目录合并、降级策略、
多个接口组合等业务编排进入 `features/{module}/services/`。

`clients` 可以依赖 `lib` 中确属日志、Request ID、认证等框架或基础设施的能力；
`lib` 不得反向依赖 `clients`。业务规则不得为了复用而继续堆入 `lib`，应优先留在
对应 Feature 中，避免逐步形成 `lib ↔ clients` 双向依赖。

当前后端调用应优先收敛至：

```text
clients/backend/
```

等明确边界，不在 `lib/api`、`services/backend` 或不同业务组件中重复建立功能相同的请求实现。

而：

```text
apps/web/clients/knowledge/
apps/web/clients/deep-research/
apps/web/clients/auto-research/
```

这类 `apps/web/clients/<capability>/` 属于前端领域 Client（当前已存在 `clients/knowledge`、`clients/profile`、`clients/settings`），负责面向当前业务能力提供稳定接口，使用 ShenZhi 自身的 Backend Contract，并可复用 `clients/backend` 的 transport。它们不感知科研组原始 API，不保存科研服务地址，也不直接处理科研组原始 Schema。`clients/deep-research`、`clients/auto-research` 表示后续能力采用这一边界时的命名示例，不代表对应 Client 已经实现。

因此，`clients/knowledge` 表示前端的 Knowledge 领域调用边界，不表示浏览器直接连接知识底座科研组。

---

## 六、科研能力接入边界

Knowledge Base、Deep Research、Auto Research 及后续科研能力原则上统一经 ShenZhi FastAPI 接入；科研组服务不直接绑定页面、Feature 或前端领域 Client。

统一产品调用链为：

```text
Page / Component
        ↓
Feature
        ↓
apps/web/clients/<capability>
        ↓
Next.js BFF（按需转发）
        ↓
ShenZhi FastAPI
        ↓
Backend API
        ↓
Backend Service
        ↓
backend integrations/<capability>
        ↓
科研组 API
```

前端领域 Client 只依赖 ShenZhi Backend Contract。科研组 API 的原始协议、字段、服务地址和异常统一隔离在 `apps/backend/app/integrations/<capability>/`，External Research Service 不作为前端的直接调用目标。

### Backend Service 与 Integration

```text
apps/backend/app/services/
```

负责 ShenZhi 自身的产品业务逻辑，包括：

- 产品级能力编排与参数组织
- Query / Intent 处理
- 多个能力的组合
- 缓存、降级等产品策略
- 返回 ShenZhi Domain Schema

```text
apps/backend/app/integrations/<capability>/
```

负责连接上游科研能力，包括：

- 上游服务 URL、HTTP method/path、Header、Timeout
- Retry / transport 等按需采用的通信策略
- 上游输入输出 Schema
- 上游 Schema 与 ShenZhi Domain Schema 之间的 Adapter
- timeout、connection、rate limit、invalid response、upstream unavailable 等上游异常的统一转换与隔离

可以概括为：

```text
services：深知怎么使用能力
integrations：深知怎么连接能力
```

ShenZhi 的产品业务逻辑不应大量进入 integrations。例如，自然语言问题如何组织为产品级检索参数属于 Service / 业务层问题；科研组接口字段如何映射为 ShenZhi Schema 属于 Integration Adapter 问题。

一个 `integrations/<capability>/` 按实际职责通常可以包含：

```text
client.py
schemas.py
adapter.py
exceptions.py
```

- `client.py`：调用科研组 API，封装 base URL、HTTP method/path、Header、Timeout，以及按需采用的 Retry / transport 等连接细节。
- `schemas.py`：描述科研组上游接口自身的输入输出格式，不作为 ShenZhi Domain Contract。
- `adapter.py`：在上游 Schema 与 ShenZhi 自身业务 Schema 之间完成转换。
- `exceptions.py`：统一转换并隔离上游异常。

只有职责真实存在时才创建相应文件，不要求所有 Integration 机械具备完整结构。

### Knowledge Base 当前实现

Knowledge Base 是 `integrations/<capability>/` 通用结构在当前仓库已经落地的第一个实例，其真实调用链为：

```text
Frontend Page / Feature
        ↓
apps/web/clients/knowledge
        ↓
ShenZhi BFF / FastAPI
        ↓
backend api
        ↓
backend services
        ↓
backend integrations/knowledge
        ↓
知识底座科研组 API
```

当前 `app/integrations/knowledge/` 已包含：

- `client.py` 只负责 base URL、HTTP method/path、query/body、timeout 与 transport。
- `schemas.py` 只描述科研组上游实际字段，不作为 ShenZhi Domain Contract。
- `adapter.py` 集中完成上游协议与 `app/schemas/knowledge.py` Domain Schema 之间的映射。
- `exceptions.py` 统一 timeout、connection、rate limit、not found、invalid response、contract violation 与 upstream unavailable 等上游异常。

Knowledge Base 当前接入论文检索、详情、图谱、会议浏览、学者、主题、基金与知识库总览等能力（接口清单见 [apps/backend/README.md](../../apps/backend/README.md)）；科研组内部业务由科研组维护，ShenZhi 只调用、隔离和适配，不在此边界内修改、补偿或修复科研组业务。

当前仓库尚未存在 `integrations/deep_research` 或 `integrations/auto_research`。目前可用的 Deep Research 是深知自身的 Agent Skill（`apps/backend/skills/deep-research/`），在 Agent Runtime 内运行，不属于科研组能力接入；说明见 [docs/agent](../agent/README.md)。Deep Research、Auto Research 等能力后续在真实服务化、接口稳定并开始产品接入时，优先遵循 `backend integrations/<capability>` 边界；在职责尚未出现前，不创建空目录，也不描述为已存在稳定 Integration。

接入科研能力前，需要明确：

- 输入 Schema
- 输出 Schema
- 状态定义
- Timeout
- Retry
- 错误码
- 错误处理
- 服务可用性
- Mock 方式
- 降级方案

不要默认科研组已经提供稳定生产 API。

当前存在的边界例外（登记在 [已知偏移与待收敛项](known-gaps.md)）：

- `apps/web/app/api/paper-images/` 由 Web 服务端直接代理知识底座图片（`KNOWLEDGE_BASE_API_URL`），说明见 [论文图片](../knowledge/PAPER-IMAGES.md)。
- `services/agent/` 中部分外部调用尚未收敛到 `integrations/`：Agent 自有的流式 Provider、`chart_tools.py` 的 Exa 搜索、`read_paper.py` 的 arXiv / OpenReview / Unpaywall 全文获取及 `fetch_url.py`。

当科研接口或内部实现仍在演进时，产品侧优先通过：

```text
Client
Adapter
Service
```

吸收变化，避免接口变化扩散到页面和大量业务组件。

产品系统负责：

```text
如何把科研能力可靠地转换为产品能力
```

科研模块内部算法实现原则上仍由对应科研组维护。

---

## 七、公共代码与子功能组织

业务模块内部类型优先放在对应 Feature 内。

例如：

```text
features/{module}/types.ts
```

只有真正被多个业务模块共同使用的类型，再提升到全局位置。

公共组件：

```text
components/ui/       # 基础 UI
components/common/   # 跨 Feature 通用组件
```

搜索导航恢复、搜索草稿与 AppShell 响应式布局属于 Web 框架级能力，分别位于
`lib/navigation/` 与 `components/common/layout/`，维护说明见
[响应式布局与搜索连续性](responsive-core.md)。

依赖方向上，`components/common`、`stores`、`providers` 等全局层原则上不依赖
`features/*`：被多个模块共用的组件、Hook 与工具应放入 `components/common` 或 `lib`。
确实难以避免时可以保留，但不应继续扩大；现有的反向依赖登记在
[已知偏移与待收敛项](known-gaps.md)，在相关模块修改时顺带收敛。

不要因为两个组件代码相似就立即提升为全局公共组件；只有职责稳定且确有跨模块复用时再抽取。

一个主要业务可以包含多个子功能。

例如：

```text
knowledge
├── papers
├── patents
├── scholars
└── institutions
```

业务层级可以分别体现在：

```text
apps/web/app/
apps/web/features/
docs/
```

三者应保持一致的业务语义，但不要求严格镜像。

例如：

```text
app/knowledge/papers/[id]/page.tsx
```

并不要求存在：

```text
features/knowledge/papers/[id]/
```

业务实现仍可统一维护在：

```text
features/knowledge/papers/
```

---

## 八、文档、开发与架构变更

开发文档统一维护在：

```text
docs/
```

主要业务模块可建立独立目录，例如：

```text
docs/engineering/
docs/auth/
docs/agent/
docs/knowledge/
docs/deep-research/
docs/auto-research/
```

文档可以记录：

- 架构说明
- API 契约
- 数据结构
- 联调说明
- 功能设计
- 关键技术决策
- 维护说明
- 重要问题

`docs/` 不要求与代码目录严格镜像。维护文档与一次性记录分开存放，交付报告、验收记录等一次性记录放入 `docs/dev/records/<模块>/`，详见 [docs/README.md](../README.md)。

分支、Commit 与合并流程以 [git-conventions.md](git-conventions.md) 为准。

普通业务任务不得擅自进行与当前任务无关的大范围架构调整。

若确需修改：

- 核心目录结构
- 前后端职责边界
- 重要接口协议
- 核心技术栈
- 公共调用链路

应先明确影响范围，并同步更新相关文档。

开发过程中重点避免：

- 将大量业务逻辑集中在 `page.tsx`
- 页面组件直接连接数据库
- 页面组件直接绑定科研服务或第三方服务
- 在多个组件中散布重复 API 请求逻辑
- 绕过现有 Client / Service 边界建立平行调用方式
- 为满足形式创建没有实际职责的空 Service、Hook、Client 或目录
- 不同业务模块重复实现职责相同的公共能力
- 在普通业务任务中顺手重构无关模块
- 重要接口或架构已经变化但文档长期不更新

总体目标是维持：

```text
科研能力
   ↓
稳定服务
   ↓
统一接口
   ↓
产品功能
   ↓
真实用户使用
```

并持续保证：

- 清晰的模块边界
- 稳定的接口边界
- 良好的可维护性
- 良好的可扩展性
- 对科研能力变化的适应能力
- 较低的跨组协作和后续维护成本

## LLM 接入基础设施

Agent 与后续 AI Feature 统一通过 `integrations/llm` 的 Model Registry / Resolver
解析 Model ID、Provider、上游型号和能力；流式协议处理由 Agent 的
`services/agent/provider.py` 负责。模型品牌只用于展示，实际路由由
`provider_id` 决定；Provider 凭据仅在服务端加载。接入规则、兼容策略及声明示例见
[LLM API Foundation](llm-api-foundation.md)。
