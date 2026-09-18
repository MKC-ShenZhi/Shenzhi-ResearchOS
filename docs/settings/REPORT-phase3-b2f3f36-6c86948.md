# 个人设置 · 阶段三 · 进度与验收报告

> **统计范围：** `b2f3f36`（基线）至 `6c86948`（阶段三-评测修订）
> **分支：** `feat/personal-settings-foundation`
> **说明：** 本文只陈述该提交区间内已经进入 Git 历史的内容。

---

## 一、进度总览

| 工作项 | 当前状态 | 已交付结果 | 验收边界 / 待办 |
|--------|----------|------------|-----------------|
| 账户设置页 | 已完成 | 账户摘要、昵称、邮箱变更、密码、会话、注销入口集中在「个人」页签 | 真实浏览器会话列表目前返回 403，会话管理不能判定通过 |
| 昵称与身份隔离 | 已完成 | 调用 Better Auth 更新昵称；用户切换时以身份 key 重建设置组件，异步回调校验当前用户 | 仍需真实双账号浏览器验收草稿与提示清理 |
| 邮箱变更 | 部分完成 | 启用 Better Auth changeEmail，当前邮箱确认后再验证新邮箱；变更前要求重新登录并校验身份未切换 | 尚未完成真实邮件投递、唯一性冲突与 Session 策略端到端验收 |
| 密码管理 | 部分完成 | 有密码账户走 Better Auth changePassword；无真实密码账户走登录态绑定的邮箱 OTP 首次设密 | Email OTP / GitHub OAuth 真实账户矩阵未完成 |
| 登录会话 | 未完成验收 | 已接入 listSessions / revokeOtherSessions UI 与错误态 | 浏览器实测 GET `/api/auth/list-sessions` 返回 403，需修复后再进行双浏览器验收 |
| 注销与业务数据删除 | 核心代码完成 | 服务端先清理 Profile、Settings、Chat 会话/消息及进程缓存，再删除 Better Auth 账号；清理幂等 | 尚未用可丢弃账号完成真实认证库删除、部分失败恢复和多进程取消验收 |
| 架构边界 | 已完成代码约束 | Feature Service → Client/Route → Backend；lib 不反向依赖 clients | 自定义首次设密路由属于受控例外，需持续保持文档和集成测试覆盖 |
| 自动化与数据库验证 | 已完成当前范围 | Web 201/201、TypeScript、后端 160 项、Ruff、真实 CHAT_DATABASE_URL 清理测试均通过 | 自动化不替代真实邮件、OAuth、双浏览器和生产验收 |

### 提交链路

```
b2f3f36  阶段三开始前基线
  └─ 9f3b86c  设置页账户区与基础账户管理
      └─ ab2c1eb  对齐 foundation 分支 Client 导入路径
          └─ 3314746  加固首次设置密码 OTP
              └─ 4901658  邮箱变更、重新认证与身份隔离
                  └─ 72be73f  跨库注销业务数据清理编排
                      └─ 6c86948  评测修订：运行时清理、真实数据库测试、身份复核
```

区间共修改 **28** 个版本化文件，累计 **+1266 / -90** 行。Web 负责 Better Auth UI、同源 Route 与前端业务编排；Backend 只负责可信身份下的业务数据清理，不承担第二套认证、密码或 Session 系统。

---

## 二、提交区间内的完整文件树与职责

下列树列出 `b2f3f36..6c86948` 的所有修改文件；**[新增]** 表示该区间新建，**[修改]** 表示在原有文件上改动。

