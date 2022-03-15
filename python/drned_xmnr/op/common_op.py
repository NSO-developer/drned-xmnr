import os
import re

from _ncs import OPERATIONAL
from ncs import maagic

from datetime import datetime

from drned_xmnr.namespaces.drned_xmnr_ns import ns

from .base_op import ActionBase
from .base_op import maapi_keyless_create
from .ex import ActionError
from .parse_log_errors import ProblemData, gather_problems

from abc import abstractmethod
from typing import Any, Dict, List, Optional, TypeVar
from drned_xmnr.typing_xmnr import ActionResult, Tctx
from ncs.maagic import Node
from ncs.maapi import Transaction


class DevcliLogMatch(object):
    """Common matching of Devcli messages.

    Can be extended for more specific purposes; extending classess
    should call the `match` method of this class.

    """
    matchexpr = (
        r'(?:(?P<devcli>.*DevcliException: No device definition found)'
        r'|(?P<traceback>Traceback [(]most recent call last[)]:)'
        r'|(?P<newstate>^STATE: (?P<state>[^ ]*) : .*)'
        r'|(?P<match>^MATCHED \'(?P<matchstate>.*)\', SEND: .*)'
        r'|(?P<closed>device communication failure: .*EOF.*)'
        r'|(?P<timeout>device communication failure: .*Timeout.*)'
        r'|(?P<pytestfail>DrNED thrown a pytest failure)'
        r'|(?P<authfailed>failed to authenticate)'
        r')$')
    matchrx = re.compile(matchexpr)

    def __init__(self) -> None:
        self.waitstate: Optional[str] = None
        self.devcli_error: Optional[str] = None

    def match(self, msg: str) -> Optional[str]:
        match = DevcliLogMatch.matchrx.match(msg)
        if match is None:
            return None
        if match.lastgroup == 'traceback':
            self.devcli_error = 'the device driver appears to be broken'
            return 'device driver failed'
        elif match.lastgroup == 'newstate':
            self.waitstate = match.groupdict()['state']
            return None
        elif match.lastgroup == 'match':
            self.waitstate = None
            return None
        elif match.lastgroup == 'closed':
            self.devcli_error = 'connection closed'
            return 'Could not connect to the device or device connection closed'
        elif match.lastgroup == 'timeout':
            self.devcli_error = 'device communication timeout'
            return 'Device communication timeout'
        elif match.lastgroup == 'pytestfail':
            # that can be a multitude of reasons
            self.devcli_error = 'device communication failure'
            return 'Device communication failure'
        elif match.lastgroup == 'authfailed':
            self.devcli_error = 'failed to authenticate'
            return 'Failed to authenticate to the device CLI'
        return None


class LoadDefaultConfigOp(ActionBase):
    """ Action handler used to "reset" device configuration to a default by
        loading specified device CLI configuration file from the filesystem
        of a device.
    """
    action_name = 'xmnr load-default-config'

    def __init__(self, *args: Any) -> None:
        super(LoadDefaultConfigOp, self).__init__(*args)
        self.filter = DevcliLogMatch()

    def cli_filter(self, msg: str) -> None:
        report = self.filter.match(msg)
        if report is not None:
            super(LoadDefaultConfigOp, self).cli_filter(report + '\n')

    def perform(self) -> ActionResult:
        result, _ = self.devcli_run('load-default-config.py', [])
        if result != 0:
            raise ActionError('Failed to load default configuration!')

        if self.filter.devcli_error is None:
            return {'success': 'Loaded initial config.'}
        return {'failure': 'Device driver failed.'}


class SaveDefaultConfigOp(ActionBase):
    """ Action handler used to save/create default device configuration
        by saving running configuration to the filesystem of the device.
    """
    action_name = 'xmnr save-default-config'

    def __init__(self, *args: Any) -> None:
        super(SaveDefaultConfigOp, self).__init__(*args)
        self.filter = DevcliLogMatch()

    def cli_filter(self, msg: str) -> None:
        report = self.filter.match(msg)
        if report is not None:
            super(SaveDefaultConfigOp, self).cli_filter(report + '\n')

    def perform(self) -> ActionResult:
        result, _ = self.devcli_run('save-default-config.py', [])
        if result != 0:
            raise ActionError('Failed to save default configuration!')

        if self.filter.devcli_error is None:
            return {'success': 'Saved initial config.'}
        return {'failure': 'Could not save config.'}


class ParseLogErrorsOp(ActionBase):
    """ Action handler used to parse and print errors from drned-xmnr logfiles.
    """
    action_name = 'xmnr parse-log-errors'

    def _init_params(self, params: Node) -> None:
        self.target_log = self.param_default(params, "target_log", None)

    def perform(self) -> ActionResult:
        self.parsed_problems: Optional[List[ProblemData]] = None
        try:
            filepath = self._get_target_filepath()
            with open(filepath, 'r', newline='\n') as logfile:
                self.parsed_problems = gather_problems(logfile)
        except OSError as ose:
            # TODO - do not reveal potential filepath attempted?
            msg = "Couldn't read target log file: {0}".format(os.strerror(ose.errno))
            raise ActionError(msg)
        return self.run_with_trans(self._store_parsed_problems, write=True, db=OPERATIONAL)

    def _store_parsed_problems(self, trans: Transaction) -> ActionResult:
        problems_count = self._store_problems(trans)
        return {'success': 'Target %s parsed - %d problems found.' % (self.target_log, problems_count)}

    def _get_target_filepath(self) -> str:
        tag = self.target_log
        if tag == ns.drned_xmnr_common_xmnr_log:
            path = os.path.join(
                os.getcwd(), 'logs', 'ncs-python-vm-drned-xmnr.log'
            )
        elif tag == ns.drned_xmnr_device_trace:
            path = os.path.join(
                # self.dev_test_dir,
                os.getcwd(), 'logs',
                'netconf-' + self.dev_name + '.trace'
            )
        else:
            raise ActionError("Unimplemented target log...")
        return path

    def _store_problems(self, trans: Transaction) -> int:
        if self.parsed_problems is None:
            return 0
        problem_count = len(self.parsed_problems)

        # clean up previously stored problems
        root = maagic.get_root(trans)
        device_xmnr_node = root.devices.device[self.dev_name].drned_xmnr
        problems_node = device_xmnr_node.parsed_problems
        problems_node.problems.delete()
        problems_node.target_log = self.target_log
        problems_node.parse_time = datetime.now()

        # and push new ones into CDB
        problem_list = problems_node.problems
        for problem in self.parsed_problems:
            problem_instance = problem_list.create(problem.line_num)
            problem_instance.phase = problem.phase
            problem_instance.test_case = problem.test_case
            if problem.time is not None:
                problem_instance.time = problem.time
            for (j, line) in enumerate(problem.lines):
                line_instance = maapi_keyless_create(problem_instance.message_lines, j)
                line_instance.line = line.rstrip()
        problems_node.count = problem_count

        trans.apply()
        return problem_count


NextType = TypeVar('NextType')


class Handler:
    ''' Stub data provider handler.
        See documentation of ncs.experimental.DataCallbacks for details.
    '''

    @abstractmethod
    def get_object(self, tctx: Tctx, kp: str, args: Dict[str, Any]) -> Dict[str, Any]:
        ...

    @abstractmethod
    def get_next(self, tctx: Tctx, kp: str, args: Dict[str, Any], next: NextType) -> Optional[NextType]:
        ...

    @abstractmethod
    def count(self) -> int:
        ...
