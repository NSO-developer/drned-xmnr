import sys
from typing import Dict, Optional, Union

from _ncs import TransCtxRef

# TODO - might split this file into proper locations for all aliases?

OptArgs = Optional[Dict[str, str]]

Tctx = Union[TransCtxRef]

if sys.version_info > (3, 8):
    from typing import Literal
    LogLevel = Literal['none', 'overview', 'drned-overview', 'all']
    ActionField = Literal['failure', 'success', 'error']
else:
    LogLevel = str
    ActionField = str

ActionResult = Union[Dict[ActionField, str], None]
