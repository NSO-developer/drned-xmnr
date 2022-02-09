from typing import Any, Optional
from drned_xmnr.typing_xmnr import Tctx

from _ncs import RUNNING


class Maapi:
    __enter__: Any
    __exit__: Any
    attach: Any
    msock: Any
    def close(self) -> None: ...
    def start_user_session(self, user: str, context: str, *args: Any, **kwargs: Any) -> None: ...


class Transaction:
    __enter__: Any
    __exit__: Any
    apply: Any
    delete: Any
    load_rollback: Any
    load_config: Any
    maapi: Any
    revert: Any
    validate: Any
    save_config: Any

    def __init__(self, maapi: Maapi, th: Optional[Tctx] = None, rw: Optional[int] = None, db: int = RUNNING, *args: Any, **kwargs: Any) -> None: ...
    def finish(self) -> None: ...


def single_read_trans(*args: Any, **kws: Any) -> Transaction: ...
def single_write_trans(*args: Any, **kws: Any) -> Transaction: ...
