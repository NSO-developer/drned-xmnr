from typing import Any, Callable, Dict, Generator, Literal, Optional, Union

from _ncs import TransCtxRef

# TODO - might split this file into proper locations for all aliases?

ActionResult = Union[Dict[str, str], None, Any]

OptArgs = Optional[Dict[str, Any]]

Tctx = Union[TransCtxRef, int]

StrConsumer = Generator[None, str, None]
StrWriter = Callable[[str], Any]

LogLevel = Literal['none', 'overview', 'drned-overview', 'all']
