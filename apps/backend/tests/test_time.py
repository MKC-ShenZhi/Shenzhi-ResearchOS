import unittest
from datetime import datetime, timezone

from app.core.time import utc_now


class TimeTests(unittest.TestCase):
    def test_utc_now_returns_timezone_aware_utc_datetime(self):
        current = utc_now()

        self.assertIsInstance(current, datetime)
        self.assertIs(current.tzinfo, timezone.utc)
        self.assertEqual(current.utcoffset(), timezone.utc.utcoffset(current))


if __name__ == '__main__':
    unittest.main()
