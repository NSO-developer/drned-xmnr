from typing import Dict, Literal, Optional, Union

from _ncs import TransCtxRef

# TODO - might split this file into proper locations for all aliases?

OptArgs = Optional[Dict[str, str]]

Tctx = Union[TransCtxRef]

LogLevel = Literal['none', 'overview', 'drned-overview', 'all']

ActionField = Literal['failure', 'success', 'error']

ActionResult = Union[Dict[ActionField, str], None]
