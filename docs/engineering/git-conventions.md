# Git 协作与提交规范

本文用于约定 ShenZhi 项目的基础 Git 协作方式，包括分支使用、Commit 信息和合并流程。

目标是保持提交记录清晰、便于审查、便于回溯，并降低多人协作时的维护成本。

---

## 一、分支约定

项目主要使用以下分支：

```text
main
dev
<type>/*    # 工作分支：feat/*、fix/*、refactor/*、docs/*、chore/*、test/*
```

### `main`

稳定 / 发布分支。

原则上不直接在 `main` 上进行日常功能开发。

### `dev`

日常集成开发分支。

各功能完成开发和验收后，统一合并回 `dev`。

### `<type>/*`

工作分支，前缀与 Commit 类型一致（见第三节）：新功能用 `feat/*`，问题修复用 `fix/*`，文档用 `docs/*`，依此类推。

工作分支原则上从最新的 `dev` 创建，例如：

```text
feat/knowledge-search
fix/email-login
docs/docs-maintenance
```

基本流程：

```text
dev
 ↓
<type>/*
 ↓
dev
 ↓
main
```

---

## 二、Commit 信息格式

Commit 信息统一采用：

```text
<type>: <中文描述>
```

其中：

* `type` 使用英文
* 具体修改内容使用中文描述
* 描述应简洁、明确地说明本次提交做了什么

例如：

```text
feat: 新增论文收藏功能
fix: 修复验证码登录异常
refactor: 调整 Chat 服务调用边界
docs: 完善 docs 目录结构与文档规范
chore: 后端切换至 uv 依赖管理
test: 补充 Chat 接口测试
```

团队日常协作以中文为主，因此不要求 Commit 描述全部使用英文。

---

## 三、常用 Commit 类型

推荐使用：

```text
feat:
fix:
refactor:
docs:
chore:
test:
```

含义如下：

```text
feat      新增功能
fix       修复问题
refactor  重构代码，但不改变主要功能
docs      文档修改
chore     工程配置、依赖、构建等维护性修改
test      测试相关修改
```

其他类型如确有需要可以使用，但不建议随意增加大量自定义类型。

---

## 四、Commit 粒度

一个 Commit 应尽量对应一个明确目的。

推荐：

```text
docs: 完善工程架构说明
```

不推荐：

```text
docs: 改文档顺便修登录和调整页面
```

应尽量避免：

* 将互不相关的修改放进同一个 Commit
* 一个 Commit 同时包含大范围重构和普通功能修改
* 使用无法判断修改内容的描述，例如：

```text
update
fix
修改代码
调整一下
```

Commit 记录应能够帮助后续开发者快速理解：

```text
这次改了什么
为什么会有这个提交
问题出现时应该回看哪个提交
```

---

## 五、分支命名

分支名称建议使用英文，并保持简短明确。

推荐：

```text
feat/auth
feat/chat
feat/knowledge-search
fix/email-login
refactor/chat-service
```

不建议使用：

```text
feat/test123
new
my-branch
final-final
```

分支名主要用于 Git 和工程协作，因此保持英文更利于工具、脚本和长期维护。

---

## 六、合并原则

工作分支完成后，通过 PR 合并：

```text
<type>/* → dev
```

准备发布时：

```text
dev → main
```

合并前应确认：

* 当前功能可以正常运行
* 相关测试已通过
* 不包含明显无关修改
* 未误提交环境变量、密钥或本地文件
* 重要接口或架构变化已同步文档

不要为了快速合并而忽略明显的结构问题或未完成状态。

---

## 七、与架构规范的关系

Git 协作规范负责：

```text
如何开发
如何提交
如何合并
```

总体工程架构负责：

```text
代码放在哪里
模块职责是什么
前后端如何分工
服务如何调用
```

进行较大修改前，应同时参考：

```text
docs/engineering/architecture-confirmation.md
docs/engineering/git-conventions.md
```

如果某次修改涉及核心架构、接口边界或目录结构变化，应同步更新对应工程文档。
