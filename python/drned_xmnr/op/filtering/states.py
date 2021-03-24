'''Simple pushodwn automaton implementing a LL(1) "grammar" with DrNED
output events as terminals.

In the module `drned_xmnr.op.filtering.events`, the DrNED output is processed to
DrNED events; these events are handled by the automaton states with following
two effects:

* the events are filtered according to filtering level (only "overview" and
  "drned-overview") and sent to the next consumer in the pipe (such as stdout or
  CLI write);

* an instance of `TransitionEventContext` is informed about new transition or
  other test events or their failures.

'''

import collections

from .events import DrnedPrepare, DrnedLoadEvent, DrnedActionEvent, InitStates, StartState, \
    InitFailed, Transition, InitialPrepareEvent, TransFailed, PyTest, DrnedFailedStatesEvent, \
    DrnedTeardown, DrnedRestore, DrnedEmptyCommit, DrnedCommitNoqueueEvent, DrnedCommitNNEvent, \
    DrnedCommitResult, DrnedCommitQueueEvent, DrnedCommitEvent, DrnedFailureReason, \
    DrnedCommitComplete, DrnedCompareEvent
from .cort import coroutine


TransitionDesc = collections.namedtuple('TransitionDesc',
                                        ['start', 'to', 'failure', 'failure_message'])


class TransitionEventContext(object):
    '''Transition event context.

    An instance of the context stores events of all transitions.  An event is a
    state file load, commit, rollback and so on; an event is also a failure of
    any of these actions.

    '''
    def __init__(self):
        self.state = '(init)'
        self.test_events = []
        self.exploring_from = None
        self.cleanup()

    def cleanup(self):
        self.event = None
        self.rollback = False
        self.to = None

    def start_explore(self, state):
        self.complete_transition()
        self.exploring_from = state

    def start_transition(self, to):
        self.complete_transition()
        self.to = to
        self.rollback = False
        self.event = 'load'

    def transition_event(self, event_type):
        self.event = event_type
        if event_type == 'rollback':
            self.rollback = True

    def fail_transition(self, msg=None):
        event = 'rollback' if self.rollback else self.event
        self.complete_transition(event, msg)
        return self.failure_comment(event)

    failure_comments = {
        'compare_config': 'configuration comparison failed, configuration artifacts on the device',
        'load': 'failed to load the state, state file appears to be invalid',
        'commit': 'failed to commit, configuration refused by the device',
        'rollback': 'failed to apply rollback'}

    @staticmethod
    def failure_comment(event_type):
        return TransitionEventContext.failure_comments.get(event_type, '')

    def complete_transition(self, failure=None, msg=None):
        if self.to is None:
            return
        self.test_events.append(TransitionDesc(self.state, self.to, failure, msg))
        self.state = self.exploring_from if self.exploring_from is not None else self.to
        self.cleanup()

    def close(self):
        self.complete_transition()


class LogStateMachine(object):
    '''Simple state machine with a stack.

    Input (events) are passed for handling to states.  A state handler
    returns a 2-tuple (handled, states) or a 3-tuple (handled, states,
    event).

    handled: Bool - it True, the current event has been processed
    and another one needs to be read (if True); otherwise it is used again.

    states: [LogState] - list of states to be used in place of the
    current state (an "expansion").

    event: LineOutputEvent - the event output to be produced, if present;
    typically it is the same as the input argument.

    '''

    evtclasses = {InitStates, StartState, Transition,
                  InitFailed, TransFailed, InitialPrepareEvent,
                  PyTest, DrnedTeardown}

    def __init__(self, level, init_state, context=None):
        self.stack = [init_state]
        self.level = level
        self.context = context if context is not None else TransitionEventContext()

    def handle(self, event):
        while self.stack:
            # print('handling "', event, '"', [state.name for state in reversed(self.stack)])
            state = self.stack.pop()
            restuple = state.handle(event)
            if len(restuple) == 2:
                handled, expansion = restuple
            else:
                handled, expansion, line_event = restuple
                if self.level != 'overview' or line_event.__class__ in self.evtclasses:
                    yield line_event.produce_line()
            self.stack.extend(reversed(expansion))
            if handled:
                msg = state.update_context(self.context, event)
                if msg:
                    yield msg
                break


