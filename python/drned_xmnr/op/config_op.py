# -*- mode: python; python-indent: 4 -*-

import fnmatch
import os
import random
import socket
import subprocess
import time
import itertools

import _ncs
from ncs import maapi, maagic

import base_op
from ex import ActionError


# py.test -s --tb=short -k test_template_set --device=ce0 --init=simple_tests/init_state.cfg --fname=simple_tests/skoda0_state.cfg --unreserved
# py.test -s --tb=short -k 'test_coverage' --device ce0 --yangpath=src/yang/ --fname=src/yang/Cisco-IOS-XE-native.yang --fname=src/yang/Cisco-IOS-XE-bgp.yang 


state_metadata = """\
# automatically generated
# all XMNR state files need to be loaded in 'override' mode
mode = override
"""


class ConfigOp(base_op.BaseOp):
    statefile_extension = '.state.cfg'

    def state_name_to_filename(self, statename, devname):
        return statename + self.statefile_extension

    def state_filename_to_name(self, filename, devname):
        return filename[:-len(self.statefile_extension)]

    def run_with_trans(self, callback, write=False):
        if self.uinfo.actx_thandle == -1:
            if write:
                with maapi.single_write_trans(self.uinfo.username, self.uinfo.context) as trans:
                    return callback(trans)
            else:
                with maapi.single_read_trans(self.uinfo.username, self.uinfo.context) as trans:
                    return callback(trans)
        else:
            mp = maapi.Maapi()
            return callback(mp.attach(self.uinfo.actx_thandle))

    def setup_drned_env(self, trans):
        """Build a dictionary that is supposed to be passed to `Popen` as the
        environment.
        """
        env = dict(os.environ)
        root = maagic.get_root(trans)
        drdir = root.drned_xmnr.drned_directory
        if drdir is None:
            try:
                drdir = env['DRNED']
            except KeyError:
                raise ActionError('DrNED installation directory not set; ' +
                                  'set /drned-xmnr/drned-directory or the ' +
                                  'environment variable DRNED')
        else:
            env['DRNED'] = drdir
        if 'PYTHONPATH' in env:
            env['PYTHONPATH'] += os.pathsep + drdir
        else:
            env['PYTHONPATH'] = drdir
        try:
            env['PYTHONPATH'] += os.pathsep + env['NCS_DIR'] + '/lib/pyang'
        except KeyError:
            raise ActionError('NCS_DIR not set')
        path = env['PATH']
        # need to remove exec path inserted by NSO
        env['PATH'] = os.pathsep.join(ppart for ppart in path.split(os.pathsep)
                                      if 'ncs/erts' not in ppart)
        return env

    def drned_run(self, drned_args, timeout):
        env = self.run_with_trans(self.setup_drned_env)
        self.log.debug("using env {0}\n".format(env))
        args = ["-s", "--tb=short", "--device="+self.dev_name, "--unreserved"] + drned_args
        args.insert(0, "py.test")
        self.log.debug("drned: {0}".format(args))
        try:
            proc = subprocess.Popen(args,
                                    env=env,
                                    cwd=self.drned_run_directory,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
            self.log.debug("run_outputfun, going in")
        except OSError:
            raise ActionError('DrNED running directory ({0}) does not seem to be set up'
                              .format(self.drned_run_directory))

        def progress_fun(state, stdout):
            self.progress_msg(stdout)
            self.extend_timeout(120)
            return None
        return self.proc_run(proc, progress_fun, timeout)

    def transition_to_state(self, to_state_filename, rollback=False):
        filename = os.path.join(self.states_dir, to_state_filename)
        if not os.path.exists(filename):
            state_name = self.state_filename_to_name(to_state_filename, self.dev_name)
            raise ActionError('No such state: {0}'.format(state_name))

        # need to use relative path for DrNED to accept that
        filename = os.path.relpath(filename, self.drned_run_directory)
        self.log.debug("Transition_to_state: {0}\n".format(filename))

        # Max 120 seconds for executing DrNED
        self.extend_timeout(120)
        if rollback:
            args = ["test_template_set", "--fname={0}".format(filename)]
        else:
            args = ["test_template_raw[{0}]".format(filename)]
        result = self.drned_run(["-k"] + args, timeout=120)
        self.log.debug("Test case completed\n")
        if result != 0:
            return "drned failed"
        return True


class DeleteStateOp(ConfigOp):
    def _init_params(self, params):
        self.state_name = self.param_default(params, "state_name", "")

    def perform(self):
        self.log.debug("config_delete_state() with device {0}".format(self.dev_name))
        state_filename = self.states_dir + "/" + self.state_name_to_filename(self.state_name, self.dev_name)
        try:
            os.remove(state_filename)
        except:
            return {'error':"Could not delete " + state_filename}
        return {'success':"Deleted " + self.state_name}
        

class ListStatesOp(ConfigOp):
    def _init_params(self, params):
        pass

    def perform(self):
        self.log.debug("config_list_states() with device {0}".format(self.dev_name))
        state_files = [self.state_filename_to_name(f, self.dev_name) for f in os.listdir(self.states_dir) if fnmatch.fnmatch(f, self.state_name_to_filename('*', self.dev_name))]
        return {'success':"Saved device states: " + str(state_files)}


class RecordStateOp(ConfigOp):
    def _init_params(self, params):
        self.state_name = self.param_default(params, "state_name", "")
        self.include_rollbacks = self.param_default(params, "including_rollbacks", 0)

    def perform(self):
        return self.run_with_trans(self._perform, write=True)

    def _perform(self, trans):
        self.log.debug("config_record_state() with device {0}".format(self.dev_name))
        state_name = self.state_name
        self.log.debug("incl_rollbacks="+str(self.include_rollbacks))
        try:
            # list_rollbacks() returns one less rollback than the second argument,
            # i.e. send 2 to get 1 rollback. Therefore the +1
            rollbacks = _ncs.maapi.list_rollbacks(trans.maapi.msock, int(self.include_rollbacks)+1)
            # rollbacks are returned 'most recent first', i.e. reverse chronological order
        except:
            rollbacks = []
        self.log.debug("rollbacks="+str([r.fixed_nr for r in rollbacks]))
        index = 0
        state_filenames = []
        for rb in [None] + rollbacks:
            if rb is None:
                self.log.debug("Recording current transaction state")
            else:
                self.log.debug("Recording rollback"+str(rb.fixed_nr))
                self.log.debug("Recording rollback"+str(rb.nr))
                trans.load_rollback(rb.nr)

            save_id = trans.save_config(_ncs.maapi.CONFIG_C,
                                        "/ncs:devices/device{"+self.dev_name+"}/config")

            state_name_index = state_name
            if index > 0:
                state_name_index = state_name+"-"+str(index)
            state_filename = self.states_dir + "/" + \
                self.state_name_to_filename(state_name_index, self.dev_name)
            with open(state_filename, "w") as state_file:
                try:
                    ssocket = socket.socket()
                    _ncs.stream_connect(
                        sock=ssocket,
                        id=save_id,
                        flags=0,
                        ip='127.0.0.1',
                        port=_ncs.NCS_PORT)

                    while True:
                        config_data = ssocket.recv(4096)
                        if not config_data:
                            break
                        state_file.write(str(config_data))
                        self.log.debug("Data: "+str(config_data))
                finally:
                    ssocket.close()
                with open(state_filename + ".load", 'w') as meta:
                    print >> meta, state_metadata
            state_filenames += [state_name_index]

            # maapi.save_config_result(sock, id) -> None

            index += 1
            trans.revert()
        return {'success': "Recorded states " + str(state_filenames)}


class ExploreTransitionsOp(ConfigOp):
    def _init_params(self, params):
        stp = params.stop_after
        self.stop_time = 24 * int(self.param_default(stp, "days", 0))
        self.stop_time = 60 * int(self.param_default(stp, "hours", self.stop_time))
        self.stop_time = 60 * int(self.param_default(stp, "minutes", self.stop_time))
        self.stop_time =      int(self.param_default(stp, "seconds", self.stop_time))
        self.stop_percent =   int(self.param_default(stp, "percent", 0))
        self.stop_cases =     int(self.param_default(stp, "cases", 0))
        self.states = 'all' if params.all.exists() else list(params.states)

    def perform(self):
        self.log.debug("config_explore_transitions() with device {0}".format(self.dev_name))
        state_files = [f for f in os.listdir(self.states_dir)
                       if fnmatch.fnmatch(f, self.state_name_to_filename('*', self.dev_name))]
        if self.states == 'all':
            states = state_files
        else:
            states = [state + self.statefile_extension
                      for state in self.states
                      if state + self.statefile_extension in state_files]
        num_states = len(states)
        num_transitions = num_states * (num_states - 1)
        if(0 == num_transitions):
            return {'error': "No transitions to make. Run 'config record-state' several times, "
                    "with some device configuration changes in between each recorded state "
                    "before running this command."}
        msg = "Found {0} states recorded for device {1} which gives a total of {2} transitions.\n"
        self.progress_msg(msg.format(num_states, self.dev_name, num_transitions))

        failed_transitions = []
        rstates = list(states)
        random.shuffle(rstates)
        transitions = itertools.permutations(rstates, 2)
        stop_cases = self.stop_cases
        if self.stop_percent:
            stop_cases = int(self.stop_percent / 100.0 * num_transitions + .999)  # Round upwards
        stop_time = self.stop_time
        if stop_time:
            stop_time += time.time()
        self.log.debug("stop_cases = {0}, stop_time = {1}".format(stop_cases, stop_time))
        index = 0
        error_msg = None
        for (from_state, to_state) in transitions:
            if (stop_time and time.time() > stop_time) or (stop_cases and index >= stop_cases):
                self.progress_msg("Requested stop-after limit reached\n")
                break

            index += 1
            if not remaining_transitions.has_key(from_state):
                ## Could not find any transitions from the current (perhaps undefined) state
                ## So let's pick a from_state at random and go to that first
                start_attempts_remaining = 10
                while start_attempts_remaining:
                    from_state = random.choice(remaining_transitions.keys())
                    from_name = self.state_filename_to_name(states[from_state], self.dev_name)
                    self.progress_msg("\nStarting from known state {0}\n".format(from_name))
                    result = self.transition_to_state(states[from_state])
                    if True != result:
                        self.progress_msg("... failed setting known state\n")
                        start_attempts_remaining -= 1
                    else:
                        break
                if True != result:
                    error_msg = "Failed to regain a known state despite multiple attempts"
                    break

            ## Pick a remaining to_state at random
            (to_state, dummy_val) = remaining_transitions[from_state].popitem()                 
            if 0 == len(remaining_transitions[from_state]):
                del remaining_transitions[from_state]
            
            from_name = self.state_filename_to_name(states[from_state], self.dev_name)
            to_name = self.state_filename_to_name(states[to_state], self.dev_name)
            self.progress_msg("Transition {0}/{1}: {2} ==> {3}\n".format(index, num_transitions, from_name, to_name))
            result = self.transition_to_state(states[to_state])
            if True != result:
                failed_transitions += [(from_name, to_name, result)]
                self.progress_msg("   {0}\n".format(result))
                from_state = None ## Now in undefined state
            else:
                from_state = to_state
        if not failed_transitions and not error_msg:
            return {'success':"Completed successfully"}
        result = {'failure':"\n".join(["{0}: {1} ==> {2}".format(c,f,t) for (f,t,c) in failed_transitions])}
        if error_msg:
            result['error'] = error_msg
        return result


class TransitionToStateOp(ConfigOp):
    def _init_params(self, params):
        self.state_name = self.param_default(params, "state_name", "")
        self.rollback = params.rollback

    def perform(self):
        msg = "config_transition_to_state() with device {0} to state {1}" \
              .format(self.dev_name, self.state_name)
        self.log.debug(msg)
        to_filename = self.state_name_to_filename(self.state_name, self.dev_name)
        result = self.transition_to_state(to_filename, self.rollback)
        if result is True:
            return {'success': "Done"}
        else:
            return {'failure': result}

