"""The publication case-count check must refuse a report that defaults it.

Before this check, the standalone publication tests compared
`report.get('case_count', len(report['cases']))` with zero: a report without
the key satisfied the comparison with its own length.
"""
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from published_case_count import assert_case_count


class PublishedCaseCountTests(unittest.TestCase):
    def check(self, report):
        assert_case_count(self, report)

    def test_declared_count_matching_the_cases_is_accepted(self):
        self.check({'case_count': 2, 'cases': [{}, {}]})

    def test_missing_count_is_refused(self):
        with self.assertRaisesRegex(AssertionError, 'case_count'):
            self.check({'mismatches': [], 'cases': [{}, {}]})

    def test_count_that_disagrees_with_the_cases_is_refused(self):
        with self.assertRaises(AssertionError):
            self.check({'case_count': 3, 'cases': [{}, {}]})

    def test_non_integer_counts_are_refused(self):
        for count in (2.0, True, '2'):
            with self.subTest(count=count), self.assertRaises(AssertionError):
                self.check({'case_count': count, 'cases': [{}, {}]})

    def test_case_collection_must_be_a_list(self):
        with self.assertRaises(AssertionError):
            self.check({'case_count': 2, 'cases': {'a': {}, 'b': {}}})

    def test_empty_case_list_is_refused(self):
        with self.assertRaises(AssertionError):
            self.check({'case_count': 0, 'cases': []})


if __name__ == '__main__':
    unittest.main()
