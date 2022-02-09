from drned_xmnr.op.coverage_op import Handler
from ncs.log import Log


class DataCallbacks(object):
    def __init__(self, log: Log):
        ...

    def register(self, path: str, handler: Handler) -> None:
        ...
