import drned
import pytest
import common.test_incomplete as common

config = {}

config["CMD_FOOBAR"] = (
    [
        # Prefix
    ],
    [
        # Avoid
    ],
    [
        # Test
    ]
)

@pytest.mark.parametrize("name", config)
def test_incomplete_single(device, name, iteration):
    common.test_incomplete_single(device, config, name, iteration)

def test_incomplete_union(device, iteration):
    common.test_incomplete_union(device, config, iteration)
