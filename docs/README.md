# ShenZhi 文档目录说明

本目录维护 ShenZhi 的工程规范、模块说明、产品与设计资料，以及开发过程中的历史记录。

新增或维护文档时，优先放入对应分类目录，并先确认是否已有文档可以继续维护，避免重复建立相同职责的说明。

## 目录说明

```text
docs/
├── engineering/     # 全局工程架构、部署、开发规范与公共技术决策
├── agent/           # 深知 AI（Agent）对话、会话持久化与 Skill
├── auth/            # 登录、注册、认证与账号体系
├── chat/            # Chat 基础设施（匿名身份、会话存储等仍被 Agent 复用的部分）
├── knowledge/       # 知识库：论文库、学者、主题、互动与统计、论文图片
├── conferences/     # 会议DDL（会议截稿）
├── settings/        # 个人设置与账号管理
├── deep-research/   # Deep Research 原型页面
├── logging/         # Logging Core 与异常观测
├── design/          # 品牌、视觉主题与设计资产
├── prd/             # 产品需求文档
├── prototypes/      # 早期 HTML 原型（frontend_v1 静态 Demo）
└── dev/             # 阶段性开发资料与一次性记录
    └── records/<模块>/
```

入口文档：

* 工程架构：[engineering/architecture-confirmation.md](engineering/architecture-confirmation.md)
* 部署与运行环境：[engineering/deployment.md](engineering/deployment.md)
* 已知偏移与待收敛项：[engineering/known-gaps.md](engineering/known-gaps.md)
* Git 协作：[engineering/git-conventions.md](engineering/git-conventions.md)
* 模块全景：[engineering/V1-modules.md](engineering/V1-modules.md)

## 维护文档与一次性记录

模块目录（`engineering/`、`agent/`、`knowledge/` 等）只放**维护文档**：描述当前有效的实现、接口、配置与约定，代码变化时同步更新。

交付报告、验收记录、修复日志、工作日志、分工与进度等**一次性记录**统一放入 `dev/records/<模块>/`，例如：

```text
dev/records/engineering/idempotency-delivery.md
dev/records/knowledge/PAPER-LIBRARY-V2-validation.md
```

一次性记录只反映记录当时的状态，不作为当前实现的依据，也不随代码持续更新。维护文档中如有对应记录，在文末链接即可。

`dev/` 根目录下的 `开发日志.md`、`项目介绍.md` 等为项目早期的阶段性资料，同样只作历史参考。

## 业务模块文档

某个业务模块形成较稳定的开发与维护内容时，可建立独立目录，按需维护：

```text
README.md
API.md
ARCHITECTURE.md
CONFIGURATION.md
```

不要求所有模块采用完全一致的结构；文档较少时直接用清晰的文件名维护。

## 设计资产

`design/` 下的 SVG、HTML 与 PNG 为品牌与卡片设计的过程稿和效果图，不被代码引用；品牌 Logo 原图（`design/brand/日间logo.png`、`夜间logo.png`）由 `tools/brand/process_logo.py` 处理后生成运行时资产。`prototypes/demo.html` 为早期静态 Demo，仅作参考。

## 文档维护原则

1. `docs/` 不要求与代码目录严格镜像，但应保持一致的业务语义。
2. 项目级工程规范统一放入 `engineering/`；具体业务实现说明放入对应业务目录。
3. 维护文档与一次性记录分开存放，一次性记录放入 `dev/records/<模块>/`。
4. 真实服务器 IP、上游服务地址与密钥不写入文档，统一使用占位符。
5. 不为追求目录完整性创建无实际内容的空目录。
6. 核心架构、接口或业务边界发生实质变化时，同步更新相关文档。
