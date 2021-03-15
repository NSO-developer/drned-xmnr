'''Simple pushodwn automaton implementing a LL(1) grammar with DrNED
output events as terminals.

'''

from .events import DrnedPrepare, DrnedLoadEvent, DrnedActionEvent, InitStates, StartState, \
    InitFailed, Transition, TransFailed, PyTest, DrnedFailedStatesEvent, DrnedTeardown, \
    DrnedRestore, DrnedEmptyCommit, DrnedCommitNoqueueEvent, DrnedCommitNNEvent, \
    DrnedCommitResult, DrnedCommitQueueEvent, DrnedCommitEvent, DrnedFailureReason, \
    DrnedCommitComplete, DrnedCompareEvent
from .cort import coroutine


class LogStateMachine(object):
    '''Simple state machine with a stack.

    Input (events) are passed for handling to states.  A state handler
    returns a 2-tuple (handled, states) or a 3-tuple (handled, states,
    line).

    handled: Bool - it True, the current event has been processed
    and another one needs to be read (if True); otherwise it is used again.

    states: [LogState] - list of states to be used in place of the
    current state (an "expansion").

    line: Str - output to be produced, if present; typically from `event.produce_line()`.

    '''

    def __init__(self, init_state):
        self.stack = [init_state]

    def handle(self, event):
        handled = False
        while not handled and self.stack:
            # print('handling "', event, '"', [state.name for state in reversed(self.stack)])
            state = self.stack.pop()
            restuple = state.handle(event)
            if len(restuple) == 2:
                handled, expansion = restuple
            else:
                handled, expansion, line = restuple
                yield line
            self.stack.extend(reversed(expansion))


class LogState(object):
    name = 'general logstate'

    def handle(self, event):
        raise Exception('Unhandled event', event)


class TransitionTestState(LogState):
    'Tinitial state for "transition" action output filtering.'

    name = 'transition-test'

    def __init__(self, level):
        self.level = level

    def handle(self, event):
        if self.level == 'overview':
            return (True, [self])
        return (False, [TransitionState()], DrnedPrepare().produce_line())


class TransitionState(LogState):

    '''
    Transition -> (Commit)* Load Commit Compare (Rollback Commit Compare)*

    The first commits are just ignored.
    '''
    name = 'transition'

    def handle(self, event):
        return (False, [CommitsState(),
                        GenState(DrnedLoadEvent),
                        ActionState('commit', [CommitState()]),
                        ActionState('compare_config', [CompareState()]),
                        RollbacksState()])


class RollbacksState(LogState):
    '''
    Rollbacks -> Rollback Commit Compare Rollbacks | []
    '''
    name = 'rollback'

    def handle(self, event):
        if event.__class__ == DrnedActionEvent and event.action == 'rollback':
            return (False, [ActionState('rollback'),
                            ActionState('commit', [CommitState()]),
                            ActionState('compare_config', [CompareState()]),
                            self])
        else:
            return (False, [])


class ExploreState(LogState):
    'Initial state for "explore" actions output filtering.'
    name = 'explore'

    def __init__(self, level):
        self.level = level

    def handle(self, event):
        if self.level == 'overview':
            return (False, [BriefTransitionsState()])
        return (False,
                [GenState(InitStates), ExploreTransitionsState()])


class WalkState(LogState):
    'Initial state for "walk" actions output filtering.'
    name = 'walk'

    def __init__(self, level):
        self.level = level

    def handle(self, event):
        if self.level == 'overview':
            return (True, [BriefTransitionsState()], event.produce_line())
        return (True, [CommitsState(), WalkTransitionsState()], event.produce_line())


class ExploreTransitionsState(LogState):
    '''
    ETs -> (start prepare TransitionS ExtTrans)*

    It is a top-most state, it is always on the stack.
    '''
    name = 'explore'

    def handle(self, event):
        if isinstance(event, StartState):
            return (True,
                    [GenState(DrnedPrepare), TransitionState(), ExtendedTransitionsState(), self],
                    event.produce_line())
        return (True, [self])


