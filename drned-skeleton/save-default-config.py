from __future__ import print_function

from contextlib import closing

from devcli import Devcli, XDevice


def _save_default_config(nso_device, target_device):
    target_device.save_config()
    #do we want nso_device.sync_to/from() here?

def save_default_config(nsargs):
    def init_cli_dev():
        return closing(Devcli(nsargs))

    def init_nso_dev(devcli):
        return closing(XDevice(devcli.devname))

    with init_cli_dev() as target_device, \
            init_nso_dev(target_device) as nso_device:
        _save_default_config(nso_device, target_device)


# Usage: save-default-config.py [Devcli options]
#
#  run "save-default-config.py --help" to get more details

if __name__ == "__main__":
    parser = Devcli.argparser()
    save_default_config(parser.parse_args())
