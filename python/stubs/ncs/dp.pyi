from typing import Any, Callable, Dict, Optional, Union, TypeVar
import _ncs
import ncs
from ncs.maagic import Node
from ncs.maapi import Transaction

class Daemon:
    class State: ...


ActionObj = TypeVar('ActionObj', bound='Action')

ACallback6 = Callable[[ActionObj, _ncs.UserInfo, str, _ncs.HKeypathRef, Node, Node],
                      Optional[int]]
ACallback7 = Callable[[ActionObj, _ncs.UserInfo, str, _ncs.HKeypathRef, Node, Node, Transaction],
                      Optional[int]]
ActionCallback = Union[ACallback6[ActionObj], ACallback7[ActionObj]]
WrappedCallback = Callable[[ActionObj, _ncs.UserInfo, str, _ncs.HKeypathRef, list],
                           Optional[int]]


class Action:
    log: ncs.log.Log = ...
    _state: Daemon.State = ...

    @staticmethod
    def action(fn: ActionCallback[ActionObj]) -> WrappedCallback[ActionObj]:
        ...

    def _make_key(self, uinfo: _ncs.UserInfo) -> str: ...


def _daemon_as_dict(daemon: Union[Daemon, Dict[str, Any]]) -> Dict[str, Any]: ...

def return_worker_socket(state: Daemon.State, key: str) -> None: ...
