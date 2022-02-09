from typing import Type
from .dp import Action
from .log import Log
from drned_xmnr.typing_xmnr import OptArgs


class Service: ...


class Application:
    log: Log

    def register_action(self, actionpoint: str, action_cls: Type[Action], init_args: OptArgs = None) -> None:
        ...

    def register_service(self, servicepoint: str, service_cls: Type[Service], init_args: OptArgs = None) -> None:
        ...
