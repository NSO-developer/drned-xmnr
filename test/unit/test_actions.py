from . import mocklib
from .mocklib import xtest_patch
from unittest import mock
import pytest
from drned_xmnr import action
from drned_xmnr.op import config_op, base_op, coverage_op, ex
import os
import sys
import re
from random import randint
import functools
import itertools
import _ncs


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
commit dry-run
% No modifications to commit.
commit
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
============================== load(./mockdevice.cfg)
--generic drned data--
============================== sync_from()
test_template_single[../states/{state_to}.state.cfg]
--generic drned data--
============================== rload(../states/{state_to}.state.cfg)
--generic drned data--
============================== commit()
--generic drned data--
commit commit-queue sync
commit-queue {{
    id 1529558544009
    status failed
    failed-device {{
        name mockdevice
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
commit commit-queue sync
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
failed to commit, configuration refused by the device
   compare config
       {compare_result}
   rollback
   commit
       succeeded
   compare config
       succeeded
'''


drned_walk_output_base = '''\
--generic drned data--
============================== rload(../states/{{state_to}}.state.cfg)
--generic drned data--
============================== commit()
--generic drned data--
{commit_message}
Commit complete.
--generic drned data--
============================== compare_config()
--generic drned data--
============================== rollback()
--generic drned data--
============================== commit()
--generic drned data--
{commit_message}
Commit complete.
--generic drned data--
============================== compare_config()
--generic drned data--
'''

commit_queue_message = '''\
commit commit-queue sync
commit-queue {{
    id 1529566674280
    status completed
}}
'''
drned_walk_output = drned_walk_output_base.format(commit_message=commit_queue_message)
drned_walk_output_noqueues = drned_walk_output_base.format(commit_message='commit')

drned_walk_output_outro = '''\
### TEARDOWN, RESTORE DEVICE ###
--generic drned data--
============================== sync_from()
--generic drned data--
============================== load(drned-work/before-session.xml)
--generic drned data--
============================== commit()
--generic drned data--
commit
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
    states = ('state1', 'state2', 'other.state1')

    def check_output(self, output, success=None):
        assert output.error is None
        assert output.failure is None
        if success is not None:
            assert output.success == success

    def unit_log_file(self):
        if not hasattr(self, 'log_file'):
            self.log_file = self.real_open('/tmp/unit.log', 'a')
        return self.log_file

    def log(self, prefix, *args):
        lf = self.unit_log_file()
        print(prefix, *args, file=lf)
        lf.flush()

    def setup_log(self, handler):
        handler.log = mock.Mock()
        for level in self.log_levels:
            prefix = '<{}>'.format(level.upper())
            setattr(handler.log, level, functools.partial(self.log, prefix))

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
            stname = state + base_op.XmnrBase.cfg_statefile_extension
            system.ff_patcher.fs.create_file(os.path.join(spath, stname),
                                             contents='{} test data'.format(state))
            if state_path is None:
                system.ff_patcher.fs.create_file(os.path.join(spath, stname + '.load'),
                                                 contents=config_op.state_metadata)


class TestStartup(TestBase):
    """Simple action registration and setup test.

    """
    def test_registry(self):
        xmnr = action.Xmnr()
        xmnr.setup()
        xmnr.register_action.assert_has_calls([mock.call('drned-xmnr', action.ActionHandler),
                                               mock.call('drned-xmnr-completion',
                                                         action.CompletionHandler)])
        xmnr.register_service.assert_has_calls([mock.call('coverage-data', action.XmnrDataHandler),
                                                mock.call('xmnr-states', action.XmnrDataHandler)])


class TestSetup(TestBase):
    """Test of the action `setup-xmnr`.

    """
    def setup_fs_data(self, system):
        system.ff_patcher.fs.create_dir(mocklib.XMNR_DIRECTORY)
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
        output = self.invoke_action('setup-xmnr', overwrite=True, use_commit_queue=True,
                                    save_default_config=False)
        self.check_output(output)
        with open(os.path.join(self.test_run_dir, 'drned-skeleton', 'skeleton')) as skel_test:
            assert skel_test.read() == 'drned skeleton'
        popen_mock = xpatch.system.patches['subprocess']['Popen']
        popen_mock.assert_called_once()
        assert popen_mock.call_args[0] == (['make', 'env.sh'],)


class TestPytestEnv(TestBase):
    """Test lookup for available `pytest` exacutable.

    """
    def set_env(self, executable):
        base_op.ActionBase._pytest_executable = None
        self.xpatch.system.set_pytest_env(executable)

    @xtest_patch
    def test_environments(self, xpatch):
        self.xpatch = xpatch
        py_variant = str(sys.version_info[0])
        ab = base_op.ActionBase(mock.Mock(), mocklib.DEVICE_NAME, None, mock.Mock())
        try:
            for executable in ['pytest', 'py.test',
                               'pytest-' + py_variant, 'py.test-' + py_variant]:
                self.set_env(executable)
                assert ab.pytest_executable() == executable
            with pytest.raises(ex.ActionError):
                self.set_env(None)
                ab.pytest_executable()
        finally:
            self.set_env('py.test')  # expected by other tests


class LoadConfig(object):
    exc_message = 'Error: {} cannot be loaded'

    def __init__(self, ncs, fail_states=[]):
        self.fail_states = fail_states
        self.tcx_mock = mocklib.CxMgrMock(load_config=mock.Mock(side_effect=self.load_config))
        ncs.data['trans_mgr'].trans_obj = self.tcx_mock
        states_dir = os.path.join(TestBase.test_run_dir, 'states')
        self.sub_rx = re.compile(r'/{}/(.*)\.state\.cfg'.format(states_dir))
        self.loaded_states = []

    def load_config(self, _flags, filename):
        state = self.sub_rx.sub(r'\1', filename)
        self.loaded_states.append(state)
        if state in self.fail_states:
            raise _ncs.error.Error(self.exc_message.format(state))


class LoadSaveConfig(object):
    def __init__(self, system, ncs):
        self.tcx_mock = mocklib.CxMgrMock(load_config=mock.Mock(side_effect=self.load_config),
                                          save_config=mock.Mock(side_effect=self.save_config))
        ncs.data['trans_mgr'].trans_obj = self.tcx_mock
        self.data = []
        self.system = system

    def load_config(self, _flags, filename):
        with open(filename) as data:
            self.data = ''.join(data)

    def save_config(self, _type, _path):
        self.system.socket_data(self.data.encode())
        return 1


class TestStates(TestBase):
    """Test recording, importing, deleting and listing of device states.

    Involves mocking of the states data on the fake filesystem, done
    in `TestBase.setup_states_data`.

    """
    def state_files(self, states, disabled):
        return sorted(itertools.chain((st + '.state.cfg.disabled' for st in disabled),
                                      *((st + '.state.cfg', st + '.state.cfg.load')
                                        for st in states)))

    def check_states(self, states, disabled=[]):
        statesfiles = os.listdir(os.path.join(self.test_run_dir, 'states'))
        assert (sorted(statesfiles) == self.state_files(states, disabled))

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
                                    overwrite=False,
                                    including_rollbacks=None)
        self.check_output(output)
        state_path = 'states/test_state' + base_op.XmnrBase.cfg_statefile_extension
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
                                    overwrite=False,
                                    including_rollbacks=None)
        self.check_output(output)
        state_path = 'states/test_state_xml' + base_op.XmnrBase.xml_statefile_extension
        assert os.path.exists(os.path.join(self.test_run_dir, state_path))
        with open(os.path.join(self.test_run_dir, state_path + '.load')) as metadata:
            assert metadata.read() == config_op.state_metadata
        with open(os.path.join(self.test_run_dir, state_path)) as state_data:
            assert state_data.read() == test_state_data_xml

    def invoke_import_state_files(self, path, expected_success=True, **extra_action_params):
        output = self.invoke_action('import-state-files',
                                    file_path_pattern=os.path.join(path, '*1.state.cfg'),
                                    format="c-style",
                                    target_format="c-style",
                                    merge=False,
                                    **extra_action_params)
        states = None
        if expected_success:
            self.check_output(output)
            states = sorted(state for state in self.states if state.endswith('1'))
            self.check_states(states)
        else:
            assert output.failure is not None or output.error is not None
        return states

    @xtest_patch
    def test_import_states(self, xpatch):
        path = '/tmp/data'
        xpatch.system.ff_patcher.fs.create_dir(path)
        self.setup_states_data(xpatch.system, state_path=path)
        LoadSaveConfig(xpatch.system, xpatch.ncs)
        destdir = os.path.join(self.test_run_dir, 'states')
        states = self.invoke_import_state_files(path)
        assert states is not None
        test_data_p = 'devices device {} config\n{{}} test data'.format(mocklib.DEVICE_NAME)
        for state in states:
            filename = os.path.join(destdir, state + '.state.cfg')
            with open(filename) as state_file:
                assert state_file.read() == test_data_p.format(state)
            with open(filename + '.load') as metadata:
                assert metadata.read() == config_op.state_metadata

    @xtest_patch
    def test_import_states_skip(self, xpatch):
        path = '/tmp/data'
        xpatch.system.ff_patcher.fs.create_dir(path)
        self.setup_states_data(xpatch.system, state_path=path)
        LoadSaveConfig(xpatch.system, xpatch.ncs)
        # import first time into clean environment
        states = self.invoke_import_state_files(path)
        assert len(states) > 0
        # try default import again and fail
        states = self.invoke_import_state_files(path, expected_success=False)
        assert states is None
        # reimport with skipping already existing states
        states = self.invoke_import_state_files(path, skip_existing=True)
        assert len(states) > 0
        # reimport with overwrite
        states = self.invoke_import_state_files(path, overwrite=True)
        assert len(states) > 0

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
                                    state_name='other.state1')
        self.check_output(output)
        states = list(self.states[:])
        states.remove('other.state1')
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
    def test_disable_states(self, xpatch):
        self.setup_states_data(xpatch.system)
        output = self.invoke_action('disable-state',
                                    state_name_pattern=None,
                                    state_name='other.state1')
        self.check_output(output)
        self.check_states(self.states, ['other.state1'])
        output = self.invoke_action('enable-state',
                                    state_name_pattern='*',
                                    state_name=None)
        self.check_output(output)
        self.check_states(self.states)
        output = self.invoke_action('disable-state',
                                    state_name_pattern='*state1',
                                    state_name=None)
        self.check_output(output)
        self.check_states(self.states, ['state1', 'other.state1'])
        output = self.invoke_action('delete-state',
                                    state_name_pattern=None,
                                    state_name='other.state1')
        self.check_output(output)
        self.check_states([state for state in self.states if state != 'other.state1'],
                          ['state1'])

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


class TestConvertMessage(TestBase):
    """Test the `import-convert` action.

    The action is invoked, but the `Popen` call to run the conversion
    itself is mocked and a fake data is inserted as its standard
    output.  The tests verify that the standard output data is
    interpreted correctly.

    """
    config_states = ['clistate1', 'clistate2', 'otherclistate', 'clistate3']
    config_path = '/cfgpath'

    def action_uinfo(self):
        return mock.Mock(context='cli')

    def setup_config_files(self, system, failures={}, format_failures={}, states=None):
        if states is None:
            states = self.config_states
        for state in states:
            # this is needed, the action prepares the state set based on existing files
            filename = os.path.join(self.config_path, state + '.cfg')
            system.ff_patcher.fs.create_file(filename, contents='{} test data'.format(state))
        self.config_pattern = os.path.join(self.config_path, '*.cfg')
        self.system = system
        self.failures = failures
        self.format_failures = format_failures
        self.states_to_process = states[:]

    def popen_effect(self, *args, **kwargs):
        cwd = kwargs['cwd']
        self.path_pattern = os.path.join(cwd, 'drned-ncs', '{}.xml')
        data = []
        for state in self.states_to_process:
            path = self.path_pattern.format(state)
            self.system.ff_patcher.fs.create_file(path)
            if state in self.failures:
                data.append('failed to convert group {}'.format(state))
            elif state in self.format_failures:
                data.append('Filename format not understood: ' + path)
            else:
                data.append('converting {}.cfg to {}'.format(state, path))
        self.system.proc_data(b''.join((line + '\n').encode() for line in data))
        return mock.DEFAULT

    def setup_and_start(self, xpatch, **setup_args):
        self.setup_config_files(xpatch.system, **setup_args)
        popen_mock = xpatch.system.patches['subprocess']['Popen']
        popen_mock.side_effect = self.popen_effect
        output = self.invoke_action('import-convert-cli-files',
                                    file_path_pattern=self.config_pattern,
                                    overwrite=True,
                                    driver='cli-device')
        return output

    def expected_writes(self, states=None):
        if states is None:
            states = self.config_states
        for state in states:
            if state in self.failures:
                yield 'failed to import group {}\n'.format(state)
            elif state in self.format_failures:
                filename = self.path_pattern.format(state)
                yield 'unknown filename format: {}; should be name[:index].ext\n'.format(filename)
            else:
                yield 'importing state {}\n'.format(state)

    @xtest_patch
    def test_convert_message(self, xpatch):
        self.check_output(self.setup_and_start(xpatch))
        calls = xpatch.ncs.data['ncs']['cli_write'].call_args_list
        assert ''.join(self.expected_writes()) == ''.join(call[0][2] for call in calls)

    @xtest_patch
    def test_convert_failure_messages(self, xpatch):
        output = self.setup_and_start(xpatch, failures={'otherclistate'})
        assert output.failure is not None
        calls = xpatch.ncs.data['ncs']['cli_write'].call_args_list
        assert ''.join(self.expected_writes()) == ''.join(call[0][2] for call in calls)

    @xtest_patch
    def test_convert_file_format(self, xpatch):
        output = self.setup_and_start(xpatch, format_failures={'otherclistate'})
        assert output.failure is not None
        calls = iter(xpatch.ncs.data['ncs']['cli_write'].call_args_list)
        assert ''.join(self.expected_writes()) == ''.join(call[0][2] for call in calls)


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
    """Basic tests the three transitions actions.

    All state data is mocked, all that is verified is that DrNED
    `pytest` is called with correct arguments.

    """
    def check_drned_new_call(self, call, rollback=False):
        state_arg = call[0][0][4]
        state_rx = r'-k .*\[(.*)\.state\.cfg\]'
        match = re.match(state_rx, state_arg)
        assert match
        state = match.groups()[0]
        self.check_drned_call(call, state, rollback)
        return state

    def check_drned_call(self, call, state=None, rollback=False, fnames=None, builtin_drned=False):
        if fnames is None:
            test = 'test_template_single' if rollback else 'test_template_raw'
            test_args = ['-k {}[{}.state.cfg]'.format(test, state)]
        else:
            state_dir = os.path.join(self.test_run_dir, 'states')
            full_dir = os.path.abspath(state_dir)
            test_args = ['--fname={}'.format(os.path.join(full_dir, state_fname + '.state.cfg'))
                         for state_fname in fnames]
            if not rollback:
                test_args += ['--end-op', '']
            test_args += ['--ordered=false', '-k', 'test_template_set']
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

    @xtest_patch
    def test_explore_ignore_states(self, xpatch):
        self.setup_states_data(xpatch.system)
        output = self.invoke_action('explore-transitions',
                                    states=[],
                                    ignore_states=['state1'],
                                    stop_after=self.stop_params())
        self.check_output(output)
        states = list(self.states)
        states.remove('state1')
        self.check_popen_invocations(xpatch, states=states)

    def check_popen_invocations(self, xpatch, count=None, states=None):
        popen_mock = xpatch.system.patches['subprocess']['Popen']
        if states is None:
            states = self.states
        ls = len(states)
        max = ls * ls if count is None else count
        calls = 0
        transitions = 0
        call_iter = iter(popen_mock.call_args_list)
        from_states = list(states)
        while from_states:
            call = next(call_iter)
            from_state = self.check_drned_new_call(call)
            from_states.remove(from_state)
            calls += 1
            to_states = list(states)
            to_states.remove(from_state)
            while to_states:
                if transitions == max:
                    break
                to_state = self.check_drned_new_call(next(call_iter), rollback=True)
                to_states.remove(to_state)
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
                                        stop_after=self.stop_params(seconds=TIME_SEC - 1))
            self.check_output(output)
            # for every len(states) transitions under test there is one more
            exp_calls = TIME_SEC + TIME_SEC // len(self.states) + 1
            assert len(popen_mock.call_args_list) == exp_calls
            timer.reset(step=60)
            output = self.invoke_action('explore-transitions',
                                        states=self.states,
                                        stop_after=self.stop_params(minutes=TIME_MIN - 1))
            self.check_output(output)
            exp_calls += TIME_MIN + TIME_MIN // len(self.states) + 1
            assert len(popen_mock.call_args_list) == exp_calls

    def popen_fail_state(self, args, *rest, **kwargs):
        for arg in args:
            if 'other.state1' in arg:
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
        assert 'Failed to initialize state other.state1' in output.error
        assert '==> other.state1' in output.failure

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
    def test_walk_disabled_states(self, xpatch):
        self.setup_states_data(xpatch.system)
        output = self.invoke_action('disable-state',
                                    state_name_pattern=None,
                                    state_name='other.state1')
        self.check_output(output)
        output = self.invoke_action('walk-states',
                                    rollback=False,
                                    ignore_states=[],
                                    states=[])
        self.check_output(output)
        popen_mock = xpatch.system.patches['subprocess']['Popen']
        states = list(self.states)
        states.remove('other.state1')
        self.check_drned_call(popen_mock.call_args, fnames=states)
        popen_mock.assert_called_once()

    @xtest_patch
    def test_walk_ignore_states(self, xpatch):
        self.setup_states_data(xpatch.system)
        output = self.invoke_action('walk-states',
                                    rollback=False,
                                    states=[],
                                    ignore_states=['other.state1'])
        self.check_output(output)
        states = list(self.states)
        states.remove('other.state1')
        popen_mock = xpatch.system.patches['subprocess']['Popen']
        self.check_drned_call(popen_mock.call_args, fnames=states)
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
        next_data = next(self.output_iter).encode()
        self.system.proc_data(next_data)
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
        elif self.filter_type == 'overview':
            transition_output = 'failed to commit, configuration refused by the device\n'
        else:
            transition_output = ''
        yield transition_output.format(state_to=self.state_data, compare_result=compare_success)

    def output(self):
        yield drned_transition_output.format(state_to=self.state_data, compare_result='')


