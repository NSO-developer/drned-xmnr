from __future__ import print_function

from . import mocklib
from .mocklib import mock, xtest_patch
from drned_xmnr import action
from drned_xmnr.op import config_op, base_op, coverage_op
import os
from random import randint
import functools
import itertools

device_data = '''
    <config xmlns="http://tail-f.com/ns/config/1.0">
      <devices xmlns="http://tail-f.com/ns/ncs">
        <device>
          <name>mock-device</name>
          <address>127.0.0.1</address>
          <port>2022</port>
          <ssh/>
          <connect-timeout/>
          <read-timeout/>
          <trace/>
          <config/>
        </device>
      </devices>
    </config>
'''


test_state_data = '''
test state data
'''


drned_collect_output = '''
Found a total of {nodes-total} nodes (0 of type empty) and {lists-total} lists,
     {nodes[read-or-set][total]} (  {nodes[read-or-set][percent]}%) nodes read or set
     {lists[read-or-set][total]} (  {lists[read-or-set][percent]}%) lists read or set
     {lists[deleted][total]} (  {lists[deleted][percent]}%) lists deleted
     {lists[multi-read-or-set][total]} (  {lists[multi-read-or-set][percent]}%) \
lists with multiple entries read or set
     {nodes[set][total]} (  {nodes[set][percent]}%) nodes set
     {nodes[deleted][total]} (  {nodes[deleted][percent]}%) nodes deleted
     {nodes[set-set][total]} (  {nodes[set-set][percent]}%) nodes set when already set
     {nodes[deleted-separately][total]} (  {nodes[deleted-separately][percent]}%) \
nodes deleted separately (disregarding 9 bool-no|prefix-key|mandatory)
     {grouping-nodes[read-or-set][total]} (  {grouping-nodes[read-or-set][percent]}%) \
grouping nodes read or set
     {grouping-nodes[set][total]} (  {grouping-nodes[set][percent]}%) grouping nodes set
     {grouping-nodes[deleted][total]} (  {grouping-nodes[deleted][percent]}%) grouping nodes deleted
     {grouping-nodes[set-set][total]} (  {grouping-nodes[set-set][percent]}%) \
grouping nodes set when already set
     {grouping-nodes[deleted-separately][total]} \
(  {grouping-nodes[deleted-separately][percent]}%) \
grouping nodes deleted separately (disregarding 9 bool-no|prefix-key|mandatory)
'''


class TestBase(object):
    real_open = open
    log_levels = ('error', 'warning', 'info', 'debug')
    test_run_dir = os.path.join(mocklib.XMNR_DIRECTORY, mocklib.DEVICE_NAME, 'test')
    states = ('state1', 'state2', 'otherstate1')

    def check_output(self, output, success=None):
        assert output.error is None
        assert output.failure is None
        if success is not None:
            assert output.success == success

    def unit_log_file(self):
        if not hasattr(self, 'log_file'):
            self.log_file = self.real_open('/tmp/unit.log', 'a')
        return self.log_file

    def setup_log(self, handler):
        handler.log = mock.Mock()
        for level in self.log_levels:
            prefix = '<{}>'.format(level.upper())
            setattr(handler.log, level, functools.partial(print, prefix, file=self.unit_log_file()))

    def invoke_action(self, action_name, **action_params):
        params = mock.Mock(spec=action_params.keys(), **action_params)
        ah = action.ActionHandler()
        self.setup_log(ah)
        kp = [[mocklib.DEVICE_NAME], None, None]
        output = mock.Mock(error=None, failure=None, success=None)
        ah.cb_action(mock.Mock(), action_name, kp, params, output)
        return output

    def setup_states_data(self, system, state_path=None):
        spath = state_path
        if spath is None:
            spath = os.path.join(self.test_run_dir, 'states')
        for state in self.states:
            stname = state + base_op.XmnrBase.statefile_extension
            system.ff_patcher.fs.create_file(os.path.join(spath, stname),
                                             contents='{} test data'.format(state))
            if state_path is None:
                system.ff_patcher.fs.create_file(os.path.join(spath, stname + '.load'),
                                                 contents=config_op.state_metadata)


class TestStartup(TestBase):
    def test_registry(self):
        xmnr = action.Xmnr()
        xmnr.setup()
        xmnr.register_action.assert_called_once_with('drned-xmnr', action.ActionHandler)
        xmnr.register_service.assert_has_calls([mock.call('coverage-data', action.XmnrDataHandler),
                                                mock.call('xmnr-states', action.XmnrDataHandler)])


class TestSetup(TestBase):
    def setup_fs_data(self, system):
        system.ff_patcher.fs.create_dir(mocklib.XMNR_DIRECTORY)
        system.ff_patcher.fs.add_real_file('/dev/null')
        system.ff_patcher.fs.create_file(os.path.join(mocklib.XMNR_INSTALL, 'drned', 'skeleton'),
                                         contents='drned skeleton')

    def setup_ncs_data(self, ncs):
        device = ncs.data['device']
        device.device_type = mock.Mock(netconf='netconf', ne_type='netconf')

    @xtest_patch
    def test_setup(self, xpatch):
        self.setup_fs_data(xpatch.system)
        self.setup_ncs_data(xpatch.ncs)
        xpatch.system.socket_data(device_data.encode())
        output = self.invoke_action('setup-xmnr', overwrite=True)
        self.check_output(output)
        with open(os.path.join(self.test_run_dir, 'drned/skeleton')) as skel_test:
            assert skel_test.read() == 'drned skeleton'
        popen_mock = xpatch.system.patches['subprocess']['Popen']
        popen_mock.assert_called_once()
        assert popen_mock.call_args[0] == (['make', 'env.sh'],)