```
shenzhi/
├─ apps/
│  ├─ backend/
│  │  ├─ app/
│  │  │  ├─ api/
│  │  │  │  └─ account_deletion.py                         [新增]
│  │  │  │     └─ 内部业务数据清理入口；只接受可信 BFF 身份和注销标记。
│  │  │  ├─ services/
│  │  │  │  ├─ account_deletion.py                         [新增]
│  │  │  │  │  └─ 幂等删除 user_profiles、user_settings、user:* Chat 数据。
│  │  │  │  ├─ sessions.py                                 [修改]
│  │  │  │  │  └─ 内存会话仓库新增按 owner 取消任务并清理附件缓存能力。
│  │  │  │  └─ postgres_sessions.py                        [修改]
│  │  │  │     └─ PostgreSQL 会话仓库新增当前进程消息任务/上传缓存清理能力。
│  │  │  └─ main.py                                        [修改]
│  │  │     └─ 注册账户注销业务数据清理路由。
│  │  └─ tests/
│  │     ├─ test_account_deletion_api.py                   [新增]
│  │     │  └─ 验证内部入口拒绝未登录、拒绝缺少内部标记、允许可信请求。
│  │     ├─ test_account_deletion_persistence.py           [新增]
│  │     │  └─ 真实 CHAT_DATABASE_URL：目标数据删除、他人隔离、消息级联、幂等。
│  │     └─ test_account_deletion_runtime.py               [新增]
│  │        └─ 内存模式：注销取消目标任务、清理上传、保留他人数据。
│  └─ web/
│     ├─ app/api/auth/
│     │  ├─ account-deletion/route.ts                       [新增]
│     │  │  └─ Web 服务端注销编排：读取 Better Auth Session，先调 Backend 清理，再删认证账号。
│     │  └─ password/
│     │     ├─ send-otp/route.ts                            [修改]
│     │     │  └─ 无真实密码用户的首次设密 OTP：检查账户状态、限频、失败回滚验证码。
│     │     └─ set/route.ts                                 [修改]
│     │        └─ 校验 OTP 前确认尚无真实密码，防止已有密码账户绕过改密流程。
│     ├─ components/auth/
│     │  └─ auth-errors.ts                                  [修改]
│     │     └─ 增加稳定认证错误码的人类可读映射。
│     ├─ features/settings/
│     │  ├─ components/
│     │  │  ├─ account-section.tsx                          [修改]
│     │  │  │  └─ 账户区总编排：昵称、邮箱、密码、会话、注销、重认证和身份切换保护。
│     │  │  ├─ account-sessions.tsx                         [新增]
│     │  │  │  └─ 会话列表与「退出其他会话」独立组件，使用 Better Auth Client。
│     │  │  └─ settings-tabs.tsx                            [修改]
│     │  │     └─ 以认证用户 ID 作为 key，账号变化时重置 Settings/Account 子树。
│     │  ├─ services/
│     │  │  ├─ account-deletion.ts                          [新增]
│     │  │  │  └─ Feature Service 封装同源注销请求；浏览器不传 user_id。
│     │  │  └─ account-password.ts                          [新增]
│     │  │     └─ Feature Service 封装首次设密 OTP 请求和安全错误读取。
│     │  └─ i18n.ts                                        [修改]
│     │     └─ 增加账户模块中英文文案、确认语、错误态与重认证提示。
│     ├─ lib/auth/
│     │  ├─ server.ts                                       [修改]
│     │  │  └─ 启用 Better Auth 邮箱变更：旧邮箱确认后发起新邮箱验证。
│     │  ├─ email/
│     │  │  ├─ callbacks.ts                                 [修改]
│     │  │  ├─ messages.ts                                  [修改]
│     │  │  └─ requirements.ts                              [修改]
│     │  │     └─ 补齐邮箱变更邮件类型、文案及邮件服务可用性要求。
│     │  └─ password/otp.ts                                 [修改]
│     │     └─ OTP 值增加签发时间；提供服务端重发冷却与兼容解析。
│     └─ tests/
│        ├─ auth/
│        │  ├─ change-email.integration.test.mjs            [新增]
│        │  ├─ email-configuration.test.ts                  [修改]
│        │  └─ set-password-otp.test.ts                     [新增]
│        │     └─ 验证邮箱变更契约、邮件配置、OTP 限频与历史记录兼容。
│        └─ settings/
│           └─ settings-account.test.ts                     [新增]
│              └─ 验证账户组件边界、错误分支、身份切换和高风险重认证。
└─ docs/
   └─ settings/
      └─ README.md                                          [修改]
         └─ 记录账户模块职责、依赖方向、首次设密例外与跨库注销契约。
```

### 按提交说明的增量作用

