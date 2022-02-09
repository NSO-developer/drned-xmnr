from typing import Any, Callable, Dict, Union
import _ncs
from ncs import log
from ncs.maagic import Node
from ncs.maapi import Transaction


class Daemon:
    class State: ...


ActionCallback = Callable[[_ncs.UserInfo, str, _ncs.HKeypathRef, Node, Node, Transaction], Any]


class Action:
    log: log.Log = ...
    _state: Daemon.State = ...

    @staticmethod
    def action(fn: ActionCallback) -> Any: ...

    def _make_key(self, uinfo: _ncs.UserInfo) -> str: ...


def _daemon_as_dict(daemon: Union[Daemon, Dict[str, Any]]) -> Dict[str, Any]: ...

def return_worker_socket(state: Daemon.State, key: str) -> None: ...
