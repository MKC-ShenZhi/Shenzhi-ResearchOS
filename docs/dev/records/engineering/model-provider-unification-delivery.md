# Model Provider 统一声明与 OpenLux 交付记录

更新日期：2026-11-24。当前分支 `feat/model-provider-unification`，HEAD `3d791e148beadc1e3e728689cc5ed99d504b6a69`。
基线为已同步的 `chore/docker-compose-infra`；本轮沿用当前分支与上一轮未提交修改。没有新分支、Worktree、提交、推送或合并。
本轮真实探测、Docker 启动、专用账号和本地 Research 权益初始化均获用户明确授权；随后用户要求不执行 Deep Research，已遵守。

## 1. 改造前问题与本轮清理

此前模型注册依赖 Provider 分支、Python 默认列表、环境型号清单和凭据优先级；上一轮保留了临时选择器和废弃告警。本轮直接删除 `_legacy_settings`、全部选择/过滤/能力授予及 FutureWarning 逻辑。

移除的配置：`DASHSCOPE_MODEL`、`DEEPSEEK_MODEL`、`ZHIPU_MODEL`、`AUTODL_MODELS`、`AI_ALLOWED_MODELS`；同时清除旧 `OPENLUX_MODELS`、`OPENLUX_AGENT_MODELS`、无效的 `AUTODL_MODEL` 示例/测试。运行时、测试 fixture、原生/Docker 示例和当前维护文档均不再依赖它们。

没有迁移框架或第二套注册机制。现有完整 Model ID 与固定 Alias 保留，未重写会话/任务/Policy 的模型标识。普通组员只需 Key；高级部署保留 Base URL、两个显式默认、Registry 文件和 timeout。

## 2. 最终加载流程与默认选择

`catalog.json` → 校验源声明 → 按 ID 合并可信 `AI_MODEL_REGISTRY_FILE` → 通用 `<PROVIDER>_BASE_URL` 覆盖 → `AI_DEFAULT_MODEL` / `AI_AGENT_DEFAULT_MODEL` → `ModelRegistry(catalog, dict(os.environ))`。

Catalog 维持原扁平 Schema，是实际白名单来源。同 ID 文件条目完整替换并保留原位置，新条目追加。Provider 配置状态、Model 关联、用途、Alias、默认与公开目录继续由原 Registry 校验。缺 Key 不公开且真实请求拒绝，不换渠道；未知/禁用/无工具能力的型号不放行。

自动默认按可用声明顺序：DashScope → DeepSeek → 智谱 → AutoDL → OpenLux。OpenLux 内部 DeepSeek → Qwen → GLM → Kimi；显式默认仍优先。只配 OpenLux Key 时首选 `openlux/deepseek-v4.1-flash`。本机原有显式 AutoDL 默认未被改动，验收请求明确选择 OpenLux。

固定裸名 Alias 不随 Key 变化；例如 `deepseek-chat` 始终绑定 `deepseek/deepseek-chat`，AutoDL/OpenLux 不自动生成裸名 Alias。同名上游在不同供应商下是独立实例。

## 3. 文件与职责

- `apps/agent/src/agent_app/integrations/llm/catalog.json`：五家 Provider、实际白名单、禁用历史模板和固定 Alias。
- `resolver.py`：统一加载/覆盖，删除 Provider 专用分支、AutoDL 常量与旧变量兼容。`registry_from_config()` 仅保留已有显式离线测试注入，不读取旧环境型号清单。
- `apps/agent/scripts/openlux_probe.py`：复用既有 T0–T7 探测；`apps/backend/scripts/autodl_probe.py` 仅增加保持旧默认行为的可选目录校验开关。
- `apps/agent/tests/unit/test_llm_{registry,config_api,routing}.py`、`test_openlux.py`、`test_export_capabilities.py`：声明/用途/路由/能力导出及凭据边界；其他 Agent 测试仅清除旧型号 fixture（Deep Research 测试未执行）。
- `infra/docker/prepare-env.py`、环境示例与 `test_prepare_env.py`：仅导入模板声明的 Key/高级配置；通用处理可选非空覆盖，不再维护型号选择器。
- `.env.example`、Agent README、Model Provider 指南、Docker README、handoff 文档：当前配置与开发操作。
- 本目录 `openlux-*.json`：脱敏真实探测、容器注入和端到端结算证据；不含密码、Cookie、Key、签名封套、生成思考文本。

