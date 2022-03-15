'''
parse-log-errors tests based on actual or shortened log data.
'''
from io import StringIO
from typing import NamedTuple

from drned_xmnr.op.parse_log_errors import ProblemsParser  # noqa


class TestParseLog:
    @staticmethod
    def prepare(*args):
        # TODO
        return None

    def test_parse_error_log(self):
        # dataclass would be better, but not in python 3.6
        class ErrorPattern(NamedTuple):
            match: str
            terminator: str
            max_lines: int

        pattern_list = [
            ErrorPattern(match=" !! ", terminator=">>>> \"exit\" >>>>",
                         max_lines=100),
            ErrorPattern(match="E  ", terminator=None, max_lines=None),
            ErrorPattern(match="sync-from failed:", terminator=None,
                         max_lines=None),
            ErrorPattern(match="Aborted: RPC error", terminator=None,
                         max_lines=None),
        ]
        parser = ProblemsParser(pattern_list)

        fileSz = StringIO(
            '''
            <DEBUG> 14-Jan-2022::22:03:00.114 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - 5 items committed in 4 sec (1)items/sec
<DEBUG> 14-Jan-2022::22:03:01.93 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - run_outputfun, output len=37
<DEBUG> 14-Jan-2022::22:03:01.95 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - Updating.
<DEBUG> 14-Jan-2022::22:03:01.96 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - Updated Commit database in 1 sec 
<DEBUG> 14-Jan-2022::22:03:01.177 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - run_outputfun, output len=76
<DEBUG> 14-Jan-2022::22:03:01.179 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - RP/0/RSP0/CPU0:ios#show configuration failed
<DEBUG> 14-Jan-2022::22:03:01.180 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - 
Fri Jan 14 22:03:00.823 UTC
<DEBUG> 14-Jan-2022::22:03:01.836 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - run_outputfun, output len=430
<DEBUG> 14-Jan-2022::22:03:01.838 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - !! SYNTAX/AUTHORIZATION ERRORS: This configuration failed due to
<DEBUG> 14-Jan-2022::22:03:01.839 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - !! one or more of the following reasons:
<DEBUG> 14-Jan-2022::22:03:01.840 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - !!  - the entered commands do not exist,
<DEBUG> 14-Jan-2022::22:03:01.841 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - !!  - the entered commands have errors in their syntax,
<DEBUG> 14-Jan-2022::22:03:01.842 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - !!  - the software packages containing the commands are not active,
<DEBUG> 14-Jan-2022::22:03:01.843 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - !!  - the current user is not a member of a task-group that has 
<DEBUG> 14-Jan-2022::22:03:01.844 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - !!    permissions to use the commands.
<DEBUG> 14-Jan-2022::22:03:01.844 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - 
<DEBUG> 14-Jan-2022::22:03:01.845 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - controller Optics0/0/0/10
<DEBUG> 14-Jan-2022::22:03:01.846 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: -  breakout 1x100
<DEBUG> 14-Jan-2022::22:03:01.846 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - 
<DEBUG> 14-Jan-2022::22:03:02.847 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - run_outputfun, output len=19
<DEBUG> 14-Jan-2022::22:03:02.848 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - run_outputfun, output len=892
<DEBUG> 14-Jan-2022::22:03:02.850 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - RP/0/RSP0/CPU0:ios#<<<< 1:" to view the errors.
<DEBUG> 14-Jan-2022::22:03:02.851 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - Committing.
<DEBUG> 14-Jan-2022::22:03:02.852 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - Prepared commit in 0 sec
<DEBUG> 14-Jan-2022::22:03:02.853 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - show configuration failed
<DEBUG> 14-Jan-2022::22:03:02.854 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - ...
<DEBUG> 14-Jan-2022::22:03:02.854 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - 5 items committed in 4 sec (1)items/sec
<DEBUG> 14-Jan-2022::22:03:02.855 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - Updating.
<DEBUG> 14-Jan-2022::22:03:02.855 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - Updated Commit database in 1 sec 
<DEBUG> 14-Jan-2022::22:03:02.856 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - RP/0/RSP0/CPU0:ios#show configuration failed
<DEBUG> 14-Jan-2022::22:03:02.857 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - 
Fri Jan 14 22:03:00.823 UTC
<DEBUG> 14-Jan-2022::22:03:02.858 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - !! SYNTAX/AUTHORIZATION ERRORS: This configuration failed due to
<DEBUG> 14-Jan-2022::22:03:02.858 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - !! one or more of the following reasons:
<DEBUG> 14-Jan-2022::22:03:02.859 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - !!  - the entered commands do not exist,
<DEBUG> 14-Jan-2022::22:03:02.860 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - !!  - the entered commands have errors in their syntax,
<DEBUG> 14-Jan-2022::22:03:02.860 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - !!  - the software packages containing the commands are not active,
<DEBUG> 14-Jan-2022::22:03:02.861 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - !!  - the current user is not a member of a task-group that has 
<DEBUG> 14-Jan-2022::22:03:02.862 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - !!    permissions to use the commands.
<DEBUG> 14-Jan-2022::22:03:02.862 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - 
<DEBUG> 14-Jan-2022::22:03:02.863 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - controller Optics0/0/0/10
<DEBUG> 14-Jan-2022::22:03:02.864 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: -  breakout 1x100
<DEBUG> 14-Jan-2022::22:03:02.864 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - 
<DEBUG> 14-Jan-2022::22:03:02.865 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - RP/0/RSP0/CPU0:ios#" <<<<
<DEBUG> 14-Jan-2022::22:03:02.866 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - MATCHED '^.+?# ?$', SEND: 'None' -> NEXT_STATE: 'done'
<DEBUG> 14-Jan-2022::22:03:02.866 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - STATE: exit : [(None, 'exit', 'exit-done')]
<DEBUG> 14-Jan-2022::22:03:02.867 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - MATCHED 'None', SEND: 'exit' -> NEXT_STATE: 'exit-done'
<DEBUG> 14-Jan-2022::22:03:02.868 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - >>>> "exit" >>>>
<DEBUG> 14-Jan-2022::22:03:02.899 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - run_outputfun, output len=71
<DEBUG> 14-Jan-2022::22:03:02.900 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr: - exit
            '''
        )

        file = open("testdata/ncs-python-vm-drned-xmnr.log")
        problems = parser.gather_problems(file)
        assert len(problems) == 69
