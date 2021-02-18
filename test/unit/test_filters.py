'''Message log-filtering tests based on actual or shortened log data.
There are several log-filtering tests in the `test_actions` module,
but they pretty much just generate the data.

All tests just take one of the log file and run a filter in
"drned-overview" and "overview" mode and the filter output is then
compared with the expected result.

The log files and results are all stored in ./logs; log files as
"*.log", corresponding results as "*.log.dr" and "*.log.ov" for the
two filtering modes.

'''

import os
import six

from drned_xmnr.op import filtering


class FilteringTest(object):
    log_directory = 'logs'
    log_extension = '.log'
    log_overview_ext = '.log.ov'
    log_dred_ext = '.log.dr'

    filter = None

    def filter_test(self, logname):
        logbase = os.path.join(self.log_directory, logname)
        logfile = logbase + self.log_extension
        for level, ext in [('overview', self.log_overview_ext),
                           ('drned-overview', self.log_dred_ext)]:
            out = six.StringIO()
            filtering.run_test_filter(self.__class__.filter, logfile, out=out, level=level)
            with open(logbase + ext) as res:
                assert res.read() == out.getvalue()


class TestTransitions(FilteringTest):
    filter = filtering.transition_output_filter

    def test_trans_nonempty(self):
        self.filter_test('trans-nonempty')

    def test_trans_empty(self):
        self.filter_test('trans-empty')


class TestWalk(FilteringTest):
    filter = filtering.walk_output_filter

    def test_walk(self):
        self.filter_test('walk')

    def test_walkq(self):
        self.filter_test('walkq')

    def test_walk_groups(self):
        self.filter_test('walk-groups')

    def test_walk_failure(self):
        self.filter_test('walk-fail')


class TestExplore(FilteringTest):
    filter = filtering.explore_output_filter

    def test_explore(self):
        self.filter_test('explore')

    def test_expl_groups(self):
        self.filter_test('expl-groups')