'''
Filter composition implemented as coroutine chaining.  See `David
Beazly's presentation
<http://www.dabeaz.com/coroutines/Coroutines.pdf>`_ about coroutines.
'''

import sys
import functools
import re


def coroutine(fn):
    @functools.wraps(fn)
    def start(*args, **kwargs):
        cr = fn(*args, **kwargs)
        next(cr)
        return cr
    return start


@coroutine
def drop():
    while True:
        yield


@coroutine
def filter_sink(writer):
    while True:
        item = yield
        if isinstance(item, str):
            # the writer needs full line
            writer(item + '\n')


class Closeable(object):
    def __init__(self, coroutine, consumer):
        self.coroutine = coroutine
        self.consumer = consumer

    def close(self):
        self.consumer.close()
        self.coroutine.close()

    def send(self, data):
        self.coroutine.send(data)


#
# Event handling
#
# Event is an instance of `LineOutputEvent`; it is produced by
# `event_generator` and passed to a simple pushdown automaton.  The
# automaton takes care of state transitions during log processing - an
# event can cause a state transition and an output in the form of a
# line sent to the next filter in the chain.


class LineOutputEvent(object):
    indent = 3 * ' '
    state_name_regexp = re.compile(r'.*/states/([^/]*)\.state\.(cfg|xml)')

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


class InitStates(LineOutputEvent):
    pass


class StartState(LineOutputEvent):
    pass


class Transition(LineOutputEvent):
    pass


class InitFailed(LineOutputEvent):
    pass


class TransFailed(LineOutputEvent):
    pass


class PyTest(LineOutputEvent):
    def produce_line(self):
        state = self.state_name_regexp.search(self.line).groups()[0]
        return 'Test transition to {}'.format(state)


class DrnedPrepare(LineOutputEvent):
    def __init__(self):
        super(DrnedPrepare, self).__init__('')

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
        if self.action == 'load':
            state = self.state_name_regexp.search(self.line).groups()[0]
            line = 'load ' + state
        elif self.action == 'compare_config':
            line = 'compare config'
        else:
            line = self.action
        return self.indent_line(line)


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


class DrnedCommitResult(DrnedCommitEvent):
    def __init__(self, line, success):
        super(DrnedCommitResult, self).__init__(line)
        self.success = success

    def __str__(self):
        return 'Drned commit result event'

    def produce_line(self):
        line = '    succeeded' if self.success else '    failed'
        return self.indent_line(line)


class DrnedEmptyCommit(DrnedCommitResult):
    def __init__(self):
        super(DrnedEmptyCommit, self).__init__('    (no modifications)', True)

    def __str__(self):
        return 'Drned empty commit event'

    def produce_line(self):
        return self.indent_line(self.line)


class DrnedCommitComplete(DrnedCommitResult):
    def __init__(self, line):
        super(DrnedCommitComplete, self).__init__(line, True)

    def __str__(self):
        return 'Drned commit complete event'


class DrnedFailureReason(DrnedCommitEvent):
    def __init__(self, reason):
        super(DrnedFailureReason, self).__init__('')
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


class DrnedCompareEvent(DrnedEvent):
    def __init__(self, success):
        super(DrnedCompareEvent, self).__init__('')
        self.success = success

    def __str__(self):
        return 'Drned compare complete event: {}'.format(self.success)

    def produce_line(self):
        line = '    succeeded' if self.success else '    failed'
        return self.indent_line(line)


class DrnedTeardown(LineOutputEvent):
    def __init__(self):
        super(DrnedTeardown, self).__init__('')

    def __str__(self):
        return 'Drned teardown event'

    def produce_line(self):
        return 'Device cleanup'


class DrnedRestore(DrnedActionEvent):
    def __init__(self):
        super(DrnedRestore, self).__init__('restore', 'load before-session')


class TerminateEvent(LineOutputEvent):
    def __init__(self):
        super(TerminateEvent, self).__init__('')

    def __str__(self):
        return 'Terminate event'

    def produce_line(self):
        return None


