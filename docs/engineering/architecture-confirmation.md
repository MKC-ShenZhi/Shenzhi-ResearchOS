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
Client / Adapter
        ↓
FastAPI / External Research Service
        ↓
Database / AI / Knowledge Service
```

核心原则：

```text
页面负责路由、展示与组合
业务逻辑进入 Feature
服务调用通过 Client / Adapter 隔离
核心业务由 FastAPI 承载
科研能力通过稳定接口接入
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
│       │   ├── api/             # API 路由与请求边界
│       │   ├── schemas/         # 输入输出 Schema
│       │   ├── services/        # 核心业务逻辑
│       │   ├── integrations/    # 外部服务与科研能力接入边界
│       │   │   └── knowledge/   # Knowledge Base Research Capability
│       │   ├── core/            # 配置、身份、错误等基础能力
│       │   └── main.py          # FastAPI 应用入口
│       ├── tests/
│       ├── pyproject.toml
│       └── uv.lock
│
├── docs/                        # 开发与产品文档
├── tests/
├── tools/
├── scripts/
├── infra/
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
chat
deep-research
auto-research
search
knowledge
papers
scholars
projects
login
settings
submit
...
```

当前 Agent 相关页面路由继续维护在 `app/agents` 体系下，Chat、Deep Research、Auto Research 等具体业务分别由对应 Feature 承载。

旧 Deep Search 静态搜索结果原型统一归入：

```text
features/search
```

不再建立平行业务实现。

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

主要负责：

- HTTP / SSE 请求
- 服务地址管理
- Header / Token
- 请求协议封装
- 通用错误标准化
- 与 FastAPI、BFF 或外部服务通信

当前后端调用应优先收敛至：

```text
clients/backend/
```

等明确边界，不在 `lib/api`、`services/backend` 或不同业务组件中重复建立功能相同的请求实现。

---

## 六、科研能力接入边界

科研能力原则上不直接绑定页面或业务组件。

推荐：

```text
React Component
      ↓
Feature Service
      ↓
Client / Adapter
      ↓
FastAPI / Research API
      ↓
Knowledge / Deep Research / Auto Research / AI Service
```

Knowledge Base 在 FastAPI 内部采用明确的后端调用链：

```text
FastAPI API
      ↓
backend services
      ↓
backend integrations/knowledge
      ↓
上游知识底座科研组 API
```

其中 `app/integrations/knowledge/` 是外部 Research Capability 的唯一接入边界：

- `client.py` 只负责 base URL、HTTP method/path、query/body、timeout 与 transport。
- `schemas.py` 只描述科研组上游实际字段，不作为 ShenZhi Domain Contract。
- `adapter.py` 只将上游 Schema 映射为 `app/schemas/knowledge.py` 的 Domain Schema。
- `exceptions.py` 统一 timeout、connection、rate limit、not found、invalid response、contract violation 与 upstream unavailable 等上游异常。

Knowledge Base 当前只承诺 Search、Paper Detail、Paper Graph；科研组内部业务由科研组维护，ShenZhi 只调用、隔离和适配，不在此边界内修改、补偿或修复科研组业务。

接入科研能力前，需要明确：

- 输入 Schema
- 输出 Schema
- 状态定义
- 错误处理
- 超时策略
- 服务可用性
- Mock 方式
- 降级方案

不要默认科研组已经提供稳定生产 API。

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
features/chat/types.ts
features/search/types.ts
```

只有真正被多个业务模块共同使用的类型，再提升到全局位置。

公共组件：

```text
components/ui/       # 基础 UI
components/common/   # 跨 Feature 通用组件
```

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
docs/chat/
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

`docs/` 不要求与代码目录严格镜像。

Git 基本流程：

```text
dev
 ↓
feat/*
 ↓
dev
 ↓
main
```

其中：

- `main`：稳定 / 发布分支
- `dev`：日常集成开发分支
- `feat/*`：从 `dev` 创建的新功能开发分支

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
