"""
Unit testing for message.py.
"""

import unittest

from parameterized import parameterized
from triggers.message import is_subword


class TestIsSubword(unittest.TestCase):
    """Unit testing for is_subword."""

    @parameterized.expand([
        ('this is a message with best song in it', 'best song', False),
        ('flute', 'flute', False),
        ('"flute?"', 'flute', False),
        ('through', 'rough', True)
    ])
    def test_is_subword(self, text, trigger, expected):
        self.assertEqual(is_subword(text, trigger), expected)