未改 Agent Adapter、Runtime/Loop、生命周期、Web/Admin 代码、API 契约、授权或计量核心。没有新增依赖或修改锁文件。

## 4. 完整内置白名单

下表 ID 为全局完整 ID；Key 未配置时不公开。已注册、可配置、支持 Agent、Policy 已批准和存在模型预算是不同状态。

| Provider | Model ID | Agent 状态 |
| --- | --- | --- |
| dashscope | `dashscope/qwen-plus` | 沿用已有声明 |
| deepseek | `deepseek/deepseek-chat` | 沿用已有声明 |
| zhipu | `zhipu/glm-4-plus` | 原有 Mock 验证；官方渠道真实联调仍待完成 |
| autodl | `autodl/DeepSeek-V4.1-Flash-1017` | 沿用既有真实探测记录 |
| autodl | `autodl/Qwen3.5-397B-A17B` | 同上 |
| autodl | `autodl/Kimi-K2.5` | 同上 |
| openlux | `openlux/deepseek-v4.1-flash` | 本轮真实探测通过，首选 |
| openlux | `openlux/qwen3.8-flash` | 本轮基础真实探测通过 |
| openlux | `openlux/glm-5.3-flash` | 本轮基础真实探测通过 |
| openlux | `openlux/kimi-k2.6` | 本轮基础真实探测通过 |
| openlux | `openlux/gemini-3.8-flash` | 保留 Chat 声明；输出上限异常，Agent 禁用且未导出/配置预算 |

保持禁用的五款历史模板：`dashscope/qwen-max`、`dashscope/qwen-turbo`、`dashscope/deepseek-v3`、`dashscope/deepseek-r1`、`deepseek/deepseek-reasoner`。模板不自动开放，定义和固定历史 Alias 仍保留；启用需显式受信任声明及能力验证。

OpenLux Label/Brand 精确采用用户给定表。官方目录核对：https://www.openlux.ai/pricing 、https://doc.openlux.ai/ 。未注册其他平台型号；没有价格运行时配置或全量同步。

## 5. OpenLux 真实验证结果与限制

证据：[T0–T7](openlux-probe-20261124.json)、[非流式输出限制](openlux-token-limits-20261124.json)。

五个精确 ID 均在本次 Key 的 `/models` 中，状态200；五者均通过普通 SSE、stream_options usage、temperature=0.3 参数接受及两次两轮工具调用（结果回传且不回传 reasoning）。错误Key返回401。DeepSeek/Qwen见 reasoning_content，GLM见 reasoning_content/reasoning；Kimi/Gemini本次未出现正文推理字段，不根据名称猜测。

所有型号暂设输出上限4096，不填写未知的真实上下文窗口；不声明额外 thinking 策略。32768仅验证请求被接受并收到首块，未证明长输出上限。另以非流式 `max_tokens=64` 请求长输出：

| 型号 | 返回 completion_tokens | reasoning_tokens | 结果 |
| --- | --- | --- | --- |
| DeepSeek | 64 | 64 | length；思考计入completion的小样本证据 |
| Qwen | 64 | 64 | length；同上 |
| GLM | 64 | 26 | length；同上 |
| Kimi | 64 | 1 | length |
| Gemini | 4160 | 268 | stop；不遵守本次64输出限制 |

Gemini虽通过工具往返，仍保守设 `tool_calling=false`，排除Agent与能力导出；不能凭首块成功批准预算。需确认其参数映射、流式输出限制及reasoning语义后再开放。其余四款通过的是本次渠道/Key分组的小样本，不等于生产 SLA 或数学 Token 上界。部分上游 usage 附带 estimated 的计费元数据，本次不改现有计量解析，也不把供应商报告视为独立 tokenizer 证明。

## 6. 本地配置与管理员操作

