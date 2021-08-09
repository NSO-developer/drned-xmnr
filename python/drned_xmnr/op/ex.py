# -*- mode: python; python-indent: 4 -*-


class ActionError(Exception):
    def __init__(self, info):
        if isinstance(info, dict):
            self.info = info
        else:
            self.info = {'failure': info}
        super(ActionError, self).__init__()

    def get_info(self):
        return self.info
