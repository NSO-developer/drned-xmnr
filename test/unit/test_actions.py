from __future__ import print_function

from . import mocklib
from .mocklib import mock, xtest_patch
from drned_xmnr import action
from drned_xmnr.op import config_op, base_op, coverage_op
import os
import sys
import re
from random import randint
import functools
import itertools
import _ncs

if sys.version_info >= (3, 0):
    def bytestream(data):
        return data.encode()
else:
    def bytestream(data):
        return data

device_data = '''\
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

test_state_data_xml = '''\
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
          <config>
             <aaa xmlns="http://cisco.com/ns/yang/Cisco-IOS-XR-aaa-lib-cfg">
              <diameter xmlns="http://cisco.com/ns/yang/Cisco-IOS-XR-aaa-diameter-cfg">
                <origin>
                  <realm>cisco.com</realm>
                  <host>iotbng.cisco.com</host>
                </origin>
              </diameter>
            </aaa>
          </config>
        </device>
      </devices>
    </config>
'''

test_state_data_xml_transformed = '''\
<config xmlns="http://tail-f.com/ns/config/1.0" xmlns:ncs="http://tail-f.com/ns/ncs">
  <aaa xmlns="http://cisco.com/ns/yang/Cisco-IOS-XR-aaa-lib-cfg">
    <diameter xmlns="http://cisco.com/ns/yang/Cisco-IOS-XR-aaa-diameter-cfg">
      <origin>
        <realm>cisco.com</realm>
        <host>iotbng.cisco.com</host>
      </origin>
    </diameter>
  </aaa>
</config>
'''

test_state_data = '''\
test state data
'''


drned_explore_start_output = '''\
--generic drned data--
============================== sync_from()
--generic drned data--
test_template_raw[../states/{state_from}.state.cfg]
============================== rload(../states/{state_from}.state.cfg)
--generic drned data--
============================== commit()
--generic drned data--
% No modifications to commit.
============================== compare_config()
'''

drned_init_failed = '''\
Failed to initialize state {state_from}
'''

drned_transition_failed = '''\
Transition failed
'''

drned_explore_start_output_filtered = '''\
   prepare the device
   load {state_from}
   commit
       (no modifications)
   compare config
       succeeded
'''

drned_transition_output = '''\
--generic drned data--
============================== load(./polaris.cfg)
--generic drned data--
============================== sync_from()
test_template_single[../states/{state_to}.state.cfg]
--generic drned data--
============================== rload(../states/{state_to}.state.cfg)
--generic drned data--
============================== commit()
--generic drned data--
commit-queue {{
    id 1529558544009
    status failed
    failed-device {{
        name polaris
        reason RPC error towards test device
    }}
}}
Commit complete.
============================== compare_config()
--generic drned data--
{compare_result}
--generic drned data--
============================== rollback()
--generic drned data--
============================== commit()
--generic drned data--
commit-queue {{
    id 1528715048477
    status completed
}}
Commit complete.
============================== compare_config()
'''

drned_transition_output_filtered = '''\
   prepare the device
   load {state_to}
   commit
       failed (RPC error towards test device)
   compare config
       {compare_result}
   rollback
   commit
       succeeded
   compare config
       succeeded
'''


drned_walk_output = '''\
--generic drned data--
============================== rload(../states/{state_to}.state.cfg)
--generic drned data--
============================== commit()
--generic drned data--
commit-queue {{
    id 1529566672491
    status completed
}}
Commit complete.
--generic drned data--
============================== compare_config()
--generic drned data--
============================== rollback()
--generic drned data--
============================== commit()
--generic drned data--
commit-queue {{
    id 1529566674280
    status completed
}}
--generic drned data--
============================== compare_config()
--generic drned data--
'''

drned_walk_output_outro = '''\
### TEARDOWN, RESTORE DEVICE ###
--generic drned data--
============================== sync_from()
--generic drned data--
============================== load(drned-work/before-session.xml)
--generic drned data--
============================== commit()
--generic drned data--
% No modifications to commit.
--generic drned data--
============================== compare_config()
--generic drned data--
'''


drned_walk_output_filtered = '''\
   load {state_to}
   commit
       succeeded
   compare config
       succeeded
   rollback
   commit
       succeeded
   compare config
       succeeded
