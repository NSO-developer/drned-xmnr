import drned
import pytest

# Test sync-from
def test_load_and_sync(device_raw):
    device = device_raw
    device.cmd("devices device %s sync-from" % device.name)
