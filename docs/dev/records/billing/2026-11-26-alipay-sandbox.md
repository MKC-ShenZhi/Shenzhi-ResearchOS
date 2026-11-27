# 支付宝本机沙箱联调

2026-11-26，保持 feat/billing-subscription，未提交、未推送。

- 本地 backend.env 配置与两份安全文件就绪，容器内私钥签名检查通过；未输出密钥。env/secrets 已核实被 Git 忽略。
- Cloudflare Quick Tunnel 转发本机 loopback 临时代理；仅 POST `/api/payment-notifications/alipay` 可到达 Backend 的固定支付宝通知端点，保留原始请求体。根路径、settings、Admin 路径均 404，伪造通知 400。不注册 Windows 服务。临时脚本及进程信息保存在已忽略的 Backend .venv 内。
- 自动更新本地通知 URL，重新创建 Backend/Admin，无镜像构建。其他服务未调整。
- 发现 SDK 默认旧沙箱网关证书过期，依据支付宝官方指南改为 `https://openapi-sandbox.dl.alipaydev.com/gateway.do`；不跳过证书检查。仅修改支付宝适配及对应测试期望，6 项 AlipayTests 通过，新网关 HTTP 200。
- 普通测试账号购买 Pro，金额 2 分，用户手动完成沙箱付款。收银台成功返回；浏览器自动读取沙箱页面曾超时，未阻塞人工付款。
- 22:12:50（Asia/Shanghai）Backend 收到支付宝异步通知并返回 HTTP 200；现有通知入口严格验签并验证 App/seller，订单 paid/completed，履约无错误。
- 对应 billing 审计仅 1 条；订阅从 2027-01-25 延长至 2027-02-24 17:29:12（Asia/Shanghai）。日额度 1,000,000 Token，used=2313、held=0 未被续费重置。
- 返回后的订阅页面显示 Pro 生效及“支付完成，权益已到账”。结果基于真实异步通知及数据库，未以同步返回参数认定付款成功。

本轮支付宝沙箱下单、人工付款、通知、验签、订单及权益闭环通过；不代表正式收款或微信渠道通过。临时隧道暂保留供继续联调，重启后必须更新通知 URL。商户身份、通知域名、交易号及签名不写入本记录。

官方网关依据：https://aipay.alipay.com/wallet-guide