| 提交 | 主要改动 | 产生的作用 |
|------|----------|------------|
| `9f3b86c` | 账户区重构、会话组件、首次设密 Service、账户文案和回归测试 | 将既有 Better Auth 能力在设置页形成可操作 UI，消除演示式硬编码文案。 |
| `ab2c1eb` | 对齐 SettingsLocale 的 Client 导入路径 | 保持 foundation 分支的模块边界和类型来源一致。 |
| `3314746` | OTP 冷却、已有密码拦截、邮件失败清理 | 防止重复发码、已有密码用户错误进入首次设密、发送失败留下可用验证码。 |
| `4901658` | Better Auth 邮箱变更配置、文案、身份切换保护 | 让邮箱变更采用「旧邮箱确认 → 新邮箱验证」契约，并避免旧账号异步响应覆盖新账号 UI。 |
| `72be73f` | Web/Backend 跨库注销编排、权限和幂等 API 测试 | 将业务数据清理与 Better Auth 账号删除按顺序编排，浏览器不能直接指定删除目标。 |
| `6c86948` | 运行时 Chat 清理、重认证后身份复核、真实 PostgreSQL 测试 | 补上注销时的内存任务/上传残留问题，降低重新登录到其他账号后误操作风险，并证明业务数据实际删除。 |

---

## 三、实现逻辑与数据流

### 1. 总体职责与依赖方向

阶段三没有新建用户表、密码表或认证 Session 表。认证主数据仍完全由 Better Auth 的 `user`、`account`、`session`、`verification` 表管理；业务资料仍在 FastAPI 的 `user_profiles`、`user_settings` 和 Chat 表中。

```
AccountSection（UI）
  ├─ authClient / AuthProvider
  │    └─ /api/auth/[...all] → Better Auth → DATABASE_URL
  ├─ features/settings/services/account-password.ts
  │    └─ /api/auth/password/*（首次设密的受控同源 Route）
  └─ features/settings/services/account-deletion.ts
       └─ /api/auth/account-deletion
            ├─ FastAPI /api/v1/account-deletion/cleanup → CHAT_DATABASE_URL
            └─ Better Auth deleteUser → DATABASE_URL
```

对应修订意见（1）的目标方向：**Feature Service → Client / Route → Backend / External Service**。`clients/backend/*` 仍只用于 FastAPI 通用 BFF；认证不放入 clients。`lib/auth/*` 只放 Better Auth 配置、邮件和安全基础设施，且不导入 clients。业务组合（首次设密、注销）放在 `features/settings/services/` 与同源 Route，而不是扩散到 lib 或 clients。

### 2. 账户摘要、昵称和账号切换

1. `AccountSection` 只使用 `useAuth()` 提供的当前 Better Auth Session 展示邮箱和昵称。
2. 保存昵称调用 `authClient.updateUser({ name })`；成功后调用 `refetchSession()`，使侧边栏、设置页等依赖同一 Session 的组件同步。
3. `settings-tabs.tsx` 以 `session.user.id` 作为 Settings 和 Account 组件的 React key；身份切换时旧组件卸载，表单草稿、成功提示和会话组件状态不会被下一位用户复用。
4. 每个异步操作都保留开始操作时的 `userId`，回调后检查 `activeUserIdRef`；旧账号的迟到响应不再覆盖新账号界面。

### 3. 邮箱变更与重新认证

1. Better Auth Server 的 `user.changeEmail` 被显式启用，并接入 `sendChangeEmailConfirmation`。
2. 用户提交新邮箱时，页面先开启统一登录弹窗进行重新认证，而不是直接向 `changeEmail` 发请求。
3. 认证回调再次调用 `authClient.getSession()`，确认返回的用户 ID 与操作开始时的用户 ID 完全一致；若登录成其他账号，显示「账户不一致，操作已取消」，不会变更新账号邮箱。
4. 校验通过后调用 `authClient.changeEmail`，由 Better Auth 执行旧邮箱确认和新邮箱验证。邮件服务未配置、敏感 Session 失效等错误都以稳定错误码映射为页面提示。

### 4. 密码与首次设密 OTP

**已有真实密码（hasPassword=true）：**

1. 页面要求输入当前密码、新密码和确认密码。
2. 前端检查 12–64 位、大小写字母和数字组合、两次输入一致且新旧密码不同。
3. 调用 Better Auth `changePassword`，并请求撤销其他会话；成功后刷新 Session。

**无真实密码（Email OTP / OAuth 占位 credential）：**

1. 页面显示 6 位邮箱 OTP 与「设置密码」而非「修改密码」。
2. send-otp Route 从当前登录 Session 得到 user ID 与邮箱；拒绝未登录、邮件服务未配置和已有真实密码账户。
3. OTP 以 hash、签发时间、尝试次数写入 Better Auth verification 存储；服务端执行重发冷却，邮件发送失败会删除刚创建的验证码。
4. set Route 先验证密码策略、账户仍无真实密码、OTP 是否过期/重放/超过次数；验证成功后写入 Better Auth credential，并清除 OAuth 随机占位密码标记。

