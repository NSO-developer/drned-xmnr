# Taken and adapted from DrNED
from __future__ import print_function

from collections import namedtuple
from contextlib import closing
import itertools
import operator
import os
import re
import sys

from devcli import Devcli, XDevice
from devcli import DevcliException, DevcliAuthException, DevcliDeviceException


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
    backup_config = 'drned-backup'
    devcli.save_config(backup_config)
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
        except (DevcliAuthException, DevcliDeviceException):
            raise
        except BaseException as e:
            print('failed to convert group', groupname)
            print('exception:', e)
        devcli.restore_config(backup_config)
    device.sync_from()


def cli2netconf(nsargs):
    fnames = nsargs.files
    try:
        with closing(Devcli(nsargs)) as devcli, \
                closing(XDevice(devcli.devname)) as device:
            _cli2netconf(device, devcli, fnames)
    except DevcliException as e:
        print()  # make sure the exception is on a new line
        print(e)
        return -1
    return 0


# Usage: cli2netconf.py [Devcli options] [files]
#
#  files: file names
#
#  run "cli2netconf.py --help" to get more details
#
#  A device driver is loaded and its Devcfg class is instantiated with
#  two arguments: the path of the driver and the device name.  The
#  driver may use other files, if needed.
#
#  It then converts (or tries to) all files to a XML/NETCONF form and saves
#  them to the same directory, under the same name with the extension .xml.

if __name__ == "__main__":
    parser = Devcli.argparser()
    parser.add_argument('files', nargs='*')
    nsargs = parser.parse_args()
    sys.exit(cli2netconf(nsargs))