class TestStates(TestBase):
    def state_files(self, states):
        return sorted(itertools.chain(*((st + '.state.cfg', st + '.state.cfg.load')
                                        for st in states)))

    def check_states(self, states):
        assert (sorted(os.listdir(os.path.join(self.test_run_dir, 'states'))) ==
                self.state_files(states))

    @xtest_patch
    def test_states_data(self, xpatch):
        log = mock.Mock()
        sp = config_op.StatesProvider(log)
        self.setup_log(sp)
        self.setup_states_data(xpatch.system)
        tctx = mock.Mock()
        obj = sp.get_object(tctx, None, {'device': mocklib.DEVICE_NAME})
        assert sorted(st['state'] for st in obj['states']) == sorted(self.states)

    @xtest_patch
    def test_list_states(self, xpatch):
        self.setup_states_data(xpatch.system)
        output = self.invoke_action('list-states')
        self.check_output(output)
        part = 'Saved device states: '
        assert output.success.startswith(part)
        rest = output.success[len(part):]
        rstates = eval(rest)
        assert sorted(rstates) == sorted(self.states)

    @xtest_patch
    def test_record_state(self, xpatch):
        xpatch.system.socket_data(test_state_data.encode())
        output = self.invoke_action('record-state',
                                    state_name='test_state',
                                    including_rollbacks=None)
        self.check_output(output)
        state_path = 'states/test_state' + base_op.XmnrBase.statefile_extension
        assert os.path.exists(os.path.join(self.test_run_dir, state_path))
        with open(os.path.join(self.test_run_dir, state_path + '.load')) as metadata:
            assert metadata.read() == config_op.state_metadata
        with open(os.path.join(self.test_run_dir, state_path)) as state_data:
            assert state_data.read() == test_state_data

    @xtest_patch
    def test_import_states(self, xpatch):
        path = '/tmp/data'
        xpatch.system.ff_patcher.fs.create_dir(path)
        self.setup_states_data(xpatch.system, state_path=path)
        output = self.invoke_action('import-state-files',
                                    file_path_pattern=os.path.join(path, '*1.state.cfg'),
                                    overwrite=None)
        self.check_output(output)
        destdir = os.path.join(self.test_run_dir, 'states')
        states = sorted(state for state in self.states if state.endswith('1'))
        self.check_states(states)
        for state in states:
            filename = os.path.join(destdir, state + '.state.cfg')
            with open(filename) as state_file:
                assert state_file.read() == '{} test data'.format(state)
            with open(filename + '.load') as metadata:
                assert metadata.read() == config_op.state_metadata

    @xtest_patch
    def test_delete_states_pattern(self, xpatch):
        self.setup_states_data(xpatch.system)
        output = self.invoke_action('delete-state',
                                    state_name=None,
                                    state_name_pattern='*1')
        self.check_output(output)
        self.check_states(st for st in self.states if not st.endswith('1'))

    @xtest_patch
    def test_delete_state(self, xpatch):
        self.setup_states_data(xpatch.system)
        output = self.invoke_action('delete-state',
                                    state_name_pattern=None,
                                    state_name='otherstate1')
        self.check_output(output)
        states = list(self.states[:])
        states.remove('otherstate1')
        self.check_states(states)

    @xtest_patch
    def test_delete_failure(self, xpatch):
        self.setup_states_data(xpatch.system)
        output = self.invoke_action('delete-state',
                                    state_name_pattern=None,
                                    state_name='no-such-state')
        assert output.failure is not None
        self.check_states(self.states)


