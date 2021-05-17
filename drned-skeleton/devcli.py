# Implementation of a "device" handler that allows connecting to a device
# that suppors connections over SSH.

from __future__ import print_function

from contextlib import closing
import importlib
import inspect
import os
import pexpect
import sys
import types
from time import sleep

import drned


VERBOSE = True
INDENT = "=" * 30 + " "


if sys.version_info > (3, 0):
    pexpect_args = dict(encoding='utf-8')
    os_makedirs = os.makedirs
else:
    pexpect_args = {}

    def os_makedirs(dirname, exist_ok=False):
        """
        In Python 2.7 the argument exist_ok is not available for os.makedirs.
        """
        try:
            os.makedirs(dirname)
        except OSError:
            if not exist_ok:
                raise


class DevcliException(Exception):
    pass


class XDevice(drned.Device):
    def close(self):
        self.ncs.close()


class Devcli:
    def __init__(self, driver_file, workdir, timeout):
        self.driver_file = driver_file
        self.workdir = workdir
        self.initial_config = 'drned-init'
        self.trace = None
        self.verbose = VERBOSE
        self.timeout = timeout
        self.log_lines = 0
        self._read_device_config()

    def close(self):
        if hasattr(self, 'cli'):
            self.cli.close()

    def _find_driver(self):
        if os.path.isfile(self.driver_file):
            return
        raise DevcliException('No device definition found')

    def _read_device_config(self):
        self._find_driver()
        dfile = self.driver_file
        dirname = os.path.dirname(dfile)
        basename = os.path.basename(dfile)
        module_name = os.path.splitext(basename)
        sys.path.append(dirname)
        module = importlib.import_module(module_name)
        for m in dir(module):
            if not m.startswith("__"):
                setattr(self, m, getattr(module, m))

        self.devcfg = self.Devcfg(self.path, self.driver_file)
        self.ssh = "ssh -o StrictHostKeyChecking=no" + \
                   " -o UserKnownHostsFile=/dev/null" + \
                   " -o PasswordAuthentication=yes" + \
                   " -p %s %s@%s" % (self.devcfg.get_port(),
                                     self.devcfg.get_username(),
                                     self.devcfg.get_address())

    def _ssh(self):
        for _ in range(3):
            try:
                self.cli = pexpect.spawn(self.ssh, timeout=self.timeout,
                                         logfile=sys.stdout, **pexpect_args)
                self.interstate_one("enter")
            except Exception as exc:
                e = exc
            else:
                return self.cli
            sleep(2)
        else:
            raise e

    def _banner(self, txt):
        if self.trace:
            self.trace(INDENT + inspect.stack()[1][3] + "(%s)" % txt)

    def load_config(self, fname):
        """Send configuration to the device.
        """
        self._banner(fname)
        self.data = fname
        self.interstate(["put", "exit"])
        return self

    def get_config(self, fname):
        """Get configuration from the device.
        """
        self._banner(fname)
        self.data = fname
        try:
            os.remove(fname)
        except OSError:
            pass
        self.interstate(["get", "exit"])
        if not os.path.isfile(fname):
            raise DevcliException("Failed to get config into %s" % fname)
        return self

    def restore_config(self, fname=None):
        """Restore configuration on the device.

        If `fname` is not provided, the initial configuration is used.
        """
        if fname is None:
            fname = self.initial_config
        self._banner(fname)
        self.data = fname
        self.interstate(["restore", "exit"])
        if self.trace:
            self.trace(self.cli.before + self.cli.after)
        return self

    def clean_config(self):
        """Clean all device configuration and enter initial state.
        """
        return self.restore_config()

    def save_config(self, fname=None):
        """Save the initial configuration.
        """
        if fname is None:
            fname = self.initial_config
        self._banner(fname)
        self.data = fname
        self.interstate(["save", "exit"])
        if self.trace:
            self.trace(self.cli.before + self.cli.after)
        return self

    def interstate(self, init_states):
        """Run the state machine for all initial states.
        """
        with closing(self._ssh()):
            if isinstance(init_states, list):
                for init_state in init_states:
                    self.interstate_one(init_state)
            else:
                self.interstate_one(init_states)

    def interstate_one(self, init_state):
        """Run the state machine.
        """
        state_machine = self.devcfg.get_state_machine()
        state = init_state
        while state not in {"done", "failure"}:
            state_def = state_machine[state]
            if self.verbose:
                print("STATE: %s : %s" % (state, state_def))
            patterns = [p for (p, _, _) in state_def]
            n = 0 if patterns == [None] else self.cli.expect(patterns)
            if self.verbose and patterns != [None]:
                print("<<<< %d:\"%s\" <<<<" %
                      (n, self.cli.before + self.cli.after))
            (p, cmd, state) = state_def[n]
            if state is None:
                raise IOError("%s : %s" % (cmd, self.cli.before))
            if isinstance(cmd, types.FunctionType) \
               or isinstance(cmd, types.BuiltinFunctionType):
                cmd = cmd(self)
            if self.verbose:
                print("MATCHED '%s', SEND: '%s' -> NEXT_STATE: '%s'" %
                      (p, cmd, state))
            if cmd is not None:
                if self.verbose:
                    print(">>>> \"%s\" >>>>" % cmd)
                self.cli.sendline(cmd)
        if state == "failure":
            raise DevcliException("failed to move to state " + init_state)


def devcli_init_dirs():
    """ Initialize directories needed by DrNED device.
    Returns working directory.
    """
    os_makedirs('drned-work', exist_ok=True)
    workdir = os.path.realpath(os.environ['NC_WORKDIR'])
    os_makedirs(workdir, exist_ok=True)
    return workdir
