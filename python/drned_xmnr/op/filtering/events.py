'''DrNED output events.

Instances of the class `LineOutputEvent` are generated for important
DrNED output lines.  They are passed to a simple pushdown automaton
that takes care of generating filtered output and transition events.
'''

import re
from .cort import coroutine

from typing import Generator, Pattern
from drned_xmnr.typing_xmnr import StrConsumer


class LineOutputEvent(object):
    indent = 3 * ' '
    state_name_regexp: Pattern[str] = re.compile(r'.*/states/([^/]*?)(?:\.state)?\.(cfg|xml)')

    @staticmethod
    def indent_line(line: str) -> str:
        return '{}{}'.format(LineOutputEvent.indent, line)

    def __init__(self, line: str) -> None:
        self.line = line
        self.complete = False

    def __str__(self) -> str:
        return 'Line event {} {}'.format(self.__class__.__name__, self.line)

    def mark_complete(self) -> None:
        self.complete = True

    def produce_line(self) -> str:
        return self.line


EventConsumer = Generator[None, LineOutputEvent, None]


class InitialPrepareEvent(LineOutputEvent):
    def __init__(self) -> None:
        super(InitialPrepareEvent, self).__init__('Prepare the device')


class InitStatesEvent(LineOutputEvent):
    pass


class StartStateEvent(LineOutputEvent):
    def __init__(self, line: str, state: str) -> None:
        super(StartStateEvent, self).__init__(line)
        self.state = state


class TransitionEvent(LineOutputEvent):
    pass


class InitFailedEvent(LineOutputEvent):
    pass


class TransFailedEvent(LineOutputEvent):
    pass


class PyTestEvent(LineOutputEvent):
    def produce_line(self) -> str:
        s = self.state_name_regexp.search(self.line)
        if s is None:
            raise Exception("Invalid PyTestEvent")
        state = s.groups()[0]
        return 'Test transition to {}'.format(state)


class DrnedPrepareEvent(LineOutputEvent):
    def __init__(self) -> None:
        super(DrnedPrepareEvent, self).__init__('')

    def produce_line(self) -> str:
        return self.indent_line('prepare the device')


class DrnedEvent(LineOutputEvent):
    pass


class DrnedActionEvent(DrnedEvent):
    def __init__(self, line: str, action: str) -> None:
        super(DrnedActionEvent, self).__init__(line)
        self.action = action

    def __str__(self) -> str:
        return 'Drned event ' + self.action

    def produce_line(self) -> str:
        if self.action == 'compare_config':
            line = 'compare config'
        else:
            line = self.action
        return self.indent_line(line)


class DrnedLoadEvent(DrnedActionEvent):
    def __init__(self, line: str) -> None:
        s = self.state_name_regexp.search(line)
        if s is None:
            raise Exception("Invalid DrnedLoadEvent")
        self.state = s.groups()[0]
        super(DrnedLoadEvent, self).__init__(line, 'load ' + self.state)


class DrnedCommitEvent(DrnedEvent):
    pass


class DrnedCommitQueueEvent(DrnedCommitEvent):
    def __init__(self) -> None:
        super(DrnedCommitQueueEvent, self).__init__('')

    def __str__(self) -> str:
        return 'Drned commit queue event'

    def produce_line(self) -> str:
        return self.indent_line('commit...')  # should not be used?


class DrnedCommitNoqueueEvent(DrnedCommitEvent):
    def __init__(self) -> None:
        super(DrnedCommitNoqueueEvent, self).__init__('')

    def __str__(self) -> str:
        return 'Drned commit event'

    def produce_line(self) -> str:
        return self.indent_line('commit...')  # should not be used?


class DrnedCommitNNEvent(DrnedCommitEvent):
    def __init__(self) -> None:
        super(DrnedCommitNNEvent, self).__init__('')

    def __str__(self) -> str:
        return 'Drned commit no-networking event'

    def produce_line(self) -> str:
        # should not be used?
        return self.indent_line('commit no networking...')