class DrnedTransitionOutputFailure(DrnedOutput):
    def expected_output(self):
        compare_result = 'failed\n' \
            'configuration comparison failed, configuration artifacts on the device'
        yield drned_transition_output_filtered.format(state_to=self.state_data,
                                                      compare_result=compare_result)

    def output(self):
        yield drned_transition_output.format(state_to=self.state_data, compare_result='diff ')


class DrnedExploreOutput(DrnedOutput):
    def expected_output(self):
        if self.filter_type == 'none':
            return
        count = len(self.state_data)
        num_transitions = count * (count - 1)
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
        elif self.filter_type == 'overview':
            start_output = ''
            compare_success = ''
            transition_output = 'failed to commit, configuration refused by the device\n'
        else:
            start_output = transition_output = ''
        for from_state in self.state_data:
            yield 'Starting with state {}\n'.format(from_state)
            if self.filter_type != 'overview':
                yield start_output.format(state_from=from_state)
            if from_state == 'other.state1':
                yield drned_init_failed.format(state_from=from_state)
                continue
            for to_state in self.state_data:
                if to_state == from_state:
                    continue
                index += 1
                yield 'Transition {}/{}: {} ==> {}\n'.format(
                    index, num_transitions, from_state, to_state)
                yield transition_output.format(state_to=to_state,
                                               compare_result=compare_success)
                if to_state == 'other.state1':
                    yield drned_transition_failed

    def output(self):
        for from_state in self.state_data:
            if from_state == 'other.state1':
                self.failure = True
            yield drned_explore_start_output.format(state_from=from_state)
            if from_state == 'other.state1':
                continue
            for to_state in self.state_data:
                if to_state == from_state:
                    continue
                if to_state == 'other.state1':
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
            end_op = '--end-op= ' if state == 'other.state1' else ''
            yield intro_output.format(state_to=state, end_op=end_op)
            if self.filter_type != 'overview':
                yield trans_output.format(state_to=state)
        if self.filter_type != 'overview':
            yield outro_output

    def full_output(self):
        for state in self.state_data:
            end_op = '--end-op= ' if state == 'other.state1' else ''
            yield drned_walk_output_intro.format(state_to=state, end_op=end_op)
            yield drned_walk_output.format(state_to=state)
        yield drned_walk_output_outro

    def output(self):
        yield ''.join(self.full_output())