`/api/auth/password/*` 是对 `[...all]` 的受控补充：它解决官方初始设密服务端能力不能直接满足「已登录用户 + 邮箱所有权 OTP + OAuth 占位 credential」组合规则的问题。Route 自身不把密码交给 FastAPI、不向浏览器暴露 Adapter，也不创建第二个 Auth 实例；这一例外已记录在 `docs/settings/README.md` 并由测试约束。

### 5. 会话列表与撤销其他会话

`AccountSessions` 使用 `authClient.listSessions()` 读取 Better Auth Session 表，并按 token 标记「当前 / 其他」；「退出其他会话」调用 `authClient.revokeOtherSessions()` 后重新加载列表。按钮只有在确实存在其他 token 时才启用，避免误撤销当前会话。

**但浏览器实测中 GET `/api/auth/list-sessions` 返回 403**，页面显示「无法加载登录会话」。因此上述代码路径已经存在，但尚不能被称为完成验收；需要先修复该 Better Auth 接口的权限/Origin/Session 契约问题。

### 6. 注销账户与跨库清理

用户确认注销并完成重新认证后，流程如下：

```
浏览器
  → POST /api/auth/account-deletion（不接受 user_id）
  → Web Route 从 Better Auth Session 获取可信 user.id
  → POST FastAPI /api/v1/account-deletion/cleanup
       ├─ 验证 BFF 身份为 user
       ├─ 验证仅 Web Route 才会加上的注销标记
       ├─ 收集 user:<id> Chat Session
       ├─ 取消当前进程正在生成的 Chat Task
       ├─ 删除当前用户 uploads / messages 缓存
       └─ 单一 CHAT_DATABASE_URL 事务删除 Profile、Settings、Chat Session
            （Chat Message 由外键级联删除）
  → FastAPI 成功后，Web Route 调用 Better Auth deleteUser
       └─ Better Auth 删除 user/account/session/verification 认证数据
```

**关键安全及恢复规则：**

- 浏览器不能传递要删除的 `user_id`；目标只能来自当前认证 Session。
- 后端清理入口既要收到可信 BFF 用户身份，也要收到仅注销编排 Route 添加的内部标记，不能作为普通业务接口调用。
- 业务清理先于认证删除。若业务清理失败，认证账号不删除；若业务清理成功但 Better Auth 最终删除失败，再次登录后重试会得到零行删除结果，仍可继续完成认证删除。
- `BusinessDataDeletionResult` 只返回类别数量，不回显消息正文、会话 ID 或个人内容。
- `6c86948` 补充进程内缓存清理，避免数据库行删除后，仍有生成任务、Message 或上传内容继续留在当前 Worker 内存中。
- 当前实现只保证当前进程取消任务。多 Worker / 分布式部署仍需要独立的跨进程取消机制，不能据此声明完全解决。

---

## 四、对规划文档及两份意见的完成情况

### 1. 阶段三规划文档验收映射

| 规划验收要求 | 状态 | 证据与说明 |
|--------------|------|------------|
| 三类账号有明确页面表现 | 部分完成 | 代码按 hasPassword 区分已有密码与首次设密，并处理 OAuth 占位 credential；但尚未在真实 Email OTP、GitHub OAuth 浏览器账户中逐项验收。 |
| 昵称持久化、刷新/重新登录一致，用户间不串数据 | 部分完成 | updateUser + refetchSession、组件 key 与异步用户 ID 守卫已实现；真实双账号浏览器操作仍未完成。 |
| 邮箱变更：唯一性、验证、重认证、Session 策略 | 部分完成 | Better Auth 旧邮箱确认/新邮箱验证、重新认证和身份复核已实现；真实邮件、唯一性冲突和变更后其他 Session 策略尚未验收。 |
| 设置/修改密码覆盖账户和错误分支，不泄露密码/OTP | 部分完成 | 密码规则、OTP 哈希、有效期、重放、次数、冷却、邮件失败清理均有代码/自动化覆盖；真实 OAuth/Email OTP 和邮件服务尚未验收。 |
| 两个独立浏览器看到真实会话，撤销其他端后失效 | 未完成 | 当前浏览器会话列表接口 403；尚未进行双浏览器上下文操作。 |
| 注销可丢弃账号端到端；认证库与业务库按政策一致，部分失败可重试可观测 | 部分完成 | 跨库清理、幂等、权限、真实 CHAT_DATABASE_URL 测试已完成；尚未真正删除可丢弃认证账号，未完成认证库级联、部分失败运维告警和多 Worker 验收。 |
| Web lint/typecheck/组件与 Auth 测试/构建；真实 DATABASE_URL；Backend API/权限/幂等/CHAT_DATABASE_URL | 部分完成 | Web 201/201、TypeScript、Backend 160 项、Ruff、真实 CHAT_DATABASE_URL 删除测试已通过；本次未把真实 DATABASE_URL、生产构建、全量 lint 作为已完成结论。 |
| 报告区分自动化与真实邮件/OAuth/浏览器/生产边界 | 已完成 | 本文及浏览器评测明确列出了未完成的真实环境边界。 |

