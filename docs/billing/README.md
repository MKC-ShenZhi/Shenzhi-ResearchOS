# Billing & Subscription Phase 1

核心业务在 FastAPI，Web 只负责设置页、Better Auth 身份转发与原始支付通知转发。
微信的签名、响应验签及通知解密由独立 Go Payment 服务中的官方 SDK 完成；支付宝使用官方 Python SDK。
Payment 无数据库，不识别用户，不分配权益，Compose 不发布其宿主端口。

## 订单、订阅与权益

`app/services/billing/catalog.py` 集中定义 Basic / Pro / Research 商业配置，与 Agent Policy 分离。
Basic 为 0 元、永久免费，不创建订单；Pro 为 19.90 元（1990 分）/ 自然月，Research 为 49.90 元（4990 分）/ 自然月，CNY。当前为支付宝沙盒演示价格，不代表未来正式售价；前端只展示 Backend Catalog 返回的价格。
购买与续费增加一个上海自然月，目标月份没有对应日期取月末；历史订单快照中的 `duration_days=30` 仍按固定 30 天履约。
正式收款前必须审定并修改该配置；本次不启用正式商业收款，没有商品后台或折扣系统。
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
已支付待履约订单始终保留，并阻止再次下单；应先查询／重试履约，避免重复付款。
履约失败会回滚权益事务，保留 paid/pending；业务拒绝原因保存在订单中。
意外异常同样保留已提交支付，通知返回非成功使渠道重试；用户也可以安全重试履约。

订阅直接使用 `agent_owner_entitlements`，不增加平行的订阅授权系统：

- `expires_at` 可空；NULL 表示现有长期权益。迁移不使历史权益过期。
- `source` 仅用于审计（admin / billing / registration / expiry），不作为购买限制。
- 邮箱及 OAuth 首次注册幂等初始化永久 Basic，未发布或 Backend 暂不可用不阻止注册；历史缺失通过 Admin `initialize_only` 补齐。已有权益、停用及异常记录不被初始化覆盖。
- Basic／无权益可购买 Pro 或 Research；有限期 Pro／Research 可同档续费，从 `max(履约时间, 原到期时间)` 加一个自然月。首次购买从实际履约生效时间加一个自然月。
- 有效高级权益支持同套餐续费；有限期 Pro 可差价升级至 Research，管理员赠予的 Pro 同样适用。Research 不支持主动降级。
- 历史永久 Pro／Research 不自动改动，购买返回 `LEGACY_PERMANENT_ENTITLEMENT_REQUIRES_ADMIN`，由管理员明确设置有限期。
- 有效期内续费固定当前 Policy Revision；新的发布不会在续费时悄悄切换已有任务的 Policy。
- 已到期高级权益在订阅查询／关键授权入口按需回落正式 Basic。未关闭 Grant 时保留到期状态及待排空原因，拒绝新高级授权，后续可重试；不新建调度器。Basic 未发布、原权益异常、管理员停用时不静默覆盖。
- Admin 显式 assign 使用原来的发布校验/预览/审计：Basic 永久，Pro／Research 赠予 1～12 个自然月，从操作生效时间直接覆盖。预览提示可能缩短已有权益。disable/restore 保留原有效期；恢复不会延长已过期订阅。
- 下单与履约均核验 Policy 和切换保护；新订单保存原权益快照，付款期间 Admin 改动或其他权益变化会使订单保留 paid/pending 及 `ENTITLEMENT_CHANGED`，不静默覆盖。停用不能通过购买／初始化解除。

Admin 和 Billing 共用 `agent_entitlements/assignment.py`，无需模拟管理员或请求 Admin API。
日额度计数保留原 used/held；继续使用原有跨 Revision `daily_balance`，购买、续费和升级不能刷新当天额度。
owner（新任务）、permit、start 实时判断有效期，Permit/Start 截止时间也不超过订阅有效期。
结算/历史锁路径不检查订阅活跃性，已启动调用到期后仍能上报和结算。

`ACTIVE_GRANTS_REQUIRE_DRAIN` 表示旧 Grant 尚未安全关闭，可能仍在等待用量结算。
用户可等待任务及结算结束，再点击“查询支付 / 重试履约”；不能强制释放预留。
没有自动补偿调度器，其他人工权益冲突需管理员根据已支付订单处理，不提供退款实现。

### Pro → Research 差价升级

V1 支持有效期内的有限期 Pro 升级。`POST /billing/quote` 接收 `{plan_id: "research"}`，Backend 校验原权益、目标发布及切换保护，返回 `amount`（整数分）、`currency`、`quoted_at`、`quote_expires_at`、`quote_token`、目标 Policy Revision 和保留的 `subscription_expires_at`。报价有效期为 5 分钟，且不晚于原权益到期时间。

差价采用 Catalog 月价差乘以剩余自然月价值：以原到期时刻为锚点，按上海时区向前划分自然月，完整月份计 1，当前未满月份按剩余微秒 / 该月段总微秒折算。月底按既有 `add_calendar_months` 截断，多月赠予／续费按全部剩余月份计算。使用有理数计算后一次四舍五入至整数分，正剩余期限最低 1 分；例如剩余半个月段差价 1500 分。原权益没有起始日字段，因此月段统一按保留的到期日反推，不从支付金额或来源推断赠予价值。

