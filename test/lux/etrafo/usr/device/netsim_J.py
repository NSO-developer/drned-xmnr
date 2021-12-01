import os


def _get_data(devcli):
    os.rename("/tmp/" + os.path.basename(devcli.data), devcli.data)
    return None


syncfifo = "/tmp/timeout-sync.fifo"


class Devcfg(object):
    def __init__(self, path, name):
        self.path = path
        self.name = name
        self.state_file = None
        with open(syncfifo, "r") as fifo:
            self.state = fifo.read()[:-1]

    def init_params(self, devname='netsim0',
                    ip='127.0.0.1', port=12022,
                    username='admin', password='admin',
                    **args):
        self.devname = devname
        self.ip = ip
        self.port = port - 2000
        self.username = username
        self.password = password
        self.prompt = "{}@{}%$".format(self.username, self.devname)

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
                ("[Pp]assword:", self.get_password(), "enter"),
                ("^.*>$", "set paginate false", "enter-done"),
            ],
            'enter-done': [
                ("^.*>$", "config", 'prompt-done'),
            ],
            "prompt-done": [
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
                ("Error: (syntax error|bad value) on line", None, "failure"),
                (self.get_prompt(), self.put_sync, "commit"),
            ],
            "commit": [
                ("Commit complete|No modifications to commit", None,
                 "prompt-done"),
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
                 "restore-commit"),
            ],
            "restore-commit": [
                (self.get_prompt(), self.restore_sync, "commit"),
            ],
            # Exit
            "exit": [
                (None, "exit", "exit-enabled"),
            ],
            "exit-enabled": [
                (".*>$", "exit", "exit-done"),
            ],
            "exit-done": [
                ("Connection to .* closed\\.", None, "done"),
            ],
        }

    def put_sync(self, devcli):
        self.state_file = None
        if "usr03" in devcli.data:
            self.state_file = devcli.data
            if self.state == "put":
                self.sync(devcli)
        return "commit"

    def restore_sync(self, devcli):
        if self.state_file is not None and self.state == "restore":
            print('syncing restore')
            self.sync(devcli)
        return "commit"

    def sync(self, devcli):
        with open(syncfifo, 'a') as fifo:
            print('sync: {}'.format(self.state_file), file=fifo)
        with open(syncfifo, 'r') as fifo:
            fifo.read()