### 2. 修订意见 1：依赖方向与边界

避免 lib ↔ clients 双向依赖，并把业务组合放到 `features/{module}/services/`。

**已完成：**

- `account-password.ts` 和 `account-deletion.ts` 位于 `features/settings/services/`，承接设置模块业务编排。
- `clients/backend/*` 继续只服务于 FastAPI 业务 Client；账户认证不被放入 Client 层。
- `lib/auth/*` 只负责 Better Auth Server、邮件、OTP、策略和基础设施，不反向 import clients。
- 自动化架构检查已验证：lib 不 import clients、clients 不依赖 Feature/UI、Backend 基础文件不依赖模块 Client。

**持续约束：**

- clients → lib 只允许日志、Request ID 等基础设施级依赖；新增依赖必须先判断职责。
- 不应把注销、OTP 等跨多个接口的流程组合迁移到 lib 或 clients。

### 3. 修订意见 2：Backend、[...all] 与实现位置

| 意见问题 | 当前回答与实现结果 | 状态 |
|----------|-------------------|------|
| 为什么会涉及 Backend 修改 | 只在注销涉及跨数据库业务数据时使用 Backend。认证仍由 Web Better Auth 管理；Backend 只清理 Profile、Settings、Chat 等业务数据。 | 已完成 |
| 既有 [...all]，为什么还有 password Route | `[...all]` 仍是 Better Auth 官方 HTTP Handler；`password/*` 是首次设密的受控补充，用于 OTP 邮箱所有权证明和 OAuth 占位 credential 清理，浏览器侧先经 Feature Service。 | 已完成，但需持续测试 |
| 逻辑究竟在哪里实现 | UI 在 account-section.tsx，前端组合在 features/settings/services，认证契约在 lib/auth/server.ts 与 Better Auth，跨库注销在 Web Route + Backend Service。 | 已完成 |
| clients 与 lib 双向调用风险 | 当前以模块边界测试和文件职责避免循环；未发现 lib ↔ clients 双向依赖。 | 已完成 |

---

## 五、验证记录与未完成事项

### 2026-09-18 验收回执（Codex）

| 项目 | 结论 | 证据摘要 |
|------|------|----------|
| `list-sessions` 403 | **已修复** | Better Auth 1.6.28 对 `list-sessions` 强制 fresh Session，默认 24 小时；旧 Session 返回 `403 / SESSION_NOT_FRESH`。UI 现触发既有重新登录弹窗、校验账号未切换并自动重试，未关闭 `freshAge` 安全保护。 |
| 双浏览器 Session | **通过** | 两个隔离 Chromium Context 登录同一账号，`GET /api/auth/list-sessions` 返回 200 且共 2 条；`POST /api/auth/revoke-other-sessions` 返回 200；当前 Context 仍有效、列表剩 1 条，另一 Context 的 `get-session` 返回 `null`。 |
| 完整账户注销 | **通过** | 可丢弃账号经 `/api/auth/account-deletion` 返回 200，浏览器未传 `user_id`。删除前 user/account/session/verification/profile/settings/chat session/chat message 均为 1，删除后均为 0。补充 Better Auth user-delete hook 清理无外键的 `set-password-otp:<userId>` verification。 |
| 邮箱/密码账户 | **通过** | 真实 Better Auth Route：`hasPassword=true`，改密返回 200，当前 Session 继续有效。 |
| Email OTP 账户形态 | **部分通过** | 真实 Better Auth OTP 登录及首设密 Route：`hasPassword false → true`，OTP 重放被 409 拒绝；未使用真实邮箱收件箱完成投递 E2E。 |
| GitHub OAuth 账户形态 | **部分通过** | 按 GitHub + OAuth placeholder credential 的真实数据库形态验证：`hasPassword false → true`，首设密返回 200；本机 `GITHUB_CLIENT_SECRET` 为空，真实 GitHub 回调未验收。 |
| changeEmail / 邮件异常矩阵 | **部分通过** | 内存适配器集成测试覆盖旧邮箱确认、新邮箱验证；自动化覆盖 OTP 过期、尝试次数、重放、60 秒重发冷却及发送失败清理。真实 changeEmail 双邮件点击因无受控收件箱未完成。 |
| 架构边界 | **通过** | `client-boundaries.test.ts` 与 `settings-account.test.ts` 通过；认证仍只走 Web Better Auth，业务编排仍在 Feature Service，FastAPI 仅清理业务数据。 |
| 多 Worker Chat 取消 | **记录，未解决** | 当前仅取消当前 Worker 的生成任务；分布式取消/可靠重试与告警仍是 P1，不在本次做过度实现。 |

