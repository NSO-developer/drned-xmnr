from __future__ import print_function

from contextlib import closing
import os
import sys

from devcli import *


def _load_default_config(nso_device, target_device):
    target_device.restore_config()
    nso_device.sync_from()


def load_default_config(*args):
    args = list(args)
    assert len(args) == 2
    dev_name, driver_name = args
    timeout = 120 # TODO - should be global parameter of device/actions
    # TODO - should not be mandatory params?
    module_path = None
    workdir = None
    nso_device = closing(XDevice(dev_name))
    target_device = closing(Devcli(driver_name, module_path, workdir, timeout))
    with nso_device, target_device:
        _load_default_config(nso_device, target_device)


# Usage: load-default-config.py netconf-device driver-name file-path
#
#  - device-name: device name; the device must be configured by DrNED/XMNR
#  - driver-module: device driver file to be executed to do the config reload
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
