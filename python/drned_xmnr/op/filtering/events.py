'''DrNED output events.

Instances of the class `LineOutputEvent` are generated for important
DrNED output lines.  They are passed to a simple pushdown automaton
that takes care of generating filtered output and transition events.
'''

import re
from .cort import coroutine


class LineOutputEvent(object):
    indent = 3 * ' '
    state_name_regexp = re.compile(r'.*/states/([^/.]*)(?:\.state)?\.(cfg|xml)')

    @staticmethod
    def indent_line(line):
        return '{}{}'.format(LineOutputEvent.indent, line)

    def __init__(self, line):
        self.line = line
        self.complete = False

    def __str__(self):
        return 'Line event {} {}'.format(self.__class__.__name__, self.line)

    def mark_complete(self):
        self.complete = True

    def produce_line(self):
        return self.line


class InitialPrepareEvent(LineOutputEvent):
    def __init__(self):
        super(InitialPrepareEvent, self).__init__('Prepare the device')


class InitStatesEvent(LineOutputEvent):
    pass


class StartStateEvent(LineOutputEvent):
    def __init__(self, line, state):
        super(StartStateEvent, self).__init__(line)
        self.state = state


class TransitionEvent(LineOutputEvent):
    pass


class InitFailedEvent(LineOutputEvent):
    pass


class TransFailedEvent(LineOutputEvent):
    pass


class PyTestEvent(LineOutputEvent):
    def produce_line(self):
        state = self.state_name_regexp.search(self.line).groups()[0]
        return 'Test transition to {}'.format(state)


class DrnedPrepareEvent(LineOutputEvent):
    def __init__(self):
        super(DrnedPrepareEvent, self).__init__('')

    def produce_line(self):
        return self.indent_line('prepare the device')


class DrnedEvent(LineOutputEvent):
    pass


class DrnedActionEvent(DrnedEvent):
    def __init__(self, line, action):
        super(DrnedActionEvent, self).__init__(line)
        self.action = action

    def __str__(self):
        return 'Drned event ' + self.action

    def produce_line(self):
        if self.action == 'compare_config':
            line = 'compare config'
        else:
            line = self.action
        return self.indent_line(line)


class DrnedLoadEvent(DrnedActionEvent):
    def __init__(self, line):
        self.state = self.state_name_regexp.search(line).groups()[0]
        super(DrnedLoadEvent, self).__init__(line, 'load ' + self.state)


class DrnedCommitEvent(DrnedEvent):
    pass


class DrnedCommitQueueEvent(DrnedCommitEvent):
    def __init__(self):
        super(DrnedCommitQueueEvent, self).__init__('')

    def __str__(self):
        return 'Drned commit queue event'

    def produce_line(self):
        return self.indent_line('commit...')  # should not be used?


class DrnedCommitNoqueueEvent(DrnedCommitEvent):
    def __init__(self):
        super(DrnedCommitNoqueueEvent, self).__init__('')

    def __str__(self):
        return 'Drned commit event'

    def produce_line(self):
        return self.indent_line('commit...')  # should not be used?


class DrnedCommitNNEvent(DrnedCommitEvent):
    def __init__(self):
        super(DrnedCommitNNEvent, self).__init__('')

    def __str__(self):
        return 'Drned commit no-networking event'

    def produce_line(self):
        # should not be used?
        return self.indent_line('commit no networking...')


class DrnedCommitResultEvent(DrnedCommitEvent):
    def __init__(self, line, success):
        super(DrnedCommitResultEvent, self).__init__(line)
        self.success = success

    def __str__(self):
        return 'Drned commit result event'

    def produce_line(self):
        line = '    succeeded' if self.success else '    failed'
        return self.indent_line(line)


class DrnedEmptyCommitEvent(DrnedCommitResultEvent):
    def __init__(self):
        super(DrnedEmptyCommitEvent, self).__init__('    (no modifications)', True)

    def __str__(self):
        return 'Drned empty commit event'

    def produce_line(self):
        return self.indent_line(self.line)


class DrnedCommitCompleteEvent(DrnedCommitResultEvent):
    def __init__(self, line):
        super(DrnedCommitCompleteEvent, self).__init__(line, True)

    def __str__(self):
        return 'Drned commit complete event'


class DrnedFailureReasonEvent(DrnedCommitEvent):
    def __init__(self, reason):
        super(DrnedFailureReasonEvent, self).__init__('')
        self.reason = reason

    def __str__(self):
        return 'Drned commit failure: {}'.format(self.reason)

    def produce_line(self):
        max = 40
        if len(self.reason) > max:
            msg = self.reason[:max] + "..."
        else:
            msg = self.reason
        line = '    failed ({})'.format(msg)
        return self.indent_line(line)


class DrnedCompareEvent(LineOutputEvent):
    def __init__(self, success):
        super(DrnedCompareEvent, self).__init__('')
        self.success = success

    def __str__(self):
        return 'Drned compare complete event: {}'.format(self.success)

    def produce_line(self):
        line = '    succeeded' if self.success else '    failed'
        return self.indent_line(line)


class DrnedFailedStatesEvent(LineOutputEvent):
    def __init__(self, failed_states):
        super(DrnedFailedStatesEvent, self).__init__('')
        self.failed_states = failed_states

    def __str__(self):
        return 'Drned walk-states failures: {}'.format(self.failed_states)

    def produce_line(self):
        return 'Failed States {}'.format(self.failed_states)


class DrnedTeardownEvent(LineOutputEvent):
    def __init__(self):
        super(DrnedTeardownEvent, self).__init__('')

    def __str__(self):
        return 'Drned teardown event'

    def produce_line(self):
        return 'Device cleanup'


class DrnedRestoreEvent(DrnedActionEvent):
    def __init__(self):
        super(DrnedRestoreEvent, self).__init__('restore', 'load before-session')


class TerminateEvent(LineOutputEvent):
    def __init__(self):
        super(TerminateEvent, self).__init__('')

    def __str__(self):
        return 'Terminate event'

    def produce_line(self):
        return None


class EventGenerator(object):
    def __init__(self, consumer):
        self.consumer = consumer
        self.coroutine = event_generator(consumer)

    def send(self, data):
        self.coroutine.send(data)

    def close(self):
        try:
            # we need to let the consumer know; but it can raise
            # StopIteration
            self.consumer.send(TerminateEvent())
        except StopIteration:
            pass
        self.coroutine.close()


line_regexp = re.compile('''\
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
(?P<failure_reason> *reason (?P<reason>RPC error .*))|\
(?P<teardown>### TEARDOWN, RESTORE DEVICE ###)|\
(?P<restore>={30} load\\(drned-work/before-session.xml\\))|\
(?P<diff>diff *)|\
(?P<failed_states>.*Failed states:(?P<state_list> \\[.*\\]))\
)$''')


@coroutine
def event_generator(consumer):
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
            elif match.lastgroup == 'failure_reason':
                consumer.send(DrnedFailureReasonEvent(match.groupdict()['reason']))
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