本次命令结果：

- `cd apps/web && pnpm typecheck`：通过。
- `cd apps/web && pnpm test`：192/192 通过。
- 指定 Backend unittest：4/4 通过（首次运行因本机 PostgreSQL 未启动失败；按仓库文档启动 `127.0.0.1:5432` 后重跑通过）。
- 浏览器 Network 与截图摘要保存在本机 `_local-only/phase3-evidence-1789707331847-c03f257a/`，不提交仓库；测试账号及数据已清理。

**验收结论：** 会话管理和完整注销两个直接 P0 阻塞已关闭；三类账户的核心数据形态与 Route 行为已验证。阶段三仍不能标记为全部完成，剩余阻塞是受控真实邮箱的 changeEmail/投递链路和真实 GitHub OAuth Provider 回调。

### 已完成验证

| 类型 | 结果 | 覆盖内容 |
|------|------|----------|
| Web 自动化测试 | 201/201 通过 | 账户组件、认证、设置、架构边界等现有测试集。 |
| Web TypeScript | 通过 | 阶段三组件、Service、i18n 和认证 Client 类型。 |
| Backend 自动化测试 | 160 通过，21 条按环境条件跳过 | API、会话、Profile、Settings、Chat 等回归。 |
| Backend Ruff | 通过 | 阶段三 Backend Service 与新增测试文件。 |
| 真实 PostgreSQL | 通过 | 使用本地 CHAT_DATABASE_URL 执行迁移与账户业务数据删除、级联、隔离、幂等测试。 |
| 内置浏览器 | 已执行 | 设置页签、非法 tab 回退、语言刷新保持、已登录 Profile/Settings 加载；**同时发现会话列表 403**。 |

### 未完成 / 不应夸大为完成的事项

1. 修复 GET `/api/auth/list-sessions` 的 403，随后验证「退出其他会话」不影响当前会话。
2. 用两个独立浏览器上下文完成真实多 Session 验收。
3. 使用可丢弃测试账号完成真实账户注销，验证 Better Auth user/account/session/verification 级联结果。
4. 在可控邮件环境完成邮箱变更、首次设密、验证码过期/重放与邮件发送失败的端到端测试。
5. 完成 Email OTP、GitHub OAuth、邮箱/密码三类真实账号矩阵。
6. 明确并实施多 Worker 情况下生成任务的分布式取消或可靠后台重试/告警。
7. 在真实 DATABASE_URL 及生产前环境完成认证持久化、构建、全量 lint 与浏览器验收；当前自动化和 HTTP 成功响应不能替代这些结论。

---

## 六、结论

`b2f3f36..6c86948` 已将阶段三从「设置页中有账户入口」推进到「有明确认证边界、前端业务编排、首次设密安全规则、邮箱变更、跨库注销清理和数据库级验证」的状态。核心代码已提交并推送至 `feat/personal-settings-foundation`，最新提交为 `6c86948`。

**但阶段三尚不应标记为全部验收完成：** 会话列表 403 是当前最直接的功能阻塞；真实邮件、OAuth、双浏览器、认证库注销和生产环境验证仍需按上节逐项完成。

---

*机器可读摘要见 [HANDOFF-phase3-codex.json](./HANDOFF-phase3-codex.json)*
