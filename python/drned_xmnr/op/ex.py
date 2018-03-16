# -*- mode: python; python-indent: 4 -*-


class ActionError(Exception):
    def __init__(self, info):
        if type(info) is dict:
            self.info = info
        else:
            self.info = {'failure': info}

    def get_info(self):
        return self.info
