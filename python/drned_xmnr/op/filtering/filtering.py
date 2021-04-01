import sys
from contextlib import closing

from .cort import filter_sink
from .events import EventGenerator, InitialPrepareEvent
from .states import TransitionEventContext, LogStateMachine, TransitionTestState, \
    run_event_machine, ExploreState, WalkState


def transition_output_filter(level, sink, context=None):
    machine = LogStateMachine(level, TransitionTestState(), context)
    return run_event_machine(machine, sink)


def explore_output_filter(level, sink, context=None):
    machine = LogStateMachine(level, ExploreState(), context)
    return run_event_machine(machine, sink)


def walk_output_filter(level, sink, context=None):
    machine = LogStateMachine(level, WalkState(), context)
    handler = run_event_machine(machine, sink)
    handler.send(InitialPrepareEvent())
    return handler


def run_test_filter(outfilter, filename, level='drned-overview', out=sys.stdout):
    '''
    Testing and experimenting utility.  Can be used as

       filtering.run_test_filter(filtering.transition_output_filter, "data.txt")
    '''
    sink = filter_sink(out.write)
    ctx = TransitionEventContext()
    lines = outfilter(level, sink, ctx)
    evts = EventGenerator(lines)
    with closing(ctx):
        with closing(evts):
            with open(filename) as data:
                for line in data:
                    ln = line.strip()
                    if ln:
                        evts.send(ln)
    return ctx
