# Billing & Subscription Phase 1

核心业务在 FastAPI，Web 只负责设置页、Better Auth 身份转发与原始支付通知转发。
微信的签名、响应验签及通知解密由独立 Go Payment 服务中的官方 SDK 完成；支付宝使用官方 Python SDK。
Payment 无数据库，不识别用户，不分配权益，Compose 不发布其宿主端口。

## 订单、订阅与权益

`app/services/billing/catalog.py` 集中定义 Basic / Pro / Research 商业配置，与 Agent Policy 分离。
当前全部是测试价格：1 / 2 / 3 分，CNY，每次购买增加 30×24 小时，页面明确标注。
正式收款前必须审定并修改该配置；没有商品后台、折扣或差价计算。
只允许购买 Admin 已发布、approved 且非 test_only 的正式 Policy。

`billing_orders` 保存用户、套餐/价格/周期快照、Policy Revision、金额（整数分）、币种、渠道、
Mock/live 模式、商户/App 身份、第三方交易号、支付信息与创建/支付/履约时间。
支付状态 `pending / paid / closed` 与履约状态 `pending / completed` 分开存储。
`channel + mode + transaction_id` 唯一；每个订单的权益审计操作 ID 为 `billing:<order_id>`。

支付创建/查询等网络请求在数据库事务之外执行。SDK 验证后的事实必须匹配本地订单号、金额、币种、
渠道、模式、商户和 App。支付确认先单独持久化；随后在另一事务中一起提交权益、有效期、审计与履约标记。
订单行锁及与 Admin 共用的初始分配/发布锁防止重复通知、并发续费重复发放。
创建订单在同一事务锁内检查本人全部待支付及已支付待履约订单：不同套餐返回
`UNFINISHED_ORDER_PLAN_CONFLICT`，同套餐重复 checkout 复用已有待支付订单及原支付渠道。
已支付订单始终保留；没有待支付订单时，同套餐仍可创建续费订单。
履约失败会回滚权益事务，保留 paid/pending；业务拒绝原因保存在订单中。
意外异常同样保留已提交支付，通知返回非成功使渠道重试；用户也可以安全重试履约。

订阅直接使用 `agent_owner_entitlements`，不增加平行的订阅授权系统：

- `expires_at` 可空；NULL 表示现有长期权益。迁移不使历史权益过期。
- `source` 为 `admin` 或 `billing`，历史记录默认 admin。
- 所有仍有效的 Admin 权益（包括长期 Basic/Pro/Research）均禁止被 Billing 覆盖，以免长期权益被缩短为限时权益。
  无现有权益或已到期且未停用的人工权益可以购买；人工停用必须由 Admin 处理。
- Billing 有效期内仅允许同套餐续费，延长至 `max(当前时间, 原到期时间) + 30 天`。
- 有效期内续费固定当前 Policy Revision；新的发布不会在续费时悄悄切换已有任务的 Policy。
- 到期后允许重新购买任一套餐，但跨 Revision 分配仍保留 `ACTIVE_GRANTS_REQUIRE_DRAIN`。
- Admin 显式 assign 使用原来的发布校验/预览/审计，分配结果为长期人工权益（清除到期时间）。
  disable/restore 保留原有效期并将来源转为 admin；恢复操作不会自动延长已过期订阅。
- 下单后 Admin 修改权益也会在履约时重新检查；不会以购买为由解除停用或覆盖长期付费权益。

Admin 和 Billing 共用 `agent_entitlements/assignment.py`，无需模拟管理员或请求 Admin API。
日额度计数保留原 used/held；继续使用原有跨 Revision `daily_balance`，购买/续费不能刷新当天额度。
owner（新任务）、permit、start 实时判断有效期，Permit/Start 截止时间也不超过订阅有效期。
结算/历史锁路径不检查订阅活跃性，已启动调用到期后仍能上报和结算。

`ACTIVE_GRANTS_REQUIRE_DRAIN` 表示旧 Grant 尚未安全关闭，可能仍在等待用量结算。
用户可等待任务及结算结束，再点击“查询支付 / 重试履约”；不能强制释放预留。
没有自动补偿调度器，其他人工权益冲突需管理员根据已支付订单处理，不提供退款实现。

## 用户及回调 API

用户接口均通过已有同源 BFF，要求登录，只能访问自己的订单。

