from typing import Any, Tuple


__all__ = ("Value", "TransCtxRef", "UserInfo", "HKeypathRef")


class Value:
    def __init__(self, init: Any, type: int):
        ...


class TransCtxRef:
    ...


class UserInfo:
    context: str
    usid: int
    username: str
    actx_thandle: int


class HKeypathRef:
    def __getitem__(self, i: int) -> Tuple[Value]:
        ...