'''


drned_walk_output_intro = '''\
py.test -k test_template_set --fname=.../states/{state_to}.state.cfg \
--op=load --op=commit --op=compare-config {end_op}--device=device
'''


drned_walk_output_outro_filtered = '''\
Device cleanup
   load before-session
   commit
       (no modifications)
   compare config
       succeeded
'''


drned_collect_output = '''\
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

    def action_uinfo(self):
        return mock.Mock()

    def invoke_action(self, action_name, **action_params):
        params = mock.Mock(spec=action_params.keys(), **action_params)
        ah = action.ActionHandler()
        self.setup_log(ah)
        kp = [[mocklib.DEVICE_NAME], None, None]
        output = mock.Mock(error=None, failure=None, success=None)
        ah.cb_action(self.action_uinfo(), action_name, kp, params, output)
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
        xmnr.register_action.assert_has_calls([mock.call('drned-xmnr', action.ActionHandler),
                                               mock.call('drned-xmnr-completion',
                                                         action.CompletionHandler)])
        xmnr.register_service.assert_has_calls([mock.call('coverage-data', action.XmnrDataHandler),
                                                mock.call('xmnr-states', action.XmnrDataHandler)])


class TestSetup(TestBase):
    def setup_fs_data(self, system):
        system.ff_patcher.fs.create_dir(mocklib.XMNR_DIRECTORY)
        system.ff_patcher.fs.add_real_file('/dev/null')
        system.ff_patcher.fs.create_file(os.path.join(mocklib.XMNR_INSTALL,
                                                      'drned-skeleton',
                                                      'skeleton'),
                                         contents='drned skeleton')
        system.ff_patcher.fs.create_dir(os.path.join(mocklib.XMNR_INSTALL,
                                                     'drned'))

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
        with open(os.path.join(self.test_run_dir, 'drned-skeleton', 'skeleton')) as skel_test:
            assert skel_test.read() == 'drned skeleton'
        popen_mock = xpatch.system.patches['subprocess']['Popen']
        popen_mock.assert_called_once()
        assert popen_mock.call_args[0] == (['make', 'env.sh'],)


class LoadConfig(object):
    exc_message = 'Error: {} cannot be loaded'

    def __init__(self, ncs, fail_states=[]):
        self.fail_states = fail_states
        self.tcx_mock = mocklib.CxMgrMock(load_config=mock.Mock(side_effect=self.load_config))
        ncs.data['maapi'].start_write_trans = lambda *args, **dargs: self.tcx_mock
        states_dir = os.path.join(TestBase.test_run_dir, 'states')
        self.sub_rx = re.compile(r'{}/(.*)\.state\.cfg'.format(states_dir))
        self.loaded_states = []

    def load_config(self, _flags, filename):
        state = self.sub_rx.sub(r'\1', filename)
        self.loaded_states.append(state)
        if state in self.fail_states:
            raise _ncs.error.Error(self.exc_message.format(state))


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
                                    format="c-style",
                                    including_rollbacks=None)
        self.check_output(output)
        state_path = 'states/test_state' + base_op.XmnrBase.statefile_extension
        assert os.path.exists(os.path.join(self.test_run_dir, state_path))
        with open(os.path.join(self.test_run_dir, state_path + '.load')) as metadata:
            assert metadata.read() == config_op.state_metadata
        with open(os.path.join(self.test_run_dir, state_path)) as state_data:
            assert state_data.read() == test_state_data

    @xtest_patch
    def test_record_state_xml(self, xpatch):
        xpatch.system.socket_data(test_state_data_xml.encode())
        output = self.invoke_action('record-state',
                                    state_name='test_state_xml',
                                    format="xml",
                                    including_rollbacks=None)
        self.check_output(output)
        state_path = 'states/test_state_xml' + base_op.XmnrBase.statefile_extension
        assert os.path.exists(os.path.join(self.test_run_dir, state_path))
        with open(os.path.join(self.test_run_dir, state_path + '.load')) as metadata:
            assert metadata.read() == config_op.state_metadata
        with open(os.path.join(self.test_run_dir, state_path)) as state_data:
            assert state_data.read() == test_state_data_xml_transformed

    @xtest_patch
    def test_import_states(self, xpatch):
        path = '/tmp/data'
        xpatch.system.ff_patcher.fs.create_dir(path)
        self.setup_states_data(xpatch.system, state_path=path)
        output = self.invoke_action('import-state-files',
                                    file_path_pattern=os.path.join(path, '*1.state.cfg'),
                                    format="c-style",
                                    merge=False,
                                    overwrite=None)
        self.check_output(output)
        destdir = os.path.join(self.test_run_dir, 'states')
        states = sorted(state for state in self.states if state.endswith('1'))
        self.check_states(states)
        test_data_p = 'devices device {} config\n{{}} test data'.format(mocklib.DEVICE_NAME)
        for state in states:
            filename = os.path.join(destdir, state + '.state.cfg')
            with open(filename) as state_file:
                assert state_file.read() == test_data_p.format(state)
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

    @xtest_patch
    def test_check_states(self, xpatch):
        self.setup_states_data(xpatch.system)
        load_calls = LoadConfig(xpatch.ncs)
        output = self.invoke_action('check-states', state_name_pattern=None, validate=True)
        self.check_output(output)
        assert sorted(self.states) == sorted(load_calls.loaded_states)

    @xtest_patch
    def test_check_failed_states(self, xpatch):
        self.setup_states_data(xpatch.system)
        failures = ['state1', 'state2']
        load_calls = LoadConfig(xpatch.ncs, failures)
        output = self.invoke_action('check-states', state_name_pattern=None, validate=True)
        assert sorted(self.states) == sorted(load_calls.loaded_states)
        fail_msg = 'states not consistent with the device model: \n'
        assert output.failure.startswith(fail_msg)
        rest_msgs = output.failure[len(fail_msg):].split('\n')
        assert ['{}: {}'.format(state, load_calls.exc_message.format(state))
                for state in sorted(failures)] == sorted(rest_msgs)