class DrnedCommitResultEvent(DrnedCommitEvent):
    def __init__(self, line: str, success: bool) -> None:
        super(DrnedCommitResultEvent, self).__init__(line)
        self.success = success

    def __str__(self) -> str:
        return 'Drned commit result event'

    def produce_line(self) -> str:
        line = '    succeeded' if self.success else '    failed'
        return self.indent_line(line)


class DrnedEmptyCommitEvent(DrnedCommitResultEvent):
    def __init__(self) -> None:
        super(DrnedEmptyCommitEvent, self).__init__('    (no modifications)', True)

    def __str__(self) -> str:
        return 'Drned empty commit event'

    def produce_line(self) -> str:
        return self.indent_line(self.line)


class DrnedCommitCompleteEvent(DrnedCommitResultEvent):
    def __init__(self, line: str) -> None:
        super(DrnedCommitCompleteEvent, self).__init__(line, True)

    def __str__(self) -> str:
        return 'Drned commit complete event'


class DrnedFailureReasonEvent(DrnedCommitResultEvent):
    def __init__(self, msg: str) -> None:
        super(DrnedFailureReasonEvent, self).__init__(msg, False)
        self.msg = msg
        self.reason = 'device request timeout' if 'transport timeout' in msg else None

    def __str__(self) -> str:
        return 'Drned commit failure: {}'.format(self.reason)

    def produce_line(self) -> str:
        max = 40
        if len(self.msg) > max:
            msg = self.msg[:max] + "..."
        else:
            msg = self.msg
        line = '    failed ({})'.format(msg)
        return self.indent_line(line)


class DrnedCompareEvent(LineOutputEvent):
    def __init__(self, success: bool) -> None:
        super(DrnedCompareEvent, self).__init__('')
        self.success = success

    def __str__(self) -> str:
        return 'Drned compare complete event: {}'.format(self.success)

    def produce_line(self) -> str:
        line = '    succeeded' if self.success else '    failed'
        return self.indent_line(line)


class DrnedFailedStatesEvent(LineOutputEvent):
    def __init__(self, failed_states: str) -> None:
        super(DrnedFailedStatesEvent, self).__init__('')
        self.failed_states = failed_states

    def __str__(self) -> str:
        return 'Drned walk-states failures: {}'.format(self.failed_states)

    def produce_line(self) -> str:
        return 'Failed states {}'.format(self.failed_states)


class DrnedTeardownEvent(LineOutputEvent):
    def __init__(self) -> None:
        super(DrnedTeardownEvent, self).__init__('')

    def __str__(self) -> str:
        return 'Drned teardown event'

    def produce_line(self) -> str:
        return 'Device cleanup'


class DrnedRestoreEvent(DrnedActionEvent):
    def __init__(self) -> None:
        super(DrnedRestoreEvent, self).__init__('restore', 'load before-session')


class TerminateEvent(LineOutputEvent):
    def __init__(self) -> None:
        super(TerminateEvent, self).__init__('')

    def __str__(self) -> str:
        return 'Terminate event'

    def produce_line(self) -> str:
        return ''


class EventGenerator(object):
    def __init__(self, consumer: EventConsumer) -> None:
        self.consumer = consumer
        self.coroutine: StrConsumer = event_generator(consumer)

    def send(self, data: str) -> None:
        self.coroutine.send(data)

    def close(self) -> None:
        try:
            # we need to let the consumer know; but it can raise
            # StopIteration
            self.consumer.send(TerminateEvent())
        except StopIteration:
            pass
        self.coroutine.close()


