"""Deterministic Chat-only Knowledge retrieval query normalization tests."""

import unittest

from app.services.chat.knowledge_query import normalize_knowledge_query


class KnowledgeQueryNormalizerTests(unittest.TestCase):
    def test_strips_small_chinese_question_wrappers_without_changing_term(self):
        cases = {
            "用一句话解释 Transformer。": "Transformer",
            "什么是图神经网络？": "图神经网络",
            "请简单介绍 GraphRAG": "GraphRAG",
            "帮我介绍一下 diffusion model": "diffusion model",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_knowledge_query(raw), expected)

    def test_english_query_is_unchanged_and_empty_normalization_is_safe(self):
        self.assertEqual(normalize_knowledge_query("GraphRAG"), "GraphRAG")
        self.assertEqual(normalize_knowledge_query("什么是？"), "什么是？")
        self.assertEqual(normalize_knowledge_query("   "), "   ")

    def test_result_does_not_exceed_existing_knowledge_limit(self):
        raw = "请简单介绍 " + ("Transformer " * 30)
        self.assertLessEqual(len(normalize_knowledge_query(raw)), 500)


if __name__ == "__main__":
    unittest.main()
