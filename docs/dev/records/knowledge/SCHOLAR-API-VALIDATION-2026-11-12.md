# 学者库底座接口复测

2026-11-12（北京时间）。使用本地配置的知识底座地址发送只读 HTTP GET，按[接口提需](<学者库 API 需求.md>)核对响应。

## 实测结果

| 场景 | 结果 |
| --- | --- |
| 默认浏览 `GET /api/v1/scholars` | HTTP 200。默认返回 20 条，`total=363`、`has_more=true`。刷新首屏 ID 顺序一致，前两页共 40 个不同 ID，按姓名排序。用每页 100 条遍历得到 363 个不同 ID，最后一页 63 条且 `has_more=false`。超出末页返回空数组并保留总数。 |
| 英文名、别名、机构检索 | `Aayush Mishra`、`Mishra, Aayush`、`The Johns Hopkins University` 均召回浏览首位的 `openalex:A5013900997`。该记录的头像、机构和统计在浏览、搜索、详情中一致。 |
| 搜索分页、参数校验 | `Marcel` 总数 111，前两页各 20 条且 ID 无交集。无结果查询返回 200、`total=0`、`has_more=false`。缺少 q、纯空白 q、非法分页均返回 400。未知学者详情返回 404。 |
| 详情字段 | Aayush Mishra 的 OpenAlex 画像有英文简介、5 条任职、2022 至 2026 年的 5 条年度引用。作品数 17、总引用 203、h 指数 5、i10 指数 5。引用元数据有来源和覆盖说明，统计截至日期为空。Adi Simhi 和 Ahmed Heakl 的卡片各返回 3 个主题，详情各返回 4 个，顺序一致。 |
| 关联论文 | Aayush Mishra 的 OpenAlex 画像 `paper_count=2`，论文接口 `total=2`。Kaiming He 的 legacy 画像和 Marcel Kockmann 均为 `paper_count=11`、论文 `total=11`。Kockmann 的外部统计返回 `null`。Bin Cao 有 25 项来源作品，`paper_count=0`，论文接口返回空数组且 `total=0`。 |
| 数据覆盖 | 363 张浏览卡片中，285 张有头像字段、351 张有关联机构、314 张有主题，四项展示统计均为非空值。浏览响应的 `name_zh` 均为空。 |

## 待确认与接入差异

- **中文姓名召回。** 搜「何恺明」返回 0 条，搜 `Kaiming He` 返回 2 条。单字「张」返回 7 条，中文字符可进入搜索，仍需补齐已确认的中文别名并验收中英文命中同一 ID。
- **同名记录排序和归并。** 搜 `Aayush Mishra` 返回 3 个同名 ID，完整的 OpenAlex 画像排第 3，前两条缺少外部统计。其中 `author:aayush_mishra` 与 OpenAlex 画像共享约翰斯·霍普金斯大学机构线索及 1 个平台论文 ID。是否为同一人需底座核对，确认后再决定归并方式和展示优先级。
- **头像资源地址。** Aayush Mishra 返回以 `/` 开头的路径，在底座地址上请求该资源返回 206 和 `image/jpeg`。ShenZhi 现有 Adapter 仅保留 HTTPS 头像地址，因此当前路径会被清空。接入时需明确 HTTPS 资源地址或同源资源转发方式。
- **快照覆盖有差异。** 本地快照有 364 条，线上有 363 条。按归一化英文名多重集合比对，线上比快照多一条 Haoyang Chen，少一条 Jiayi Liao 和一条 Yifan Wang。名称比对可用于核对导入范围，身份对应关系仍需底座确认。

## ShenZhi 接入后的端到端验收

使用 `NEXT_PUBLIC_SCHOLAR_PREVIEW=0` 构建独立 Web 实例，连接本机 FastAPI 和已配置的真实底座。头像的相对路径已在 FastAPI 转为同源接口。正式页面的详情下方展示平台关联论文，静态预览继续展示公共精选。

| 场景 | Chrome 验收 |
| --- | --- |
| 首页和分页 | 首屏 20 位、总数 363。Aayush Mishra 的头像成功解码，卡片显示 h 与 i10 指数。点击下一页看到第 2 页的 20 位学者。 |
| 搜索和返回 | 输入 `Mishra, Aayush` 得到一张卡片。打开详情再返回可恢复该搜索，清空回到默认浏览第一页。 |
| 详情和论文 | Aayush Mishra 详情展示 5 条任职、年度引用和 2 篇关联论文。 |
| 请求链路 | 浏览、搜索、详情、论文和头像的同源 BFF 请求均返回 200。浏览器没有请求静态 `profiles.json`，未捕获未处理的页面异常。 |

FastAPI 学者专项 14 项、Web 全量 435 项测试通过。Web 类型检查、学者相关 ESLint 检查和生产构建通过。