class EventGenerator(Closeable):
    def __init__(self, consumer):
        cort = event_generator(consumer)
        super(EventGenerator, self).__init__(cort, consumer)

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
(?P<start>Starting with state .*)|\
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
(?P<diff>diff *)\
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
                consumer.send(StartState(match.string))
                consumer.send(DrnedPrepare())
            elif match.lastgroup == 'init_failed':
                consumer.send(InitFailed(match.string))
            elif match.lastgroup == 'trans_failed':
                consumer.send(TransFailed(match.string))
            elif match.lastgroup == 'transition':
                consumer.send(Transition(match.string))
                consumer.send(DrnedPrepare())
            elif match.lastgroup == 'py_test':
                consumer.send(PyTest(match.string))
            elif match.lastgroup == 'init_states':
                consumer.send(InitStates(match.string))
            elif match.lastgroup == 'drned_load':
                consumer.send(DrnedActionEvent(match.string, 'load'))
            elif match.lastgroup == 'drned':
                consumer.send(DrnedActionEvent(match.string, match.groupdict()['drned_op']))
            elif match.lastgroup == 'no_modifs':
                consumer.send(DrnedEmptyCommit())
            elif match.lastgroup == 'commit_queue':
                consumer.send(DrnedCommitQueueEvent())
            elif match.lastgroup == 'commit_noqueue':
                consumer.send(DrnedCommitNoqueueEvent())
            elif match.lastgroup == 'commit_nn':
                consumer.send(DrnedCommitNNEvent())
            elif match.lastgroup == 'commit_result':
                consumer.send(DrnedCommitResult(match.string,
                                                match.groupdict()['result'] == 'completed'))
            elif match.lastgroup == 'commit_complete':
                consumer.send(DrnedCommitComplete(match.string))
            elif match.lastgroup == 'failure_reason':
                consumer.send(DrnedFailureReason(match.groupdict()['reason']))
            elif match.lastgroup == 'teardown':
                consumer.send(DrnedTeardown())
            elif match.lastgroup == 'restore':
                consumer.send(DrnedRestore())
            elif match.lastgroup == 'diff':
                consumer.send(DrnedCompareEvent(False))
    except GeneratorExit:
        consumer.close()


class LSMachine(object):
    '''Simple state machine with a stack.

    Input (events) are passed for handling to states.  A state handler
    returns a 2-tuple (handled, states) or a 3-tuple (handled, states,
    line).

    handled: Bool - it True, the current event has been processed
    and another one needs to be read (if True); otherwise it is used again.

    states: [LS] - list of states to be used in place of the current state (an "expansion").

    line: Str - output to be produced, if present; typically from `event.produce_line()`.

    '''

    def __init__(self, init_state):
        self.stack = [init_state]

    def handle(self, event):
        handled = False
        while not handled and self.stack:
            # print('handling', event, [state.name for state in reversed(self.stack)])
            state = self.stack.pop()
            restuple = state.handle(event)
            if len(restuple) == 2:
                handled, expansion = restuple
            else:
                handled, expansion, line = restuple
                yield line
            self.stack.extend(reversed(expansion))


class LS(object):
    name = 'general logstate'

    def handle(self, event):
        return (False, [self], event.produce_line())


class TransitionTestS(LS):
    'Tinitial state for "transition" action output filtering.'

    name = 'transition-test'

    def __init__(self, level):
        self.level = level

    def handle(self, event):
        if self.level == 'overview':
            return (True, [self])
        return (False, [TransitionS()], DrnedPrepare().produce_line())


class TransitionS(LS):

    '''
    Transition -> (Commit)* Load Commit Compare (Rollback Commit Compare)*

    The first commits are just ignored.
    '''
    name = 'transition'

    def handle(self, event):
        return (False, [CommitsS(),
                        ActionS('load'),
                        ActionS('commit', [CommitS()]),
                        ActionS('compare_config', [CompareS()]),
                        RollbacksS()])


class RollbacksS(LS):
    '''
    Rollbacks -> Rollback Commit Compare Rollbacks | []
    '''
    def handle(self, event):
        if event.__class__ == DrnedActionEvent and event.action == 'rollback':
            return (False, [ActionS('rollback'),
                            ActionS('commit', [CommitS()]),
                            ActionS('compare_config', [CompareS()]),
                            self])
        else:
            return (False, [])


class ExploreS(LS):
    'Initial state for "explore" actions output filtering.'

    name = 'explore'

    def __init__(self, level):
        self.level = level

    def handle(self, event):
        if self.level == 'overview':
            return (False, [SilentTransitionsS()])
        return (False,
                [GenS(InitStates), ExploreTransitionsS()])


class WalkS(LS):
    'Initial state for "walk" actions output filtering.'

    name = 'walk'

    def __init__(self, level):
        self.level = level

    def handle(self, event):
        if self.level == 'overview':
            return (True, [SilentTransitionsS()], event.produce_line())
        return (True, [CommitsS(), WalkTransitionsS()], event.produce_line())


class ExploreTransitionsS(LS):
    '''
    ETs -> ((start | transition) prepare TransitionS (transfailed | initfailed)? )* teardown restore
    '''

    name = 'transitions'

    def handle(self, event):
        if isinstance(event, StartState) or isinstance(event, Transition):
            return (True,
                    [GenS(DrnedPrepare), TransitionS(),
                     GenS(TransFailed), GenS(InitFailed),
                     self],
                    event.produce_line())
        if isinstance(event, DrnedTeardown):
            return (True, [ActionS('restore')], event.produce_line())
        return (False, [])


class GenS(LS):
    '''A generic log state.

    Every event of given type is accepted (and its line is produced),
    everything else is left for further processing.

    (So e.g. GenS(prepare) -> prepare | [])

    '''

    def __init__(self, eventclass):
        self.eventclass = eventclass
        self.name = 'gen({})'.format(eventclass.__name__)

    def handle(self, event):
        if isinstance(event, self.eventclass):
            return (True, [], event.produce_line())
        return (False, [])


