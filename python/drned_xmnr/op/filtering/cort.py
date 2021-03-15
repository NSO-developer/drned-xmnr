'''Filter composition implemented as coroutine chaining.

See [David Beazly's presentation](http://www.dabeaz.com/coroutines/Coroutines.pdf) about coroutines.

'''

import functools


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