class StopTestTimer(object):
    def __init__(self, **args):
        self.reset(**args)

    def reset(self, step=1):
        self.step = step
        self._time = 0

    def tick(self, *args, **kwargs):
        for drned_arg in args[0]:
            if 'test_template_single' in drned_arg:
                # this is a transition under test, do a tick
                self._time += self.step
                break
        return mock.DEFAULT

    def time(self):
        return self._time


class TransitionsTestBase(TestBase):
    stop_names = ['seconds', 'minutes', 'hours', 'days', 'percent', 'cases']

    def stop_params(self, **params):
        pars = {stop: None for stop in self.stop_names}
        pars.update(**params)
        return mock.Mock(**pars)


class TestTransitions(TransitionsTestBase):
    def check_drned_call(self, call, state=None, rollback=False, fnames=None, builtin_drned=False):
        if fnames is None:
            test = 'test_template_single' if rollback else 'test_template_raw'
            test_args = ['-k {}[../states/{}.state.cfg]'.format(test, state)]
        else:
            test_args = ['--fname={}'.format(os.path.join(self.test_run_dir,
                                                          'states',
                                                          state + '.state.cfg'))
                         for state in self.states]
            if not rollback:
                test_args += ['--end-op', '']
            test_args += ['--unsorted', '-k', 'test_template_set']
        args = ['py.test', '-s', '--tb=short', '--device=' + mocklib.DEVICE_NAME]
        if not builtin_drned:
            args.append('--unreserved')
        args += test_args
        assert sorted(call[0][0]) == sorted(args)

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
    def test_transition_builtin(self, xpatch):
        self.setup_states_data(xpatch.system)
        root = xpatch.ncs.data['root']
        root.drned_xmnr.drned_directory = 'builtin'
        output = self.invoke_action('transition-to-state',
                                    state_name='state1',
                                    rollback=False)
        self.check_output(output)
        popen_mock = xpatch.system.patches['subprocess']['Popen']
        self.check_drned_call(popen_mock.call_args, 'state1', rollback=False, builtin_drned=True)

    @xtest_patch
    def test_explore_states(self, xpatch):
        self.setup_states_data(xpatch.system)
        output = self.invoke_action('explore-transitions',
                                    states=self.states,
                                    stop_after=self.stop_params())
        self.check_output(output)
        self.check_popen_invocations(xpatch)

    def check_popen_invocations(self, xpatch, count=None):
        popen_mock = xpatch.system.patches['subprocess']['Popen']
        ls = len(self.states)
        max = ls*ls if count is None else count
        calls = 0
        transitions = 0
        call_iter = iter(popen_mock.call_args_list)
        for from_state in self.states:
            self.check_drned_call(next(call_iter), from_state)
            calls += 1
            for to_state in self.states:
                if transitions == max:
                    break
                if from_state == to_state:
                    continue
                self.check_drned_call(next(call_iter), to_state, rollback=True)
                calls += 1
                transitions += 1
            if transitions == max:
                break
        assert len(popen_mock.call_args_list) == calls

    @xtest_patch
    def test_explore_stop_cases(self, xpatch):
        self.setup_states_data(xpatch.system)
        output = self.invoke_action('explore-transitions',
                                    states=self.states,
                                    stop_after=self.stop_params(cases=3))
        self.check_output(output)
        self.check_popen_invocations(xpatch, 3)

    @xtest_patch
    def test_explore_stop_time(self, xpatch):
        timer = StopTestTimer(step=1)
        popen_mock = xpatch.system.patches['subprocess']['Popen']
        popen_mock.side_effect = timer.tick
        self.setup_states_data(xpatch.system)
        TIME_SEC = 3
        TIME_MIN = 2
        with mock.patch('time.time', side_effect=timer.time):
            output = self.invoke_action('explore-transitions',
                                        states=self.states,
                                        stop_after=self.stop_params(seconds=TIME_SEC-1))
            self.check_output(output)
            # for every len(states) transitions under test there is one more
            exp_calls = TIME_SEC + TIME_SEC // len(self.states) + 1
            assert len(popen_mock.call_args_list) == exp_calls
            timer.reset(step=60)
            output = self.invoke_action('explore-transitions',
                                        states=self.states,
                                        stop_after=self.stop_params(minutes=TIME_MIN-1))
            self.check_output(output)
            exp_calls += TIME_MIN + TIME_MIN // len(self.states) + 1
            assert len(popen_mock.call_args_list) == exp_calls

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
                                    stop_after=self.stop_params())
        assert output.success is None
        assert 'Failed to initialize state otherstate1' in output.error
        assert '==> otherstate1' in output.failure

    @xtest_patch
    def test_walk_states(self, xpatch):
        self.setup_states_data(xpatch.system)
        output = self.invoke_action('walk-states',
                                    rollback=False,
                                    states=self.states)
        self.check_output(output)
        popen_mock = xpatch.system.patches['subprocess']['Popen']
        self.check_drned_call(popen_mock.call_args, fnames=self.states)
        popen_mock.assert_called_once()

    @xtest_patch
    def test_walk_rollback_states(self, xpatch):
        self.setup_states_data(xpatch.system)
        output = self.invoke_action('walk-states',
                                    rollback=True,
                                    states=self.states)
        self.check_output(output)
        popen_mock = xpatch.system.patches['subprocess']['Popen']
        self.check_drned_call(popen_mock.call_args, rollback=True, fnames=self.states)
        popen_mock.assert_called_once()


