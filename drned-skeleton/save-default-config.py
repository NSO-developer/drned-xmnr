from __future__ import print_function

from argparse import Namespace
from contextlib import closing

from devcli import Devcli, NcsDevice


def _save_default_config(nso_device: NcsDevice, target_device: Devcli) -> None:
    target_device.backup_config()


def save_default_config(nsargs: Namespace) -> None:
    def init_cli_dev() -> closing[Devcli]:
        return closing(Devcli(nsargs))

    def init_nso_dev(devcli: Devcli) -> NcsDevice:
        return NcsDevice(devcli.devname)

    with init_cli_dev() as target_device, \
            init_nso_dev(target_device) as nso_device:
        _save_default_config(nso_device, target_device)


# Usage: save-default-config.py [Devcli options]
#
#  run "save-default-config.py --help" to get more details

if __name__ == "__main__":
    parser = Devcli.argparser()
    save_default_config(parser.parse_args())
