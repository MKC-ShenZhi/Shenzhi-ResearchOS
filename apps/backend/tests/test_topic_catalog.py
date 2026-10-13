import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from app.services.topics.catalog import CATALOG_PATH, TopicCatalogError, load_topic_catalog
from app.services.topics.registry import TopicRegistry


class TopicCatalogTests(unittest.TestCase):
    def setUp(self):
        load_topic_catalog.cache_clear()
        self.raw = json.loads(CATALOG_PATH.read_text(encoding='utf-8'))
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'catalog.json'

    def tearDown(self):
        load_topic_catalog.cache_clear()
        self.temp.cleanup()

    def load(self, rows):
        self.path.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
        load_topic_catalog.cache_clear()
        with patch('app.services.topics.catalog.CATALOG_PATH', self.path):
            return load_topic_catalog()

    def test_current_catalog_quality_and_repository_assets(self):
        topics = load_topic_catalog()
        enabled = [topic for topic in topics if topic.enabled]
        self.assertEqual(len(topics), 293)
        self.assertEqual(len(enabled), 293)
        self.assertEqual(Counter(topic.category for topic in enabled), {
            '机器学习': 49, '计算机视觉': 34, '自然语言处理': 30, '大语言模型': 58,
            '智能体': 25, '多模态': 22, '语音/音频处理': 40, '生成式AI': 35,
        })
        self.assertEqual(len({topic.id for topic in topics}), len(topics))
        self.assertEqual(len({topic.subject_query.strip().casefold() for topic in topics}), len(topics))
        public = CATALOG_PATH.parents[4] / 'apps' / 'web' / 'public'
        for topic in topics:
            with self.subTest(topic=topic.id):
                for value in (topic.id, topic.name_zh, topic.name_en, topic.subject_query,
                              topic.category, topic.description_zh, topic.description_en):
                    self.assertTrue(value.strip())
                if topic.image_path:
                    self.assertTrue((public / topic.image_path.lstrip('/')).is_file())

    def test_runtime_accepts_new_count_category_and_asset_without_web_checkout(self):
        topic = {**self.raw[0], 'category': '新增分类', 'imagePath': '/images/topics/new-cover.webp'}
        result = self.load([topic])
        self.assertEqual(TopicRegistry(result).list_topics().categories, ['新增分类'])
        self.assertEqual(len(result), 1)
        result = self.load([topic, {**self.raw[1], 'enabled': False, 'imagePath': None}])
        self.assertEqual(TopicRegistry(result).list_topics().total, 1)

    def test_runtime_rejects_duplicate_ids_and_subject_queries(self):
        for duplicate in [
            {**self.raw[1], 'id': self.raw[0]['id']},
            {**self.raw[1], 'subjectQuery': ' ' + self.raw[0]['subjectQuery'].upper() + ' '},
        ]:
            with self.subTest(duplicate=duplicate['id']), self.assertRaises(TopicCatalogError):
                self.load([self.raw[0], duplicate])

    def test_runtime_rejects_unsafe_image_paths(self):
        for image in ['/images/topics/../secret.png', '/images/topics/%2e%2e.png',
                      'https://example.test/cover.png', '/images/topics/a.png?x=1',
                      '/images/topics/a\\b.png', '/images/topics//a.png', '']:
            with self.subTest(image=image), self.assertRaises(TopicCatalogError):
                self.load([{**self.raw[0], 'imagePath': image}])

    def test_runtime_rejects_missing_or_blank_required_fields_and_negative_count(self):
        for field in ['id', 'nameZh', 'nameEn', 'subjectQuery', 'category', 'descriptionZh', 'descriptionEn']:
            for value in [None, ' ']:
                with self.subTest(field=field, value=value), self.assertRaises(TopicCatalogError):
                    self.load([{**self.raw[0], field: value}])
        with self.assertRaises(TopicCatalogError):
            self.load([{**self.raw[0], 'paperCount': -1}])

    def test_runtime_reports_unreadable_and_malformed_catalog(self):
        with patch('app.services.topics.catalog.CATALOG_PATH', self.path), self.assertRaises(TopicCatalogError):
            load_topic_catalog()
        self.path.write_text('{', encoding='utf-8')
        with patch('app.services.topics.catalog.CATALOG_PATH', self.path), self.assertRaises(TopicCatalogError):
            load_topic_catalog()
        for invalid in [{}, [None]]:
            with self.assertRaises(TopicCatalogError):
                self.load(invalid)
