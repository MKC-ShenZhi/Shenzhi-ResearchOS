# 主题封面生成

从仓库根目录运行。需要 Python 3.10+、支持 WebP 的 Pillow，以及已启动且配置了论文图片代理的 ShenZhi Web。可用 `uv run --no-project --with Pillow` 单独运行工具，无需修改应用依赖。

```powershell
uv run --no-project --with Pillow python tools/topic-cover/generate.py --all --skip-existing
```

工具从 ShenZhi Web 的主题关联论文接口收集候选，再经同源图片代理取图。它会去掉外圈留白，跳过人工排除的图片、疑似整页 PDF、过小的图和重复配图。A1 布局选用 8 张图，按 1／3／3／1 排入四条 −16° 条带，条带之间留 20 px 浅灰绿间隔。

`--all` 从当前启用的主题目录获取 ID。用 `--topic openalex:topic:T10028` 可单独生成一张。默认输出到 `apps/web/public/topic-covers/`，完整 ID 中的 `openalex:topic:` 前缀去掉后得到文件名，如 `T10028.webp`。尺寸为 1440 × 400 px。命令行会列出各条带使用的论文和图片 ID，以及生成、跳过和失败数量。

默认尝试收集 32 张候选，最多扫描 12 页。可用 `--candidates`、`--max-pages` 调整。用 `--origin` 指定 Web 入口，用 `--cache` 指定原图缓存目录，用 `--output-dir` 指定输出目录。批量运行时可用 `--jobs` 调整并发主题数。
