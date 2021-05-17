from __future__ import print_function

from contextlib import closing
import sys

from devcli import Devcli, XDevice, devcli_init_dirs


def _load_default_config(nso_device, target_device):
    target_device.restore_config()
    nso_device.sync_from()


def load_default_config(dev_name, driver_file, timeout, *args):
    workdir = devcli_init_dirs()

    def init_nso_dev():
        return closing(XDevice(dev_name))

    def init_cli_dev():
        return closing(Devcli(driver_file, workdir, int(timeout)))

    with init_nso_dev() as nso_device, init_cli_dev() as target_device:
        _load_default_config(nso_device, target_device)


# Usage: load-default-config.py netconf-device driver-file file-path
#
#  - device-name: device name; the device must be configured by DrNED/XMNR
#  - driver-file: device driver file to be executed to do the config reload
#  - timeout: operation execution time limit to perform the request
#
#  First, the CLI device driver in the form <name>.py is looked up:
#
#  * in the first file's directory
#  * its device/ subdirectory
#  * in the current directory
#  * in its device/ subdirectory
#
#  If one of the above succeeds, the driver is loaded. It then loads previously
#  stored default configuration file on a device using it's native CLI,
#  to return device to a default config state.

if __name__ == "__main__":
    load_default_config(*sys.argv[1:])