当前原生 `.env` 未含旧型号变量；一次性从 Docker `agent.env` 删除了两项空旧配置。通过现有 `prepare-env.py --from-local` 导入已配置 OpenLux Key，保留原有非空 Docker 值及显式默认。真实值仅留忽略的本地环境/私密配置。

组员：填写 `apps/agent/.env` 的 Provider Key并用 `uv run --env-file .env ...` 启动三个Agent进程；Docker使用 `infra/docker/env/agent.env`。重启不重读env，修改后应重建三个容器。

新增/调整型号：编辑 Catalog（或可信文件），明确enabled/能力/参数，验证后启用；新增协议兼容Provider仅加Provider与Model声明和Key示例，无需Python分支。

本次用户另行授权创建本地验收账号并初始化 Research。专用账号为 `provider-acceptance-20261124@example.invalid`；私密凭据在忽略的 `infra/docker/secrets/provider-acceptance.json`，不进入报告或命令输出。

账号仅在Docker的 `postgres` 数据库初始化，使用现有 Better Auth `hashPassword` 与 credential schema，未修改已有账号；专用 .invalid 地址不发送外部邮件，作为管理员授权的本地已验证账号fixture。后续真实登录走原Web密码登录、Cookie会话与身份BFF，没有关闭登录认证或新增测试登录接口。

最终容器能力导出后，复用现有 `agent_entitlements.plans` 生成 basic/pro/research 包；通过容器内loopback的既有 Admin 登录、发布、分配预览、分配确认 API 操作，未使用被禁止的 CLI assign/install 旁路。Admin仍local_password/local-only，没有对外管理入口或关闭同源检查。

发布修订为 `<plan>-v1-local-openlux-20261124-r1`；仅给专用账号分配Research，额度3000000/上海自然日。生产用户和其他既有分配未修改。

仅为 `model:openlux/deepseek-v4.1-flash` 配置本地验收预算：max_output_tokens4096、UTF-8输入风险估算1字节/Token＋1024封装余量。旧Schema必填context_window_tokens4096仅为本地兼容风险字段，不代表上游真实上下文，也未填入Catalog；现有逻辑不将其当第二个输入配额。其他模型无预算仍保持调用拒绝，Gemini不在Agent快照中。

approval_ref=`local-user-authorization-20261124`；risk profile/ref明确 `local-only` 并指向本次探测。现有正式套餐发布机制固定写approved/non-test_only格式，这是**本地数据库内**复用正式业务流程，不代表生产审批或可把该包部署生产。

本地保留（全部被忽略）：`provider-account-setup.mjs`、`provider-admin-setup.py`、`provider-e2e.py`、`provider-capabilities.json`、`provider-model-budgets.json`、`provider-plans.json`、`provider-publication.json`与结果文件，均位于`infra/docker/secrets/`。容器临时私密账号副本已清理；宿主私密文件保留供后续开发复用。

## 7. Docker 与端到端结果

复用既有命令：

```powershell
python infra/docker/prepare-env.py --from-local
cd infra/docker
docker compose -f compose.yml -f compose.dev.yml --profile full config --quiet
docker compose -f compose.yml -f compose.dev.yml --profile full up -d --build --wait
docker compose -f compose.yml -f compose.dev.yml --profile full exec -T backend python /opt/docker/smoke.py --full
```

Engine29.9.2；全部构建与原有数据库迁移成功，完整系统持续运行。Web localhost:3300、Backend localhost:8800、Agent localhost:8811均保持loopback绑定；未删卷、重建空库或部署生产。

[容器配置证据](openlux-container-config-20261124.json)：三个Agent容器均已配置OpenLux，凭据与原生Key在内存比对一致（仅输出布尔值），四款Agent目录一致；Worker protocol=2、V1 drain_only、Backend authorized保持。

现有smoke通过Web/BFF/Backend/认证会话/数据库Schema、缺服务凭据拒绝、公开Admin路径拒绝和V2角色隔离。

[真实端到端与结算证据](openlux-docker-e2e-20261124.json)：专用账号经真实Web密码登录取得会话，通过Web BFF建立fast会话并请求OpenLux DeepSeek；Worker返回 `OPENLUX_ACCEPTANCE_OK`，公开状态 `done`，1轮，无工具/技能调用。

