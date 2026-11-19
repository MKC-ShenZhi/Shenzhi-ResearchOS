# 主工作区本地验收配置准备

日期：2026-11-19。用户授权生成本地密钥、将唯一原账号加入管理员白名单，并预置假验收账号。本次只准备本地配置和账号，没有启动业务服务或调用真实模型。

## 已完成

- 保留并复用既有 BFF secret，Web/Backend 值一致；没有轮换 Better Auth secret，没有修改原账号密码、资料或套餐。
- 为 Agent service、gateway、fact reader、control、worker 五个角色生成各不相同的随机密钥，补齐跨服务同名配置。
- 生成 Ed25519 PEM 私钥、kid 和公钥 JSON 清单，并进行签名/验签匹配验证。
- 更新本地 `apps/backend/.env`、`apps/agent/.env`、`apps/web/.env.local`；原文件先备份到 Backend 忽略目录。保留用户已填的有效参数，只补缺失值/占位符及必须一致的共享值。
- Agent 数据库连接串指向独立的本机 `shenzhi_agent`，沿用本机现有 PostgreSQL 凭据。仅配置连接串，没有创建数据库。
- 将已有本地 Provider 配置复用到 Agent，不输出密钥、不发上游请求。离线目录中有三个已配置公开模型，默认模型可解析；不代表上游鉴权或实际调用已验证。
- 工作区和持久 usage spool 目录已创建；投递参数已验证。
- 修正 Web 本地 env 中一条无法解析的非赋值文本：保留原文并改成注释，原始文件已有备份。
- 将原有唯一正式账号加入 Backend `SHENZHI_ADMIN_USER_IDS`；只改变环境白名单，不改变该账号普通功能。

## 两个普通验收账号

| 用途 | 邮箱 | 昵称 |
| --- | --- | --- |
| Free 流程验收 | `acceptance-free@example.test` | 验收账号 Free |
| 额度流程验收 | `acceptance-quota@example.test` | 验收账号 Quota |

本机注册用户由 1 个变成 3 个。两个新账号为用户明确授权的本地 fixture，通过已安装 Better Auth internal adapter 建立真实 user/credential 记录，并使用官方密码哈希；本地 fixture 标记邮箱已验证，不发送邮件，不改变应用注册、验证码或 BFF 校验配置。两者均经 Better Auth 标准 verified-email/password sign-in 校验成功，脚本只清理自己的临时登录 session。

随机密码仅写在 `apps/backend/workspace/local-entitlement-keys/acceptance-accounts.json`。该目录和 env 备份目录限制为当前 Windows 用户与 SYSTEM 可访问；密钥、密码、env 和备份全部由已有 Git 规则忽略，没有写入本记录。两个假账号均未加入管理员白名单。

账号用途名称不代表已经分配 Free 权益。仍需安装已批准 Policy 并运行历史补齐，才能取得真实 OwnerEntitlementRow；没有用假套餐或测试 Policy 冒充已初始化。

## 尚未执行

1. 创建独立 `shenzhi_agent` 数据库并应用既有 Agent migration。
2. 对主 `shenzhi` 业务库执行既有 Backend migration。
3. 最终 Worker 能力快照导出、Free Policy 安装及历史用户补齐。
4. 单独的模型风险配置批准；本次没有生成任何假的 risk profile，也没有解除模型调用门禁。
5. 重启五个服务进程和真实浏览器端到端验收。

配置文件已写好，但运行中的进程须重新启动才会加载新值。后续流程见 `v1-free-admin-mvp-2026-11-19.md`。
