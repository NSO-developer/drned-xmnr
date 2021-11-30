# Taken and adapted from DrNED
from __future__ import print_function

from collections import namedtuple
from contextlib import closing
import itertools
import operator
import os
import re
import sys
import socket
import _ncs
from ncs import maapi, maagic

from devcli import Devcli
from devcli import DevcliException, DevcliAuthException, DevcliDeviceException


testrx = re.compile(r'(?P<set>[^:.]*)(?::(?P<index>[0-9]+))?(?:\..*)?$')
SetDesc = namedtuple('SetDesc', ['fname', 'fset', 'index'])


backup_config = 'drned-backup'


def fname_set_descriptors(fnames):
    for fname in sorted(fnames):
        m = testrx.match(fname)
        if m is None:
            print('Filename format not understood: ' + fname)
            continue
        d = m.groupdict()
        ix = 0 if d['index'] is None else d['index']
        yield SetDesc(fname=fname, fset=d['set'], index=int(ix))


def sync_from(device):
    res = device.sync_from.request()
    if not res.result:
        print('sync-from failed:', res.info)
        raise DevcliDeviceException('sync-from failed')


def save(device, target):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sck, \
            open(target, 'wb') as out:
        sid = device._backend.save_config(_ncs.maapi.CONFIG_XML,
                                          device._path + '/config')
        _ncs.stream_connect(sck, sid, 0, '127.0.0.1', _ncs.PORT)
        while True:
            data = sck.recv(1024)
            if len(data) <= 0:
                break
            out.write(data)


def group_cli2netconf(device, devcli, group):
    for desc in group:
        base = os.path.basename(os.path.splitext(desc.fname)[0])
        target = os.path.join(devcli.workdir, base + ".xml")
        print("converting", desc.fname, 'to', target)
        # Load config on device and read back
        devcli.load_config(desc.fname)
        try:
            sync_from(device)
        except BaseException:
            devcli.restore_config(backup_config)
            sync_from(device)
            raise
        save(device, target)
        print("converted", desc.fname, 'to', target)


def _cli2netconf(device, devcli, fnames):
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
    sync_from(device)


def cli2netconf(nsargs):
    fnames = nsargs.files
    try:
        with closing(Devcli(nsargs)) as devcli, \
                maapi.single_read_trans('admin', 'system') as tp:
            root = maagic.get_root(tp)
            device = root.devices.device[devcli.devname]
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
