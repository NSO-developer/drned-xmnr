# Taken and adapted from DrNED
from collections import namedtuple
from contextlib import closing
import itertools
import operator
import os
import re
import sys

from devcli import Devcli, NcsDevice
from devcli import DevcliException, DevcliAuthException, DevcliDeviceException

from typing import Iterator, List, Pattern
from argparse import Namespace


testrx: Pattern[str] = re.compile(r'(?P<set>[^:.]*)(?::(?P<index>[0-9]+))?(?:\..*)?$')
SetDesc = namedtuple('SetDesc', ['fname', 'fset', 'index'])


backup_config = 'drned-backup'


def fname_set_descriptors(fnames: List[str]) -> Iterator[SetDesc]:
    for fname in sorted(fnames):
        m = testrx.match(fname)
        if m is None:
            print('Filename format not understood: ' + fname)
            continue
        d = m.groupdict()
        ix = 0 if d['index'] is None else d['index']
        yield SetDesc(fname=fname, fset=d['set'], index=int(ix))


def group_cli2netconf(device: NcsDevice, devcli: Devcli, group: List[SetDesc]) -> None:
    for desc in group:
        base = os.path.basename(os.path.splitext(desc.fname)[0])
        target = os.path.join(devcli.workdir, base + ".xml")
        print("converting", desc.fname, 'to', target)
        # Load config on device and read back
        devcli.load_config(desc.fname)
        try:
            device.sync_from()
        except BaseException:
            devcli.restore_config(backup_config)
            device.sync_from()
            raise
        device.save(target)
        print("converted", desc.fname, 'to', target)


def _cli2netconf(device: NcsDevice, devcli: Devcli, fnames: List[str]) -> None:
    # Save initial CLI state
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
            # these are critical - don't try to recover
            raise
        except DevcliException as e:
            print('failed to convert group', groupname)
            print('exception:', e)
        try:
            devcli.restore_config(backup_config)
        except DevcliException as e:
            # this is serious, the device is left configured somehow
            print('failed to restore device config after group', groupname)
            print('exception:', e)
            raise
    device.sync_from()


def cli2netconf(nsargs: Namespace) -> int:
    fnames = nsargs.files
    try:
        with closing(Devcli(nsargs)) as devcli, \
                NcsDevice(devcli.devname) as device:
            _cli2netconf(device, devcli, fnames)
    except DevcliException as e:
        print()  # make sure the exception is on a new line
        print(e)
        return -1
    except BaseException as e:
        if e.__class__.__name__ == 'Failed':
            # result of `pytest.fail()` call - DrNED does that if NSO
            # or the device responds in unexpected ways
            print()
            print('DrNED thrown a pytest failure')
            return -1
        raise  # give up
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
