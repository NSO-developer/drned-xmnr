'''
parse-log-errors tests based on actual or shortened log data.
'''
import os
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
<DEBUG> 14-Jan-2022::22:03:01.839 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr:\
- !! one or more of the following reasons:
<DEBUG> 14-Jan-2022::22:03:01.840 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr:\
- !!  - the entered commands do not exist,
<DEBUG> 14-Jan-2022::22:03:01.841 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr:\
- !!  - the entered commands have errors in their syntax,
<DEBUG> 14-Jan-2022::22:03:01.842 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr:\
- !!  - the software packages containing the commands are not active,
<DEBUG> 14-Jan-2022::22:03:01.843 drned-xmnr ncs-dp-68-drned-xmnr:drned_xmnr-1-usid-62-drned-xmnr:\
- !!  - the current user is not a member of a task-group that has
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
<DEBUG> 20-Jan-2022::14:31:58.57 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   diff" in:
<DEBUG> 20-Jan-2022::14:31:58.59 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   devices device nc0 compare-config
<DEBUG> 20-Jan-2022::14:31:58.60 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   Thu Jan  20 14:31:28.211 UTC+00:00
<DEBUG> 20-Jan-2022::14:31:58.61 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   diff
<DEBUG> 20-Jan-2022::14:31:58.62 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E    devices {
<DEBUG> 20-Jan-2022::14:31:58.63 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E        device nc0 {
<DEBUG> 20-Jan-2022::14:31:58.64 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E            config {
<DEBUG> 20-Jan-2022::14:31:58.65 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E                Cisco-IOS-XR-um-aaa-cfg:aaa {
<DEBUG> 20-Jan-2022::14:31:58.65 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E                    accounting {
<DEBUG> 20-Jan-2022::14:31:58.66 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E                        exec {
<DEBUG> 20-Jan-2022::14:31:58.67 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   +                        accounting-list default {
<DEBUG> 20-Jan-2022::14:31:58.68 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   +                            start-stop {
<DEBUG> 20-Jan-2022::14:31:58.69 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   +                            }
<DEBUG> 20-Jan-2022::14:31:58.70 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   +                            groups {
<DEBUG> 20-Jan-2022::14:31:58.71 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   +                                group-1 {
<DEBUG> 20-Jan-2022::14:31:58.71 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   +                                    tacacs {
<DEBUG> 20-Jan-2022::14:31:58.72 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   +                                    }
<DEBUG> 20-Jan-2022::14:31:58.73 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   +                                }
<DEBUG> 20-Jan-2022::14:31:58.74 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   +                            }
<DEBUG> 20-Jan-2022::14:31:58.75 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   +                        }
<DEBUG> 20-Jan-2022::14:31:58.76 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E                        }
<DEBUG> 20-Jan-2022::14:31:58.76 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E                        commands {
<DEBUG> 20-Jan-2022::14:31:58.79 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   +                        accounting-list default {
<DEBUG> 20-Jan-2022::14:31:58.80 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   +                            start-stop {
<DEBUG> 20-Jan-2022::14:31:58.81 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   +                            }
<DEBUG> 20-Jan-2022::14:31:58.82 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   +                            groups {
<DEBUG> 20-Jan-2022::14:31:58.82 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   +                                group-1 {
<DEBUG> 20-Jan-2022::14:31:58.84 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   +                                    tacacs {
<DEBUG> 20-Jan-2022::14:31:58.84 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   +                                    }
<DEBUG> 20-Jan-2022::14:31:58.85 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   +                                }
<DEBUG> 20-Jan-2022::14:31:58.86 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   +                            }
<DEBUG> 20-Jan-2022::14:31:58.87 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E   +                        }
<DEBUG> 20-Jan-2022::14:31:58.88 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E                        }
<DEBUG> 20-Jan-2022::14:31:58.89 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E                    }
<DEBUG> 20-Jan-2022::14:31:58.89 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E                }
<DEBUG> 20-Jan-2022::14:31:58.90 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E            }
<DEBUG> 20-Jan-2022::14:31:58.91 drned-xmnr ncs-dp-58-drned-xmnr:drned_xmnr-3-usid-65-drned-xmnr:\
- E        }
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

        file = open(os.path.join(os.path.dirname(__file__), 'testdata/') + "ncs-python-vm-drned-xmnr.log")
        problems = parser.gather_problems(file)
        assert len(problems) == 69
