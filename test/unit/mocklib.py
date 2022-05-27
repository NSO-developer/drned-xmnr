import re
import os
import sys
from contextlib import contextmanager
import functools
from pyfakefs import fake_filesystem_unittest as ffs
from unittest.mock import patch, Mock, MagicMock, DEFAULT


class CxMgrMock(Mock):
    def __enter__(self):
        return self

    def __exit__(*ignore):
        pass


class MaapiMock(CxMgrMock):
    pass


@contextmanager
def nest_mgrs(mgrs):
    if mgrs == []:
        yield []
    else:
        with mgrs[0] as v:
            with nest_mgrs(mgrs[1:]) as vs:
                vs.append(v)
                yield vs


class XtestPatch(object):
    """Mimic `unittest.mock.patch` behavior to make pytest ignore test
    function arguments."""

    def __init__(self, mock_gens):
        self.attribute_name = None
        self.new = DEFAULT
        self.mock_gens = mock_gens

    def __call__(self, fn):
        if hasattr(fn, 'patchings'):
            raise RuntimeError('cannot combine XtestPatch with mock.patch')
        fn.patchings = [self]

        @functools.wraps(fn)
        def wrapper(*args):
            with nest_mgrs([gen() for gen in self.mock_gens]) as mocks:
                for mock_inst in mocks:
                    setattr(self, mock_inst.name, mock_inst)
                args = list(args)
                args.append(self)
                fn(*args)
        return wrapper


def xtest_patch(*patch_args):
    if len(patch_args) == 1 and callable(patch_args[0]):
        return XtestPatch((system_mock, ncs_mock))(patch_args[0])
    return XtestPatch(patch_args)


class XtestMock(object):
    def __init__(self, name):
        self.name = name


XMNR_DIRECTORY = 'test_xmnr_dir'
DRNED_DIRECTORY = 'drned_dir'
DEVICE_NAME = 'mock-device'
XMNR_INSTALL = 'xmnr-install'
MOCK_NED_ID = 'id:mock-id-1.0'


class TransMgr(object):
    def __init__(self):
        self.trans_obj = MagicMock(name='transobj')

    def __enter__(self):
        return self.trans_obj

    def __exit__(*ignore):
        pass


class MockNcsError(Exception):
    pass


def mock_path(path, value):
    if len(path) == 1:
        rhs = value
    else:
        rhs = mock_path(path[1:], value)
    return Mock(**{path[0]: rhs})


@contextmanager
def ncs_mock():
    nonex = Mock(exists=lambda: False)
    device = Mock(device_type=Mock(ne_type='netconf', netconf=Mock(ned_id=MOCK_NED_ID)),
                  read_timeout=None, address='1.2.3.4', port='5555', authgroup='default')
    authgrp = Mock(default_map=Mock(remote_name='admin', remote_password='admin',
                                    same_name=nonex, same_pass=nonex),
                   umap={})
    apmock = {'xmnr-cli-log': mock_path(['daemon', 'id'], None)}
    rootmock = Mock(name='rootmock',
                    devices=Mock(device={DEVICE_NAME: device},
                                 authgroups=Mock(group={'default': authgrp})),
                    packages=Mock(package={'drned-xmnr': Mock(directory=XMNR_INSTALL)}),
                    drned_xmnr=Mock(xmnr_directory=XMNR_DIRECTORY,
                                    drned_directory=DRNED_DIRECTORY,
                                    log_detail=Mock(cli='all'),
                                    last_test_results=MagicMock(),
                                    cli_log_file=None,
                                    xmnr_log_file=None),
                    ncs_state=mock_path(['internal', 'callpoints', 'actionpoint'], apmock))
    ncs_items = ['_ncs.stream_connect', '_ncs.dp.action_set_timeout', '_ncs.maapi.cli_write',
                 '_ncs.decrypt']
    maapi_inst = MaapiMock()
    tmgr = TransMgr()
    with patch('ncs.maapi.Maapi', return_value=maapi_inst), \
            patch('ncs.maapi.single_write_trans', return_value=tmgr), \
            patch('_ncs.error.Error', new=MockNcsError), \
            patch('_ncs.maapi.list_rollbacks', return_value=[]), \
            patch('_ncs.maapi.CONFIG_MERGE', return_value=0), \
            patch('ncs.maagic.get_root', return_value=rootmock), \
            nest_mgrs([patch(ncs_item) for ncs_item in ncs_items]) as ncs_patches:
        mock_inst = XtestMock('ncs')
        items = [it.split('.')[-1] for it in ncs_items]
        mock_inst.data = dict(maapi=maapi_inst,
                              trans_mgr=tmgr,
                              root=rootmock,
                              device=device,
                              ncs=dict(zip(items, reversed(ncs_patches))))
        yield mock_inst