class TestTransitions(TestBase):
    stop_names = ['seconds', 'minutes', 'hours', 'days', 'percent', 'cases']
    stop_params = {stop: None for stop in stop_names}

    def check_drned_call(self, call, state=None, rollback=False, fnames=None):
        if fnames is None:
            test = 'test_template_single' if rollback else 'test_template_raw'
            test_args = ['-k {}[../states/{}.state.cfg]'.format(test, state)]
        else:
            test_args = ['--fname={}'.format(os.path.join(self.test_run_dir,
                                                          'states',
                                                          state + '.state.cfg'))
                         for state in self.states]
            test_args += ['--unsorted', '-k', 'test_template_set']
        args = ['py.test', '-s', '--tb=short', '--device=' + mocklib.DEVICE_NAME, '--unreserved']
        args += test_args
        assert call[0] == (args,)

    @xtest_patch
    def test_transition_to_state(self, xpatch):
        self.setup_states_data(xpatch.system)
        output = self.invoke_action('transition-to-state',
                                    state_name='state1',
                                    rollback=False)
        self.check_output(output)
        popen_mock = xpatch.system.patches['subprocess']['Popen']
        popen_mock.assert_called_once()
        self.check_drned_call(popen_mock.call_args, 'state1', rollback=False)

    @xtest_patch
    def test_transition_to_state_rollback(self, xpatch):
        self.setup_states_data(xpatch.system)
        output = self.invoke_action('transition-to-state',
                                    state_name='state1',
                                    rollback=True)
        self.check_output(output)
        popen_mock = xpatch.system.patches['subprocess']['Popen']
        popen_mock.assert_called_once()
        self.check_drned_call(popen_mock.call_args, 'state1', rollback=True)

    @xtest_patch
    def test_transition_to_state_failed(self, xpatch):
        self.setup_states_data(xpatch.system)
        output = self.invoke_action('transition-to-state',
                                    state_name='no-such-state',
                                    rollback=True)
        popen_mock = xpatch.system.patches['subprocess']['Popen']
        popen_mock.assert_not_called()
        assert output.failure is not None
        assert output.failure.startswith('No such state')

    @xtest_patch
    def test_explore_states(self, xpatch):
        self.setup_states_data(xpatch.system)
        output = self.invoke_action('explore-transitions',
                                    states=self.states,
                                    stop_after=mock.Mock(**self.stop_params))
        self.check_output(output)
        popen_mock = xpatch.system.patches['subprocess']['Popen']
        ls = len(self.states)
        assert len(popen_mock.call_args_list) == ls*ls
        calls = iter(popen_mock.call_args_list)
        for from_state in self.states:
            self.check_drned_call(next(calls), from_state)
            for to_state in self.states:
                if from_state == to_state:
                    continue
                self.check_drned_call(next(calls), to_state, rollback=True)

    def popen_fail_state(self, args, *rest, **kwargs):
        for arg in args:
            if 'otherstate1' in arg:
                return mock.Mock(wait=mock.Mock(return_value=-1))
        return mock.DEFAULT

    @xtest_patch
    def test_explore_failure(self, xpatch):
        self.setup_states_data(xpatch.system)
        popen_mock = xpatch.system.patches['subprocess']['Popen']
        popen_mock.side_effect = self.popen_fail_state
        output = self.invoke_action('explore-transitions',
                                    states=self.states,
                                    stop_after=mock.Mock(**self.stop_params))
        assert output.success is None
        assert 'Failed to initialize state otherstate1' in output.error
        assert '==> otherstate1' in output.failure

    @xtest_patch
    def test_walk_states(self, xpatch):
        self.setup_states_data(xpatch.system)
        output = self.invoke_action('walk-states',
                                    states=self.states,
                                    stop_after=mock.Mock(**self.stop_params))
        self.check_output(output)
        popen_mock = xpatch.system.patches['subprocess']['Popen']
        self.check_drned_call(popen_mock.call_args, fnames=self.states)
        popen_mock.assert_called_once()


class TestCoverage(TestBase):
    collect_groups = {'nodes': ['read-or-set', 'set', 'deleted', 'set-set', 'deleted-separately'],
                      'lists': ['read-or-set', 'deleted', 'multi-read-or-set'],
                      'grouping-nodes': ['read-or-set', 'set', 'deleted', 'set-set',
                                         'deleted-separately']}

    def line_entry(self, total, percent):
        return dict(total=total, percent=percent)

    @xtest_patch
    def test_coverage_reset(self, xpatch):
        output = self.invoke_action('reset')
        self.check_output(output)
        popen_mock = xpatch.system.patches['subprocess']['Popen']
        popen_mock.assert_called_once()
        assert popen_mock.call_args[0] == (['make', 'covstart'],)

    @xtest_patch
    def test_coverage_collect(self, xpatch):
        collect_dict = {'nodes-total': randint(0, 1000), 'lists-total': randint(0, 1000)}
        for (group, entries) in self.collect_groups.items():
            collect_dict[group] = {}
            for entry in entries:
                collect_dict[group][entry] = self.line_entry(randint(0, 1000), randint(0, 100))
        xpatch.system.proc_data(drned_collect_output.format(**collect_dict))
        output = self.invoke_action('collect', yang_patterns=['pat1', 'pat2'])
        self.check_output(output)
        log = mock.Mock()
        cdata = coverage_op.DataHandler(log)
        self.setup_log(cdata)
        tctx = mock.Mock()
        obj = cdata.get_object(tctx, None, {'device': mocklib.DEVICE_NAME})
        data = obj['drned-xmnr']['coverage']['data']
        assert int(data['nodes-total']) == collect_dict['nodes-total']
        assert int(data['lists-total']) == collect_dict['lists-total']
        for group in self.collect_groups:
            assert data['percents'][group] == collect_dict[group]

    @xtest_patch
    def test_coverage_failure(self, xpatch):
        log = mock.Mock()
        cdata = coverage_op.DataHandler(log)
        self.setup_log(cdata)
        tctx = mock.Mock()
        obj = cdata.get_object(tctx, None, {'device': mocklib.DEVICE_NAME})
        assert obj['drned-xmnr']['coverage']['data'] == {}
