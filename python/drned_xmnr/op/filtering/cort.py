'''Filter composition implemented as coroutine chaining.

See [David Beazly's presentation](http://www.dabeaz.com/coroutines/Coroutines.pdf) about coroutines.

'''

import functools

import sys
from typing import Any, Callable, Generator, TypeVar

if sys.version_info >= (3, 8):
    from typing import Protocol

FnRes = TypeVar('FnRes')
T = TypeVar('T')


CoRoutine = Generator[None, T, None]
StrWriter = Callable[[str], int]
StrConsumer = CoRoutine[str]

CoroutineGenT = TypeVar('CoroutineGenT', bound=Callable[..., CoRoutine[Any]])


def coroutine(fn: CoroutineGenT) -> CoroutineGenT:
    @functools.wraps(fn)
    def start(*args: Any, **kwargs: Any) -> CoRoutine[Any]:
        cr = fn(*args, **kwargs)
        next(cr)
        return cr
    return start  # type: ignore


@coroutine
def drop() -> CoRoutine[T]:
    while True:
        yield


if sys.version_info >= (3, 8):
    class IsStrConsumer(Protocol):
        def send(self, msg: str) -> None: ...
        def close(self) -> None: ...
else:
    IsStrConsumer = Any


@coroutine
def fork(c1: IsStrConsumer, c2: IsStrConsumer) -> StrConsumer:
    while True:
        item = yield
        c1.send(item)
        c2.send(item)


@coroutine
def filter_sink(writer: StrWriter) -> StrConsumer:
    while True:
        item = yield
        if isinstance(item, str):
            # the writer needs full line
            writer(item + '\n')
