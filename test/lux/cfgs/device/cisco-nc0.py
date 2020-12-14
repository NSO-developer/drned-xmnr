import os
import re


def _get_data(devcli):
    os.rename("/tmp/" + os.path.basename(devcli.data), devcli.data)
    return None


class Devcfg(object):
    def __init__(self, path, name):
        self.path = path
        self.name = name
        print('devcfg', path, name)

    def _get(self, what):
        with open(os.path.join(self.path, self.name + ".cfg")) as f:
            m = re.search(what, f.read(), re.MULTILINE)
        return m.group(1)

    def get_address(self):
        return '127.0.0.1'

    def get_port(self):
        return '10022'

    def get_username(self):
        return 'admin'

    def get_password(self):
        return 'admin'

    def get_prompt(self):
        return "^.*[(].+[)]# ?$"

    def get_state_machine(self):
        return {
            # After login
            "enter": [
                ("[Pp]assword:", self.get_password(), "enter"),
                ("^.*> $", "enable", "config")
            ],
            "config": [
                ("^.*# $", "config", "enter-done"),
            ],
            "enter-done": [
                (self.get_prompt(), None, "done"),
            ],
            # Get data from device
            "get": [
                (None, lambda devcli:
                 "save {}".format("/tmp/" + os.path.basename(devcli.data)),
                 "get-confirm"),
            ],
            "get-confirm": [
                ("File already exists. Overwrite[?] [[]yes,no[]]", "yes",
                 "get-confirm"),
                (self.get_prompt(), None, "get-data"),
            ],
            "get-data": [
                (None, _get_data, "done"),
            ],
            # Load data to device
            "load-merge": [
                (None, lambda devcli: "load merge {}".format(devcli.data),
                 "load-done"),
            ],
            "load": [
                (None, lambda devcli: "load override {}".format(devcli.data),
                 "load-done"),
            ],
            "load-done": [
                (self.get_prompt(), None, "done"),
            ],
            # Restore - just load initial config
            "restore": [
                (None, None, "load"),
            ],
            "restore-done": [
                (self.get_prompt(), None, "done"),
            ],
            # Exit
            "exit": [
                (None, "exit", "exit-enabled"),
            ],
            "exit-enabled": [
                (".*# $", "exit", "exit-done"),
            ],
            "exit-done": [
                ("Connection to .* closed\\.", None, "done"),
            ],
        }
