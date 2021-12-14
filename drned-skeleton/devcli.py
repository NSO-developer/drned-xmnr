# Implementation of a "device" handler that allows connecting to a device
# that suppors connections over SSH.

from __future__ import print_function

import argparse
from contextlib import closing
import importlib
import inspect
import os
import pexpect
import sys
from time import sleep

import socket
import _ncs
from ncs import maapi, maagic


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
    def __str__(self):
        return 'devcli exception: ' + str(self.args[0])


class DevcliAuthException(DevcliException):
    def __str__(self):
        return "failed to authenticate"


class DevcliDeviceException(DevcliException):
    def __str__(self):
        return 'device communication failure: ' + str(self.args[0])


class NcsDevice:
    def __init__(self, devname):
        self.devname = devname

    def __enter__(self):
        self.tc = maapi.single_read_trans('admin', 'system')
        self.tp = self.tc.__enter__()
        root = maagic.get_root(self.tp)
        self.device = root.devices.device[self.devname]
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self.tc.__exit__(exc_type, exc_value, traceback)

    def close(self):
        self.tp.maapi.close()

    def sync_from(self):
        res = self.device.sync_from.request()
        if not res.result:
            print('sync-from failed:', res.info)
            raise DevcliException('sync-from failed')

    def save(self, target):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sck, \
                open(target, 'wb') as out:
            path = self.device._path + '/config'
            sid = self.device._backend.save_config(_ncs.maapi.CONFIG_XML, path)
            _ncs.stream_connect(sck, sid, 0, '127.0.0.1', _ncs.PORT)
            while True:
                data = sck.recv(1024)
                if len(data) <= 0:
                    break
                out.write(data)


class Devcli:
    @staticmethod
    def argparser():
        parser = argparse.ArgumentParser(description='Devcli arguments')
        parser.add_argument('--driver', '-d')
        parser.add_argument('--workdir', '-w')
        parser.add_argument('--devname', '-n')
        parser.add_argument('--username', '-u', default='admin')
        parser.add_argument('--password', '-p', default='admin')
        parser.add_argument('--port', '-P', type=int)
        parser.add_argument('--ip', '-i')
        parser.add_argument('--timeout', '-t', type=int, default=120)
        return parser

    def __init__(self, nsargs):
        self.cli = None
        self.params = {}
        for parname in ['devname', 'username', 'password', 'port', 'ip']:
            self.params[parname] = getattr(nsargs, parname)
        self.driver = nsargs.driver
        self.workdir = nsargs.workdir
        self.devname = nsargs.devname
        self.timeout = nsargs.timeout
        self.initial_config = 'drned-init'
        self.trace = None
        self.verbose = VERBOSE
        self.log_lines = 0
        devcli_init_dirs(self.workdir)
        self._read_device_config()

    def close(self):
        if self.cli is not None:
            self.cli.close()

    def _find_driver(self):
        if os.path.isfile(self.driver):
            return
        raise DevcliException('No device definition found')

    def _read_device_config(self):
        self._find_driver()
        dfile = self.driver
        dirname = os.path.dirname(dfile)
        basename = os.path.basename(dfile)
        module_name = os.path.splitext(basename)[0]
        sys.path.append(dirname)
        module = importlib.import_module(module_name)
        for m in dir(module):
            if not m.startswith("__"):
                setattr(self, m, getattr(module, m))

        self.devcfg = self.Devcfg(dirname, dfile)
        if hasattr(self.devcfg, 'init_params'):
            self.devcfg.init_params(**self.params)
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
            except DevcliAuthException:
                # no reason to retry
                raise
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

    def restore_config(self, fname):
        """Restore configuration on the device.

        If `fname` is not provided, the initial configuration is used.
        """
        self._banner(fname)
        self.data = fname
        self.interstate(["restore", "exit"])
        if self.trace:
            self.trace(self.cli.before + self.cli.after)
        return self

    def clean_config(self):
        """Clean all device configuration and enter initial state.
        """
        return self.restore_config(self.initial_config)

    def backup_config(self):
        """Save the device initial configuration.
        """
        return self.save_config(self.initial_config)

    def save_config(self, fname):
        """Save the initial configuration.
        """
        self._banner(fname)
        self.data = fname
        self.interstate(["save", "exit"])
        if self.trace:
            self.trace(self.cli.before + self.cli.after)
        return self

    def interstate(self, init_states):
        """Run the state machine for all initial states.
        """
        try:
            with closing(self._ssh()):
                try:
                    if isinstance(init_states, list):
                        for init_state in init_states:
                            self.interstate_one(init_state)
                    else:
                        self.interstate_one(init_states)
                except pexpect.exceptions.ExceptionPexpect as exc:
                    raise DevcliException(exc)
        except pexpect.exceptions.ExceptionPexpect as exc:
            # this happens when the device timed out while logging in
            # or even refused the connection - no reason to keep on
            # trying
            raise DevcliDeviceException(exc)

    def interstate_one(self, init_state):
        """Run the state machine.
        """
        state_machine = self.devcfg.get_state_machine()
        state = init_state
        while state not in {"done", "authfailed", "failure"}:
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
            if callable(cmd):
                cmd = cmd(self)
            if self.verbose:
                print("MATCHED '%s', SEND: '%s' -> NEXT_STATE: '%s'" %
                      (p, cmd, state))
            if cmd is not None:
                if self.verbose:
                    print(">>>> \"%s\" >>>>" % cmd)
                self.cli.sendline(cmd)
        if state == "authfailed":
            raise DevcliAuthException()
        if state == "failure":
            raise DevcliException("failed to move to state " + init_state)


def devcli_init_dirs(workdir):
    """ Initialize directories needed by DrNED device.
    Returns working directory.
    """
    os_makedirs('drned-work', exist_ok=True)
    os_makedirs(workdir, exist_ok=True)
    return workdir
