"""工具参数 JSON 的解析与修复：pi `packages/ai/src/utils/json-parse.ts` 的移植。

为什么需要它：模型给出的 `function.arguments` 可能是**残缺**的——写大文件时被输出上限
截断（实测一次 write_file 的 content 停在半个字符串里）。pi 在 AI 层就把参数解析成对象，
回传时再 `JSON.stringify`，因此"发回服务端的参数永远是合法 JSON"是结构性成立的；
我们保留 `ToolCall.arguments` 为文本（执行前才校验的契约不变），于是在这里做同一件事：
用同一条阶梯把文本**规范化成合法 JSON**，残缺的部分尽量还原已写完的字段。

阶梯（pi parseStreamingJson 逐级对照）：

1. 空 / 纯空白            → `{}`
2. 标准解析（含修复）      → 对象
3. 部分解析（截断的文本）  → 对象
4. 修复后再部分解析        → 对象
5. 全部失败               → `{}`

第 3/4 级 pi 依赖 npm 包 `partial-json`；此处按同一思路本地实现（不为此引入第三方依赖），
覆盖真实的失败形态：字符串未闭合、容器未闭合、末尾停在半个键/值/逗号。
"""
from __future__ import annotations

import json
from typing import Any

VALID_JSON_ESCAPES = frozenset('"\\/bfnrtu')

_CONTROL_LITERALS = {'\b': '\\b', '\f': '\\f', '\n': '\\n', '\r': '\\r', '\t': '\\t'}


def _escape_control(char: str) -> str:
    return _CONTROL_LITERALS.get(char, f'\\u{ord(char):04x}')


def repair_json(text: str) -> str:
    """修复非法 JSON 字符串字面量（pi repairJson 逐行对照）：

    - 字符串内的裸控制字符（真换行/制表符等）转义；
    - 非法转义序列前面的反斜杠翻倍。
    """
    repaired: list[str] = []
    in_string = False
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if not in_string:
            repaired.append(char)
            if char == '"':
                in_string = True
            index += 1
            continue
        if char == '"':
            repaired.append(char)
            in_string = False
            index += 1
            continue
        if char == '\\':
            following = text[index + 1] if index + 1 < length else None
            if following is None:
                repaired.append('\\\\')
                index += 1
                continue
            if following == 'u':
                digits = text[index + 2:index + 6]
                if len(digits) == 4 and all(c in '0123456789abcdefABCDEF' for c in digits):
                    repaired.append(f'\\u{digits}')
                    index += 6
                    continue
            if following in VALID_JSON_ESCAPES:
                repaired.append(f'\\{following}')
                index += 2
                continue
            repaired.append('\\\\')
            index += 1
            continue
        repaired.append(_escape_control(char) if ord(char) <= 0x1F else char)
        index += 1
    return ''.join(repaired)


def parse_json_with_repair(text: str) -> Any:
    """标准解析；失败则修复后重试（pi parseJsonWithRepair）。"""
    try:
        return json.loads(text)
    except ValueError:
        repaired = repair_json(text)
        if repaired != text:
            return json.loads(repaired)  # 仍失败则由调用方按阶梯降级
        raise


def parse_partial_json(text: str) -> Any:
    """尽量解析被截断的 JSON（pi 用 partial-json 包；此处为本地等价实现）。

    做法：先修复非法转义，再补全未闭合的字符串与容器（丢掉末尾写了一半的键/值/逗号），
    然后交给标准解析器。截断的 write_file 参数因此仍能还原出已写完的字段，
    而不是整份丢成空对象。

    失败抛 ValueError，由 parse_streaming_json 继续降级。
    """
    repaired = repair_json(text)
    completed = _complete_truncated(repaired)
    return json.loads(completed)


def _complete_truncated(text: str) -> str:
    """补全被截断的 JSON 文本（假定已修复过转义）。"""
    closers: list[str] = []
    in_string = False
    index = 0
    length = len(text)
    # 最近一次"结构完整"的位置：不在字符串里，且字符是值结束/分隔/开容器
    while index < length:
        char = text[index]
        if in_string:
            if char == '\\':
                index += 2
                continue
            if char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
        elif char in '{[':
            closers.append('}' if char == '{' else ']')
        elif char in '}]':
            if closers:
                closers.pop()
        index += 1
    body = text.rstrip()
    if in_string:
        body += '"'          # 字符串停在半个值里：闭合它
    body = body.rstrip()
    if body.endswith(','):
        body = body[:-1]     # 末尾悬空的逗号
    # 末尾停在写了一半的键（"key": 或 "key"）时去掉它
    for _ in range(2):
        body = body.rstrip()
        if body.endswith(':'):
            cut = body.rfind('"', 0, len(body) - 1)
            cut = body.rfind('"', 0, cut) if cut > 0 else -1
            body = body[:cut] if cut > 0 else body[:-1]
            continue
        if body.endswith(',') or body.endswith('{') or body.endswith('['):
            break
        if body.endswith('"'):
            # 可能是"只有键、没有值"：交给下面的补括号尝试，失败会整体降级
            break
        break
    return body + ''.join(reversed(closers))


def parse_streaming_json(raw: str | None) -> Any:
    """始终返回对象的参数解析（pi parseStreamingJson 的完整阶梯，绝不抛错）。"""
    if raw is None or not raw.strip():
        return {}
    try:
        return parse_json_with_repair(raw)
    except ValueError:
        try:
            result = parse_partial_json(raw)
            return {} if result is None else result
        except ValueError:
            try:
                result = parse_partial_json(repair_json(raw))
                return {} if result is None else result
            except ValueError:
                return {}