class TransitionsLogFiltersTestBase(TransitionsTestBase):
    def setup_filter(self, xpatch, level, redirect=None):
        root = xpatch.ncs.data['root']
        root.drned_xmnr.log_detail.cli = level
        root.drned_xmnr.cli_log_file = redirect

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
    """Test DrNED output filtering.

    In these tests one of the three transition actions is run, but the
    `Popen` calls are captured and prepared data is inserted as their
    standard output.  It is subsequently verified that the filtered
    output corresponds to the prepared filtered data.

    """
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
    """Test DrNED output redirecting and behavior in other context than
    CLI.

    """
    @xtest_patch
    def test_filter_redirect(self, xpatch):
        redir_file = os.path.join(self.test_run_dir, 'redirect.output')
        self.setup_filter(xpatch, 'drned-overview', redir_file)
        self.setup_states_data(xpatch.system)
        drned_output = DrnedWalkOutput(self.states, 'drned-overview', xpatch.system)
        output = self.invoke_action('walk-states', states=self.states,
                                    rollback=False)
        self.check_output(output)
        with open(redir_file) as r_out:
            print('redir:', r_out.read())
        with open(redir_file) as r_out:
            assert r_out.readline() == '\n'
            assert re.match('-+$', r_out.readline()) is not None
            assert re.match(r'[0-9]{4}(-[0-9]{2}){2} [0-9]{2}(:[0-9]{2}){2}\.[0-9]* - walk states$',
                            r_out.readline()) is not None
            assert re.match('-+$', r_out.readline()) is not None
            assert ''.join(drned_output.expected_output()) == r_out.read()

    @xtest_patch
    def test_filter_no_cli(self, xpatch):
        self.setup_filter(xpatch, 'all')
        self.setup_states_data(xpatch.system)
        DrnedWalkOutput(self.states, 'none', xpatch.system)
        output = self.invoke_action('walk-states', states=self.states, rollback=False)
        self.check_output(output)
        calls = xpatch.ncs.data['ncs']['cli_write'].call_args_list
        assert ''.join(call[0][2] for call in calls) == ''


class TestCoverage(TestBase):
    """Test coverage actions and operational data.

    For the `collect` action, the coverage data is mocked, stored in
    `unit.mocklib.SystemMock.proc_data` and returned as a process
    output.

    """
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
        xpatch.system.proc_data(drned_collect_output.format(**collect_dict).encode())
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
