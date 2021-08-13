import os


def _get_data(devcli):
    os.rename("/tmp/" + os.path.basename(devcli.data), devcli.data)
    return None


class Devcfg(object):
    def __init__(self, path, name):
        self.path = path
        self.name = name

    def init_params(self, devname='netsim0',
                    ip='127.0.0.1', port=12022,
                    username='admin', password='admin',
                    **args):
        self.devname = devname
        self.ip = ip
        self.port = port - 2000
        self.username = username
        self.password = password
        self.prompt = "{}[(].+[)]# ?$".format(self.devname)

    def get_address(self):
        return self.ip

    def get_port(self):
        return self.port

    def get_username(self):
        return self.username

    def get_password(self):
        return self.password

    def get_prompt(self):
        return self.prompt

    def get_state_machine(self):
        return {
            # After login
            "enter": [
                ("Permission denied, please try again", None, "authfailed"),
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
                 "save /tmp/{}".format(os.path.basename(devcli.data)),
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
            "put": [
                (None, lambda devcli: "load merge {}".format(devcli.data),
                 "put-done"),
            ],
            "put-done": [
                (self.get_prompt(), None, "done"),
            ],
            # Save the initial configuration
            "save": [
                (None,
                 lambda devcli: "save /tmp/{}".format(devcli.data),
                 "save-confirm"),
            ],
            "save-confirm": [
                ("File already exists. Overwrite[?] [[]yes,no[]]", "yes",
                 "save-confirm"),
                (self.get_prompt(), None, "done"),
            ],
            # Restore - just load the initial config
            "restore": [
                (None,
                 lambda devcli: "load override /tmp/{}".format(devcli.data),
                 "restore-done"),
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
