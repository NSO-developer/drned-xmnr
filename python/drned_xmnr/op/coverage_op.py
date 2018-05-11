# -*- mode: python; python-indent: 4 -*-

import re
import os
import glob
import operator
import functools
import itertools
from collections import defaultdict
import pickle
import traceback

from ncs import maapi

from . import base_op
from .ex import ActionError


class ResetCoverageOp(base_op.ActionBase):
    action_name = 'reset coverage'

    def perform(self):
        result, _ = self.run_in_drned_env(['make', 'covstart'])
        if result != 0:
            raise ActionError('drned failed')
        return {'success': "Completed successfully"}


class CoverageOp(base_op.ActionBase):
    action_name = 'collect coverage'

    def _init_params(self, params):
        self.patterns = list(params.yang_patterns)

    def collect_data(self, state, stdout):
        if state is None:
            state = []
        state.append(stdout)
        self.progress_fun(state, stdout)
        return state

    def perform(self):
        if self.patterns == []:
            self.patterns = [self.device_modules_pattern()]
        globs = [glob.glob(pattern) for pattern in self.patterns]
        yangfiles = set(functools.reduce(operator.concat, globs, []))
        yangpath = set(os.path.dirname(yf) for yf in yangfiles)
        fnames = ['--fname=' + yang for yang in yangfiles]
        args = ['py.test',
                '-s',
                '--device='+self.dev_name,
                '-k', 'test_coverage',
                '--yangpath='+':'.join(yangpath)]
        result, output = self.run_in_drned_env(args+fnames)
        if result != 0:
            raise ActionError("drned failed")
        self.parse_output(output)
        return {'success': "Completed successfully"}

    def device_modules_pattern(self):
        # FIXME: should we try to lookup device package first?
        return os.path.join(os.getcwd(), 'packages', self.dev_name, 'src', 'yang', '*.yang')

    def parse_output(self, output):
        lines = iter(output.split('\n'))
        expr = ('Found a total of (?P<nodes>[0-9]*) nodes \([0-9]* of type empty\)' +
                ' and (?P<lists>[0-9]*) lists')
        rx = re.compile(expr)
        valrx = re.compile(' *(?P<total>[0-9]*) \( *(?P<percent>[0-9]*)%\) ')
        lines = itertools.dropwhile(lambda line: rx.match(line) is None, lines)
        match = rx.match(lines.next())
        self.covdata = dict(total=match.groupdict(), percents=defaultdict(dict))
        for (cname, value) in [('nodes', 'read-or-set'),
                               ('lists', 'read-or-set'),
                               ('lists', 'deleted'),
                               ('lists', 'multi-read-or-set'),
                               ('nodes', 'set'),
                               ('nodes', 'deleted'),
                               ('nodes', 'set-set'),
                               ('nodes', 'deleted-separately'),
                               ('grouping-nodes', 'read-or-set'),
                               ('grouping-nodes', 'set'),
                               ('grouping-nodes', 'deleted'),
                               ('grouping-nodes', 'set-set'),
                               ('grouping-nodes', 'deleted-separately')]:
            mx = valrx.match(lines.next())
            self.covdata['percents'][cname][value] = mx.groupdict()
        with open(os.path.join(self.dev_test_dir, 'coverage.data'), 'w') as data:
            pickle.dump(self.covdata, data)


class DataHandler(object):
    def __init__(self, log):
        self.log = log

    def get_object(self, tctx, kp, args):
        with maapi.Maapi() as mp:
            trans = mp.attach(tctx)
            dd = DeviceData(args['device'], self.log, trans).get_data()
            mp.detach(tctx)
            return {'drned-xmnr': {'coverage': {'data': dd}}}


class DeviceData(base_op.XmnrBase):
    def __init__(self, dev_name, log, trans):
        super(DeviceData, self).__init__(dev_name, log)
        self._setup_directories(trans)

    def get_data(self):
        try:
            with open(os.path.join(self.dev_test_dir, 'coverage.data')) as data:
                data = pickle.load(data)
                self.log.debug('unpickled data: ', data)
        except Exception as exc:
            self.log.error('Could not load coverage data, "collect" may not have been run')
            self.log.debug(traceback.format_exc(exc))
            return {}
        return {'nodes-total': data['total']['nodes'],
                'lists-total': data['total']['lists'],
                'percents': data['percents']}