class DrnedOutput(object):
    def __init__(self, state_data, filter_type, system):
        self.state_data = state_data
        self.system = system
        self.filter_type = filter_type
        self.output_iter = self.output()
        self.failure = False
        self.popen_mock = system.patches['subprocess']['Popen']
        self.popen_mock.side_effect = self.popen_effect

    def popen_effect(self, *args, **kwargs):
        next_data = next(self.output_iter)
        self.system.proc_data(bytestream(next_data))
        if self.failure:
            self.failure = False
            self.popen_mock.return_value.wait = mock.Mock(return_value=-1)
        else:
            self.popen_mock.return_value.wait = mock.Mock(return_value=0)
        return mock.DEFAULT


class DrnedTransitionOutput(DrnedOutput):
    def expected_output(self):
        compare_success = 'succeeded'
        if self.filter_type == 'all':
            transition_output = drned_transition_output
            compare_success = ''
        elif self.filter_type == 'drned-overview':
            transition_output = drned_transition_output_filtered
        else:
            transition_output = ''
        yield transition_output.format(state_to=self.state_data, compare_result=compare_success)

    def output(self):
        yield drned_transition_output.format(state_to=self.state_data, compare_result='')


class DrnedTransitionOutputFailure(DrnedOutput):
    def expected_output(self):
        yield drned_transition_output_filtered.format(state_to=self.state_data,
                                                      compare_result='failed')

    def output(self):
        yield drned_transition_output.format(state_to=self.state_data, compare_result='diff ')


