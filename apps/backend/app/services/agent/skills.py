"""SkillStore：Agent Skills 开放标准技能的装载、校验与三级渐进披露。

目录即信任级别：
- 第一方根（`skills/`，可带 tools.py）：**严格**——任何校验错误 = 装载失败，配置错误
  不允许以能力静默缺失上线（pi 对 name 违规只 warning，这里是有意收紧）；
- 外部根（`skills_vendor/`，白名单/全量启用，任何 .py 永不被 import）：**隔离**——单个
  技能坏掉只跳过它并告警，其余技能照常可用（一个第三方目录不该拖垮整座技能库）。

装载结果按技能目录的内容签名缓存：新增/修改/删除技能目录后下一次取用即时生效，
不需要重启进程（"随时可装载一切技能"）。
"""
from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from app.core.errors import BusinessError
from app.services.agent.tools import AfterToolCall, Tool, tool
from app.services.agent.types import FollowUpContext, ToolCall, ToolResult

logger = logging.getLogger('app.agent')

READ_SKILL = 'read_skill'

MAX_NAME_CHARS = 64
MAX_DESCRIPTION_CHARS = 3072
MAX_BODY_CHARS = 60_000
MAX_FILE_CHARS = 300_000

_NAME_PATTERN = re.compile(r'^[a-z0-9-]+$')


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str  # SKILL.md 正文；references 不内联（L3 按需读取）
    path: Path  # SKILL.md 位置（清单里的 location）
    root: Path  # 技能目录（read_file 的禁闭边界）
    executable: bool  # 第一方=True；vendor 永为 False
    disable_model_invocation: bool = False  # pi 扩展字段：不进清单，仅可常驻


@dataclass(frozen=True)
class SkillRoot:
    path: Path
    executable: bool          # .py 是否可被 import（第一方 True；外部根恒 False）
    only: tuple[str, ...] = ()  # 白名单：仅加载这些子目录；空 = 目录下全部


def _escape_xml(value: str) -> str:
    return (value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;').replace("'", '&apos;'))


def _parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    """CRLF/BOM 归一后切分 frontmatter 与正文（pi parseFrontmatter + BOM 处理）。"""
    normalized = raw.replace('\r\n', '\n').replace('\r', '\n')
    if normalized.startswith('\ufeff'):
        normalized = normalized[1:]
    if not normalized.startswith('---'):
        return {}, normalized.strip()
    end = normalized.find('\n---', 3)
    if end == -1:
        return {}, normalized.strip()
    try:
        front = yaml.safe_load(normalized[4:end]) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f'frontmatter 不是合法 YAML: {exc}') from exc
    if not isinstance(front, dict):
        raise ValueError('frontmatter 必须是键值对')
    return front, normalized[end + 4:].strip()


def _name_problems(name: str, dirname: str) -> list[str]:
    problems = []
    if name != dirname:
        problems.append(f'name "{name}" 必须等于目录名 "{dirname}"')
    if len(name) > MAX_NAME_CHARS:
        problems.append(f'name 超过 {MAX_NAME_CHARS} 字符')
    if not _NAME_PATTERN.match(name):
        problems.append('name 只能是小写字母、数字与连字符')
    if name.startswith('-') or name.endswith('-'):
        problems.append('name 首尾不得为连字符')
    if '--' in name:
        problems.append('name 不得包含连续连字符')
    return problems


def _load_skill(directory: Path, executable: bool) -> Skill:
    skill_md = directory / 'SKILL.md'
    front, body = _parse_frontmatter(skill_md.read_text(encoding='utf-8'))
    name = front.get('name') if isinstance(front.get('name'), str) else ''
    description = front.get('description') if isinstance(front.get('description'), str) else ''
    errors = []
    if not name:
        errors.append('frontmatter 缺少 name')
    if not description.strip():
        errors.append(f'frontmatter 缺少 description（它是模型决定装载的唯一依据）')
    if name:
        errors.extend(_name_problems(name, directory.name))
    if len(description) > MAX_DESCRIPTION_CHARS:
        errors.append(f'description 超过 {MAX_DESCRIPTION_CHARS} 字符')
    if len(body) > MAX_BODY_CHARS:
        errors.append(f'正文超过 {MAX_BODY_CHARS} 字符')
    if errors:
        raise ValueError(f'技能 {directory} 无效：' + '；'.join(errors))
    return Skill(name=name, description=description.strip(), body=body, path=skill_md,
                 root=directory, executable=executable,
                 disable_model_invocation=front.get('disable-model-invocation') is True)


def _import_module(module_name: str, path: Path):
    spec = spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f'无法加载 {path}')
    module = module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise ValueError(f'{path} 加载失败: {exc}') from exc
    return module


