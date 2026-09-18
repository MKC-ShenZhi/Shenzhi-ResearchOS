"""Skill 机制不变量测试。"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


from app.core.errors import BusinessError
from app.services.agent import (
    AgentRuntime, SkillRoot, SkillStore, StopReason, ToolCall, ToolResultMessage, UserMessage,
    default_store, tool,
)
from app.services.agent.provider import Finish, TextDelta, ToolCallEvent
from app.services.agent.skills import MAX_BODY_CHARS, MAX_DESCRIPTION_CHARS, MAX_FILE_CHARS
from app.services.agent.tools import ToolRegistry
from tests.test_agent import FakeProvider, make_echo

TOOLS_PY = '''
from pydantic import BaseModel
from app.services.agent.tools import tool


class P(BaseModel):
    v: str = ''


def build_tools():
    @tool(name='skill_hello', description='来自技能的工具', params=P)
    async def hello(args):
        return f'hello:{args.v}'
    return [hello]
'''


def make_skill(base: Path, name: str, *, body='技能正文', description='测试技能描述',
               extra_front='', dirname=None, tools_py=None, references=None) -> Path:
    directory = base / (dirname or name)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'SKILL.md').write_text(
        f'---\nname: {name}\ndescription: {description}\n{extra_front}---\n\n{body}', encoding='utf-8')
    if tools_py is not None:
        (directory / 'tools.py').write_text(tools_py, encoding='utf-8')
    if references:
        for filename, content in references.items():
            (directory / 'references').mkdir(exist_ok=True)
            (directory / 'references' / filename).write_text(content, encoding='utf-8')
    return directory


class StoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.first = self.base / 'first'
        self.first.mkdir()
        self.vendor = self.base / 'vendor'
        self.vendor.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_load_valid_skill(self):
        make_skill(self.first, 'alpha')
        store = SkillStore.load([SkillRoot(self.first, executable=True)])
        self.assertEqual(store.names(), ['alpha'])
        skill = store.get('alpha')
        self.assertTrue(skill.executable)
        self.assertEqual(skill.body, '技能正文')

    def test_invalid_skill_skipped_not_fatal(self):
        """pi harness/skills.ts 口径：诊断是 warning，坏的跳过、好的照常装载。"""
        cases = [
            ('Name Mismatch', dict(dirname='other-dir')),          # name ≠ 目录名
            ('Bad Case', dict(name='Alpha')),
            ('Leading Hyphen', dict(name='-alpha')),
            ('Double Hyphen', dict(name='al--pha')),
            ('Too Long', dict(name='a' * 65)),
            ('No Description', dict(description='  ')),
            ('Description Too Long', dict(description='长' * (MAX_DESCRIPTION_CHARS + 1))),
            ('Body Too Long', dict(body='正' * (MAX_BODY_CHARS + 1))),
        ]
        for label, kwargs in cases:
            with self.subTest(label=label):
                root = self.base / f'case-{abs(hash(label)) % 10_000}'
                root.mkdir(exist_ok=True)
                name = kwargs.pop('name', 'alpha')
                make_skill(root, name, **kwargs)
                make_skill(root, 'healthy', description='正常技能')
                store = SkillStore.load([SkillRoot(root, executable=True)])
                self.assertEqual(store.names(), ['healthy'])  # 坏的被跳过，好的照常

    def test_duplicate_names_skipped(self):
        """重名：先装载的胜出，后来者跳过并告警（pi 诊断口径，不炸装载）。"""
        make_skill(self.first, 'alpha', description='第一方')
        make_skill(self.vendor, 'alpha', description='外部')
        store = SkillStore.load([SkillRoot(self.first, True), SkillRoot(self.vendor, False)])
        self.assertEqual(store.names(), ['alpha'])
        self.assertEqual(store.get('alpha').description, '第一方')

    def test_bom_and_crlf_tolerance(self):
        directory = self.first / 'bom-skill'
        directory.mkdir()
        (directory / 'SKILL.md').write_bytes(
            '\ufeff---\r\nname: bom-skill\r\ndescription: 带BOM与CRLF\r\n---\r\n\r\n正文'.encode('utf-8'))
        store = SkillStore.load([SkillRoot(self.first, executable=True)])
        self.assertEqual(store.get('bom-skill').body, '正文')

    def test_vendor_whitelist_and_no_import(self):
        make_skill(self.vendor, 'allowed', tools_py='raise RuntimeError("vendor 永不执行")')
        make_skill(self.vendor, 'blocked')
        store = SkillStore.load([SkillRoot(self.vendor, executable=False, only=('allowed',))])
        self.assertEqual(store.names(), ['allowed'])
        self.assertEqual(store.tools(), [])  # vendor 的 tools.py 物理上不被 import

    def test_vendor_whitelist_miss_skips(self):
        """白名单点名不存在的目录：跳过并告警（pi 诊断口径，不因配置笔误炸启动）。"""
        make_skill(self.vendor, 'allowed')
        store = SkillStore.load([SkillRoot(self.vendor, executable=False, only=('allowed', 'typo-name'))])
        self.assertEqual(store.names(), ['allowed'])

    def test_recursive_discovery(self):
        """递归发现嵌套技能（pi loadSkillsFromDirInternal 递归语义）；隐藏/依赖目录跳过。"""
        make_skill(self.first, 'alpha')  # 顶层技能同时在场
        nested = self.first / 'domain' / 'nested-skill'
        nested.mkdir(parents=True)
        (nested / 'SKILL.md').write_text(
            '---\nname: nested-skill\ndescription: 嵌套技能\n---\n\n正文', encoding='utf-8')
        # 隐藏目录与依赖目录里的 SKILL.md 不算技能
        hidden = self.first / '.hidden-skill'
        hidden.mkdir()
        (hidden / 'SKILL.md').write_text(
            '---\nname: hidden-skill\ndescription: 不应加载\n---\n\n正文', encoding='utf-8')
        cache = self.first / '__pycache__'
        cache.mkdir()
        (cache / 'SKILL.md').write_text(
            '---\nname: cached-skill\ndescription: 不应加载\n---\n\n正文', encoding='utf-8')
        store = SkillStore.load([SkillRoot(self.first, executable=True)])
        self.assertIn('nested-skill', store.names())       # 递归命中
        self.assertIn('alpha', store.names())              # 顶层不受影响
        self.assertNotIn('hidden-skill', store.names())    # 隐藏目录排除
        self.assertNotIn('cached-skill', store.names())    # __pycache__ 排除

    def test_listing_prompt_pi_format(self):
        make_skill(self.first, 'alpha', description='含<尖括号>的描述')
        make_skill(self.first, 'hidden', extra_front='disable-model-invocation: true\n')
        store = SkillStore.load([SkillRoot(self.first, executable=True)])
        listing = store.listing_prompt()
        self.assertIn('<available_skills>', listing)
        self.assertIn('<name>alpha</name>', listing)
        self.assertIn('<description>含&lt;尖括号&gt;的描述</description>', listing)  # XML 转义
        self.assertIn('read_skill(name, file=', listing)
        self.assertNotIn('<name>hidden</name>', listing)  # disable-model-invocation 不进清单

    def test_read_body_wrapped_and_unknown(self):
        make_skill(self.first, 'alpha')
        store = SkillStore.load([SkillRoot(self.first, executable=True)])
        body = store.read_body('alpha')
        self.assertTrue(body.startswith(f'<skill name="alpha"'))
        self.assertIn('技能正文', body)
        self.assertTrue(body.endswith('</skill>'))
        with self.assertRaises(BusinessError) as ctx:
            store.read_body('nope')
        self.assertIn('可用技能: alpha', ctx.exception.message)

    def test_read_file_confinement(self):
        make_skill(self.first, 'alpha', references={'guide.md': '参考内容'})
        (self.first / 'alpha' / 'secret.md').write_text('机密', encoding='utf-8')
        store = SkillStore.load([SkillRoot(self.first, executable=True)])
        self.assertEqual(store.read_file('alpha', 'references/guide.md'), '参考内容')
        for bad in ['../secret.md', 'references/../../secret.md', str(self.first / 'alpha' / 'secret.md'),
                    'references/missing.md']:
            with self.subTest(path=bad), self.assertRaises(BusinessError):
                store.read_file('alpha', bad)
        make_skill(self.first, 'huge', references={'big.md': 'x' * (MAX_FILE_CHARS + 1)})
        store = SkillStore.load([SkillRoot(self.first, executable=True)])
        with self.assertRaises(BusinessError):
            store.read_file('huge', 'references/big.md')

    def test_default_store_loads_real_skills(self):
        """默认装载真实技能目录：只有 deep-research（其余技能已内化成它的小节）。

        vendor 开关对第一方技能无影响。
        """
        with patch.dict(os.environ, {'SKILLS_VENDOR': ''}):
            store = default_store()
            self.assertEqual(store.names(), ['deep-research'])
            self.assertTrue(store.get('deep-research').executable)
        with patch.dict(os.environ, {'SKILLS_VENDOR': 'none'}):
            store = default_store()
            self.assertEqual(store.names(), ['deep-research'])

    def test_store_cache_follows_directory_content(self):
        """技能目录变更后下一次取用即时生效（不需要重启：随时可装载新技能）。"""
        tmp = tempfile.mkdtemp()
        try:
            root = Path(tmp) / 'skills_vendor'
            root.mkdir()
            make_skill(root, 'probe-one', description='探针一')
            with patch.dict(os.environ, {'SKILLS_VENDOR': ''}), \
                    patch('app.services.agent.skills.VENDOR_SKILLS_DIR', root):
                first = default_store()
                self.assertIn('probe-one', first.names())
                make_skill(root, 'probe-two', description='探针二')   # 新增目录
                second = default_store()
                self.assertIn('probe-two', second.names())           # 同一进程立即可见
                shutil.rmtree(root / 'probe-two')
                self.assertNotIn('probe-two', default_store().names())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_broken_skill_isolated_in_every_root(self):
        """坏技能只影响它自己：任何根都不因单个技能失效而整体失败（pi 同口径）。"""
        tmp = tempfile.mkdtemp()
        try:
            root = Path(tmp)
            make_skill(root, 'good', description='好的')
            bad = root / 'bad'
            bad.mkdir()
            (bad / 'SKILL.md').write_text('---\nname: mismatch\ndescription: d\n---\n正文',
                                          encoding='utf-8')
            for executable in (False, True):
                with self.subTest(executable=executable):
                    store = SkillStore.load([SkillRoot(root, executable=executable)])
                    self.assertEqual(store.names(), ['good'])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class RuntimeSkillTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.first = self.base / 'first'
        self.first.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_skill_tools_registered_and_conflict(self):
        make_skill(self.first, 'with-tools', tools_py=TOOLS_PY)
        store = SkillStore.load([SkillRoot(self.first, executable=True)])
        runtime = AgentRuntime(skills=store)
        self.assertIn('skill_hello', runtime.registry.tools)
        self.assertIn('read_skill', runtime.registry.tools)
        with self.assertRaises(ValueError):  # 技能工具与业务工具重名 → 启动即失败
            AgentRuntime(tools=[make_echo(name='skill_hello')], skills=store)

    async def test_skill_name_misdirected_as_tool(self):
        """模型把技能名当工具直接调 → 返回引导文本（非错误，不阻断任何后续动作）。"""
        make_skill(self.first, 'guide', body='Guide 技能正文')
        store = SkillStore.load([SkillRoot(self.first, executable=True)])
        provider = FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'guide', {})), Finish(StopReason.TOOL_CALLS)],
            [ToolCallEvent(ToolCall('c2', 'read_skill', {'name': 'guide'})), Finish(StopReason.TOOL_CALLS)],
            [TextDelta('好的'), Finish(StopReason.STOP)],
        ])
        runtime = AgentRuntime(provider=provider, skills=store)
        result = await runtime.run('q')
        self.assertEqual(result.status, 'done')
        results = [m for m in result.messages if isinstance(m, ToolResultMessage)]
        self.assertFalse(results[0].is_error)     # 引导而非拦截
        self.assertIn('read_skill(name="guide")', results[0].content)
        self.assertFalse(results[1].is_error)     # 随后正确装载

    async def test_read_skill_roundtrip_and_reload(self):
        """重复装载是幂等的：不拦截、不报错，正文照常返回。"""
        make_skill(self.first, 'alpha', body='Alpha 技能正文')
        store = SkillStore.load([SkillRoot(self.first, executable=True)])
        provider = FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'read_skill', {'name': 'alpha'})), Finish(StopReason.TOOL_CALLS)],
            [ToolCallEvent(ToolCall('c2', 'read_skill', {'name': 'alpha'})), Finish(StopReason.TOOL_CALLS)],
            [TextDelta('好的'), Finish(StopReason.STOP)],
        ])
        runtime = AgentRuntime(provider=provider, skills=store, system='业务提示')
        result = await runtime.run('q')
        self.assertEqual(result.status, 'done')
        self.assertIn('业务提示', runtime.system)
        self.assertIn('<available_skills>', runtime.system)
        results = [m for m in result.messages if isinstance(m, ToolResultMessage)]
        self.assertFalse(results[0].is_error)
        self.assertTrue(results[0].pinned)          # 装载内容截断豁免
        self.assertIn('Alpha 技能正文', results[0].content)
        self.assertFalse(results[1].is_error)       # 重复装载不再被拦截
        self.assertIn('Alpha 技能正文', results[1].content)

    async def test_load_has_no_budget_gate(self):
        """装载不做预算拦截：pinned 只记账，没有任何规则阻止模型装载技能。"""
        make_skill(self.first, 'alpha', body='A' * 500, references={'guide.md': 'G' * 300})
        store = SkillStore.load([SkillRoot(self.first, executable=True)])
        provider = FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'read_skill',
                                    {'name': 'alpha', 'file': 'references/guide.md'})),
             Finish(StopReason.TOOL_CALLS)],
            [ToolCallEvent(ToolCall('c2', 'read_skill', {'name': 'alpha'})), Finish(StopReason.TOOL_CALLS)],
            [TextDelta('done'), Finish(StopReason.STOP)],
        ])
        # 即便把预算设得极小，也照样装载成功
        runtime = AgentRuntime(provider=provider, skills=store, max_pinned_chars=1)
        result = await runtime.run('q')
        results = [m for m in result.messages if isinstance(m, ToolResultMessage)]
        self.assertFalse(results[0].is_error)
        self.assertTrue(results[0].pinned)
        self.assertFalse(results[1].is_error)
        self.assertIn('<skill name="alpha"', results[1].content)   # 正文照常返回
        self.assertIn('AAAA', results[1].content)


if __name__ == '__main__':
    unittest.main()
