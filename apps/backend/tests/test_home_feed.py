"""Home-feed rule B and source composition."""

import unittest

from app.schemas.discovery import DiscoveryPaper
from app.services.home_feed.composer import compose, spread_venues
from app.services.home_feed.rules import admit

ABSTRACT = 'A displayable abstract for the home card. ' * 6


def raw(**changes):
    values = {
        'id': 'paper:1', 'title': 'A readable paper title', 'abstract': ABSTRACT, 'authors': ['Ada Lovelace'],
        'year': 2026, 'venue': 'CVPR', 'image_id': '/images/CVPR_2026/1.png',
        'keywords': ['diffusion models'], 'subjects': ['diffusion models', 'CVPR.2026 - Accept'],
    }
    values.update(changes)
    return values


def papers(prefix, count, venue='V'):
    return [DiscoveryPaper(id=f'{prefix}:{index}', title='t', abstract='a', year=2026, venue=f'{venue}{index % 6}',
                           image_id=f'/images/{prefix}{index}.png') for index in range(count)]


class AdmissionRuleTests(unittest.TestCase):
    def test_a_displayable_paper_is_cleaned(self):
        paper, reason = admit(raw(title='  A   readable   paper title ', venue='  CVPR '))
        self.assertIsNone(reason)
        self.assertEqual((paper.title, paper.venue), ('A readable paper title', 'CVPR'))
        self.assertEqual(paper.subjects, ['diffusion models'])

    def test_each_rejection_names_its_reason(self):
        cases = {
            'image_missing': raw(image_id=None),
            'image_format': raw(image_id='/images/ICLR_2026/x.svg'),
            'year': raw(year=None),
            'title': raw(title='1 Introduction'),
            'abstract': raw(abstract='Too short.'),
            'authors': raw(authors=['Stanford University']),
        }
        for reason, value in cases.items():
            self.assertEqual(admit(value), (None, reason), reason)
        self.assertEqual(admit(raw(year=2025), year=2026), (None, 'year'))

    def test_packaged_static_thumbnails_stand_in_for_a_knowledge_image(self):
        paper, _ = admit(raw(image_id=None, thumbnail_url='/paper-thumbnails/2604.1v1.webp'))
        self.assertEqual(paper.thumbnail_url, '/paper-thumbnails/2604.1v1.webp')
        # Anything else in thumbnail_url is not trusted as an image.
        self.assertEqual(admit(raw(image_id=None, thumbnail_url='https://evil.example/x.webp')), (None, 'image_missing'))


class ComposerTests(unittest.TestCase):
    def test_quotas_shape_every_screen_and_exhausted_sources_yield_their_slots(self):
        composed = compose({'a': papers('a', 60), 'b': papers('b', 4), 'c': papers('c', 30)}, {'a': 6, 'b': 4, 'c': 2})
        first = [paper.source for paper in composed[:12]]
        self.assertEqual((first.count('a'), first.count('b'), first.count('c')), (6, 4, 2))
        self.assertEqual(len(composed), 94)
        # After `b` runs out, `a` and `c` keep their 6 : 2 ratio.
        later = [paper.source for paper in composed[24:48]]
        self.assertEqual((later.count('a'), later.count('c')), (18, 6))

    def test_duplicates_keep_the_first_placement_and_the_limit_holds(self):
        shared = papers('x', 10)
        composed = compose({'a': shared, 'b': shared}, {'a': 1, 'b': 1}, limit=8)
        self.assertEqual(len(composed), 8)
        self.assertEqual(len({paper.id for paper in composed}), 8)

    def test_venues_left_over_at_the_end_are_swapped_into_earlier_screens(self):
        varied = [DiscoveryPaper(id=f'v:{index}', title='t', abstract='a', year=2026, venue=f'V{index}',
                                 image_id='/images/v.png') for index in range(16)]
        crowded = [DiscoveryPaper(id=f'c:{index}', title='t', abstract='a', year=2026, venue='ACL',
                                  image_id='/images/c.png') for index in range(8)]
        spread = spread_venues(varied + crowded)
        for start in (0, 12):
            screen = [paper.venue for paper in spread[start:start + 12]]
            self.assertLessEqual(screen.count('ACL'), 4)
        self.assertEqual({paper.id for paper in spread}, {paper.id for paper in varied + crowded})

    def test_unknown_or_zero_quota_sources_are_ignored(self):
        composed = compose({'a': papers('a', 3), 'b': papers('b', 3)}, {'a': 1, 'b': 0, 'c': 5})
        self.assertEqual({paper.source for paper in composed}, {'a'})
        self.assertEqual(compose({}, {'a': 1}), [])


if __name__ == '__main__':
    unittest.main()