def _skill_directories(root: Path) -> Iterator[Path]:
    """递归发现含 SKILL.md 的技能目录（pi loadSkillsFromDirInternal 递归语义；
    排除隐藏目录与依赖/缓存目录，代替 pi 的 .gitignore 机制——无 SKILL.md 的
    目录（scripts/、references/ 等）天然被跳过）。"""
    for current, dirs, _files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith('.')
                   and d not in ('node_modules', '__pycache__', '.venv', 'venv')]
        if (Path(current) / 'SKILL.md').is_file() and Path(current) != root:
            yield Path(current)


class SkillStore:
    def __init__(self, skills: dict[str, Skill]):
        self._skills = skills

    @classmethod
    def load(cls, roots: Sequence[SkillRoot]) -> 'SkillStore':
        """装载全部技能；单个技能校验失败只告警跳过（pi harness/skills.ts 同口径：
        诊断以 warning 收集，其余技能照常可用——一个写坏的目录不该让整座技能库不可用）。"""
        skills: dict[str, Skill] = {}
        for root in roots:
            if not root.path.is_dir():
                logger.warning('技能根不存在，已跳过: %s', root.path)
                continue
            # 白名单模式精确点名顶层目录；默认模式递归发现（scripts/、references/ 天然跳过）
            candidates = ([d for d in sorted(root.path.iterdir())
                           if d.is_dir() and (d / 'SKILL.md').is_file()]
                          if root.only else sorted(_skill_directories(root.path)))
            for directory in candidates:
                if root.only and directory.name not in root.only:
                    continue
                try:
                    loaded = _load_skill(directory, root.executable)
                except ValueError as exc:
                    logger.warning('技能校验失败，已跳过: %s', exc)
                    continue
                if loaded.name in skills:
                    logger.warning('技能名冲突，已跳过: %s（%s 与 %s）', loaded.name,
                                   loaded.path, skills[loaded.name].path)
                    continue
                skills[loaded.name] = loaded
        return cls(skills)

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def names(self) -> list[str]:
        return sorted(self._skills)

    def listing_prompt(self, exclude: Sequence[str] = ()) -> str:
        """L1 清单，pi formatSkillsForSystemPrompt 逐字移植（路径解析指令改为 read_skill 机制）。"""
        excluded = set(exclude)
        visible = [s for s in self._skills.values()
                   if not s.disable_model_invocation and s.name not in excluded]
        if not visible:
            return ''
        lines = [
            'The following skills provide specialized instructions for specific tasks.',
            'Read the full skill file when the task matches its description.',
            '技能名不是工具：不能直接调用，须先 read_skill(name="...") 装载其说明再遵循执行。',
            '技能引用 references/ 下的参考文件时，用 read_skill(name, file="references/xxx.md") 读取。',
            '',
            '<available_skills>',
        ]
        for skill in visible:
            lines += [
                '  <skill>',
                f'    <name>{_escape_xml(skill.name)}</name>',
                f'    <description>{_escape_xml(skill.description)}</description>',
                f'    <location>{_escape_xml(str(skill.path))}</location>',
                '  </skill>',
            ]
        lines.append('</available_skills>')
        return '\n'.join(lines)

    def read_body(self, name: str) -> str:
        """L2：装载技能正文（pi formatSkillInvocation 移植 + 参考文件指令适配）。"""
        skill = self._require(name)
        return (f'<skill name="{skill.name}" location="{skill.path}">\n'
                f'参考文件用 read_skill(name="{skill.name}", file="references/xxx.md") 读取。\n\n'
                f'{skill.body}\n</skill>')

    def read_file(self, name: str, file: str) -> str:
        """L3：读取技能 references/ 下的单个文件；路径禁闭，单文件 ≤100k。"""
        skill = self._require(name)
        references = (skill.root / 'references').resolve()
        target = (skill.root / file).resolve()
        if references not in target.parents:
            raise BusinessError(20004, f'非法路径: {file}，只能读取 references/ 下的文件')
        if not target.is_file():
            raise BusinessError(20004, f'文件不存在: {file}')
        content = target.read_text(encoding='utf-8')
        if len(content) > MAX_FILE_CHARS:
            raise BusinessError(20004, f'文件超过 {MAX_FILE_CHARS} 字符上限: {file}')
        return content

    def tools(self) -> list[Tool]:
        """第一方技能的 tools.py 经 importlib 显式路径加载（build_tools 工厂）；vendor 永不到这里。"""
        result: list[Tool] = []
        for skill in sorted(self._skills.values(), key=lambda s: s.name):
            if not skill.executable:
                continue
            tools_py = skill.root / 'tools.py'
            if not tools_py.is_file():
                continue
            module = _import_module(f'shenzhi_skill_{skill.name}', tools_py)
            factory = getattr(module, 'build_tools', None)
            if not callable(factory):
                raise ValueError(f'{skill.name}/tools.py 缺少 build_tools()')
            built = factory()
            if not built:
                raise ValueError(f'{skill.name}/build_tools() 未返回工具')
            result.extend(built)
        return result

    def _require(self, name: str) -> Skill:
        skill = self._skills.get(name)
        if skill is None:
            available = ', '.join(self.names()) or '无'
            raise BusinessError(20004, f'未知技能: {name}。可用技能: {available}')
        return skill