class LogState(object):
    name = 'general logstate'

    def handle(self, event):
        '''Do a state expansion based on a log event.

        The method should return (handled, expansion) or (handled, expansion,
        event) where handled is a boolean indicating whether the event has been
        handled successfully, expansion is a list of state instances, event is a
        event (usually the input argument) whose line to be sent to the filtered
        output.

        '''
        raise Exception('Unhandled event', event)

    def update_context(self, context, event):
        '''Update the transition context if needed.

        The method is invoked only in case the state instance reported the event
        as handled.

        Args:
            context: The transition event context.
            event: The last event successfully processed by the state instance.

        '''
        pass


class TransitionTestState(LogState):
    'Tinitial state for "transition" action output filtering.'

    name = 'transition-test'

    def handle(self, event):
        return (False, [TransitionState()], DrnedPrepare())


class TransitionState(LogState):

    '''
    Transition -> (Commit)* Load Commit Compare (Rollback Commit Compare)*

    The first commits are just ignored.
    '''
    name = 'transition'

    def handle(self, event):
        return (False, [CommitsState(),
                        LoadState(),
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

    def handle(self, event):
        return (False,
                [GenState(InitStates), ExploreTransitionsState()])


class WalkState(LogState):
    'Initial state for "walk" actions output filtering.'
    name = 'walk'

    def handle(self, event):
        # expecting only InitialPrepareEvent
        return (True, [CommitsState(), WalkTransitionsState()], event)


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
                    event)
        return (True, [self])

    def update_context(self, context, event):
        if isinstance(event, StartState):
            context.start_explore(event.state)


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
            return (True, [], event)
        if isinstance(event, Transition):
            return (True, [GenState(DrnedPrepare), TransitionState(),
                           GenState(TransFailed), GenState(InitFailed),
                           TeardownState(), self],
                    event)
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
            return (True, [], event)
        return (False, [])


class WalkTransitionsState(LogState):
    '''
    WT -> (pytest? Transition)* Teardown

    It is a top-most state, it is always on the stack.
    '''

    name = 'transitions'

    def handle(self, event):
        if isinstance(event, PyTest):
            return (True, [TransitionState(), self], event)
        if isinstance(event, DrnedFailedStatesEvent):
            return (True, [], event)
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
                    event)
        return (False, [])


class LoadState(LogState):
    '''
    Load -> load LoadFailure?
    '''
    name = 'load'

    def handle(self, event):
        if isinstance(event, DrnedLoadEvent):
            return (True, [LoadFailureState()], event)
        else:
            return (False, [])

    def update_context(self, context, event):
        context.start_transition(event.state)


class LoadFailureState(LogState):
    '''
    LoadFailure -> loadfailure
    '''
    name = 'load-failure'

    def handle(self, event):
        # TODO: not implemented yet
        return (False, [])

    def update_context(self, context, _event):
        return context.fail_transition()


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
            return (True, self.expansion, event)
        return (False, [])

    def update_context(self, context, event):
        context.transition_event(self.action)


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
            return (True, [], event)
        if isinstance(event, DrnedCommitResult) and \
           not event.success:
            return (True, [CommitFailure(), CommitCompleteState()])
        return (False, [GenState(DrnedCommitResult), CommitCompleteState()])


class CommitFailure(LogState):
    '''Report commit failure reason (if any).
    '''

    def handle(self, event):
        if isinstance(event, DrnedFailureReason):
            return (True, [], event)
        return (False, [], DrnedCommitResult('', False))

    def update_context(self, context, event):
        return context.fail_transition(event.reason)


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
            return (True, [], event)
        else:
            # need to produce a line, but the event is not handled yet
            art_event = DrnedCompareEvent(True)
            return (False, [], art_event)

    def update_context(self, context, event):
        if not event.success:
            # TODO: for a compare failure we can have the full diff message; is
            # it useful?
            return context.fail_transition()


@coroutine
def run_event_machine(machine, sink):
    try:
        while True:
            event = yield
            for line in machine.handle(event):
                sink.send(line)
    except GeneratorExit:
        sink.close()
