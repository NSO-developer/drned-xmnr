import drned
import glob
import os
import pytest
import common.test_common as common

SCOPE = "session"


def pytest_addoption(parser):
    parser.addoption("--all", action="store_true", dest="all",
                     help="show all output")
    parser.addoption("--argv", action="append", dest="argv",
                     help="argument vector to pass to test")
    parser.addoption("--device", action="store", dest="device",
                     help="select device to run test on")
    parser.addoption("--diff", action="store", dest="diff",
                     help="run diff against given tag/commit (LAST means last version)")
    parser.addoption("--end-op", action="append", dest="end_op",
                     help="end operations to perform")
    parser.addoption("--exclude", action="append", dest="exclude",
                     help="exclude this from the operation")
    parser.addoption("--fname", action="append", dest="fname",
                     help="specify filename")
    parser.addoption("--include", action="append", dest="include",
                     help="include this in the operation")
    parser.addoption("--init", action="append", dest="init",
                     help="init file to load before the test")
    parser.addoption("--init-op", action="append", dest="init_op",
                     help="init file operations to perform")
    parser.addoption("--iteration", action="append", dest="iteration",
                     help="select iterations to run")
    parser.addoption("--op", action="append", dest="op",
                     help="operations to perform")
    parser.addoption("--ordered", choices=["true", "false"], default="true",
                     help="how to order config files (fnames)"),
    parser.addoption("--root", action="store", dest="root",
                     help="select traversal root")
    parser.addoption("--use", action="append", dest="use",
                     help="add drned use_xxx parameter")
    parser.addoption("--yangpath", action="append", dest="yangpath",
                     help="specify colon-separated path list", default=[])


def pytest_generate_tests(metafunc):
    # Traverse for config file list
    def get_filenames():
        filenames = []
        for root,dirs,files in os.walk(".."):
            if "/drned-" in root:
                # Do not traverse drned dirs
                del dirs[:]
            else:
                for f in files:
                    if os.path.splitext(f)[1] in [".cfg", ".txt", ".xml", ".init"]:
                        fn = (os.path.join(root, f)
                              .replace("../%s/" % os.path.basename(os.getcwd()), ""))
                        filenames.append(fn)
        return filenames

    # Look for template files
    if "template" in metafunc.fixturenames:
        filenames = get_filenames()
        if filenames:
            metafunc.parametrize("template", filenames, ids=os.path.basename,
                                 scope=SCOPE)

    # Look for fname files
    if "fname" in metafunc.fixturenames:
        if not os.path.isdir("drned-work"):
            os.mkdir("drned-work")
        # List all functions that use the fname fixture
        with open("drned-work/fname-func.tmp", "a") as f:
            f.write(metafunc.function.__name__ + "\n")
        # Write file list if not already done
        if not os.path.isfile("drned-work/fname-file.tmp"):
            with open("drned-work/fname-file.tmp", "w") as f:
                f.write("\n".join(get_filenames()) + "\n")


def none(p):
    return None if p == "none" else p


def sh(cmd):
    return common.check_output(cmd)


def rmf(p):
    try:
        os.remove(p)
    except OSError:
        pass


def touch(p):
    with open(p, "w"):
        pass


dual_mode = {
    "reread":    ["", "-reread", ""],
}


@pytest.fixture(scope=SCOPE)
def device(request):
    devname = request.config.getoption("--device")
    if devname == None:
        pytest.fail("Please enter a device name using the --device " +
                    "command-line parameter")
    # Time to create device
    use = request.config.getoption("--use")
    device = drned.Device(devname, use=use, request=request)
    device.trace("\n%s\n" % request._pyfuncitem.name)
    # Save state in XML to be able to restore reliably
    device.save("drned-work/before-session.xml", fmt="xml")
    # Also save in CLI format to make it easier to compare
    device.save("drned-work/before-session.cfg")

    yield device

    # Restore device to initial state
    device.restore()
    if device.failed_states:
        print('Failed states:', device.failed_states)


@pytest.fixture(scope=SCOPE)
def device_raw(request):
    devname = request.config.getoption("--device")
    if devname == None:
        pytest.fail("Please enter a device name using the --device " +
                    "command-line parameter")
    use = request.config.getoption("--use")
    device = drned.Device(devname, use=use)
    device.trace("\n%s\n" % request._pyfuncitem.name)
    yield device


@pytest.fixture(scope=SCOPE)
def yangpath(request):
    yield request.config.getoption("--yangpath")


@pytest.fixture(scope=SCOPE)
def ordered(request):
    option = request.config.getoption("--ordered")
    yield "true" if option is None else option


@pytest.fixture(scope=SCOPE)
def iteration(request):
    iterargs = request.config.getoption("--iteration")
    iterlist = []
    if iterargs:
        for iterarg in iterargs:
            for item in iterarg.split(","):
                if "-" in item:
                    x,y = item.split("-")
                    iterlist.extend(range(int(x), int(y)+1))
                else:
                    iterlist.append(int(item))
    else:
        iterlist = range(0, 100)
    yield iterlist


@pytest.fixture(scope=SCOPE)
def all(request):
    yield request.config.getoption("--all")


@pytest.fixture(scope=SCOPE)
def diff(request):
    yield request.config.getoption("--diff")


@pytest.fixture(scope=SCOPE)
def devname(request):
    yield request.config.getoption("--device")


@pytest.fixture(scope=SCOPE)
def argv(request):
    yield request.config.getoption("--argv")


@pytest.fixture(scope=SCOPE)
def end_op(request):
    yield request.config.getoption("--end-op")


@pytest.fixture(scope=SCOPE)
def exclude(request):
    yield request.config.getoption("--exclude")


@pytest.fixture(scope=SCOPE)
def fname(request):
    files = []
    fname = request.config.getoption("--fname")
    if fname:
        for fn in fname:
            if not fn.endswith("~"):
                files.extend(glob.glob(fn.replace("~", "-")))
    yield files


@pytest.fixture(scope=SCOPE)
def include(request):
    yield request.config.getoption("--include")


@pytest.fixture(scope=SCOPE)
def init(request):
    yield request.config.getoption("--init")


@pytest.fixture(scope=SCOPE)
def init_op(request):
    yield request.config.getoption("--init-op")


@pytest.fixture(scope=SCOPE)
def op(request):
    yield request.config.getoption("--op")


@pytest.fixture(scope=SCOPE)
def root(request):
    yield request.config.getoption("--root")


@pytest.fixture(scope=SCOPE)
def use(request):
    yield request.config.getoption("--use")
