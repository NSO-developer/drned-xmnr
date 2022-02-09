from drned_xmnr.typing_xmnr import ActionResult


class ActionError(Exception):
    def __init__(self, info: ActionResult) -> None:
        self.info: ActionResult
        if isinstance(info, dict):
            self.info = info
        else:
            if info is None:
                self.info = None
            else:
                self.info = {'failure': info}
        super(ActionError, self).__init__()

    def get_info(self) -> ActionResult:
        return self.info