def _parse_read_skill_args(call: ToolCall) -> tuple[str | None, str | None, bool]:
    """从 read_skill 的参数中提取 (name, file, complete)；缺字段交由 dispatch 正常报错。

    complete=True 是"我已按该技能走完流程"的显式声明——harness 只记录它，
    不据此判定或打回：流程是否走完由模型自己负责。
    """
    data = call.arguments
    name = data.get('name')
    file = data.get('file')
    return (name if isinstance(name, str) else None,
            file if isinstance(file, str) else None,
            data.get('complete') is True)


class SkillPolicy:
    """read_skill 的运行时语义（重复装载拦截 / pinned 预算 / 装载记账）。

    pi 的循环对技能一无所知——一切工具行为差异走钩子（agent-loop.ts 中
    prepareToolCall 的 before 分支）。本类就是那对钩子的技能实现：runtime
    构造时装配、循环只调 intercept/settle，不认识 read_skill。
    state 只碰 loaded_skills / pinned_chars 两个记账槽（checkpoint/resume 契约）。
    """

    def __init__(self, store: SkillStore, max_pinned_chars: int):
        self.store = store
        self.max_pinned_chars = max_pinned_chars

    def intercept(self, call: ToolCall, state) -> ToolResult | None:
        """执行前处理。这里只做**引导**，不做拦截——没有任何规则阻止模型装载技能：

        1. 把技能名当工具直调（模型常见混淆）→ 返回引导文本告诉它正确用法（非错误，
           也不阻断任何后续动作）；
        2. 其余情况一律放行，包括重复装载（重复装载是幂等的，没有理由拒绝）。
        技能名含连字符、工具名不允许连字符，二者永不撞名。"""
        if call.name != READ_SKILL:
            if self.store.get(call.name) is not None:
                return ToolResult(call.call_id, call.name,
                                  f'{call.name} 是技能（不是工具）。用 '
                                  f'read_skill(name="{call.name}") 装载它的完整说明，'
                                  f'然后按说明里的流程工作。')
            return None
        return None

    def settle(self, call: ToolCall, result: ToolResult, state) -> ToolResult:
        """执行后结算：完成声明回执；装载内容标 pinned 并计入预算（只记账，不拒绝）。"""
        if call.name != READ_SKILL or result.is_error:
            return result
        name, file, complete = _parse_read_skill_args(call)
        if complete and name is not None and file is None:
            return ToolResult(call.call_id, call.name,
                              f'已记录：你声明技能 {name} 的流程已走完。')
        state.pinned_chars += len(result.content)
        if name is not None and file is None:
            state.loaded_skills.add(name)
        return ToolResult(call.call_id, call.name, result.content,
                          terminal=result.terminal,
                          added_tool_names=result.added_tool_names, pinned=True)


def sync_skill_scripts(store: 'SkillStore', workspace_root: Path,
                       names: Sequence[str] | None = None) -> int:
    """把技能的 scripts/ 同步进工作区（run_command 可执行技能脚本的前提）。

    names 省略 = 全部技能；给出则只同步这些（装载时按需同步，见 sync_loaded_skill_scripts）——
    技能资产随技能到位（渐进披露同样适用于脚本），而不是每个请求把整个技能库
    （实测 1.6MB，含 vendor 的 XSD 模式树）搬进每个会话工作区。
    返回同步的技能数。
    """
    import shutil
    synced = 0
    selected = (store._skills.values() if names is None
                else [store.get(name) for name in names])
    for skill in selected:
        if skill is None:
            continue
        scripts = skill.root / 'scripts'
        if scripts.is_dir():
            shutil.copytree(scripts, workspace_root / skill.name / 'scripts',
                            dirs_exist_ok=True)
            synced += 1
    return synced