class StreamData(object):
    """Auxiliary class for mocking objects that provides streamed data."""
    def __init__(self, init=''):
        self.set_data(init, 10)
        self.init = init

    def set_data(self, data, chunk):
        if len(data) == 0:
            self.data = []
        else:
            # reversing to have better performance for pop
            self.data = list(reversed([data[i * chunk:(i + 1) * chunk]
                                       for i in range(0, (len(data) + chunk - 1) // chunk)]))

    def __iter__(self):
        return self

    def next(self):
        return self.__next__()

    def __next__(self):
        if self.finished():
            raise StopIteration
        return self.next_data()

    def finished(self):
        return self.data == []

    def select(self, rlist, *ignore):
        if self.finished():
            return [], [], []
        return rlist, [], []

    def read(self):
        if self.finished():
            return self.init
        return self.next_data()

    def next_data(self):
        return self.data.pop()

    def poll(self):
        if self.finished():
            return 0
        return None


class PyTestEnv(object):
    def __init__(self):
        self.command = 'py.test'

    def set_command(self, command):
        self.command = command

    def which(self, args, **rest):
        if args[1] == self.command:
            return 0
        else:
            return 1


class SystemMock(XtestMock):
    def __init__(self, ff_patcher, patches):
        super(SystemMock, self).__init__('system')
        self.patches = patches
        self.ff_patcher = ff_patcher
        try:
            self.ff_patcher.fs.add_real_file('/dev/null', read_only=False)
        except FileExistsError:  # noqa: F821 (to support Python 2.7 with flake8)
            # happens on newer pyfakefs - /dev/null is created automatically
            pass
        self.proc_stream = StreamData()
        self.socket_stream = StreamData(b'')
        self.pytest_env = PyTestEnv()
        self.mock_socket_data()
        self.complete_popen_mock()

    def mock_socket_data(self):
        socket = self.patches['socket']['socket']
        socket.return_value = Mock(recv=self.get_socket_data)

    def complete_popen_mock(self):
        popen = self.patches['subprocess']['Popen']
        wait_mock = Mock(return_value=0)
        stdout_mock = Mock(read=self.proc_stream.read)
        popen.return_value = Mock(wait=wait_mock,
                                  poll=self.proc_stream.poll,
                                  test=self.proc_stream.finished,
                                  stdout=stdout_mock)
        self.patches['select']['select'].side_effect = self.proc_stream.select
        self.patches['subprocess']['call'].side_effect = self.pytest_env.which

    def socket_data(self, data, chunk=10):
        self.socket_stream.set_data(data, chunk)

    def get_socket_data(self, *args):
        try:
            return next(self.socket_stream)
        except StopIteration:
            return b''

    def proc_data(self, data, chunk=10):
        self.proc_stream.set_data(data, chunk)

    def set_pytest_env(self, command):
        self.pytest_env.set_command(command)


@contextmanager
def system_mock():
    """Mock system-level functions.

    Functions from fcntl, pickle, select, socket,
    subprocess are mocked to avoid tests touching the system state.
    """
    calls = {'fcntl': ['fcntl'],
             'select': ['select'],
             'socket': ['socket'],
             'subprocess': ['Popen', 'call']}

    @contextmanager
    def make_patch_group(name):
        with nest_mgrs([patch('{}.{}'.format(name, item)) for item in calls[name]]) as mgrs:
            yield dict(zip(calls[name], reversed(mgrs)))

    with nest_mgrs([make_patch_group(name) for name in calls]) as patchlist:
        with ffs.Patcher() as ff_patcher:
            # os.environ needs special care
            with patch.dict('os.environ', {'NCS_DIR': 'tmp_ncs_dir'}):
                patches = dict(zip(calls.keys(), reversed(patchlist)))
                yield SystemMock(ff_patcher, patches)


class MockAction(Mock):
    @staticmethod
    def action(fn):
        return fn


def init_mocks():
    """Patch all necessary classes and functions.

    Some of PyAPI classes and functions need to be patched early on,
    before the modules using them are imported; this applies mostly to
    NSO PyAPI modules, classes used as superclasses, decorator
    functions.
    """
    sys.modules['ncs'] = Mock(application=Mock(Application=Mock),
                              dp=Mock(Action=MockAction))
    sys.modules['ncs.log'] = Mock()
    sys.modules['ncs.maagic'] = Mock()
    sys.modules['ncs.maapi'] = Mock()
    sys.modules['_ncs'] = Mock(LIB_VSN=0x07060000)
    sys.modules['_ncs.dp'] = Mock(Action=Mock)
    sys.modules['_ncs.maapi'] = Mock()
    rootdir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    yangfile = os.path.join(rootdir, 'src', 'yang', 'drned-xmnr.yang')
    actionrx = re.compile(' *tailf:action (.*) [{]')
    with open(yangfile) as yang:
        actions = [mtch.groups()[0]
                   for mtch in (actionrx.match(line) for line in yang)
                   if mtch is not None]
    nsdict = {'drned_xmnr_{}_'.format(action.replace('-', '_')): action
              for action in actions}
    ns = Mock(ns=Mock(actionpoint_drned_xmnr='drned-xmnr',
                      callpoint_coverage_data='coverage-data',
                      callpoint_xmnr_states='xmnr-states',
                      actionpoint_xmnr_cli_log='xmnr-cli-log',
                      **nsdict))
    namespaces = Mock(drned_xmnr_ns=ns)
    __import__('drned_xmnr').namespaces = namespaces
    sys.modules['drned_xmnr.namespaces'] = namespaces
    sys.modules['drned_xmnr.namespaces.drned_xmnr_ns'] = ns
    sys.modules['drned'] = Mock()
