'''Filter composition implemented as coroutine chaining.

See [David Beazly's presentation](http://www.dabeaz.com/coroutines/Coroutines.pdf) about coroutines.

'''

import functools

from typing import Any, Callable, Generator, Protocol, TypeVar
from drned_xmnr.typing_xmnr import StrConsumer, StrWriter

FnRes = TypeVar('FnRes')


def coroutine(fn: Callable[..., Generator[None, FnRes, None]]) -> Callable[..., Generator[None, FnRes, None]]:
    @functools.wraps(fn)
    def start(*args: Any, **kwargs: Any) -> Generator[None, FnRes, None]:
        cr = fn(*args, **kwargs)
        next(cr)
        return cr
    return start


@coroutine
def drop() -> Generator[None, Any, None]:
    while True:
        yield


class IsStrConsumer(Protocol):
    def send(self, msg: str) -> None: ...
    def close(self) -> None: ...


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