class WalkTransitionsS(LS):
    '''
    WT -> (pytest Transition)* (teardown Restore Commit Compare)?
    '''

    name = 'transitions'

    def handle(self, event):
        if isinstance(event, PyTest):
            return (True, [TransitionS(), self], event.produce_line())
        if isinstance(event, DrnedTeardown):
            return (True,
                    [GenS(DrnedRestore),
                     ActionS('commit', [CommitS()]),
                     ActionS('compare_config', [CompareS()])], event.produce_line())

        return (False, [])


class SilentTransitionsS(LS):
    'Produces output for the set of event types, ignores others.'

    name = 'silent-transitions'
    evtclasses = {InitStates, StartState, Transition,
                  InitFailed, TransFailed,
                  PyTest, DrnedTeardown}

    def handle(self, event):
        # just report events in `evtclasses`; everything else is
        # swallowed
        if event.__class__ in self.evtclasses:
            return (True, [self], event.produce_line())
        return (True, [self])


class ActionS(LS):
    '''
    Action(action) -> action | []
    '''

    def __init__(self, action, expansion=[]):
        self.action = action
        self.expansion = expansion
        self.name = 'action-' + action

    def handle(self, event):
        if isinstance(event, DrnedActionEvent) and event.action == self.action:
            return (True, self.expansion, event.produce_line())
        return (False, [])


class CommitS(LS):
    '''
    Commit -> (empty-commit)? (commit|commit-no-networking) CommitResult
    Commit -> (empty-commit)? commit-queue CommitQueueS

    The empty commit may be the result of "commit dry-run"; it is
    ignored.
    '''

    name = 'commit'

    def handle(self, event):
        if isinstance(event, DrnedEmptyCommit):
            return (True, [self])
        if isinstance(event, DrnedCommitNoqueueEvent) or \
           isinstance(event, DrnedCommitNNEvent):
            return (True, [GenS(DrnedCommitResult)])
        if isinstance(event, DrnedCommitQueueEvent):
            return (True, [CommitQueueS()])
        return (False, [])


class CommitsS(LS):
    '''A sequence of commit events, usually at the beginning of drned
    actions.  They are just ignored.'''

    name = 'commits'

    def handle(self, event):
        if isinstance(event, DrnedCommitEvent):
            return (True, [self])
        return (False, [])


class CommitQueueS(LS):
    '''"commit-queue" handling.

    It differs in that the result (success or failure) is followed by
    "Commit complete" message.

    Failure -> failure FailureReason | []
    '''

    name = 'commit queue'

    def handle(self, event):
        if isinstance(event, DrnedEmptyCommit):
            return (True, [], event.produce_line())
        if isinstance(event, DrnedCommitResult) and \
           not event.success:
            return (True, [CommitFailure(), CommitCompleteS()])
        return (False, [GenS(DrnedCommitResult), CommitCompleteS()])


class CommitFailure(LS):
    '''Report commit failure reason (if any).
    '''

    def handle(self, event):
        if isinstance(event, DrnedFailureReason):
            return (True, [], event.produce_line())
        return (False, [], DrnedCommitResult(False).produce_line())


class CommitCompleteS(LS):
    '''Just ignores the "Commit complete" message.'''
    name = 'commit-complete'

    def handle(self, event):
        # a commit success/failure message can be followed by "Commit
        # complete" - this needs to be swallowed
        return (isinstance(event, DrnedCommitComplete), [])


class CompareS(LS):
    '''The event "compare-config" in case of a success may not be followed
    by a result event.
    '''

    name = 'compare'

    def handle(self, event):
        if isinstance(event, DrnedCompareEvent):
            return (True, [], event.produce_line())
        else:
            # need to produce a line, but the event is not handled yet
            art_event = DrnedCompareEvent(True)
            return (False, [], art_event.produce_line())


def transition_output_filter(level, sink):
    machine = LSMachine(TransitionTestS(level))
    return run_event_machine(machine, sink)


def explore_output_filter(level, sink):
    machine = LSMachine(ExploreS(level))
    return run_event_machine(machine, sink)


def walk_output_filter(level, sink):
    machine = LSMachine(WalkS(level))
    handler = run_event_machine(machine, sink)
    handler.send(LineOutputEvent('Prepare the device'))
    return handler


@coroutine
def run_event_machine(machine, sink):
    try:
        while True:
            event = yield
            for line in machine.handle(event):
                sink.send(line)
    except GeneratorExit:
        sink.close()


def build_filter(op, level, write):
    sink = filter_sink(write)
    lines = op.event_processor(level, sink)
    return EventGenerator(lines)


def run_test_filter(outfilter, filename, level='drned-overview'):
    '''
    Testing and experimenting utility.  Can be used as

       filtering.run_test_filter(filtering.transition_output_filter, "data.txt")
    '''
    sink = filter_sink(sys.stdout.write)
    lines = outfilter(level, sink)
    evts = EventGenerator(lines)
    with open(filename) as data:
        for line in data:
            ln = line.strip()
            if ln:
                evts.send(ln)
    evts.close()
