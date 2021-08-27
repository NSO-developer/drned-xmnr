import operator
import collections
import os
import random
from six import functools
import sys

from .mocklib import patch, mock

import cli2netconf


class MockDevcli(object):
    def __init__(self, failures):
        self.device_calls = []
        self.failures = failures
        self.load_filename = None
        self.methods = {'save_config', 'restore_config', 'clean_config'
                        'clean', 'save'}

    def inst_init(self, argsns):
        self.workdir = argsns.workdir
        self.devname = argsns.devname

    def load_config(self, filename):
        self.gen_method('load', filename)
        self.load_filename = filename
        if filename in self.failures['load']:
            raise Exception('failed to load ' + filename)

    def sync_from(self):
        self.gen_method('sync')
        if self.load_filename in self.failures['sync']:
            raise Exception('failed to sync ' + self.load_filename)

    def close(self):
        pass

    def gen_method(self, method, *args, **kwargs):
        if args == ():
            self.device_calls.append(method)
        else:
            self.device_calls.append((method, args, kwargs))

    def __getattr__(self, attr):
        if attr in self.methods:
            return functools.partial(self.gen_method, attr)
        raise AttributeError('MockDevcli has no attribute ' + attr)


# convenience function for prints to stdout during tests; the print
# function is patched
def pprint(*args):
    sys.stdout.write('{}\n'.format(' '.join(map(str, args))))


def cnv_patch(*patch_args, **patch_kwargs):
    if patch_args and callable(patch_args[0]):
        return ConvertPatch()(*patch_args)
    return ConvertPatch({'load': patch_kwargs.get('load_failures', []),
                         'sync': patch_kwargs.get('sync_failures', [])})


class ConvertPatch(object):
    '''A wrapper class whose instance is passed to test methods as an argument.

    An instance of this class is callable (so that it can be used as a
    return value of a function decorator).  The `__call__` method
    creates a function wrapper, that creates a Devcli and XDevice mock
    (there is only one common for both classes).
    '''

    def __init__(self, failures={'load': [], 'sync': []}):
        self.failures = failures
        self.attribute_name = None
        self.new = mock.DEFAULT
        self.print_caps = []
        self.devclimock = None

    def devclimock_instance(self, *args):
        self.instantiate_devcli().inst_init(*args)
        return self.devclimock

    def xdev_instance(self, *args):
        # it's actually Devcli mock again, but we don't have the
        # Devcli init arguments now
        return self.instantiate_devcli()

    def instantiate_devcli(self):
        if self.devclimock is None:
            self.devclimock = MockDevcli(self.failures)
        return self.devclimock

    def __call__(self, fun):
        fun.patchings = [self]

        @functools.wraps(fun)
        def _wrapper(self_arg):
            # we need to capture output from the module functions
            print_ref = '__builtin__.print' if sys.version_info < (3,) else 'builtins.print'
            with patch.dict('os.environ', NC_WORKDIR='/'), \
                    patch('cli2netconf.Devcli', new=self.devclimock_instance), \
                    patch('cli2netconf.XDevice', new=self.xdev_instance), \
                    patch(print_ref, new=self.print_cap):
                return fun(self_arg, self)

        return _wrapper

    def print_cap(self, *args):
        self.print_caps.append(' '.join(map(str, args)))


ArgsNS = collections.namedtuple('ArgsNS',
                                ['devname', 'driver', 'workdir', 'ip', 'port', 'timeout', 'files'])


class TestCli2Netconf(object):
    groups = [['f1.cfg'], ['f2:1.cfg', 'f2:2.cfg'], ['f3.cfg']]

    def config_files(self):
        files = functools.reduce(operator.add, self.groups)
        random.shuffle(files)
        return files

    def run_convert_test(self, patcher):
        files = self.config_files()
        cli2netconf.cli2netconf(ArgsNS('mockdevice', '/tmp/driver', '/',
                                       '1.2.3.4', 5555, 120, files))
        calls = list(reversed(patcher.devclimock.device_calls))
        prints = list(reversed(patcher.print_caps))
        assert ('save_config', ('drned-backup',), {}) == calls.pop()
        for group in self.groups:
            for filename in group:
                base, _ = os.path.splitext(filename)
                target = '/{}.xml'.format(base)
                assert ('load', (filename,), {}) == calls.pop()
                assert 'converting {} to {}'.format(filename, target) == prints.pop()
                if filename in patcher.failures['load']:
                    groupname = base.split(':')[0]
                    assert 'failed to convert group ' + groupname == prints.pop()
                    assert 'exception: failed to load ' + filename == prints.pop()
                    break
                assert 'sync' == calls.pop()
                if filename in patcher.failures['sync']:
                    groupname = base.split(':')[0]
                    assert 'failed to convert group ' + groupname == prints.pop()
                    assert 'exception: failed to sync ' + filename == prints.pop()
                    assert 'clean_config' == calls.pop()
                    assert 'sync' == calls.pop()
                    break
                assert ('save', (target,), {'fmt': 'xml'}) == calls.pop()
                assert 'converted {} to {}'.format(filename, target) == prints.pop()
            assert ('restore_config', ('drned-backup',), {}) == calls.pop()
        assert ['sync'] == calls

    @cnv_patch
    def test_group_run(self, patcher):
        self.run_convert_test(patcher)

    @cnv_patch(load_failures=['f2:2.cfg'])
    def test_group_failure(self, patcher):
        self.run_convert_test(patcher)

    @cnv_patch(load_failures=['f1.cfg', 'f3.cfg'])
    def test_simple_failure(self, patcher):
        self.run_convert_test(patcher)

    @cnv_patch(sync_failures=['f1.cfg', 'f2:1.cfg'])
    def test_sync_failures(self, patcher):
        self.run_convert_test(patcher)
