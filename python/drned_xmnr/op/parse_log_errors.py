from drned_xmnr.namespaces.drned_xmnr_ns import ns

from collections import namedtuple
from os.path import basename

from typing import Callable, List, Optional, TextIO

TimeParser = Callable[[str], Optional[str]]


def _common_time_parser(x: str) -> Optional[str]:
    s = x.split()
    if len(s) > 1:
        return s[1]
    return None


class ProblemMatcher:
    def __init__(self,
                 match_start: str,
                 match_stop: Optional[str] = None,
                 time_parser: Optional[TimeParser] = _common_time_parser,
                 max_lines: int = 0
                 ) -> None:
        self.match_start = match_start
        self.match_stop = match_stop
        self.time_parser = time_parser
        self.max_lines = max_lines

    def is_stop_line(self, line: str) -> bool:
        if self.match_stop is None:
            return False
        return (self.match_stop in line)

    def __str__(self) -> str:
        from pprint import pformat
        return pformat(vars(self))


PROBLEM_MATCHERS = [
    ProblemMatcher(match_start=" !! ", match_stop=">>>> \"exit\" >>>>", max_lines=100),
    ProblemMatcher(match_start="E  "),
    ProblemMatcher(match_start="sync-from failed:"),
    ProblemMatcher(match_start="Aborted: RPC error"),
]


def _get_matcher(line: str) -> Optional[ProblemMatcher]:
    for m in PROBLEM_MATCHERS:
        if m.match_start in line:
            return m
    return None


TestCase = namedtuple('TestCase', ['phase', 'name'])


class ProblemData:
    """ All the data describing single instance of problem
        parsed from the log lines. """
    def __init__(self, line_num: int, match_start: str, test_case: Optional[TestCase]) -> None:
        self.line_num = line_num
        self.match_start = match_start
        self.phase = None if test_case is None else test_case.phase
        self.test_case = "----unknown----" if test_case is None else str(test_case.name)
        self.time: Optional[str] = None
        self.lines: List[str] = []


def parse_test_case(line: str) -> Optional[TestCase]:
    pattern = " converting "
    if pattern in line:
        return TestCase(phase=ns.drned_xmnr_conversion_, name=basename(_strip_pattern(pattern, line).split()[0]))

    pattern = "py.test -k"
    if pattern in line:
        sub_pattern = "test_template_set"
        if sub_pattern in line:
            fname = basename(_strip_pattern("--fname=", line).split()[0])
            return TestCase(phase=ns.drned_xmnr_test_, name=fname)
        return TestCase(phase=ns.drned_xmnr_test_, name=basename(_strip_pattern(pattern, line).split()[0]))

    return None


class PendingData:
    """ Keeps track of pending multi-line structure of file,
        last observed test-case id, problem, etc. """
    def __init__(self) -> None:
        self.test_case: Optional[TestCase] = None
        self.matcher: Optional[ProblemMatcher] = None
        self.problem: Optional[ProblemData] = None

    def update_problem(self, line: str, pending: bool = False) -> None:
        """ Add the input line to pending problem data. """
        if self.matcher is None or self.problem is None:
            return
        time_parser = self.matcher.time_parser
        self.problem.time = None if time_parser is None else time_parser(line)
        pattern = ' - '  # if pending else self.matcher.match_start
        self.problem.lines.append(_strip_pattern(pattern, line))
        if self.matcher.max_lines > 0 and len(self.problem.lines) > self.matcher.max_lines:
            del self.problem.lines[0]


def do_merge_problems(problems: List[ProblemData], problem: ProblemData) -> bool:
    """ Check whether we want to merge pending problem to the last one stored.
        (sometimes wrong EOLs split the error lines unexpectedly) """
    if len(problems) < 1:
        return False
    last_problem = problems[-1]
    if last_problem.match_start != problem.match_start:
        return False
    if last_problem.test_case != problem.test_case:
        return False
    if last_problem.phase != problem.phase:
        return False
    return True


def add_new_problem(problems: List[ProblemData], problem: ProblemData) -> None:
    """ Add the problem into resulting list - either as standalone record,
        or merged into the last/previous one in case of mutual relation. """
    if do_merge_problems(problems, problem):
        problems[-1].lines += problem.lines
    else:
        problems.append(problem)


# logger: List[str],
def gather_problems(file: TextIO) -> List[ProblemData]:
    """ Read through the input file and collect data for all the idetified
        problems found inside. """
    problems: List[ProblemData] = []

    pending = PendingData()

    for line_num, line in enumerate(file):
        test_case = parse_test_case(line)
        # new test-case opening
        if test_case is not None:
            if pending.problem is not None:
                add_new_problem(problems, pending.problem)
                pending.problem = None
            pending.test_case = test_case
            # logger.append("---- new test-case: line %d: %s" % (line_num + 1, test_case))
            continue

        # potential start of new problem
        if pending.matcher is None:
            pending.matcher = _get_matcher(line)
            if pending.matcher is None:
                # no new problem for this log file line
                continue
            pending.problem = ProblemData(line_num + 1, pending.matcher.match_start, pending.test_case)
            pending.update_problem(line)
            # logger.append("---- new problem on line: %d" % (line_num))
            continue

        # pending matcher with end pattern
        if pending.matcher.match_stop is not None:
            if pending.matcher.is_stop_line(line):
                if pending.problem is not None:
                    problems.append(pending.problem)
                    pending.problem = None
                pending.matcher = None
            else:
                pending.update_problem(line, pending=True)
            continue

        # pending exact matcher (no end pattern)
        if pending.matcher.match_start in line:
            pending.update_problem(line)
        # shorctut - two different matches cannot run in sequence with no separation
        else:
            if pending.problem is not None:
                add_new_problem(problems, pending.problem)
                pending.problem = None
            pending.matcher = None
        # logger.append("---- normal line: %s" % (line))

    return problems


def _strip_pattern(pattern: str, line: str) -> str:
    pat_index = line.find(pattern)
    pat_len = len(pattern)
    return line[(pat_index + pat_len):]
