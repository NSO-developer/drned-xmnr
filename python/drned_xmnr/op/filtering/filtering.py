import sys

from .cort import filter_sink
from .events import EventGenerator, LineOutputEvent
from .states import LogStateMachine, TransitionTestState, run_event_machine, ExploreState, WalkState


def transition_output_filter(level, sink):
    machine = LogStateMachine(TransitionTestState(level))
    return run_event_machine(machine, sink)


def explore_output_filter(level, sink):
    machine = LogStateMachine(ExploreState(level))
    return run_event_machine(machine, sink)


def walk_output_filter(level, sink):
    machine = LogStateMachine(WalkState(level))
    handler = run_event_machine(machine, sink)
    handler.send(LineOutputEvent('Prepare the device'))
    return handler


def build_filter(op, level, write):
    sink = filter_sink(write)
    lines = op.event_processor(level, sink)
    return EventGenerator(lines)


def run_test_filter(outfilter, filename, level='drned-overview', out=sys.stdout):
    '''
    Testing and experimenting utility.  Can be used as

       filtering.run_test_filter(filtering.transition_output_filter, "data.txt")
    '''
    sink = filter_sink(out.write)
    lines = outfilter(level, sink)
    evts = EventGenerator(lines)
    with open(filename) as data:
        for line in data:
            ln = line.strip()
            if ln:
                evts.send(ln)
    evts.close()
