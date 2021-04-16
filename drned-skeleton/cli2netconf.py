# Taken and adapted from DrNED
from __future__ import print_function

from collections import namedtuple
from contextlib import closing
import itertools
import operator
import os
import re
import sys
from time import sleep

import drned

from devcli import *


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
        except BaseException as e:
            print('failed to convert group', groupname)
            print('exception:', e)
        devcli.clean_config()
    device.sync_from()


def cli2netconf(devname, driver_name, *args):
    args = list(args)
    if args[0] == '-t':
        timeout = int(args[1])
        del args[0:2]
    else:
        timeout = 120
    fnames = args
    module_path = os.path.realpath(os.path.dirname(fnames[0]))
    workdir = os.path.realpath(os.environ['NC_WORKDIR'])
    os_makedirs(workdir, exist_ok=True)
    os_makedirs('drned-work', exist_ok=True)  # device needs that
    with closing(XDevice(devname)) as device, \
            closing(Devcli(driver_name, module_path, workdir, timeout)) as devcli:
        _cli2netconf(device, devcli, fnames)


# Usage: cli2netconf.py netconf-device driver-name [-t timeout] [files]
#
#  netconf-device: device name; the device must be configured by Drned/XMNR
#
#  driver-name: behavior is given by "device drivers"
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
