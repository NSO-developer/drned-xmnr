# Taken and adapted from DrNED
from __future__ import print_function

from collections import namedtuple
from contextlib import closing
import importlib
import inspect
import itertools
import operator
import os
import pexpect
import re
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


class Devcli:
    def __init__(self, name, basepath, workdir, timeout):
        self.name = name
        self.basepath = basepath
        self.workdir = workdir
        self.initial_config = 'drned-init'
        self.trace = None
        self.verbose = VERBOSE
        self.timeout = timeout
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
                if os.path.isfile(d):
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
                self.interstate_one(init_state)

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


class XDevice(drned.Device):
    def close(self):
        self.ncs.close()


testrx = re.compile(r'(?P<set>[^:.]*)(?::(?P<index>[0-9]+))?(?:\..*)?$')
SetDesc = namedtuple('SetDesc', ['fname', 'fset', 'index'])


def fname_set_descriptors(fnames):
    for fname in sorted(fnames):
        m = testrx.match(fname)
        if m is None:
            print('Filename format not understood: ' + fname)
            continue
        d = m.groupdict()
        ix = 0 if d['index'] is None else d['index']
        yield SetDesc(fname=fname, fset=d['set'], index=int(ix))


def group_cli2netconf(device, devcli, group):
    for desc in group:
        base = os.path.basename(os.path.splitext(desc.fname)[0])
        target = os.path.join(devcli.workdir, base + ".xml")
        print("converting", desc.fname, 'to', target)
        # Load config on device and read back
        devcli.load_config(desc.fname)
        try:
            device.sync_from()
        except BaseException:
            devcli.clean_config()
            device.sync_from()
            raise
        device.save(target, fmt="xml")
        print("converted", desc.fname, 'to', target)


def _cli2netconf(device, devcli, fnames):
    # Save initial CLI state
    devcli.save_config()
    namegroups = itertools.groupby(fname_set_descriptors(fnames),
                                   key=operator.attrgetter('fset'))
    for _, group in namegroups:
        sgroup = sorted(group, key=operator.attrgetter('index'))
        groupname = sgroup[0].fset
        try:
            group_cli2netconf(device, devcli, sgroup)
        except KeyboardInterrupt:
            print('Keyboard interrupt, abort')
            raise
        except BaseException as e:
            print('failed to convert group', groupname)
            print('exception:', e)
        devcli.clean_config()
    device.sync_from()


def cli2netconf(devname, devcliname, *args):
    args = list(args)
    if args[0] == '-t':
        timeout = int(args[1])
        del args[0:2]
    else:
        timeout = 120
    fnames = args
    basedir = os.path.realpath(os.path.dirname(fnames[0]))
    workdir = os.path.realpath(os.environ['NC_WORKDIR'])
    os_makedirs(workdir, exist_ok=True)
    os_makedirs('drned-work', exist_ok=True)  # device needs that
    with closing(XDevice(devname)) as device, \
            closing(Devcli(devcliname, basedir, workdir, timeout)) as devcli:
        _cli2netconf(device, devcli, fnames)


# Usage: cli2netconf.py netconf-device cli-device [-t timeout] [files]
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
#  It then converts (or tries to) all files to a XML/NETCONF form and saves
#  them to the same directory, under the same name with the extension .xml.

if __name__ == "__main__":
    cli2netconf(*sys.argv[1:])
