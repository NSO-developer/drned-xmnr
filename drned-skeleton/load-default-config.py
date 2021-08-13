from __future__ import print_function

from contextlib import closing

from devcli import Devcli, XDevice, DevcliAuthException


def _load_default_config(nso_device, target_device):
    try:
        target_device.restore_config()
        nso_device.sync_from()
    except DevcliAuthException:
        print('failed to authenticate')


def load_default_config(nsargs):
    def init_cli_dev():
        return closing(Devcli(nsargs))

    def init_nso_dev(devcli):
        return closing(XDevice(devcli.devname))

    with init_cli_dev() as target_device, \
            init_nso_dev(target_device) as nso_device:
        _load_default_config(nso_device, target_device)


# Usage: load-default-config.py [Devcli options]
#
#  run "load-default-config.py --help" to get more details

if __name__ == "__main__":
    parser = Devcli.argparser()
    load_default_config(parser.parse_args())