| 方法 | Backend 路径 | 用途 |
|---|---|---|
| GET | `/api/v1/billing/plans` | 可购套餐、发布状态、支付模式 |
| GET | `/api/v1/billing/subscription` | 当前实际权益、来源、有效期及生效状态 |
| POST | `/api/v1/billing/orders` | `{plan_id, channel}` 创建订单；金额等额外字段拒绝 |
| GET | `/api/v1/billing/orders` | 本人近期 20 个订单，刷新页面可恢复支付入口 |
| GET | `/api/v1/billing/orders/{id}` | 已持久化的订单状态，不主动查询支付渠道 |
| POST | `/api/v1/billing/orders/{id}/payment` | 获取/重试同一个未支付订单的支付入口 |
| POST | `/api/v1/billing/orders/{id}/refresh` | 查询渠道；已支付订单安全重试履约 |
| POST | `/api/v1/billing/orders/{id}/mock-pay` | 仅显式启用 Mock 的开发/测试环境可用 |
| POST | `/api/v1/payment-webhooks/{alipay,wechat}` | SDK 验证支付通知；无需用户登录 |

真实商户通知地址配置为公共 Web 的 `/api/payment-notifications/alipay` 或 `/wechat`。
专用 Next 路由按原字节转发请求体，仅透传 Content-Type 和微信签名 Header，不转发用户 Cookie、
Authorization、用户身份或 BFF Secret。不扩大 `clients/backend/forward.ts` 的普通 Header 白名单。
也可以由反向代理把两个固定 Backend 通知路径直接映射到 Backend，须保留原始请求体及微信签名 Header。
禁止因此开放其他 Backend 路由或 Admin 管理入口。
支付宝确认成功响应 `success`；微信成功响应 204；已确认但待履约也确认接收。
前端跳转/返回页不代表支付成功，只展示 Backend 状态。

Payment 内部接口使用独立 `Authorization: Bearer <PAYMENT_SERVICE_TOKEN>`：

```text
GET  /health
POST /internal/wechat/orders
GET  /internal/wechat/orders/{id}
POST /internal/wechat/verify-notification
```

## 本地与 Docker 启动

先按既有工程文档配置数据库、Better Auth、BFF 和 Agent。Backend 执行：

```powershell
cd apps/backend
uv sync --locked
uv run --env-file .env alembic upgrade head
uv run --env-file .env uvicorn app.main:app --reload
```

本地 Backend `.env` 或 Docker `env/backend.env` 开启：

```dotenv
ENVIRONMENT=development
BILLING_PAYMENT_MODE=mock
BILLING_MOCK_ENABLED=true
```

Mock 不要求支付宝/微信商户信息。默认模式是 disabled，不自动开启。
生产 override 固定 `ENVIRONMENT=production` 和 `BILLING_MOCK_ENABLED=false`，即使误选 mock 也无法确认付款。
公共履约入口同样重新检查 Mock 开关及环境；开发环境已支付但待履约的 Mock 订单迁入生产后，
refresh 或直接重试只保留 paid/pending 及拒绝原因，不分配权益。live 订单不受此 Mock 检查影响。
已建订单固定模式，切换运行模式后不可用另一模式查询/模拟支付旧订单。

Docker 在仓库根执行 `python infra/docker/prepare-env.py --from-local`，再按
[Docker 指南](../../infra/docker/README.md) 的既有 app/full 命令构建启动。
脚本新增生成 `env/payment.env`，为 Backend 和 Payment 配对独立随机服务凭据，并保留已有值。
Payment 随 app/full profile 启动；默认 `WECHAT_ENABLED=false`，无商户凭据也可健康启动。
Backend 的 `PAYMENT_SERVICE_URL=http://payment:8090`；宿主原生开发需要单独运行 Go 服务并填写可达的本机地址。
修改锁定依赖需要重建 Backend/Web；新增数据库迁移需要执行 backend-migrate。

登录 Web，打开 `/settings?tab=subscription`，选择套餐及任意支付方式，创建订单后点击“模拟支付成功”。
应显示已支付且权益到账，以及新有效期；重复查询不延长有效期，同套餐新订单续费延长 30 天。
实际 Agent 使用仍要求已有签名密钥、授权模式、正式 Policy、Worker 能力及模型预算审批都正确配置，
Billing 不会合成或放宽这些条件。没有正式发布时，页面会显示暂不可购买。

## 真实渠道配置与联调

Backend 设置 `BILLING_PAYMENT_MODE=live`，不要启用 Mock。live 也承载支付宝官方沙箱，沙箱不等于正式收款。
真实私钥/公钥/证书从运行时文件读取，不放入镜像、Git 或日志。

