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

from __future__ import print_function

import os
import six

from drned_xmnr.op import filtering
from drned_xmnr.op.filtering.states import TransitionDesc


class FilteringTest(object):
    log_directory = 'logs'
    log_extension = '.log'
    log_overview_ext = '.log.ov'
    log_dred_ext = '.log.dr'
    log_data_ext = '.data'

    filter = None

    def filter_test(self, logname):
        logbase = os.path.join(self.log_directory, logname)
        logfile = logbase + self.log_extension
        with open(logbase + self.log_data_ext) as data:
            events = eval(data.read())
        for level, ext in [('overview', self.log_overview_ext),
                           ('drned-overview', self.log_dred_ext)]:
            out = six.StringIO()
            ctx = filtering.run_test_filter(self.filter, logfile, out=out, level=level)
            with open(logbase + ext) as res:
                assert out.getvalue() == res.read()
            assert(ctx.test_events == events)


class TestTransitions(FilteringTest):
    @staticmethod
    def filter(*args):
        return filtering.transition_output_filter(*args)

    def test_trans_nonempty(self):
        self.filter_test('trans-nonempty')

    def test_trans_empty(self):
        self.filter_test('trans-empty')


class TestWalk(FilteringTest):
    @staticmethod
    def filter(*args):
        return filtering.walk_output_filter(*args)

    def test_walk(self):
        self.filter_test('walk')

    def test_walkq(self):
        self.filter_test('walkq')

    def test_walk_groups(self):
        self.filter_test('walk-groups')

    def test_walk_failure(self):
        self.filter_test('walk-fail')


class TestExplore(FilteringTest):
    @staticmethod
    def filter(*args):
        return filtering.explore_output_filter(*args)

    def test_explore(self):
        self.filter_test('explore')

    def test_expl_groups(self):
        self.filter_test('expl-groups')

    def test_expl_commit_failure(self):
        self.filter_test('explore-commitfail')
