"""工作区：可选挂载的文件访问能力，chroot 到指定根目录。

三条铁律：
1. 不挂载 = 不存在：未挂载时模型连文件工具的 schema 都看不到；
2. 挂载即禁闭：所有路径 resolve 后必须仍在工作区根内（与 read_skill 的
   references 禁闭同一模式），.. / 绝对路径逃逸直接拒绝；
3. 工具只依赖 Workspace，不直接碰 open/subprocess —— Workspace 是唯一
   收口点，将来换沙箱/远程实现只改这里。

工具语义沿 pi 已验证模式：read 的句柄式截断（offset 续读）、edit 的唯一
匹配替换（含模糊归一，edit-diff.ts 同款）、bash 保留尾部输出 + 全量 spill 到
工作区内文件。
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import shutil
import subprocess

import unicodedata
import uuid
from pathlib import Path

from pydantic import BaseModel

from app.core.errors import BusinessError
from app.services.agent.tools import Tool, tool

MAX_READ_LINES = 6_000
MAX_READ_BYTES = 150 * 1024
MAX_OUTPUT_LINES = 1_500
MAX_OUTPUT_BYTES = 60 * 1024
MAX_COMMAND_TIMEOUT_S = 900.0  # pi bash MAX_TIMEOUT_SECONDS 同思路：模型可传超时，必须封顶
SPILL_DIR = '.shenzhi'
LINE_CONTINUATION = '\n\n[显示第 {start}-{end} 行，共 {total} 行。用 offset={next_offset} 继续读取。]'
OUTPUT_CONTINUATION = '\n\n[输出已截断（保留尾部）。完整输出: {spill_path}]'

# ---- edit 模糊归一（pi edit-diff.ts normalizeForFuzzyMatch 逐行移植）----
# 目标：模型复制的 old_text 常常带尾随空白/智能引号/Unicode 破折号/特殊空格，
# 精确匹配必然失败——pi 在归一空间里匹配，行级改动叠加回原文，未改动行保留原字节。

_SMART_SINGLE = '\u2018\u2019\u201A\u201B'
_SMART_DOUBLE = '\u201C\u201D\u201E\u201F'
_DASHES = '\u2010\u2011\u2012\u2013\u2014\u2015\u2212'
_SPACES = '\u00A0\u2002-\u200A\u202F\u205F\u3000'


def _normalize_fuzzy(text: str) -> str:
    """pi edit-diff.ts normalizeForFuzzyMatch 逐行移植：渐进归一。

    - 每行尾随空白去掉；
    - 智能引号 → ASCII；
    - Unicode 破折号/连字符 → 普通连字符；
    - 特殊空格 → 普通空格。
    """
    lines = []
    for line in text.split('\n'):
        lines.append(line.rstrip())
    joined = '\n'.join(lines)
    for char in _SMART_SINGLE:
        joined = joined.replace(char, "'")
    for char in _SMART_DOUBLE:
        joined = joined.replace(char, '"')
    for char in _DASHES:
        joined = joined.replace(char, '-')
    for char in _SPACES:
        joined = joined.replace(char, ' ')
    return joined


def _find_text(content: str, old_text: str) -> dict | None:
    """精确优先，模糊兜底（pi fuzzyFindText：精确 / 归一空间精确）。"""
    index = content.find(old_text)
    if index != -1:
        return {'start': index, 'length': len(old_text), 'fuzzy': False}
    fuzzy_content = _normalize_fuzzy(content)
    fuzzy_old = _normalize_fuzzy(old_text)
    fuzzy_index = fuzzy_content.find(fuzzy_old)
    if fuzzy_index != -1:
        return {'start': fuzzy_index, 'length': len(fuzzy_old), 'fuzzy': True}
    return None


def _count_occurrences(content: str, old_text: str) -> int:
    fuzzy_content = _normalize_fuzzy(content)
    fuzzy_old = _normalize_fuzzy(old_text)
    return fuzzy_content.split(fuzzy_old).__len__() - 1


def _apply_replacements(base: str, resolved: list[dict], original: str | None) -> str:
    """按起始位置从后往前替换，偏移保持稳定。模糊时以行级叠加回原文。"""
    if original is None:
        text = base
        for item in reversed(resolved):
            text = text[:item['start']] + item['new'] + text[item['start'] + item['length']:]
        return text
    # 模糊：把 base（归一空间）的替换映射回 original——逐行对齐未改动行
    base_lines = base.split('\n')
    original_lines = original.split('\n')
    # 归一空间与原文行数一致（归一不改行数），按行切分替换区间
    replaced = []
    cursor = 0
    for item in sorted(resolved, key=lambda x: x['start']):
        if item['start'] > cursor:
            replaced.append('\n'.join(base_lines[cursor:item['start']]))
        replaced.append(item['new'])
        cursor = item['start'] + item['length']
    replaced.append('\n'.join(base_lines[cursor:]))
    merged = '\n'.join(x for x in replaced if x != '') if all(x == '' for x in replaced) else '\n'.join(replaced)
    # 未改动行回原文（行级叠加）：逐行比对 base 与 original
    out_lines = []
    merged_lines = merged.split('\n')
    for index, line in enumerate(merged_lines):
        if index < len(original_lines) and _normalize_fuzzy(original_lines[index]) == line:
            out_lines.append(original_lines[index])
        else:
            out_lines.append(line)
    return '\n'.join(out_lines)

# 极端破坏性命令拒绝清单（服务器场景必需；pi 本地靠用户人工确认，不适用）。
# 只拦"机器级不可逆破坏"（清盘/关机/fork 炸弹/注册表抹除），工作区内的普通 rm/del 不拦。
_RM_ROOT = r'rm\s+-[a-z]*[rf][a-z]*\s+(?:-[a-z]+\s+)*(/|/(?:usr|etc|var|bin|sbin|lib|boot|dev|proc|sys|home|root)(?![\w.-]))(?:\s|$)'
_DESTRUCTIVE_PATTERNS = (
    _RM_ROOT,                                       # rm -rf / 及一级系统目录（/tmp/x 等放行）
    r'rm\s+-[a-z]*[rf][a-z]*\s+~/?\s*$',            # rm -rf ~
    r'mkfs(\.\w+)?\b',                              # 格式化文件系统
    r'\bdd\b[^|]*\bof=/dev/(sd|nvme|hd)',           # dd 直写磁盘设备
    r':\(\)\s*\{\s*:\|\:&\s*\}\s*;?\s*:',           # fork bomb
    r'\b(shutdown|reboot|halt|poweroff)\b',         # 关机/重启
    r'reg\s+delete\s+HK',                           # Windows 注册表删除
    r'format\s+[a-z]:',                             # Windows 格式化盘
    r'rd\s+/s\s+/q\b',                              # Windows rd /s /q
    r'\bchmod\s+-R\s+777\s+/(?![\w.-])',            # 根目录全开放
    r'>\s*/dev/sd[a-z]',                            # 重定向直写磁盘
)
_DESTRUCTIVE_RE = [re.compile(pattern, re.I) for pattern in _DESTRUCTIVE_PATTERNS]


def _reject_destructive(command: str) -> None:
    for pattern in _DESTRUCTIVE_RE:
        if pattern.search(command):
            raise BusinessError(20001, f'该命令被安全策略拒绝（不可逆破坏性操作），请换安全的方式完成任务')


class Workspace:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise BusinessError(20001, f'工作区目录不存在: {self.root}')
        self._locks: dict[str, asyncio.Lock] = {}
        self._spill_seq = 0

    def resolve(self, path: str) -> Path:
        """相对路径基于工作区根解析；结果（含符号链接）必须仍在根内。"""
        candidate = (self.root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        if self.root not in candidate.parents and candidate != self.root:
            raise BusinessError(20004, f'路径超出工作区边界: {path}')
        return candidate

    def _lock(self, path: Path) -> asyncio.Lock:
        return self._locks.setdefault(str(path), asyncio.Lock())

    def read(self, path: str, offset: int | None = None, limit: int | None = None) -> str:
        target = self.resolve(path)
        if not target.is_file():
            raise BusinessError(20004, f'文件不存在: {path}')
        text = target.read_text(encoding='utf-8', errors='replace')
        lines = text.split('\n')
        total = len(lines)
        start = max((offset or 1) - 1, 0)
        if start >= total:
            raise BusinessError(20004, f'offset {offset} 超出文件末尾（共 {total} 行）: {path}')
        selected = lines[start:start + limit] if limit is not None else lines[start:]
        content = '\n'.join(selected)
        byte_capped = len(content.encode('utf-8')) > MAX_READ_BYTES
        if byte_capped:
            content = content.encode('utf-8')[:MAX_READ_BYTES].decode('utf-8', errors='ignore')
        shown = len(content.split('\n'))
        end = start + shown
        # 三种截断信号：字节上限 / 行数上限 / 文件还有余下部分
        if byte_capped or shown < len(selected) or end < total:
            content += LINE_CONTINUATION.format(start=start + 1, end=end, total=total, next_offset=end + 1)
        return content

    async def write(self, path: str, content: str) -> str:
        target = self.resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        async with self._lock(target):  # 同路径写操作串行化（pi file-mutation-queue 同思想）
            target.write_text(content, encoding='utf-8')
        return f'已写入 {path}（{len(content.encode("utf-8"))} 字节）'

    async def edit(self, path: str, edits: list[dict]) -> str:
        """pi edit.ts applyEditsToNormalizedContent 的语义移植（edit-diff.ts 同款）：

        - 全部 old_text 在同一份原文上匹配（不叠加）；
        - 空 old_text 拒绝；
        - 匹配走 精确 → 模糊 两段：模糊在归一空间（尾随空白/智能引号/破折号/特殊空格），
          行级改动叠加回原文，未改动行保留原字节；
        - 唯一性 + 区间重叠检测；
        - 无实际变更报错；
        - BOM 保留、行尾回原样。
        """
        target = self.resolve(path)
        if not target.is_file():
            raise BusinessError(20004, f'文件不存在: {path}')
        async with self._lock(target):
            raw = target.read_text(encoding='utf-8', errors='replace')
            bom, text = ('\ufeff', raw[1:]) if raw.startswith('\ufeff') else ('', raw)
            original_ending = '\r\n' if '\r\n' in text else '\n'
            normalized = text.replace('\r\n', '\n').replace('\r', '\n')
            normalized_edits = [
                {'old': item.get('old_text', '').replace('\r\n', '\n').replace('\r', '\n'),
                 'new': item.get('new_text', '').replace('\r\n', '\n').replace('\r', '\n')}
                for item in edits
            ]
            for index, edit in enumerate(normalized_edits):
                if not edit['old']:
                    raise BusinessError(20004, f'edits[{index}].old_text 不能为空')
            fuzzy_used = False
            matches: list[dict] = []
            for index, edit in enumerate(normalized_edits):
                match = _find_text(normalized, edit['old'])
                if match is None:
                    raise BusinessError(20004,
                                        f'edits[{index}] 的 old_text 在文件中不存在（须精确唯一匹配）: '
                                        f'{edit["old"][:80]!r}')
                fuzzy_used = fuzzy_used or match['fuzzy']
                matches.append({'index': index, **match})
            base = _normalize_fuzzy(normalized) if fuzzy_used else normalized
            # 在最终匹配空间里重新定位（模糊时偏移在归一空间）
            resolved: list[dict] = []
            for item in matches:
                match = _find_text(base, normalized_edits[item['index']]['old'])
                if match is None:
                    raise BusinessError(20004, f'edits[{item["index"]}] 的 old_text 未命中')
                occurrences = _count_occurrences(base, normalized_edits[item['index']]['old'])
                if occurrences > 1:
                    raise BusinessError(20004,
                                        f'edits[{item["index"]}] 的 old_text 命中 {occurrences} 处（须唯一）: '
                                        f'{normalized_edits[item["index"]]["old"][:80]!r}')
                resolved.append({'edit_index': item['index'], 'start': match['start'],
                                 'length': match['length'],
                                 'new': normalized_edits[item['index']]['new']})
            resolved.sort(key=lambda item: item['start'])
            for i in range(1, len(resolved)):
                if resolved[i - 1]['start'] + resolved[i - 1]['length'] > resolved[i]['start']:
                    raise BusinessError(20004,
                                        f'edits[{resolved[i - 1]["edit_index"]}] 与 '
                                        f'edits[{resolved[i]["edit_index"]}] 在 {path} 中重叠，'
                                        '请合并为一次编辑或改为互不重叠的区域')
            new_text = _apply_replacements(base, resolved, normalized if fuzzy_used else None)
            if new_text == normalized:
                raise BusinessError(20004, f'未产生任何实际变更: {path}（请检查 old_text 是否确与原文一致）')
            final = bom + (new_text.replace('\n', original_ending)
                           if original_ending == '\r\n' else new_text)
            target.write_text(final, encoding='utf-8')
        changed = sum(1 for item in edits if item.get('old_text') != item.get('new_text'))
        return f'已完成 {len(edits)} 处替换（{changed} 处实际变更）: {path}'

    def exec(self, command: str, timeout_s: float = 180.0) -> str:
        _reject_destructive(command)
        if not timeout_s or timeout_s <= 0 or timeout_s != timeout_s:  # 0/负/NaN
            raise BusinessError(20001, f'无效的超时: {timeout_s}（须为正数秒）')
        timeout_s = min(timeout_s, MAX_COMMAND_TIMEOUT_S)
        try:
            completed = subprocess.run(command, shell=True, cwd=self.root, capture_output=True,
                                       text=True, timeout=timeout_s, encoding='utf-8', errors='replace',
                                       env={**_child_env(), 'SHENZHI_WORKSPACE': str(self.root)})
        except subprocess.TimeoutExpired:
            raise BusinessError(20004, f'命令超时（{timeout_s:.0f}s）: {command[:100]}') from None
        output = (completed.stdout or '') + (completed.stderr or '')
        output = output.rstrip('\n') or '(无输出)'
        lines = output.split('\n')
        if len(lines) > MAX_OUTPUT_LINES or len(output.encode('utf-8')) > MAX_OUTPUT_BYTES:
            self._spill_seq += 1
            spill = self.root / SPILL_DIR / f'output_{self._spill_seq}.txt'
            spill.parent.mkdir(exist_ok=True)
            spill.write_text(output, encoding='utf-8')
            tail = '\n'.join(lines[-MAX_OUTPUT_LINES:])
            if len(tail.encode('utf-8')) > MAX_OUTPUT_BYTES:
                tail = tail.encode('utf-8')[-MAX_OUTPUT_BYTES:].decode('utf-8', errors='ignore')
            output = tail + OUTPUT_CONTINUATION.format(spill_path=spill.relative_to(self.root))
        status = '' if completed.returncode == 0 else f'\n[退出码: {completed.returncode}]'
        return output + status


def _child_env() -> dict[str, str]:
    """子进程环境：继承当前环境（PATH 必需），不在其中注入任何密钥类变量。"""
    return {key: value for key, value in __import__('os').environ.items()}


def build_workspace_tools(workspace: Workspace) -> list[Tool]:
    """挂载工作区后暴露给模型的工具组；未挂载时整个函数不被调用（schema 不可见）。"""

    class ReadArgs(BaseModel):
        path: str
        offset: int | None = None  # 1-based 起始行
        limit: int | None = None   # 最多读取行数

    class WriteArgs(BaseModel):
        path: str
        content: str

    class EditItem(BaseModel):
        old_text: str
        new_text: str

    class EditArgs(BaseModel):
        path: str
        edits: list[EditItem]

    class CommandArgs(BaseModel):
        command: str
        timeout_s: float = 180.0

    @tool(name='read_file',
          description='读取工作区内的文本文件。大文件自动截断并提示用 offset 继续读取。',
          params=ReadArgs,
          snippet='读取工作区文本文件（大文件截断，用 offset 续读）',
          prompt_guidelines=('查看文件内容用 read_file，不要用 run_command 的 cat/type/sed（pi 同款准则）',))
    async def read_file(args: ReadArgs) -> str:
        return workspace.read(args.path, args.offset, args.limit)

    @tool(name='write_file',
          description='在工作区内写文件（不存在则创建，自动创建父目录）。',
          params=WriteArgs,
          snippet='创建或整文件重写',
          prompt_guidelines=(
              'write_file 仅用于新文件或完整重写；局部修改用 edit_file',
              '文件制品（综述/报告/文档）要完整深入：结构、论证与引用充分展开——'
              '"简洁回答"约束对话正文，不约束写入文件的内容',
          ))
    async def write_file(args: WriteArgs) -> str:
        return await workspace.write(args.path, args.content)

    @tool(name='edit_file',
          description='精确文本替换编辑工作区内文件。每处 old_text 必须在文件中唯一匹配；'
                      '一次调用可提交多处互不重叠的替换。',
          params=EditArgs,
          snippet='精确文本替换编辑（一次调用可含多处不重叠替换）',
          prompt_guidelines=(
              'edit_file 用于精确修改：old_text 必须与文件内容精确匹配',
              '同一文件多处独立修改时，合并为一次 edit_file 调用的多处替换，而不是多次调用',
              '各处 old_text 都按原文件匹配（不叠加此前替换），不要提交互相重叠或嵌套的替换；相邻改动合并为一处',
              'old_text 在保持文件内唯一的前提下尽量短，不要包裹大片未改动内容',
          ))
    async def edit_file(args: EditArgs) -> str:
        return await workspace.edit(args.path, [item.model_dump() for item in args.edits])

    @tool(name='run_command',
          description='在工作区根目录执行 shell 命令，返回合并的 stdout/stderr（超长保留尾部并'
                      '落盘完整输出）。非零退出码会在结果中标注。',
          params=CommandArgs, timeout_s=360.0,
          snippet='在工作区根目录执行 shell 命令（超长保留尾部并落盘完整输出）',
          prompt_guidelines=(
              '文件操作优先用专用工具（read_file / write_file / edit_file），run_command 留给构建、脚本与数据处理',
              '需要 ls/find/grep 类目录检索时才用 run_command',
          ))
    async def run_command(args: CommandArgs) -> str:
        return workspace.exec(args.command, args.timeout_s)

    return [read_file, write_file, edit_file, run_command]


# ---- 平台目录注册（pi：文件能力归产品层；service 只组装不管理目录）----
# 进程内登记，owner 隔离，目录禁闭在 workspace/<owner-hash>/<id>。

WORKSPACE_ROOT = Path(__file__).resolve().parents[3] / 'workspace'

MAX_WORKSPACE_FILE_BYTES = 15 * 1024 * 1024
MAX_SESSION_FILE_BYTES = 30 * 1024 * 1024

SESSION_ID_PATTERN = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
# 后缀 → media_type。名字沿用 _TEXT_MEDIA_TYPES（既有引用面），内容已扩到图片产物：
# /assets 端点按后缀直出报告内嵌图，不需要在此引入字节嗅探（导入 mimetypes 只会多一层猜测）。
_TEXT_MEDIA_TYPES = {'.md': 'text/markdown', '.txt': 'text/plain', '.json': 'application/json',
                     '.csv': 'text/csv', '.html': 'text/html', '.log': 'text/plain',
                     '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                     '.webp': 'image/webp', '.gif': 'image/gif', '.svg': 'image/svg+xml'}

_workspaces: dict[str, tuple[str, Path]] = {}  # workspace_id -> (owner, root)


def _owner_dir(owner: str) -> Path:
    return WORKSPACE_ROOT / hashlib.sha1(owner.encode()).hexdigest()[:12]


def create_workspace(owner: str) -> dict:
    if len(_workspaces) >= 300:  # 简单上限：最旧者失效（磁盘目录保留，不阻塞新会话）
        oldest = next(iter(_workspaces))
        _workspaces.pop(oldest, None)
    workspace_id = uuid.uuid4().hex[:12]
    root = _owner_dir(owner) / workspace_id
    root.mkdir(parents=True, exist_ok=True)
    _workspaces[workspace_id] = (owner, root)
    return {'workspace_id': workspace_id}


def _workspace_root(workspace_id: str, owner: str) -> Path:
    entry = _workspaces.get(workspace_id)
    if entry is None or entry[0] != owner:
        raise BusinessError(20004, '工作区不存在或已过期，请重新上传文件夹', 404)
    return entry[1]


def mount_workspace(workspace_id: str, owner: str) -> Workspace:
    """按注册表挂载已上传的工作区（owner 校验 + 路径禁闭）。"""
    return Workspace(_workspace_root(workspace_id, owner))


def ensure_session_workspace(owner: str, session_id: str) -> Path:
    """会话即工作区：同一 session 恒定映射到同一目录（幂等，无需上传）。"""
    if not SESSION_ID_PATTERN.match(session_id):
        raise BusinessError(20001, '非法的会话标识')
    root = _owner_dir(owner) / session_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def mount_workspace_into(target_root: Path, workspace_id: str, owner: str) -> int:
    """把上传工作区的文件同步进目标工作区，返回同步的文件数。

    一个 run 只能有一个工作区根：会话目录是 agent 的工作台（技能脚本、状态文件、产物
    都在这里），上传的文件夹以内容同步的方式挂进来——read_file 与 run_command 都能直接
    触及。此前"会话 + 上传"会各挂一套同名工具，ToolRegistry 直接构造失败。
    按 mtime/大小判定是否重同步：重复上传才覆盖，常驻会话不重复搬运。
    """
    source = _workspace_root(workspace_id, owner).resolve()
    target = target_root.resolve()
    if source == target:
        return 0
    synced = 0
    for item in source.rglob('*'):
        if item.is_dir() or item.name.startswith('.'):
            continue
        relative = item.relative_to(source)
        destination = target / relative
        try:
            stat = item.stat()
            current = destination.stat()
            if current.st_mtime >= stat.st_mtime and current.st_size == stat.st_size:
                continue
        except OSError:
            pass
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)
        synced += 1
    return synced


def write_workspace_file(workspace_id: str, owner: str, relative_path: str, data: bytes) -> dict:
    if len(data) > MAX_WORKSPACE_FILE_BYTES:
        raise BusinessError(20001, f'单文件超过 {MAX_WORKSPACE_FILE_BYTES // (1024 * 1024)}MB 上限')
    root = Workspace(_workspace_root(workspace_id, owner)).root
    candidate = (root / relative_path).resolve()
    if root not in candidate.parents:
        raise BusinessError(20001, '非法的文件路径')
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_bytes(data)
    return {'path': relative_path, 'size': len(data)}


def read_session_file(owner: str, session_id: str, relative_path: str) -> tuple[bytes, str]:
    """读会话工作区文件（agent 产物）：owner 隔离 + 路径禁闭，返回 (内容, media_type)。"""
    if not SESSION_ID_PATTERN.match(session_id):
        raise BusinessError(20001, '非法的会话标识')
    workspace = Workspace(ensure_session_workspace(owner, session_id))
    target = workspace.resolve(relative_path)
    if not target.is_file():
        raise BusinessError(20004, f'文件不存在: {relative_path}', 404)
    if target.stat().st_size > MAX_SESSION_FILE_BYTES:
        raise BusinessError(20001, '文件超过 10MB，请在工作区中处理')
    content = target.read_bytes()
    suffix = target.suffix.lower()
    media_type = _TEXT_MEDIA_TYPES.get(suffix, 'application/octet-stream')
    if media_type.startswith('text/') and not content.startswith(b'\xef\xbb\xbf'):
        try:
            content.decode('utf-8')
        except UnicodeDecodeError:
            media_type = 'application/octet-stream'  # 非 UTF-8 文本按二进制交付，避免乱码
    return content, media_type
