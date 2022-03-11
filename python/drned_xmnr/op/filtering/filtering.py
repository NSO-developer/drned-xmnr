import sys
from contextlib import closing

from .cort import filter_sink, StrConsumer
from .events import EventConsumer, EventGenerator, InitialPrepareEvent
from .states import TransitionEventContext, LogStateMachine, TransitionTestState, \
    run_event_machine, ExploreState, WalkState

from typing import Callable, Optional, TextIO
from drned_xmnr.typing_xmnr import LogLevel


def transition_output_filter(level: LogLevel, sink: StrConsumer, context: Optional[TransitionEventContext] = None) -> EventConsumer:
    machine = LogStateMachine(level, TransitionTestState(), context)
    return run_event_machine(machine, sink)


def explore_output_filter(level: LogLevel, sink: StrConsumer, context: Optional[TransitionEventContext] = None) -> EventConsumer:
    machine = LogStateMachine(level, ExploreState(), context)
    return run_event_machine(machine, sink)


def walk_output_filter(level: LogLevel, sink: StrConsumer, context: Optional[TransitionEventContext] = None) -> EventConsumer:
    machine = LogStateMachine(level, WalkState(), context)
    handler = run_event_machine(machine, sink)
    handler.send(InitialPrepareEvent())
    return handler


OutputFilter = Callable[[LogLevel, StrConsumer, Optional[TransitionEventContext]],
                        EventConsumer]


def run_test_filter(outfilter: OutputFilter, filename: str, level: LogLevel = 'drned-overview', out: TextIO = sys.stdout) -> TransitionEventContext:
    '''
    Testing and experimenting utility.  Can be used as

       filtering.run_test_filter(filtering.transition_output_filter, "data.txt")
    '''
    sink: StrConsumer = filter_sink(out.write)
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
