from contextlib import contextmanager
import importlib
from pytest import raises
from unittest.mock import patch


def mock_check_import(mocker):
    def test_fun_mock(test_fun):
        def fun(self):
            check_mod = importlib.import_module('drned_xmnr.check_action')
            check = check_mod.check
            with mocker():
                test_fun(self, check, check_mod.XmnrCheckException)
        return fun
    return test_fun_mock


@contextmanager
def bad_py_version():
    with patch('sys.version_info', new=(3, 5)):
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


@contextmanager
def missing_package():
    with patch('importlib.import_module', new=ImportMock(True)):
        yield


@contextmanager
def old_package():
    with patch('importlib.import_module', new=ImportMock(False)):
        yield


@contextmanager
def no_patches():
    yield


class TestChecks:
    @mock_check_import(bad_py_version)
    def test_version_check(self, check, XmnrCheckException):
        with raises(XmnrCheckException, match='Required Python 3.6 or newer'):
            check()

    @mock_check_import(missing_package)
    def test_missing_package_check(self, check, XmnrCheckException):
        with raises(XmnrCheckException, match='XMNR cannot run without'):
            check()

    @mock_check_import(old_package)
    def test_old_package_check(self, check, XmnrCheckException):
        with raises(XmnrCheckException, match='Required pytest>=3.0'):
            check()

    @mock_check_import(no_patches)
    def test_succeed(self, check, _ignored):
        check()
