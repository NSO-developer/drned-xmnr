import re
import os
import glob
import operator
import functools
import itertools
from collections import defaultdict
import pickle
import traceback

from . import base_op
from .ex import ActionError


from .common_op import Handler

from typing import Any, Dict, List, Sequence
from drned_xmnr.typing_xmnr import ActionResult, Tctx
from ncs import maagic
from ncs.maagic import Node
from ncs.maapi import Transaction
from ncs.log import Log


class ResetCoverageOp(base_op.ActionBase):
    action_name = 'reset coverage'

    def perform(self) -> ActionResult:
        result, _ = self.run_in_drned_env(['make', 'covstart'])
        if result != 0:
            raise ActionError('drned failed')
        return {'success': "Completed successfully"}


class CoverageOp(base_op.ActionBase):
    action_name = 'collect coverage'

    def _init_params(self, params: Node) -> None:
        self.patterns: List[str] = list(params.yang_patterns)

    def cli_filter(self, msg: str) -> None:
        # no output from DrNED should be passed to CLI
        return

    def perform(self) -> ActionResult:
        if self.patterns == []:
            self.patterns = [self.device_modules_pattern()]
        globs = [glob.glob(pattern) for pattern in self.patterns]
        reduced: Sequence[str] = functools.reduce(operator.concat, globs, [])
        yangfiles = set(reduced)
        yangpath = set(os.path.dirname(yf) for yf in yangfiles)
        fnames = ['--fname=' + yang for yang in yangfiles]
        args = [self.pytest_executable(),
                '-s',
                '--device=' + self.dev_name,
                '-k', 'test_coverage',
                '--yangpath=' + ':'.join(yangpath)]
        result, output = self.run_in_drned_env(args + fnames)
        if result != 0:
            raise ActionError("drned failed; 'coverage reset' might be needed")
        self.parse_output(output)
        return {'success': "Completed successfully"}

    def device_package_name(self, trans: Transaction) -> str:
        root = maagic.get_root(trans)
        devtype = root.devices.device[self.dev_name].device_type
        if devtype.ne_type != 'netconf':
            raise ActionError('Non-netconf device; yang-patterns must be provided for collect')
        ned_id = devtype.netconf.ned_id
        for package in root.packages.package:
            for component in package.component:
                try:
                    if component.ned.netconf.ned_id == ned_id:
                        # package.directory is something like state/packages-in-use/nedname
                        return str(os.path.basename(package.directory))
                except AttributeError:
                    continue
        raise ActionError('NED package could not be found; '
                          'yang-patterns must be provided for collect')

    def device_modules_pattern(self) -> str:
        pkg_name = self.run_with_trans(self.device_package_name)
        if pkg_name is not None:
            return os.path.join(os.getcwd(), 'packages', pkg_name, 'src', 'yang', '*.yang')
        return ''

    def parse_output(self, output: str) -> None:
        lines = iter(output.split('\n'))
        expr = (r'Found a total of (?P<nodes>[0-9]*) nodes \([0-9]* of type empty\)'
                + ' and (?P<lists>[0-9]*) lists')
        rx = re.compile(expr)
        valrx = re.compile(r' *(?P<total>[0-9]*) \( *(?P<percent>[0-9]*)%\) ')
        lines = itertools.dropwhile(lambda line: rx.match(line) is None, lines)
        match = rx.match(next(lines))
        if match is None:
            raise ActionError("Invalid input coverage data")
        self.covdata: Dict[str, Any] = dict(total={k: int(v) for (k, v) in match.groupdict().items()},
                                            percents=defaultdict(dict))
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
            mx = valrx.match(next(lines))
            if mx is None:
                raise ActionError("Invalid input coverage data")
            self.covdata['percents'][cname][value] = {k: int(v)
                                                      for (k, v) in mx.groupdict().items()}
        with open(os.path.join(self.dev_test_dir, 'coverage.data'), 'wb') as data:
            pickle.dump(self.covdata, data, protocol=2)


class DataHandler(Handler):
    def __init__(self, log: Log) -> None:
        self.log = log

    def get_object(self, tctx: Tctx, kp: str, args: Dict[str, Any]) -> Dict[str, Any]:
        dd = DeviceData.get_data(tctx, args['device'], self.log, DeviceData.get_coverage_data)
        return {'drned-xmnr': {'coverage': {'data': dd}}}


class DeviceData(base_op.XmnrDeviceData):
    def get_coverage_data(self) -> Dict[str, Any]:
        try:
            with open(os.path.join(self.dev_test_dir, 'coverage.data'), 'rb') as datafile:
                # pickle.load() causes problems on some platforms
                data = pickle.loads(datafile.read())
                self.log.debug('unpickled data: ', data)
        except Exception as exc:
            self.log.error('Could not load coverage data, "collect" may not have been run', exc)
            self.log.debug(traceback.format_exc())
            return {}
        return {'nodes-total': data['total']['nodes'],
                'lists-total': data['total']['lists'],
                'percents': data['percents']}
