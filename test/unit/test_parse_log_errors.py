'''
parse-log-errors tests based on actual or shortened log data.
'''
from io import StringIO
from typing import NamedTuple

from drned_xmnr.op.parse_log_errors import ProblemsParser  # noqa


class TestParseLog:

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

        pattern1 = '''
<DEBUG> 14-Jan-2022::22:03:01.836 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr:\
- run_outputfun, output len=430
<DEBUG> 14-Jan-2022::22:03:01.838 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr:\
- !! SYNTAX/AUTHORIZATION ERRORS: This configuration failed due to
<DEBUG> 14-Jan-2022::22:03:01.844 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr:\
- !!    permissions to use the commands.
<DEBUG> 14-Jan-2022::22:03:02.867 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr:\
- MATCHED 'None', SEND: 'exit' -> NEXT_STATE: 'exit-done'
<DEBUG> 14-Jan-2022::22:03:02.868 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr:\
- >>>> "exit" >>>>
<DEBUG> 14-Jan-2022::22:03:02.899 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr:\
- run_outputfun, output len=71
'''

        pattern2 = '''
<DEBUG> 15-Jan-2022::17:14:45.523 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-4-usid-305-drned-xmnr:\
- converting /interop1.xml
<DEBUG> 18-Jan-2022::17:14:46.486 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-5-usid-1236-drned-xmnr:\
-     pytest.fail("Failed to restore default config.")
<DEBUG> 18-Jan-2022::17:14:46.487 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-5-usid-1236-drned-xmnr:\
- E   Failed: Failed to restore default config.
<DEBUG> 18-Jan-2022::17:14:46.488 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-5-usid-1236-drned-xmnr:\
- =================================== FAILURES
'''

        pattern3 = '''
<DEBUG> 20-Jan-2022::17:30:43.574 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-4-usid-305-drned-xmnr:\
- converting /interop2.xml
<DEBUG> 20-Jan-2022::14:31:58.55 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
-     raise Failed(msg=msg, pytrace=pytrace)
<DEBUG> 20-Jan-2022::14:31:58.56 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   Failed: Did not expect "
<DEBUG> 20-Jan-2022::14:31:58.85 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   +                                }
<DEBUG> 20-Jan-2022::14:31:58.92 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E    }
<DEBUG> 20-Jan-2022::14:31:58.93 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
-
<DEBUG> 20-Jan-2022::14:31:58.93 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- During handling of the above exception, another exception occurred:
'''

        pattern4 = '''
<DEBUG> 18-Jan-2022::16:57:24.569 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-5-usid-1236-drned-xmnr:\
- Tue Jan  18 16:57:22.839 UTC+00:00
<DEBUG> 18-Jan-2022::16:57:24.570 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-5-usid-1236-drned-xmnr:\
- sync-from failed: dummy text
<DEBUG> 18-Jan-2022::16:57:24.573 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-5-usid-1236-drned-xmnr:\
- run_outputfun, output len=34
'''

        pattern5 = '''
<DEBUG> 18-Jan-2022::16:57:24.569 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-5-usid-1236-drned-xmnr:\
- Tue Jan  18 16:57:22.839 UTC+00:00
<DEBUG> 18-Jan-2022::16:57:24.570 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-5-usid-1236-drned-xmnr:\
- Aborted: RPC error towards nc0: data_missing: ns1:ethernet/ns1:sla/ns1:profiles/ns1:profile[profile-name\
= 'FOO']/ns1:probe/ns1:send/ns1:packet/ns1:once
<DEBUG> 18-Jan-2022::16:57:24.573 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-5-usid-1236-drned-xmnr:\
- run_outputfun, output len=34
'''

        pattern6 = '''
<DEBUG> 18-Jan-2022::16:57:24.569 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-5-usid-1236-drned-xmnr:\
- Tue Jan  18 16:57:22.839 UTC+00:00
<DEBUG> 18-Jan-2022::16:57:24.570 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-5-usid-1236-drned-xmnr:\
- No problme: no error
<DEBUG> 18-Jan-2022::16:57:24.573 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-5-usid-1236-drned-xmnr:\
- run_outputfun, output len=34
'''

        for p in [pattern1, pattern2, pattern3, pattern4, pattern5]:
            problems = parser.gather_problems(StringIO(p))
            assert len(problems) == 1

        problems = parser.gather_problems(StringIO(pattern6))
        assert len(problems) == 0

        pattern7 = '''
<DEBUG> 15-Jan-2022::17:14:45.523 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-4-usid-305-drned-xmnr:\
- converting /interop1.xml
<DEBUG> 18-Jan-2022::17:14:46.486 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-5-usid-1236-drned-xmnr:\
-     pytest.fail("Failed to restore default config.")
<DEBUG> 18-Jan-2022::17:14:46.487 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-5-usid-1236-drned-xmnr:\
- E   Failed: Failed to restore default config.
<DEBUG> 18-Jan-2022::17:14:46.488 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-5-usid-1236-drned-xmnr:\
- =================================== FAILURES
<DEBUG> 20-Jan-2022::17:14:47.55 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
-     raise Failed(msg=msg, pytrace=pytrace)
<DEBUG> 20-Jan-2022::17:15:43.574 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-4-usid-305-drned-xmnr:\
- converting /interop2.xml
<DEBUG> 20-Jan-2022::14:31:58.56 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   Failed: Did not expect "
<DEBUG> 20-Jan-2022::14:31:58.92 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E    }
'''
        problems = parser.gather_problems(StringIO(pattern7))
        assert len(problems) == 2

        problems = parser.gather_problems(StringIO(
            pattern1 + pattern2 + pattern3 + pattern4 + pattern5 + pattern6 + pattern7))
        assert len(problems) == 7
