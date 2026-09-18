"""技能资产契约：装载、frontmatter、引用完整性、正文引用的技能真实存在。

这三类问题都在实际开发中真实发生过，且都不会让装载报错——只会在模型装载技能那一刻
才暴露（读到不存在的文件、或按正文指引去 read_skill 一个不存在的技能名）：
- SKILL.md 里写 `references/xxx.md`，但文件不存在；
- 正文说"装载 paper-triage 技能"，但技能库里没有这个名字；
- 正文提到的工具名与实际注册的工具不一致（写了 `scholar_web_search`，实际叫 `web_search`）。
"""
import re
import unittest
from pathlib import Path

import yaml

from app.services.agent.skills import SkillRoot, SkillStore

SKILLS_DIR = Path(__file__).resolve().parents[1] / 'skills'
# 正文里出现的工具名（用于校验技能指引与实际注册工具一致）
KNOWN_TOOLS = {
    'paper_search', 'paper_detail', 'citation_graph', 'web_search',
    'read_paper', 'fetch_url', 'read_skill', 'ask_user',
    'read_file', 'write_file', 'edit_file', 'run_command',
}
_CITE_REF = re.compile(r'references/[\w.-]+\.md')
# 正文中"装载 X 技能"式引用（技能名允许连字符）
_SKILL_REF = re.compile(r'`([a-z][a-z0-9-]{3,})`\s*技能')


class SkillAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = SkillStore.load([SkillRoot(SKILLS_DIR, executable=True)])

    def test_only_deep_research_remains(self):
        """只保留 deep-research：其余七道工序已内化成它的小节（检索/批读/精读/评估/成稿/审计/配图）。"""
        self.assertEqual(self.store.names(), ['deep-research'])
        body = self.store.get('deep-research').body
        for section in ('检索路由', '分级与批读', '全文精读', '证据评估',
                        '成稿', '交付审计', '配图'):
            with self.subTest(section=section):
                self.assertIn(section, body)

    def test_frontmatter_is_valid_and_name_matches_directory(self):
        for name in self.store.names():
            skill = self.store.get(name)
            with self.subTest(skill=name):
                front, _body = _frontmatter(skill.path.read_text(encoding='utf-8'))
                self.assertEqual(front.get('name'), name)
                self.assertTrue(str(front.get('description', '')).strip(),
                                'description 是模型决定装载的唯一依据')

    def test_referenced_reference_files_exist(self):
        """正文点名的 references/*.md 必须真实存在，否则模型读到即失败。"""
        for name in self.store.names():
            skill = self.store.get(name)
            for ref in sorted(set(_CITE_REF.findall(skill.body))):
                with self.subTest(skill=name, ref=ref):
                    self.assertTrue((skill.root / ref).is_file(), f'{name} 引用了不存在的 {ref}')

    def test_referenced_skills_exist(self):
        """正文指引装载的技能必须在技能库里（断链只在装载那一刻才暴露）。"""
        names = set(self.store.names())
        for name in self.store.names():
            skill = self.store.get(name)
            for ref in sorted(set(_SKILL_REF.findall(skill.body))):
                if ref == name or ref in KNOWN_TOOLS:
                    continue
                with self.subTest(skill=name, referenced=ref):
                    self.assertIn(ref, names, f'{name} 指引装载不存在的技能 {ref}')

    def test_no_stale_tool_names(self):
        """技能正文不得出现已删除的旧工具名（scholar_web_search 已并入 web_search）。"""
        for name in self.store.names():
            body = self.store.get(name).body
            with self.subTest(skill=name):
                self.assertNotIn('scholar_web_search', body)


def _frontmatter(raw: str) -> tuple[dict, str]:
    normalized = raw.replace('\r\n', '\n').lstrip('\ufeff')
    end = normalized.find('\n---', 3)
    return yaml.safe_load(normalized[4:end]) or {}, normalized[end + 4:]


if __name__ == '__main__':
    unittest.main()
