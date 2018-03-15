import drned
import pytest

# Test connection (i.e. let drned give us the fixture 'device_raw')
def test_connect(device_raw):
    print "We're done, device is setup correctly if we get here!"