def sync_loaded_skill_scripts(store: 'SkillStore', workspace_root: Path) -> AfterToolCall:
    """after_tool_call 钩子：read_skill 装载某技能后，把它的 scripts/ 同步进工作区。

    挂载在工具钩子上（pi：一切工具行为差异走钩子），循环与技能层都不知道工作区存在。
    """
    async def hook(call: ToolCall, _args: Any, result: ToolResult) -> ToolResult | None:
        if call.name != READ_SKILL or result.is_error:
            return None
        name, file, _complete = _parse_read_skill_args(call)
        if name is None or file is not None:
            return None
        if sync_skill_scripts(store, workspace_root, [name]):
            logger.info('技能脚本已同步: %s -> %s', name, workspace_root)
        return None

    return hook


def read_skill_tool(store: SkillStore) -> Tool:
    """内置 read_skill 工具，runtime 在技能存在时注册（L2/L3 渐进披露 + 完成声明）。"""

    class ReadSkillArgs(BaseModel):
        name: str
        file: str | None = None
        # 显式声明"我已按该技能走完流程"：只作为模型自己的收口声明被记录并回执，
        # harness 不据此判定任何东西。声明前先自查技能正文的要求。
        complete: bool = False

    @tool(name=READ_SKILL,
          description='装载系统提示 available_skills 清单中某个技能的完整说明；'
                      'file 省略返回 SKILL.md 正文，file="references/xxx.md" 读取该技能的参考文件。'
                      'complete=true 表示你已按该技能的流程走完并交付（仅作声明记录）。',
          params=ReadSkillArgs,
          snippet='装载 available_skills 清单中某技能的完整说明（或其 references/ 参考文件）')
    async def read_skill(args: ReadSkillArgs) -> str:
        if args.file is None:
            return store.read_body(args.name)
        return store.read_file(args.name, args.file)

    return read_skill


# 装载缓存：键 = 技能根配置 + 目录内容签名。
# 技能目录一有新增/修改/删除，签名即变，下一次取用自动重载（"随时装载一切技能"，
# 不需要重启进程）；配置只列白名单且签名（目录内容）才是缓存键，两者任一变化都重载。
_store_cache: dict[tuple, SkillStore] = {}

_BACKEND_ROOT = Path(__file__).resolve().parents[3]  # apps/backend
BUILTIN_SKILLS_DIR = _BACKEND_ROOT / 'skills'          # 可被部署脚本改写（测试经 patch 覆盖）
VENDOR_SKILLS_DIR = _BACKEND_ROOT / 'skills_vendor'


def _vendor_config() -> tuple[tuple[str, ...], bool]:
    """SKILLS_VENDOR 语义：未设置/空 = 全部启用；`none` = 关闭；列表 = 仅启用这些。"""
    raw = os.getenv('SKILLS_VENDOR', '').strip()
    if raw.lower() in ('none', 'off', '0'):
        return (), False
    return tuple(s.strip() for s in raw.split(',') if s.strip()), True


def _content_signature(roots: Sequence[SkillRoot]) -> tuple:
    """技能目录内容签名：每个 SKILL.md 的路径+mtime+大小，以及 tools.py 的存在性。
    只做轻量 stat（不读文件、不 exec 模块），每次取 store 都能负担。"""
    signature = []
    for root in roots:
        if not root.path.is_dir():
            signature.append((str(root.path), 'missing'))
            continue
        for directory in sorted(_skill_directories(root.path)):
            skill_md = directory / 'SKILL.md'
            tools_py = directory / 'tools.py'
            try:
                stat = skill_md.stat()
                marker = (directory.name, stat.st_mtime_ns, stat.st_size,
                          tools_py.stat().st_mtime_ns if tools_py.is_file() else 0)
            except OSError:
                marker = (directory.name, 'unreadable')
            signature.append(marker)
    return tuple(signature)


def default_store() -> SkillStore:
    """应用默认装载：SKILLS_DIR（严格）+ VENDOR_DIR（按 SKILLS_VENDOR 启用，隔离）。

    外部根的单个技能坏掉只跳过它并告警——一个第三方目录不该让整座技能库不可用。
    """
    rooted: list[tuple[SkillRoot, tuple]] = [
        (SkillRoot(BUILTIN_SKILLS_DIR, executable=True), ())]
    whitelist, enabled = _vendor_config()
    if enabled and VENDOR_SKILLS_DIR.is_dir():
        rooted.append((SkillRoot(VENDOR_SKILLS_DIR, executable=False, only=whitelist),
                       whitelist))
    signature = tuple((str(root.path), root.only, _content_signature([root]))
                      for root, _ in rooted)
    cached = _store_cache.get(signature)
    if cached is not None:
        return cached
    store = SkillStore.load([root for root, _ in rooted])
    _store_cache.clear()  # 只保留当前签名：技能目录重载后旧实例没有复用价值
    _store_cache[signature] = store
    logger.info('技能库已装载: %s 个（%s）', len(store.names()),
                ', '.join(store.names()) or '无')
    return store