line_regexp: Pattern[str] = re.compile('''\
(?:\
(?P<init_states>Found [0-9]* states recorded for device .*)|\
(?P<start>Starting with state (?P<state>.*))|\
(?P<py_test>py.test -k test_template_set --fname=[^ ]*.state.(cfg|xml)\
(?: --op=[^ ]*)*(?: --end-op=)? --device=[^ ]*)|\
(?P<transition>Transition [0-9]*/[0-9]*: .* ==> .*)|\
(?P<init_failed>Failed to initialize state .*)|\
(?P<trans_failed>Transition failed)|\
(?P<drned_load>={30} r?load\\(.*/states/.*\\))|\
(?P<drned>={30} (?P<drned_op>commit|compare_config|rollback)\\(.*\\))|\
(?P<no_modifs>% No modifications to commit\\.)|\
(?P<commit_queue>commit commit-queue sync)|\
(?P<commit_noqueue>commit)|\
(?P<commit_nn>commit no-networking)|\
(?P<commit_complete>Commit complete\\.)|\
(?P<commit_result> *status (?P<result>completed|failed))|\
(?P<commit_abort>Aborted: (?P<abort_reason>.*))|\
(?P<commit_failure> *reason (?P<failure_reason>RPC error .*|[^ ]*: transport timeout; .*))|\
(?P<teardown>### TEARDOWN, RESTORE DEVICE ###)|\
(?P<restore>={30} load\\(drned-work/before-session.xml\\))|\
(?P<diff>diff *)|\
(?P<failed_states>.*Failed states:(?P<state_list> \\[.*\\]))\
)$''')


@coroutine
def event_generator(consumer: EventConsumer) -> StrConsumer:
    '''Based on the line input, generate events and pass them to the consumer.
    '''
    try:
        while True:
            line = yield
            match = line_regexp.match(line)
            if match is None:
                continue
            if match.lastgroup == 'start':
                consumer.send(StartStateEvent(match.string, match.groupdict()['state']))
                consumer.send(DrnedPrepareEvent())
            elif match.lastgroup == 'init_failed':
                consumer.send(InitFailedEvent(match.string))
            elif match.lastgroup == 'trans_failed':
                consumer.send(TransFailedEvent(match.string))
            elif match.lastgroup == 'transition':
                consumer.send(TransitionEvent(match.string))
                consumer.send(DrnedPrepareEvent())
            elif match.lastgroup == 'py_test':
                consumer.send(PyTestEvent(match.string))
            elif match.lastgroup == 'init_states':
                consumer.send(InitStatesEvent(match.string))
            elif match.lastgroup == 'drned_load':
                consumer.send(DrnedLoadEvent(match.string))
            elif match.lastgroup == 'drned':
                consumer.send(DrnedActionEvent(match.string, match.groupdict()['drned_op']))
            elif match.lastgroup == 'no_modifs':
                consumer.send(DrnedEmptyCommitEvent())
            elif match.lastgroup == 'commit_queue':
                consumer.send(DrnedCommitQueueEvent())
            elif match.lastgroup == 'commit_noqueue':
                consumer.send(DrnedCommitNoqueueEvent())
            elif match.lastgroup == 'commit_nn':
                consumer.send(DrnedCommitNNEvent())
            elif match.lastgroup == 'commit_result':
                consumer.send(DrnedCommitResultEvent(match.string,
                                                     match.groupdict()['result'] == 'completed'))
            elif match.lastgroup == 'commit_complete':
                consumer.send(DrnedCommitCompleteEvent(match.string))
            elif match.lastgroup == 'commit_abort':
                consumer.send(DrnedFailureReasonEvent(match.groupdict()['abort_reason']))
            elif match.lastgroup == 'commit_failure':
                consumer.send(DrnedFailureReasonEvent(match.groupdict()['failure_reason']))
            elif match.lastgroup == 'teardown':
                consumer.send(DrnedTeardownEvent())
            elif match.lastgroup == 'restore':
                consumer.send(DrnedRestoreEvent())
            elif match.lastgroup == 'diff':
                consumer.send(DrnedCompareEvent(False))
            elif match.lastgroup == 'failed_states':
                consumer.send(DrnedFailedStatesEvent(match.groupdict()['state_list']))
    except GeneratorExit:
        consumer.close()
