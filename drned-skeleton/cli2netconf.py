# Taken and adapted from DrNED

import importlib
import inspect
import os
import pexpect
import sys
import types
from contextlib import closing

import drned

VERBOSE = True
INDENT = "=" * 30 + " "


class DevcliException(Exception):
    pass


class Devcli:
    def __init__(self, name, basepath, workdir):
        self.name = name
        self.basepath = basepath
        self.workdir = workdir
        self.initial_config = os.path.join(self.workdir, 'initial-config.txt')
        self.trace = None
        self.verbose = VERBOSE
        self.log_lines = 0
        self._read_config()

    def close(self):
        if hasattr(self, 'cli'):
            self.cli.close()

    def _find_driver(self):
        for base in [self.basepath, '.']:
            for subpath in ['.', 'device']:
                self.path = os.path.join(base, subpath)
                d = os.path.join(self.path, self.name + '.py')
                print(f'using {d}: {os.path.realpath(d)}')
                if os.path.isfile(d):
                    print('found')
                    return
        raise DevcliException('No device definition found')

    def _read_config(self):
        self._find_driver()
        sys.path.append(self.path)
        module = importlib.import_module(self.name)
        for m in dir(module):
            if not m.startswith("__"):
                setattr(self, m, getattr(module, m))

        self.devcfg = self.Devcfg(self.path, self.name)
        self.ssh = "ssh -o StrictHostKeyChecking=no" + \
                   " -o UserKnownHostsFile=/dev/null" + \
                   " -o PasswordAuthentication=yes" + \
                   " -p %s %s@%s" % (self.devcfg.get_port(),
                                     self.devcfg.get_username(),
                                     self.devcfg.get_address())

    def _ssh(self):
        for i in range(3):
            try:
                self.cli = pexpect.spawn(self.ssh, timeout=3, logfile=sys.stdout, encoding='utf-8')
            except Exception as exc:
                e = exc
            else:
                break
        else:
            raise e

    def _banner(self, txt):
        if self.trace:
            self.trace(INDENT + inspect.stack()[1][3] + "(%s)" % txt)

    def load_config(self, merge, fname):
        """Send configuration to the device.

        Args:
        Returns:
            self
        """
        self._banner(fname)
        self.data = fname
        load_state = "load-merge" if merge else "load"
        self.interstate(["enter", load_state, "exit"])
        return self

    def get_config(self, fname):
        """Get configuration from the device.

        Args:
        Returns:
            self
        """
        self._banner(fname)
        self.data = fname
        try:
            os.remove(fname)
        except OSError:
            pass
        self.interstate(["enter", "get", "exit"])
        if not os.path.isfile(fname):
            raise DevcliException("Failed to get config into %s" % fname)
        return self

    def restore_config(self, fname=None):
        """Restore configuration on the device.

        Args:
        Returns:
            self
        """
        if fname is None:
            fname = self.initial_config
        self._banner(fname)
        self.data = fname
        self.interstate(["enter", "restore", "exit"])
        if self.trace:
            self.trace(self.cli.before + self.cli.after)
        return self

    def clean_config(self):
        """Clean all device configuration and enter initial state.

        Args:
        Returns:
            self
        """
        return self.restore_config()

    def save_config(self):
        """Save the initial configuration.
        """
        self.get_config(self.initial_config)

    def interstate(self, init_states, new_ssh=True):
        if isinstance(init_states, list):
            for init_state in init_states:
                self.interstate_one(init_state, new_ssh)
                new_ssh = False
        else:
            self.interstate_one(init_state, new_ssh)

    def interstate_one(self, init_state, new_ssh=True):
        """Run a state machine.

        Args:
        Returns:
            self
        """
        if new_ssh:
            self._ssh()
        state_machine = self.devcfg.get_state_machine()
        state = init_state
        while state != "done":
            state_def = state_machine[state]
            if self.verbose:
                print("STATE: %s : %s" % (state, state_def))
            patterns = [p for (p, _, _) in state_def]
            n = 0 if patterns == [None] else self.cli.expect(patterns)
            if self.verbose and patterns != [None]:
                print("<<<< %d:\"%s\" <<<<" % (n, self.cli.before + self.cli.after))
            (p, cmd, state) = state_def[n]
            if state is None:
                raise IOError("%s : %s" % (cmd, self.cli.before))
            if isinstance(cmd, types.FunctionType) \
               or isinstance(cmd, types.BuiltinFunctionType):
                cmd = cmd(self)
            if self.verbose:
                print("MATCHED '%s', SEND: '%s' -> NEXT_STATE: '%s'" % (p, cmd, state))
            if cmd is not None:
                if self.verbose:
                    print(">>>> \"%s\" >>>>" % cmd)
                self.cli.sendline(cmd)


class XDevice(drned.Device):
    def close(self):
        self.ncs.close()


def _cli2netconf(device, devcli, merge, fnames):
    # Save initial CLI state
    devcli.save_config()
    # TODO: no support for sets
    for fname in fnames:
        base = os.path.basename(os.path.splitext(fname)[0])
        target = os.path.join(devcli.workdir, base + ".xml")
        print("converting", fname, 'to', target)
        # Load config on device and read back
        devcli.load_config(merge, fname)
        try:
            device.sync_from()
        except Exception:
            devcli.clean_config()
            device.sync_from()
            raise
        device.save(target, fmt="xml")
        devcli.clean_config()
    devcli.clean_config()
    device.sync_from()


def cli2netconf(devname, devcliname, *args):
    merge = args[0] == '-m'
    fnames = args[1:] if merge else args
    basedir = os.path.realpath(os.path.dirname(fnames[0]))
    workdir = os.path.realpath(os.environ['NC_WORKDIR'])
    os.makedirs(workdir, exist_ok=True)
    os.makedirs('drned-work', exist_ok=True)  # device needs that
    with closing(XDevice(devname)) as device, \
         closing(Devcli(devcliname, basedir, workdir)) as devcli:
        _cli2netconf(device, devcli, merge, fnames)


# Usage: cli2netconf.py netconf-device cli-device [-m] [files]
#
#  netconf-device: device name; the device must be configured by Drned/XMNR
#
#  cli-device: device name; its behavior is given by "device drivers"
#
#  files: file names
#
#  First, the CLI device driver in the form <name>.py is looked up:
#
#  * in the first file's directory
#  * its device/ subdirectory
#  * in the current directory
#  * in its device/ subdirectory
#
#  If one of the above succeeds, the driver is loaded and its Devcfg class is
#  instantiated with two arguments: the path that has been found in the process
#  above, and the device name.  The driver may use other files, if needed.
#
#  It then converts (or tries to) all files to a XML/NETCONF form and saves them
#  to the same directory, under the same name with the extension .xml.

if __name__ == "__main__":
    cli2netconf(*sys.argv[1:])
