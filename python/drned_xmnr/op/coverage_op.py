# -*- mode: python; python-indent: 4 -*-

import re
import os
import glob
import operator
import functools
import itertools

from . import base_op
from .ex import ActionError


class ResetCoverageOp(base_op.BaseOp):
    def perform(self):
        result, _ = self.run_in_drned_env(['make', 'covstart'])
        if result != 0:
            raise ActionError('drned failed')
        return {'success': "Completed successfully"}


class CoverageOp(base_op.BaseOp):
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
        args = ['py.test', '-s', '--device='+self.dev_name, '-k', 'test_coverage',
                '--yangpath='+':'.join(yangpath)]
        result, output = self.run_in_drned_env(args+fnames)
        if result != 0:
            raise ActionError("drned failed")
        return {'success': "Completed successfully"}

    def device_modules_pattern(self):
        # FIXME: should we try to lookup device package first?
        return os.path.join(os.getcwd(), 'packages', self.dev_name, 'src', 'yang', '*.yang')
