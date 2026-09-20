"""工作区不变量：路径禁闭、句柄式截断、唯一匹配编辑、写串行化、命令执行边界。"""
import asyncio
import tempfile
import unittest
from pathlib import Path

from app.core.errors import BusinessError
from app.services.agent import AgentRuntime, StopReason, ToolCall, workspace as workspace_mod
from app.services.agent.provider import Finish, TextDelta, ToolCallEvent
from app.services.agent.workspace import Workspace, build_workspace_tools
from tests.test_agent import FakeProvider


def make_ws():
    tmp = tempfile.TemporaryDirectory()
    return tmp, Workspace(tmp.name)


class ResolveTests(unittest.TestCase):
    def test_confinement(self):
        tmp, ws = make_ws()
        try:
            inside = ws.resolve('sub/dir/file.txt')
            self.assertTrue(str(inside).startswith(str(ws.root)))
            for bad in ['..', '../outside.txt', '../../etc/passwd',
                        str(Path(tmp.name).parent / 'sibling.txt')]:
                with self.subTest(path=bad), self.assertRaises(BusinessError):
                    ws.resolve(bad)
        finally:
            tmp.cleanup()

    def test_root_itself_and_deep_escape_via_dotdot(self):
        tmp, ws = make_ws()
        try:
            self.assertEqual(ws.resolve('.'), ws.root)
            # 双重 resolve 后仍逃不出：resolve('a/../../..') 必须被拒
            with self.assertRaises(BusinessError):
                ws.resolve('a/../../..')
        finally:
            tmp.cleanup()

    def test_missing_root_rejected(self):
        with self.assertRaises(BusinessError):
            Workspace(tempfile.gettempdir() + '/shenzhi-no-such-dir-xyz')



class WorkspaceToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(self._tmp.name)
        self.tools = {t.spec.name: t for t in build_workspace_tools(self.ws)}
        (Path(self._tmp.name) / 'sample.txt').write_text(
            '\n'.join(f'第{i}行' for i in range(1, 51)), encoding='utf-8')

    def tearDown(self):
        self._tmp.cleanup()

    async def call(self, name, **kwargs):
        tool = self.tools[name]
        args = tool.spec.params_model.model_validate(kwargs)  # dispatch 契约：传校验后的模型实例
        return await tool.execute(ToolCall('c1', name, kwargs), args)

    async def test_read_offset_continuation(self):
        content = await self.call('read_file', path='sample.txt')
        self.assertEqual(content.count('\n'), 49)  # 50 行全读，无续读提示
        content = await self.call('read_file', path='sample.txt', offset=45, limit=3)
        self.assertIn('第45行', content)
        self.assertNotIn('第48行', content)
        self.assertIn('用 offset=48 继续读取', content)  # 未读到末尾 → 句柄式续读
        with self.assertRaises(BusinessError):
            await self.call('read_file', path='sample.txt', offset=999)
        with self.assertRaises(BusinessError):
            await self.call('read_file', path='../outside.txt')

    async def test_read_bytes_cap(self):
        big = Path(self._tmp.name) / 'big.txt'
        big.write_text('x' * (180 * 1024), encoding='utf-8')
        content = await self.call('read_file', path='big.txt')
        self.assertLessEqual(len(content.encode('utf-8')), 150 * 1024 + 200)  # 150KB 上限 + 提示行
        self.assertIn('继续读取', content)

    async def test_write_creates_parents_and_serializes(self):
        message = await self.call('write_file', path='a/b/c.txt', content='你好')
        self.assertIn('已写入', message)
        self.assertEqual((Path(self._tmp.name) / 'a' / 'b' / 'c.txt').read_text(encoding='utf-8'), '你好')
        # 同路径并发写：串行化保证两个内容都完整落盘（不互相撕裂）
        await asyncio.gather(
            self.call('write_file', path='a/b/c.txt', content='A' * 100),
            self.call('write_file', path='a/b/c.txt', content='B' * 100))
        final = (Path(self._tmp.name) / 'a' / 'b' / 'c.txt').read_text(encoding='utf-8')
        self.assertIn(final, ('A' * 100, 'B' * 100))

    async def test_edit_unique_match_semantics(self):
        await self.call('write_file', path='code.txt', content='alpha\nbeta\ngamma')
        message = await self.call('edit_file', path='code.txt',
                                  edits=[{'old_text': 'beta', 'new_text': 'BETA'}])
        self.assertIn('1 处', message)
        self.assertEqual((Path(self._tmp.name) / 'code.txt').read_text(encoding='utf-8'),
                         'alpha\nBETA\ngamma')
        for edits, label in [([{'old_text': 'missing', 'new_text': 'x'}], '零命中'),
                             ([{'old_text': 'a', 'new_text': 'x'}], '多命中')]:
            with self.subTest(label=label), self.assertRaises(BusinessError):
                await self.call('edit_file', path='code.txt', edits=edits)

    async def test_run_command_output_spill_and_exit_code(self):
        message = await self.call('run_command', command='echo hello-workspace')
        self.assertIn('hello-workspace', message)
        # 经文件制造超长输出（绕开 cmd.exe ~8KB 命令行长度限制）
        big = Path(self._tmp.name) / 'big-output.txt'
        big.write_text('\n'.join(f'line-{i}' for i in range(3000)), encoding='utf-8')
        import sys
        read_command = 'type big-output.txt' if sys.platform == 'win32' else 'cat big-output.txt'
        message = await self.call('run_command', command=read_command)
        self.assertIn('完整输出', message)
        spill = Path(self._tmp.name) / '.shenzhi' / 'output_1.txt'
        self.assertTrue(spill.is_file())
        self.assertGreater(spill.stat().st_size, 20 * 1024)
        message = await self.call('run_command', command='exit 3')
        self.assertIn('退出码: 3', message)

    async def test_command_timeout(self):
        import sys
        sleep_cmd = 'sleep 5' if sys.platform != 'win32' else \
            'powershell -NoProfile -Command "Start-Sleep 5"'
        with self.assertRaises(BusinessError):
            await self.call('run_command', command=sleep_cmd, timeout_s=1)

    async def test_command_timeout_clamped(self):
        """模型传超大 timeout 会被封顶到 MAX_COMMAND_TIMEOUT_S（pi MAX_TIMEOUT_SECONDS 同思路）。"""
        import subprocess as sp
        from unittest.mock import patch as mock_patch
        from app.services.agent.workspace import MAX_COMMAND_TIMEOUT_S
        with mock_patch('app.services.agent.workspace.subprocess.run') as run:
            run.return_value = sp.CompletedProcess(args=[], returncode=0, stdout='', stderr='')
            await self.call('run_command', command='echo ok', timeout_s=999_999)
            self.assertEqual(run.call_args.kwargs['timeout'], MAX_COMMAND_TIMEOUT_S)  # 不以 999999 下发
        with self.assertRaises(BusinessError):
            await self.call('run_command', command='echo ok', timeout_s=-5)

    async def test_destructive_commands_rejected(self):
        """服务器场景 deny list：机器级不可逆破坏拒绝；工作区内普通操作放行。"""
        blocked = ['rm -rf /', 'rm -rf /usr', 'sudo rm -rf /etc',
                   'mkfs.ext4 /dev/sda1', 'dd if=/dev/zero of=/dev/sda',
                   'shutdown now', 'reboot',
                   'reg delete HKLM\\SOFTWARE\\Microsoft /f',
                   'rd /s /q C:\\', 'format c:',
                   'chmod -R 777 /', ':(){ :|:& };:']
        for command in blocked:
            with self.subTest(command=command), self.assertRaises(BusinessError):
                await self.call('run_command', command=command)
        # 正常命令不得误伤
        for command in ['echo ok', 'type sample.txt', 'del tmp.txt', 'rm scratch.md']:
            with self.subTest(command=command):
                await self.call('run_command', command=command)

    async def test_edit_concurrent_no_interleave(self):
        """edit 走 per-path lock（pi file-mutation-queue 覆盖全部变更）：
        并发改同一文件的不同位置，两处修改都落盘——无锁时后写会整体覆盖先写。"""
        await self.call('write_file', path='pair.txt', content='aaa\nbbb\n')
        barrier = asyncio.Event()

        async def replace(old, new):
            await barrier.wait()
            await self.call('edit_file', path='pair.txt',
                            edits=[{'old_text': old, 'new_text': new}])

        barrier.set()
        await asyncio.gather(replace('aaa', 'AAA'), replace('bbb', 'BBB'))
        final = (Path(self._tmp.name) / 'pair.txt').read_text(encoding='utf-8')
        self.assertEqual(final, 'AAA\nBBB\n')


class MountingTests(unittest.IsolatedAsyncioTestCase):
    async def test_workspace_tools_mounted(self):
        tmp, ws = make_ws()
        try:
            provider = FakeProvider([
                [ToolCallEvent(ToolCall('c1', 'read_file', {'path': 'hello.txt'})),
                 Finish(StopReason.TOOL_CALLS)],
                [TextDelta('内容是：你好'), Finish(StopReason.STOP)],
            ])
            (Path(tmp.name) / 'hello.txt').write_text('你好', encoding='utf-8')
            runtime = AgentRuntime(provider=provider, tools=build_workspace_tools(ws))
            result = await runtime.run('读取 hello.txt')
            self.assertEqual(result.status, 'done')
            self.assertEqual(result.final_text, '内容是：你好')
        finally:
            tmp.cleanup()


if __name__ == '__main__':
    unittest.main()
