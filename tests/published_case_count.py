"""A published report must declare its case count, not default it from the list.

`report.get('case_count', len(report['cases']))` is true by construction when
the key is missing: the default is the very value it is compared with.  A
writer that stopped declaring `case_count` — or renamed it — would still pass
every publication test that used the expression.  `tests/test_publication_case_count_presence.py`
holds the shared corpus check to this rule; this module gives the standalone
subprocess tests the same check.
"""


def assert_case_count(case, report):
    """Require a declared integer case count equal to the published case list."""
    case.assertIn('case_count', report)
    case.assertIs(type(report['case_count']), int)
    case.assertGreater(report['case_count'], 0)
    case.assertEqual(report['case_count'], len(report['cases']))