升级创建订单必须传 `expected_quote: {quoted_at, quote_token}`。Backend 在锁内以该时间重新计算全部金额及条件，校验时间范围和绑定用户、原权益、目标 Revision 的摘要，不接受前端价格。订单 JSON 快照保留报价、原权益、原到期时间与目标 Policy；同一个未过期待支付订单继续复用，不重写金额／渠道。目标发布或原权益变化后必须重新报价。

**普通购买、同套餐续费不请求或依赖报价，也不读取历史报价有效期。** 这两类请求不传 `expected_quote`；显式携带升级报价而当前已不符合升级条件时返回 `UPGRADE_NOT_AVAILABLE`，避免用户确认的差价升级静默变成全价购买／续费。过期后可再次调用 quote；创建新订单时将已过期的待支付升级订单本地标记 closed 并保留原记录，再创建新升级或购买／续费订单。已支付待履约订单始终保留并阻止重复下单。此本地关闭不等于渠道撤销或退款；晚到的验签支付通知仍能确认 closed 订单的付款，之后重新核验权益快照，绝不覆盖已经变化的权益。

支付入口只对未过期报价开放。报价 TTL 限制报价确认／获取支付入口，不作为延迟回调和履约重试的拒绝条件。支付成功后立即尝试分配订单固定的 Research Policy、保持原到期时间；当日 Token used/held 通过既有跨 Revision daily_balance 保留。原期限届满、权益变更、管理员停用、旧 Grant 未排空或 Policy 无效时，保留 paid/pending 及原因；排空后可通过 refresh 安全重试。永久高级权益仍须管理员先明确设置期限。

历史升级订单仅在快照完整且通过原权益／期限校验时恢复支付与履约；缺少必要快照的保留记录和付款事实，返回 `QUOTE_SNAPSHOT_INVALID` 并交由管理员处理，不猜测原权益或金额、不自动退款。

## 用户及回调 API

### 设置页交互

`/settings?tab=subscription` 按当前权益、套餐对比、用量概览、近期订单组织。
选择套餐打开居中原生模态弹窗，背景遮罩、滚动锁定、Tab 焦点循环、Escape／取消／遮罩关闭及关闭后焦点恢复均在弹窗内管理，页面不插入确认区。
弹窗核对价格、周期及每日额度，新订单默认支付宝；微信显示“暂未接入”并禁选。
确认后创建订单并在当前标签页跳转 Backend 返回的支付宝支付地址，避免异步新窗口被浏览器拦截。
待支付订单按原订单 ID 获取支付入口，展示原金额及渠道；历史微信订单引导到近期订单继续处理，不改写渠道。
请求中禁用重复确认与关闭；获取入口失败保留弹窗并刷新订单恢复列表。
Mock 订单不跳外部支付，订单状态变化与支付入口缺失时提供查看订单入口，不将前端跳转视为支付成功。
已完成／已关闭订单默认折叠，未完成订单保留支付入口及查询／重试操作。
测试价格依据套餐 `test_price` 标记显示；Basic 免费且无需支付，支付关闭、未发布、停用、Research 降级、永久高级权益及待安全回落状态禁用，并展示原因。管理员来源不限制购买。
同套餐待支付订单仍按 Backend 规则复用原订单及支付渠道，弹窗明确提示该行为。

`/settings?tab=usage` 与订阅页用量概览共用 `UsagePanel`，通过同源 BFF 读取
`GET /api/v2/agent/entitlements` 的 v2 原始响应，查询缓存按用户隔离并携带预期用户 Header。
展示实际自然日 Token 窗口中的总额度、已用、预留、剩余及按窗口时区格式化的重置时间。
读取失败显示不可用与重试入口，不以零用量替代失败；没有历史趋势数据时不生成趋势图。

用户接口均通过已有同源 BFF，要求登录，只能访问自己的订单。

| 方法 | Backend 路径 | 用途 |
|---|---|---|
| GET | `/api/v1/billing/plans` | 可购套餐、发布状态、支付模式 |
| GET | `/api/v1/billing/subscription` | 当前实际权益、来源、有效期及生效状态 |
| POST | `/api/v1/billing/quote` | 仅 Pro → Research 升级报价 |
| POST | `/api/v1/billing/orders` | `{plan_id, channel, expected_quote?}`；仅升级要求报价，金额等额外字段拒绝 |
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
应显示已支付且权益到账，以及新有效期；重复查询不延长有效期，同套餐新订单续费延长一个自然月。
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
覆盖 HTTP Mock、订单归属、金额/身份匹配、并发幂等、购买／续费／差价升级、报价过期与重取、Research 禁止降级、Admin 保留、支付持久化与履约回滚。升级及会员补充用例见 `tests.test_billing_membership`。
Agent 双库用例见 `apps/agent/tests/integration/test_billing_execution_postgres.py`，
沿用 `AGENT_A_LINE_TEST_DATABASE_URL` / `BACKEND_A_LINE_TEST_DATABASE_URL` 隔离库约定。
Web 执行 `pnpm test`、`pnpm typecheck`、`pnpm build`；Go 在 `apps/payment` 执行 `go test ./...`、`go build ./cmd/server`。
环境工具测试：`python -m unittest discover -s infra/docker/tests -p test_prepare_env.py`。