class ExtendedTransitionsState(LogState):
    '''
    ExtTrans -> (transition prepare TransitionS transfailed? Teardown)*
    ExtTrans -> initfailed

    The second variant is handling state initialization failure from
    ETs.
    '''
    name = 'extended-transitions'

    def handle(self, event):
        if isinstance(event, InitFailed):
            return (True, [], event.produce_line())
        if isinstance(event, Transition):
            return (True, [GenState(DrnedPrepare), TransitionState(),
                           GenState(TransFailed), GenState(InitFailed),
                           TeardownState(), self],
                    event.produce_line())
        return (False, [])


class GenState(LogState):
    '''A generic log state.

    Every event of given type is accepted (and its line is produced),
    everything else is left for further processing.

    (So e.g. GenState(prepare) -> prepare | [])

    '''

    def __init__(self, eventclass):
        self.eventclass = eventclass
        self.name = 'gen({})'.format(eventclass.__name__)

    def handle(self, event):
        if isinstance(event, self.eventclass):
            return (True, [], event.produce_line())
        return (False, [])


class WalkTransitionsState(LogState):
    '''
    WT -> (pytest? Transition)* Teardown

    It is a top-most state, it is always on the stack.
    '''

    name = 'transitions'

    def handle(self, event):
        if isinstance(event, PyTest):
            return (True, [TransitionState(), self], event.produce_line())
        if isinstance(event, DrnedFailedStatesEvent):
            return (True, [], event.produce_line())
        if isinstance(event, DrnedLoadEvent):
            # this happens in case of state groups; the first event of
            # a state transition is load then
            return (False, [TransitionState(), self])
        if isinstance(event, DrnedTeardown):
            return (False, [TeardownState(), self])
        return (True, [self])


class TeardownState(LogState):
    '''
    Teardown -> teardown Restore Commit Compare TransFailed?
    '''
    name = 'teardown'

    def handle(self, event):
        if isinstance(event, DrnedTeardown):
            return (True,
                    [GenState(DrnedRestore),
                     ActionState('commit', [CommitState()]),
                     ActionState('compare_config', [CompareState()]),
                     GenState(TransFailed)],
                    event.produce_line())
        return (False, [])


class BriefTransitionsState(LogState):
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


class ActionState(LogState):
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


class CommitState(LogState):
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
            return (True, [GenState(DrnedCommitResult)])
        if isinstance(event, DrnedCommitQueueEvent):
            return (True, [CommitQueueState()])
        return (False, [])


class CommitsState(LogState):
    '''A sequence of commit events, usually at the beginning of drned
    actions.  They are just ignored.'''

    name = 'commits'

    def handle(self, event):
        if isinstance(event, DrnedCommitEvent):
            return (True, [self])
        return (False, [])


class CommitQueueState(LogState):
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
            return (True, [CommitFailure(), CommitCompleteState()])
        return (False, [GenState(DrnedCommitResult), CommitCompleteState()])


class CommitFailure(LogState):
    '''Report commit failure reason (if any).
    '''

    def handle(self, event):
        if isinstance(event, DrnedFailureReason):
            return (True, [], event.produce_line())
        return (False, [], DrnedCommitResult('', False).produce_line())


class CommitCompleteState(LogState):
    '''Just ignores the "Commit complete" message.'''
    name = 'commit-complete'

    def handle(self, event):
        # a commit success/failure message can be followed by "Commit
        # complete" - this needs to be swallowed
        return (isinstance(event, DrnedCommitComplete), [])


class CompareState(LogState):
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


@coroutine
def run_event_machine(machine, sink):
    try:
        while True:
            event = yield
            for line in machine.handle(event):
                sink.send(line)
    except GeneratorExit:
        sink.close()
