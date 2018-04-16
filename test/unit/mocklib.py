from __future__ import print_function

import sys
from contextlib import contextmanager
import functools
if sys.version_info >= (3, 3):
    import unittest.mock as mock
else:
    import mock

patch = mock.patch
Mock = mock.Mock


class MaapiMock(Mock):
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
    """Mimic `unittest.mock.patch' behavior to make pytest ignore test
    function arguments."""

    def __init__(self, mock_gens):
        self.attribute_name = None
        self.new = mock.DEFAULT
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
                if hasattr(self, 'system') and hasattr(self, 'open'):
                    self.system.set_open_mocks(self.open)
                args = list(args)
                args.append(self)
                fn(*args)
        return wrapper


def xtest_patch(*mock_gens):
    return XtestPatch(mock_gens)


class XtestMock(object):
    def __init__(self, name):
        self.name = name


@contextmanager
def ncs_mock():
    device = Mock(device_type=Mock(ne_type='netconf', netconf='netconf'))
    rootmock = Mock(devices=Mock(device={'mock-device': device}),
                    packages=Mock(package={'drned-xmnr': Mock(directory='xmnr-install')}),
                    drned_xmnr=Mock(xmnr_directory='test_xmnr_dir',
                                    drned_directory='drned_dir'))
    with patch('ncs.maapi.Maapi', return_value=MaapiMock()) as maapi:
        with patch('ncs.maagic.get_root', return_value=rootmock):
            ncs_items = ['maapi', 'dp', 'stream_connect']
            with nest_mgrs([patch('_ncs.{}'.format(ncs_item))
                            for ncs_item in ncs_items]) as ncs_patches:
                mock_inst = XtestMock('ncs')
                mock_inst.data = dict(maapi=maapi,
                                      ncs=dict(zip(ncs_items, reversed(ncs_patches))))
                yield mock_inst


class FileData(object):
    def __init__(self, name, data=None):
        self.name = name
        self.data = data

    def read(self):
        if self.data is None:
            raise RuntimeError('Cannot read from {}'.format(self.name))
        return self.data

    def write(self, data):
        if self.data is None:
            self.data = b''
        self.data += data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class SystemMock(XtestMock):
    def __init__(self, patches):
        super(SystemMock, self).__init__('system')
        self.tree = {}
        self.patches = patches
        for fn, fnmock in patches['os'].items():
            fnmock.side_effect = functools.partial(self.invoke_system, fnmock, fn)
        socket = patches['socket']['socket']
        socket.return_value = mock.Mock(recv=Mock(side_effect=self.get_socket_data))
        self.socket_data('')

    def invoke_system(self, mock, name, *args):
        if name == 'path.exists':
            return self.exists(*args)
        if name == 'makedirs':
            return self.makedirs(*args)
        if name == 'remove':
            return self.remove(*args)
        if name == 'open':
            return self.open(*args)
        print('operation', name, 'not supported')
        return mock

    def set_open_mocks(self, openmock):
        for omock in openmock.mocks:
            omock.side_effect = functools.partial(self.invoke_system, omock, 'open')

    def descend_tree(self, path, start=None):
        node = self.tree if start is None else start
        part_iter = iter(path.split('/') if type(path) is str else path)
        for part in part_iter:
            child = node.get(part, None)
            if type(child) is not dict:
                return node, [part] + list(part_iter), child
            node = child
        return node, None, None

    def makedirs(self, path, start=None):
        node, rest, child = self.descend_tree(path, start=start)
        if type(child) is dict:
            raise RuntimeError('Directory exists: {}'.format(path))
        if child is not None:
            raise RuntimeError('Cannot create directory: {}'.format(path))
        for part in rest:
            node[part] = {}
            node = node[part]

    def exists(self, path):
        print('existing', path)
        _, _, child = self.descend_tree(path)
        return child is not None

    def remove(self, path):
        node, rest, child = self.descend_tree(path)
        if type(child) is not dict:
            raise RuntimeError('cannot remove: {}'.format(path))
        del node[rest[0]]

    def open(self, path, attr='r'):
        node, rest, child = self.descend_tree(path)
        if attr == 'r':
            if isinstance(child, FileData):
                return child
            raise RuntimeError('cannot read: {}'.format(path))
        if attr == 'w':
            if isinstance(child, dict):
                raise RuntimeError('cannot write to {}'.format(path))
            if len(rest) > 1:
                prest = rest[:-1]
                self.makedirs(prest, start=node)
                node, _, _ = self.descend_tree(prest, start=node)
            name = rest[-1]
            node[name] = FileData(name)
            return node[name]

    def socket_data(self, data, chunk=10):
        self.data_iter = (data[i*chunk:(i+1)*chunk] for i in range(0, (len(data)+chunk-1)//chunk))

    def get_socket_data(self, *args):
        try:
            return next(self.data_iter)
        except StopIteration:
            return ''


@contextmanager
def system_mock():
    """Mock system-level functions.

    Functions from os, fcntl, glob, pickle, select, shutil, socket,
    subprocess are mocked to avoid tests touching the system state.
    """
    calls = {'os': ['remove', 'path.exists', 'rename', 'symlink',
                    'mkdir', 'makedirs'],
             'fcntl': ['fcntl'],
             'glob': ['glob'],
             'pickle': ['load', 'dump'],
             'select': ['select'],
             'shutil': ['copy', 'copyfile', 'copytree', 'rmtree'],
             'socket': ['socket'],
             'subprocess': ['Popen']}

    @contextmanager
    def make_patch_group(name):
        with nest_mgrs([mock.patch('{}.{}'.format(name, item)) for item in calls[name]]) as mgrs:
            yield dict(zip(calls[name], reversed(mgrs)))

    with nest_mgrs([make_patch_group(name) for name in calls]) as patchlist:
        # os.environ needs special care
        with mock.patch.dict('os.environ', {'NCS_DIR': 'tmp_ncs_dir'}):
            patches = dict(zip(calls.keys(), reversed(patchlist)))
            popen = patches['subprocess']['Popen']
            wait_mock = mock.Mock(return_value=0)
            popen.return_value = mock.Mock(wait=wait_mock)
            yield SystemMock(patches)


class OpenMock(XtestMock):
    def __init__(self, open_mocks):
        super(OpenMock, self).__init__('open')
        self.mocks = open_mocks


def open_mock(*modules):
    @contextmanager
    def cmgr():
        with nest_mgrs([mock.patch('drned_xmnr.op.{}.open'.format(module))
                        for module in modules]) as open_mocks:
            yield OpenMock(open_mocks)
    return cmgr


def init_mocks():
    """Patch all necessary classes and functions.

    Some of PyAPI classes and functions need to be patched early on,
    before the modules using them are imported; this applies mostly to
    classes used as superclasses and decorator functions. These
    patchings remains active for the rest of the Python environment
    lifetime, the patchers' `stop' method is never called!
    """
    patch('ncs.application.Application', new_callable=lambda: mock.Mock).start()
    patch('ncs.dp.Action.action', side_effect=lambda fn: fn).start()
    patch('ncs.dp.Action.__init__', return_value=None).start()