class DrnedExploreOutput(DrnedOutput):
    def expected_output(self):
        if self.filter_type == 'none':
            return
        count = len(self.state_data)
        num_transitions = count * (count-1)
        yield 'Found {} states recorded for device {} '.format(count, mocklib.DEVICE_NAME)
        yield 'which gives a total of {} transitions.\n'.format(num_transitions)
        index = 0
        if self.filter_type == 'all':
            start_output = drned_explore_start_output
            transition_output = drned_transition_output
            compare_success = ''
        elif self.filter_type == 'drned-overview':
            start_output = drned_explore_start_output_filtered
            transition_output = drned_transition_output_filtered
            compare_success = 'succeeded'
        else:
            start_output = transition_output = ''
        for from_state in self.state_data:
            yield 'Starting with state {}\n'.format(from_state)
            if self.filter_type != 'overview':
                yield start_output.format(state_from=from_state)
            if from_state == 'otherstate1':
                yield drned_init_failed.format(state_from=from_state)
                continue
            for to_state in self.state_data:
                if to_state == from_state:
                    continue
                index += 1
                yield 'Transition {}/{}: {} ==> {}\n'.format(
                    index, num_transitions, from_state, to_state)
                if self.filter_type != 'overview':
                    yield transition_output.format(state_to=to_state,
                                                   compare_result=compare_success)
                if to_state == 'otherstate1':
                    yield drned_transition_failed

    def output(self):
        for from_state in self.state_data:
            if from_state == 'otherstate1':
                self.failure = True
            yield drned_explore_start_output.format(state_from=from_state)
            if from_state == 'otherstate1':
                continue
            for to_state in self.state_data:
                if to_state == from_state:
                    continue
                if to_state == 'otherstate1':
                    self.failure = True
                yield drned_transition_output.format(state_to=to_state, compare_result='')


class DrnedWalkOutput(DrnedOutput):
    def expected_output(self):
        if self.filter_type == 'none':
            return
        elif self.filter_type == 'all':
            start_output = ''
            intro_output = drned_walk_output_intro
            trans_output = drned_walk_output
            outro_output = drned_walk_output_outro
        else:
            start_output = 'Prepare the device\n'
            intro_output = 'Test transition to {state_to}\n'
            trans_output = drned_walk_output_filtered
            outro_output = drned_walk_output_outro_filtered
        yield start_output
        for state in self.state_data:
            end_op = '--end-op= ' if state == 'otherstate1' else ''
            yield intro_output.format(state_to=state, end_op=end_op)
            if self.filter_type != 'overview':
                yield trans_output.format(state_to=state)
        if self.filter_type == 'overview':
            yield 'Device cleanup\n'
        else:
            yield outro_output

    def full_output(self):
        for state in self.state_data:
            end_op = '--end-op= ' if state == 'otherstate1' else ''
            yield drned_walk_output_intro.format(state_to=state, end_op=end_op)
            yield drned_walk_output.format(state_to=state)
        yield drned_walk_output_outro

    def output(self):
        yield ''.join(self.full_output())


class TransitionsLogFiltersTestBase(TransitionsTestBase):
    def setup_filter(self, xpatch, level, redirect=None):
        root = xpatch.ncs.data['root']
        root.drned_xmnr.log_detail.cli = level
        root.drned_xmnr.log_detail.redirect = redirect

    def filter_test_run(self, xpatch, filter_type, output_data, state_data, action, **params):
        self.setup_filter(xpatch, filter_type)
        self.setup_states_data(xpatch.system)
        drned_output = output_data(state_data, filter_type, xpatch.system)
        self.invoke_action(action, **params)
        calls = xpatch.ncs.data['ncs']['cli_write'].call_args_list
        assert ''.join(drned_output.expected_output()) == \
            ''.join(call[0][2] for call in calls)

    def explore_filter_test_run(self, xpatch, filter_type):
        self.filter_test_run(xpatch, filter_type, DrnedExploreOutput, self.states,
                             'explore-transitions',
                             states=self.states, stop_after=self.stop_params())

    def transition_filter_test_run(self, xpatch, filter_type):
        self.filter_test_run(xpatch, filter_type, DrnedTransitionOutput, 'state1',
                             'transition-to-state', state_name='state1', rollback=True)

    def walk_filter_test_run(self, xpatch, filter_type):
        self.filter_test_run(xpatch, filter_type, DrnedWalkOutput, self.states,
                             'walk-states', states=self.states, rollback=False)