| 服务 | 变量 | 说明 |
|---|---|---|
| Backend | `ALIPAY_APP_ID`, `ALIPAY_SELLER_ID` | 签约 App 和收款商户身份 |
| Backend | `ALIPAY_PRIVATE_KEY_FILE`, `ALIPAY_PUBLIC_KEY_FILE` | 应用 RSA 私钥、支付宝验签公钥文件 |
| Backend | `ALIPAY_SANDBOX` | true 使用官方沙箱网关；正式商户配置 false |
| Backend | `ALIPAY_NOTIFY_URL`, `ALIPAY_RETURN_URL` | 公共 HTTPS 通知地址和订阅返回页 |
| Backend + Payment | `PAYMENT_SERVICE_TOKEN`, `WECHAT_APP_ID`, `WECHAT_MCH_ID` | 两端保持一致，服务凭据独立于 BFF/Agent |
| Backend | `PAYMENT_SERVICE_URL` | Payment 内部地址 |
| Payment | `WECHAT_ENABLED=true` | 显式启用微信 SDK |
| Payment | `WECHAT_CERT_SERIAL`, `WECHAT_PRIVATE_KEY_FILE` | 商户 API 证书序列号与对应私钥 |
| Payment | `WECHAT_API_V3_KEY` | 32 字节 API v3 密钥，用于 SDK 解密 |
| Payment | `WECHAT_NOTIFY_URL` | 公共 HTTPS `/api/payment-notifications/wechat` |

支付宝电脑网站支付要求商户产品已开通，密钥格式遵循官方 SDK。
`ALIPAY_SANDBOX=true` 时显式使用当前官方沙箱网关 `https://openapi-sandbox.dl.alipaydev.com/gateway.do`，
覆盖锁定 SDK 内的旧沙箱地址；正式环境仍使用 SDK 正式网关，不跳过 HTTPS 验证。
微信 Native 要求产品已开通，Go SDK 使用商户 API 证书方式自动下载/刷新微信平台证书；
当前未配置微信支付公钥 ID 模式，仅有公钥模式的商户需先适配 SDK 对应选项再联调。
支付宝国内交易固定 CNY；查询响应未返回 trans_currency 时，按国内电脑网站支付契约解释为 CNY。
锁定支付宝 SDK 为 `alipay-sdk-python==3.7.1467`。已核对安装包：PagePay 模型不序列化
动态添加的 `seller_id`，TradeQuery 响应模型不含可核验的 App/seller 身份。
查询仍由 SDK 验签，但成功响应返回 `PAYMENT_QUERY_IDENTITY_UNVERIFIED`，不生成可入账支付事实；
交易不存在仍返回未查询到。支付完成依赖异步通知验签，并严格检查通知实际返回的 `app_id/seller_id`。
本地配置不能代替渠道返回的身份。沙箱联调必须确保公共 HTTPS 通知可达；仅浏览器返回或主动查询不会发放权益。

Docker 私钥分别置于 `infra/docker/secrets/backend/` 和 `secrets/payment/`，在 env 中填容器挂载路径。
Payment 运行用户为 distroless nonroot（UID 65532）；Linux 上仅向该用户授予所需密钥读取权限。
Backend 继续使用原有镜像用户。运行用户必须能读取挂载文件，不通过放宽到所有用户解决权限问题。

联调依次验证：支付入口 → 官方钱包支付 → SDK 通知验签/解密 → 本地金额/身份匹配 → paid/completed → Agent 授权。
同时验证重复通知、篡改通知拒绝、支付后刷新、活跃 Grant 待履约及重试。沙箱/真实商户余额操作需人工执行。
没有真实凭据时，只能验证 SDK 离线签名、解密、内部协议、Mock 与数据库业务，不宣称完成真实收款联调。

官方 SDK 来源：[支付宝](https://github.com/alipay/alipay-sdk-python-all)、
[微信支付](https://github.com/wechatpay-apiv3/wechatpay-go)。支付宝官方 PyPI 包名为 `alipay-sdk-python`。

## 自动测试

Backend 在 `apps/backend` 执行：

```powershell
uv run --locked python -m unittest tests.test_agent_entitlements tests.test_admin_console tests.test_admin_audit_accounts tests.test_payment_providers
# 显式选择可销毁的本地 *_test PostgreSQL 数据库，不使用业务库。
$env:BILLING_TEST_DATABASE_URL='<LOCAL_BILLING_TEST_DATABASE_URL>'
uv run --locked python -m unittest tests.test_billing_postgres
```

Billing 集成测试每例创建随机 schema，执行 027/028/029 迁移并清理自己的 schema；
覆盖 HTTP Mock、订单归属、金额/身份匹配、并发幂等、续费、跨套餐限制、Admin 保留、支付持久化与履约回滚。
Agent 双库用例见 `apps/agent/tests/integration/test_billing_execution_postgres.py`，
沿用 `AGENT_A_LINE_TEST_DATABASE_URL` / `BACKEND_A_LINE_TEST_DATABASE_URL` 隔离库约定。
Web 执行 `pnpm test`、`pnpm typecheck`、`pnpm build`；Go 在 `apps/payment` 执行 `go test ./...`、`go build ./cmd/server`。
环境工具测试：`python -m unittest discover -s infra/docker/tests -p test_prepare_env.py`。
