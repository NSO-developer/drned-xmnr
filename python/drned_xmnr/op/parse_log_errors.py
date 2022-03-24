from drned_xmnr.namespaces.drned_xmnr_ns import ns

from collections import namedtuple
from os.path import basename

from typing import Callable, List, Optional, TextIO
from ncs.maagic import Node

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
    """ Extract "test-case" name from the input line.
        Lines with some text patterns defined below contain "filename"
        of the actual test case that has been executed by drned-xmnr when
        the parsed error happened.

        Only the last part of the filename (basename) is extraced.
        If no patterns match, None is returned. """
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


class ProblemsParser:
    """ Core problem parsing object. """

    def __init__(self, list_node: Node) -> None:
        """ Initialize parser's matchers with input MAAPI node from CDB
            that defines what patterns to look for in the log file. """
        self.matchers = []
        for item in list_node:
            match_start = item.match
            match_stop = None if item.terminator is None else item.terminator
            max_lines = 0 if item.max_lines is None else item.max_lines
            self.matchers.append(ProblemMatcher(match_start=match_start, match_stop=match_stop, max_lines=max_lines))

    def _get_matcher(self, line: str) -> Optional[ProblemMatcher]:
        """ Try matching the input line against all the setup matchers
            and return the first matching one. """
        for m in self.matchers:
            if m.match_start in line:
                return m
        return None

    def gather_problems(self, file: TextIO) -> List[ProblemData]:
        """ Read through the input file and collect data for all the idetified
            problems found inside. """
        problems: List[ProblemData] = []

        pending = PendingData()

        # BEWARE -> any debug prints in following loop can lead to deadlock
        # in case of log file being parsed is the one logs go into...
        for line_num, line in enumerate(file):
            test_case = parse_test_case(line)
            # new test-case opening
            if test_case is not None:
                if pending.problem is not None:
                    add_new_problem(problems, pending.problem)
                    pending.problem = None
                pending.test_case = test_case
                continue

            # potential start of new problem
            if pending.matcher is None:
                pending.matcher = self._get_matcher(line)
                if pending.matcher is None:
                    # no new problem for this log file line
                    continue
                pending.problem = ProblemData(line_num + 1, pending.matcher.match_start, pending.test_case)
                pending.update_problem(line)
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

        return problems


def _strip_pattern(pattern: str, line: str) -> str:
    """ Strip the text from beginning of the line up to & including
        the pattern. Return whole line if pattern not found. """
    pat_index = line.find(pattern)
    output = line if pat_index == -1 else line[(pat_index + len(pattern)):]
    return output
