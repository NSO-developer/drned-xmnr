from pytest import fixture, raises
from drned_xmnr.check_action import XmnrCheck, XmnrCheckException
import sys
if sys.version_info < (3, 0):
    from mock import patch
    ModuleNotFoundError = ImportError
else:
    from unittest.mock import patch


@fixture
def bad_py_version():
    with patch('sys.version_info', new=(3, 4)):
        yield


class ImportMock:
    """Pretend to either fail the import or import an old version.
    """
    def __init__(self, fail, modname='pytest'):
        self.fail = fail
        self.modname = modname
        self.__version__ = '2.5'

    def __call__(self, modname):
        if self.fail:
            raise ModuleNotFoundError
        if modname == self.modname:
            return self


@fixture
def missing_package():
    with patch('importlib.import_module', new=ImportMock(True)):
        yield


@fixture
def old_package():
    with patch('importlib.import_module', new=ImportMock(False)):
        yield


class TestChecks:
    def test_version_check(self, bad_py_version):
        with raises(XmnrCheckException, match='Required Python 2.7 or 3.5 or newer'):
            XmnrCheck().setup()

    def test_missing_package_check(self, missing_package):
        with raises(XmnrCheckException, match='XMNR cannot run without'):
            XmnrCheck().setup()

    def test_old_package_check(self, old_package):
        with raises(XmnrCheckException, match='Required pytest>=3.0'):
            XmnrCheck().setup()

    def test_succeed(self):
        XmnrCheck().setup()
