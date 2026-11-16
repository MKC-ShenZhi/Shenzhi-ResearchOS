"""提示词模板：pi harness/prompt-templates 的移植。

目录下的 .md 文件即模板（frontmatter 可带 description/argument-hint），正文支持
位置参数替换（pi substituteArgs 的完整语义）：
- `$1`、`$2`…       → 第 n 个参数（缺省空串）
- `$ARGUMENTS`、`$@` → 全部参数拼一串
- `${@:N}`           → 第 N 个起的所有参数
- `${@:N:L}`         → 第 N 个起的 L 个参数

目录位置与缓存由本模块持有：service（config 接口与 /tpl 展开）与 CLI 共用同一份
清单，改模板文件即生效（内容签名失效，同技能库口径）。
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.services.agent.skills import _parse_frontmatter

MAX_TEMPLATE_CHARS = 20_000

PROMPTS_DIR = Path(__file__).resolve().parents[3] / 'prompts'  # apps/backend/prompts


@dataclass(frozen=True)
class PromptTemplate:
    name: str        # 文件名去 .md
    description: str
    content: str
    path: Path
    argument_hint: str = ''  # pi frontmatter argument-hint：用法提示（如 "<主题> [篇幅]"）


def load_prompt_templates(directory: str | Path) -> list[PromptTemplate]:
    """加载目录下的直接 .md 子文件（非递归；pi loadTemplatesFromDir 同规则）。"""
    root = Path(directory)
    if not root.is_dir():
        return []
    templates: list[PromptTemplate] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        if not entry.is_file() or entry.suffix.lower() != '.md':
            continue
        raw = entry.read_text(encoding='utf-8', errors='replace')
        if len(raw) > MAX_TEMPLATE_CHARS:
            continue  # 异常大的文件不是模板，跳过而非报错
        try:
            front, body = _parse_frontmatter(raw)
        except ValueError:
            continue
        description = front.get('description') if isinstance(front.get('description'), str) else ''
        if not description:
            first_line = next((line.strip() for line in body.split('\n') if line.strip()), '')
            description = first_line[:60] + ('...' if len(first_line) > 60 else '')
        hint = front.get('argument-hint') if isinstance(front.get('argument-hint'), str) else ''
        templates.append(PromptTemplate(entry.stem, description.strip(), body, entry, hint.strip()))
    return templates


def prompt_templates(directory: Path | None = None) -> list[PromptTemplate]:
    """默认目录（PROMPTS_DIR）的模板清单，按内容签名缓存——改文件即生效，不重启。"""
    target = directory or PROMPTS_DIR
    signature = tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size)
                      for p in sorted(target.glob('*.md'))) if target.is_dir() else ()
    global _cache
    if _cache is not None and _cache[0] == (str(target), signature):
        return _cache[1]
    templates = load_prompt_templates(target)
    _cache = ((str(target), signature), templates)
    return templates


def find_template(name: str) -> PromptTemplate | None:
    return next((item for item in prompt_templates() if item.name == name), None)


_cache: tuple[tuple, list[PromptTemplate]] | None = None


def substitute_args(content: str, args: Sequence[str]) -> str:
    """pi substituteArgs 移植：$N / ${@:N} / ${@:N:L} / $ARGUMENTS / $@。"""
    arg_list = list(args)
    result = re.sub(r'\$(\d+)', lambda m: _at(arg_list, int(m.group(1)) - 1), content)

    def slice_repl(match: re.Match) -> str:
        start = max(int(match.group(1)) - 1, 0)
        if match.group(2) is not None:
            return ' '.join(arg_list[start:start + int(match.group(2))])
        return ' '.join(arg_list[start:])

    result = re.sub(r'\$\{@:(\d+)(?::(\d+))?\}', slice_repl, result)
    all_args = ' '.join(arg_list)
    return result.replace('$ARGUMENTS', all_args).replace('$@', all_args)


def _at(args: list[str], index: int) -> str:
    return args[index] if 0 <= index < len(args) else ''


def format_template_invocation(template: PromptTemplate, args: Sequence[str] = ()) -> str:
    """模板 + 参数 → 最终 prompt（pi formatPromptTemplateInvocation）。"""
    return substitute_args(template.content, args)
