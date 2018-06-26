import drned
import pytest
import common.test_here as common
import re
config = {}

def simple_load(name):
    def f(p):
        p.device.rload("simple_tests/%s" % name)
        p.device.dry_run(fname="drned-work/drned-load.txt")
        p.device.commit()
        return True
    return f

config["test-sequence-1"] = [
    simple_load("sample-day0.txt"),
    simple_load("sample-day1.txt"),
    # Here we can do validations of dry-run after day1 is applied
    lambda p: True
]

# Example of usage of config-chunks with validity checks of dry-run output
config["test-sequence-2"] = [
    """
    some config here
    some config here
    some config here
    some config here
    """,
    """
    some more config here
    some more config here
    some more config here
    some more config here
    """,
    lambda p: (p.drned_load.count("this line must occur 3 times") == 3),
    lambda p: (not ("this line must not occur" in p.drned_load)),
    lambda p: (p.drned_load.index("this line must occur before") <
               p.drned_load.index("this line must occur after")),
]

@pytest.mark.parametrize("name", config)
def test_here_ok(device, name):
    common.test_here_single(device, config, name, dry_run=True)