任务 `79186897d5824503ad289dc460e730da`，会话 `ses_753d692b2649495aa38b22a06cde3ea8`。Backend Permit/start记录存在，Permit completed；真实provider_usage输入2205、输出74，共2279 Token。账本held12609，最终全额解除held并used2279；Grant closed/settled、无overage。初始unknown观察与后续measured修订均verified；最终结算投影settled。Agent两条Outbox均delivered，execution sealed，关闭清单有Ack。

本次API的run摘要prompt/completion字段仍为null（既有V2展示行为）；实际计量以验证过的Inbox/Projection/Ledger为准，不把展示字段当零。未修改该无关契约。验收脚本曾把成功状态误写为completed，已按真实契约done修正并校验已保存结果，没有为该断言重新发起付费任务。

**没有执行Deep Research测试。** Research套餐含该能力的既有导出/授权定义，但验收任务实际仅激活 `model:openlux/deepseek-v4.1-flash`。

## 8. 回归测试

本轮最终：模型注册/配置/路由/OpenLux/能力导出/计量边界 **52 passed，35 subtests passed**，无废弃告警；Probe与全部Docker维护测试 **32 passed，12 subtests passed**。

```powershell
# apps/agent；不包含Deep Research测试
uv run --no-sync python -m pytest tests/unit/test_llm_registry.py tests/unit/test_llm_config_api.py tests/unit/test_llm_routing.py tests/unit/test_openlux.py tests/unit/test_export_capabilities.py tests/unit/test_metering_boundaries.py -q
# apps/backend；复用已有Agent pytest依赖，未增加依赖或改锁文件
uv run --project ../agent --no-sync python -m pytest tests/test_autodl_probe.py ../../infra/docker/tests -q
```

`git diff --check`通过。Windows异步测试需要放行本机socketpair，测试使用Mock/ASGI；真实模型请求仅在明确授权的Probe与本地验收中执行。无Web业务代码修改，未跑Web全套检查。

上一轮全量回归为266 passed、58 skipped、13 failed；全部13项已在原始基线源码复现，涉及旧运行时限/工具预算、46秒租约、结算和错误码断言。未删除或放宽这些无关断言。本轮按用户要求不执行Deep Research，因此未重跑包含该测试的全量套件；不能宣称全仓测试全绿。

## 9. 权益与计量兼容性

Registry、Web/Admin能力目录及 `export_capabilities.py` 保持同源；无Key/禁用/无Agent能力模型不进入授权快照。Identity/Digest仍绑定精确Provider、Model、upstream、能力/参数与route revision。新增型号不自动授权，也不借别家同名模型预算。

Agent Runtime、BudgetGrant、CallPermit、唯一发送权、动态输出预算、重试重新授权、用量修订/幂等结算与关闭机制未改。真实验收经过上述门禁并完成预留释放，未切换V1、关闭认证或设置豁免。

## 10. 剩余风险与管理层操作成本

Gemini max_tokens映射异常仍需供应商确认并复测，暂不开放Agent或预算；其他四款仍需生产分组/高并发/长输出与完整上下文验证，智谱官方渠道仍沿用原Mock限制。本地风险批准和账号不可复制成生产批准。

当前管理流程仍需：最终Worker配置对齐→离线导出能力→准备逐模型风险预算→生成三档包→独立Admin认证发布→选择Research修订预览/分配→验证账本。原因是能力快照必须受控、模型上界需独立批准、发布/分配与运行配置刻意分开，不能靠填Key自动授予权益。

本地专用账号初始化还需管理员准备fixture（当前Admin没有创建用户能力，正常注册需邮箱验证）；当前Compose也没有可从Web访问的Admin入口，管理写操作需在Backend loopback执行或沿用原生Admin。未为此扩大本任务范围建设新的部署/认证方案。后续平台管理层可优化受控能力导出、预算审批与本地初始化体验，同时保留这些边界。

私密验收配置只保留本机忽略目录；完整系统保持运行，未提交、推送或合并。