class TestTransitionsLogFilters(TransitionsLogFiltersTestBase):
    def action_uinfo(self):
        return mock.Mock(context='cli')

    @xtest_patch
    def test_filter_explore_overview(self, xpatch):
        self.explore_filter_test_run(xpatch, 'overview')

    @xtest_patch
    def test_filter_explore_drned(self, xpatch):
        self.explore_filter_test_run(xpatch, 'drned-overview')

    @xtest_patch
    def test_filter_explore_all(self, xpatch):
        self.explore_filter_test_run(xpatch, 'all')

    @xtest_patch
    def test_filter_explore_none(self, xpatch):
        self.explore_filter_test_run(xpatch, 'none')

    @xtest_patch
    def test_filter_transition_overview(self, xpatch):
        self.transition_filter_test_run(xpatch, 'overview')

    @xtest_patch
    def test_filter_transition_all(self, xpatch):
        self.transition_filter_test_run(xpatch, 'all')

    @xtest_patch
    def test_filter_transition_none(self, xpatch):
        self.transition_filter_test_run(xpatch, 'none')

    @xtest_patch
    def test_filter_transition_drned(self, xpatch):
        self.transition_filter_test_run(xpatch, 'drned-overview')

    @xtest_patch
    def test_filter_transition_failure(self, xpatch):
        self.filter_test_run(xpatch, 'drned-overview', DrnedTransitionOutputFailure, 'state1',
                             'transition-to-state', state_name='state1', rollback=True)

    @xtest_patch
    def test_filter_walk_overview(self, xpatch):
        self.walk_filter_test_run(xpatch, 'overview')

    @xtest_patch
    def test_filter_walk_all(self, xpatch):
        self.walk_filter_test_run(xpatch, 'all')

    @xtest_patch
    def test_filter_walk_none(self, xpatch):
        self.walk_filter_test_run(xpatch, 'none')

    @xtest_patch
    def test_filter_walk_drned(self, xpatch):
        self.walk_filter_test_run(xpatch, 'drned-overview')


class TestTransitionsLogFiltersRedirect(TransitionsLogFiltersTestBase):
    @xtest_patch
    def test_filter_redirect(self, xpatch):
        self.setup_filter(xpatch, 'drned-overview', 'redirect.output')
        self.setup_states_data(xpatch.system)
        xmnr_dir = mocklib.XMNR_DIRECTORY
        drned_output = DrnedWalkOutput(self.states, 'drned-overview', xpatch.system)
        self.invoke_action('walk-states', states=self.states, rollback=False)
        with open(os.path.join(xmnr_dir, 'redirect.output')) as r_out:
            assert r_out.readline() == '\n'
            assert re.match('-+$', r_out.readline()) is not None
            assert re.match('[0-9]{4}(-[0-9]{2}){2} [0-9]{2}(:[0-9]{2}){2}\.[0-9]* - walk states$',
                            r_out.readline()) is not None
            assert re.match('-+$', r_out.readline()) is not None
            assert ''.join(drned_output.expected_output()) == r_out.read()

    @xtest_patch
    def test_filter_no_cli(self, xpatch):
        self.setup_filter(xpatch, 'all')
        self.setup_states_data(xpatch.system)
        DrnedWalkOutput(self.states, 'none', xpatch.system)
        self.invoke_action('walk-states', states=self.states, rollback=False)
        calls = xpatch.ncs.data['ncs']['cli_write'].call_args_list
        assert ''.join(call[0][2] for call in calls) == ''


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
        xpatch.system.proc_data(bytestream(drned_collect_output.format(**collect_dict)))
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
