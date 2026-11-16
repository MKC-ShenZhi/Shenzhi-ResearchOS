"""ShenzhiAi：Agent 基座的交互式终端会话（薄 CLI，不接任何前端）。

用法（apps/backend 目录下）：
    uv run python -m app.services.agent                      # 纯对话 + 技能，无文件访问
    uv run python -m app.services.agent --workspace <目录>   # 挂载工作区（read/write/edit/run_command）
    uv run --env-file .env python -m app.services.agent     # 未激活 .env 时

不指定工作区时模型连文件工具的 schema 都看不到；挂载后所有路径禁闭在该目录内。
会话命令：/exit 退出 · /new 新会话 · /skills 列技能 · /tools 列工具 · /cwd 显示工作区。
Ctrl+C：生成中中断本轮（该轮不进入会话历史）。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.services.agent import AgentRuntime, AgentEvent, default_store
from app.services.agent.fetch_url import fetch_url_tool
from app.services.agent.policies import compose_agent_system, run_deadline_s
from app.services.agent.read_paper import read_paper_tool
from app.services.agent.types import RunChannel
from app.services.agent.skills import sync_loaded_skill_scripts
from app.services.agent.tools import Tool
from app.services.agent.types import DELTA, MESSAGE, TOOL_CALL, TOOL_END
from app.services.agent.workspace import Workspace, build_workspace_tools
from app.services.knowledge.service import KnowledgeService

BANNER = """
\033[1mShenzhiAi\033[0m · 深知科研终端智能体（Agent 基座薄 CLI）
技能：{skills} | 工具：{tools} | 模型：{model} | 工作区：{workspace}
命令：/exit 退出 · /new 新会话 · /skills 列技能 · /tools 列工具 · /cwd 显示工作区
运行中输入以 '!' 开头的行 = 插话（下一个工具轮前注入）
"""


def dim(text: str) -> str:
    return f'\033[2m{text}\033[0m'


def bold(text: str) -> str:
    return f'\033[1m{text}\033[0m'


def red(text: str) -> str:
    return f'\033[31m{text}\033[0m'


class ShenzhiAi:
    def __init__(self, workspace_root: str | None) -> None:
        self.store = default_store()
        self.workspace = Workspace(workspace_root) if workspace_root else None
        extra_tools: list[Tool] = build_workspace_tools(self.workspace) if self.workspace else []
        runtime_workspace = self.workspace.root if self.workspace else None
        # 与 service.build_run_runtime 同一套取证通道：终端与 Web 走同一条研究链路，
        # 否则本地跑研究会缺全文/网页能力（两个入口能力不一致是最难查的 bug）。
        extra_tools.append(read_paper_tool(knowledge=KnowledgeService()))
        extra_tools.append(fetch_url_tool())
        self.runtime = AgentRuntime(
            tools=extra_tools,
            skills=self.store,
            system=compose_agent_system,  # 骨架：身份 + 工具清单（按注册表生成）+ 日期
            after_tool_call=(sync_loaded_skill_scripts(self.store, runtime_workspace)
                             if runtime_workspace else None),
            max_context_chars=120_000,  # 对齐 service 产品配置：深度研究的往返历史远超默认 60k
            max_turns=120, deadline_s=run_deadline_s('deep'),  # 科研终端：用 deep 预算（人工在场，长跑正常）
            ask_user=True)  # 终端里 agent 可以反问：问题打印出来，用户下一条输入即回答
        self.history: list = []
        self.channel: RunChannel | None = None

    async def chat(self) -> None:
        while True:
            try:
                prompt = input('\n你> ').strip()
            except (EOFError, KeyboardInterrupt):
                print('\n再见。')
                return
            if not prompt:
                continue
            if prompt in ('/exit', '/quit'):
                print('再见。')
                return
            if prompt == '/new':
                self.history = []
                print(dim('（已开始新会话）'))
                continue
            if prompt == '/skills':
                for name in self.store.names():
                    skill = self.store.get(name)
                    tag = '第一方' if skill.executable else 'vendor'
                    print(f'  {name} [{tag}] {skill.description[:60]}')
                continue
            if prompt == '/tools':
                for name in sorted(self.runtime.registry.tools):
                    print(f'  {name}')
                continue
            if prompt == '/cwd':
                print(f'  {self.workspace.root}' if self.workspace else '  （未挂载工作区）')
                continue
            await self.turn(prompt)

    async def turn(self, prompt: str) -> None:
        print('ShenzhiAi> ', end='', flush=True)
        self.channel = RunChannel()  # 每轮新通道：终端单用户，上一轮的排队消息不跨轮

        async def reader() -> None:
            """后台读终端：'!' 开头的行作为运行中插话注入（pi steer）。"""
            loop = asyncio.get_running_loop()
            while True:
                try:
                    line = await loop.run_in_executor(None, input)
                except (EOFError, OSError, asyncio.CancelledError):
                    return
                line = line.strip()
                if line.startswith('!') and line[1:].strip():
                    self.channel.steer(line[1:].strip())
                    print(dim(f'（已插话，将在下一工具轮前注入）'))

        reader_task = asyncio.ensure_future(reader())
        try:
            result = await self.runtime.run(prompt, history=self.history,
                                            on_event=self._render_event, channel=self.channel)
        except (KeyboardInterrupt, asyncio.CancelledError):
            # Windows：SIGINT 直接在 await 点抛 KeyboardInterrupt；
            # Unix/Runner：首次 Ctrl+C 转为主任务 cancel（runtime 已终态落盘后重抛）。
            # 两种路径都只中断本轮，会话继续。
            print(f'\n{dim("（已中断本轮，本轮不进入会话历史）")}')
            return
        finally:
            reader_task.cancel()
        print()
        if result.output is not None:
            self._render_output(result.output)
        if result.status == 'failed':
            message = result.error.message if result.error else '未知错误'
            print(red(f'出错了：{message}'))
        elif result.status == 'stopped':
            print(dim('（本轮已停止）'))
        elif result.status == 'awaiting_input':
            print(dim('（等你回答——直接输入你的选择或补充，本轮会话继续）'))
        self.history = result.messages

    @staticmethod
    def _render_event(event: AgentEvent) -> None:
        if event.name == DELTA:
            if 'text' in event.data:
                print(event.data['text'], end='', flush=True)
            elif 'reasoning' in event.data:
                print(dim(event.data['reasoning']), end='', flush=True)
        elif event.name == MESSAGE:
            print(dim(f"\n〔插入：{event.data.get('text', '')}〕"), flush=True)
        elif event.name == TOOL_CALL:
            arguments = event.data['arguments'][:80]
            print('\n' + dim(f"→ {event.data['name']}({arguments})"), flush=True)
        elif event.name == TOOL_END:
            mark = '✗' if event.data['is_error'] else '✓'
            print(dim(f"{mark} {event.data['name']}（{event.data['duration_ms']}ms）"), flush=True)

    @staticmethod
    def _render_output(output) -> None:
        """terminal 直出制品：技能的最终交付，或 agent 反问你时的问题（都不经模型转述）。"""
        if not isinstance(output, dict):
            print(output)
            return
        if output.get('kind') == 'question':
            print('\n' + bold('【需要你确认】'))
            for index, question in enumerate(output.get('questions') or [], 1):
                prefix = f'{index}. ' if len(output.get('questions') or []) > 1 else ''
                print(f'{prefix}{question.get("prompt", "")}')
                for option_index, option in enumerate(question.get('options') or [], 1):
                    description = f"  {dim(option['description'])}" if option.get('description') else ''
                    print(f'   {option_index}) {option.get("label", "")}{description}')
                if question.get('allow_other'):
                    print(dim('   （也可以直接输入你自己的答案）'))
            return
        report = output.get('report')
        if report:
            print('\n' + str(report))
        sources = output.get('sources') or []
        if sources:
            print(f'\n{dim(f"参考来源（{len(sources)} 条）：")}')
            for index, source in enumerate(sources, 1):
                title = source.get('title') or source.get('url') or '(未命名)'
                print(f'  [{index}] {title} {source.get("url") or ""}')


async def run_print(prompt: str, workspace_root: str | None) -> int:
    """print 模式（pi modes/print-mode）：一次性跑完输出正文，供脚本/CI/批量评测。

    退出码：0=done · 1=运行失败 · 130=中断。无横幅无提示符，stdout 只有答案；
    工具进度走 stderr（不污染管道输出）。
    """
    app = ShenzhiAi(workspace_root)

    def progress(event) -> None:
        if event.name == TOOL_CALL:
            print(dim(f"→ {event.data['name']}"), file=sys.stderr, flush=True)
        elif event.name == TOOL_END and event.data['is_error']:
            print(dim(f"✗ {event.data['name']}"), file=sys.stderr, flush=True)

    try:
        result = await app.runtime.run(prompt, on_event=progress)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print('\n（已中断）', file=sys.stderr)
        return 130
    if result.output is not None:
        app._render_output(result.output)
    if result.final_text:
        print(result.final_text)
    if result.status == 'failed':
        print(red(f'运行失败：{result.error.message if result.error else "未知错误"}'), file=sys.stderr)
        return 1
    return 0


def main() -> int:
    os.system('')  # Windows 传统控制台下启用 ANSI 转义
    parser = argparse.ArgumentParser(description='ShenzhiAi 终端智能体')
    parser.add_argument('prompt', nargs='?', help='print 模式：一次性执行并输出（省略则进交互会话）')
    parser.add_argument('--workspace', help='挂载工作区目录（不指定则无任何文件访问）')
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[3] / '.env')
    if args.prompt:
        return asyncio.run(run_print(args.prompt, args.workspace))
    app = ShenzhiAi(args.workspace)
    print(BANNER.format(skills=', '.join(app.store.names()) or '无',
                        tools=', '.join(sorted(app.runtime.registry.tools)) or '无',
                        model=app.runtime.model,
                        workspace=app.workspace.root if app.workspace else '未挂载'))
    try:
        asyncio.run(app.chat())
    except Exception as exc:  # CLI 顶层：给出可读退出原因而不是 traceback
        print(red(f'ShenzhiAi 异常退出：{exc}'))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
