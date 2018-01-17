# -*- mode: python; python-indent: 4 -*-

import os
import random
import socket
import subprocess
import time
import itertools
import glob
import shutil

import _ncs
from ncs import maapi, maagic

import base_op
from ex import ActionError


state_metadata = """\
# automatically generated
# all XMNR state files need to be loaded in 'override' mode
mode = override
"""


class ConfigOp(base_op.BaseOp):
    statefile_extension = '.state.cfg'

    def state_name_to_filename(self, statename):
        return os.path.join(self.states_dir, statename + self.statefile_extension)

    def state_filename_to_name(self, filename):
        return os.path.basename(filename)[:-len(self.statefile_extension)]

    def get_states(self):
        return [self.state_filename_to_name(f) for f in self.get_state_files()]

    def get_state_files(self):
        return glob.glob(self.state_name_to_filename('*'))

    def write_metadata(self, state_filename):
        with open(state_filename + ".load", 'w') as meta:
            print >> meta, state_metadata

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

    def transition_to_state(self, filename, rollback=False):
        if not os.path.exists(filename):
            state_name = self.state_filename_to_name(filename)
            raise ActionError('No such state: {0}'.format(state_name))

        # need to use relative path for DrNED to accept that
        filename = os.path.relpath(filename, self.drned_run_directory)
        self.log.debug("Transition_to_state: {0}\n".format(filename))

        # Max 120 seconds for executing DrNED
        self.extend_timeout(120)
        test = "test_template_single" if rollback else "test_template_raw"
        args = ["-k {0}[{1}]".format(test, filename)]
        result = self.drned_run(args, timeout=120)
        self.log.debug("Test case completed\n")
        if result != 0:
            return "drned failed"
        return True


class DeleteStateOp(ConfigOp):
    def _init_params(self, params):
        self.state_name = self.param_default(params, "state_name", "")

    def perform(self):
        self.log.debug("config_delete_state() with device {0}".format(self.dev_name))
        state_filename = self.state_name_to_filename(self.state_name)
        try:
            os.remove(state_filename)
        except:
            return {'error': "Could not delete " + state_filename}
        return {'success': "Deleted " + self.state_name}


class ListStatesOp(ConfigOp):
    def _init_params(self, params):
        pass

    def perform(self):
        self.log.debug("config_list_states() with device {0}".format(self.dev_name))
        state_files = self.get_state_files()
        return {'success': "Saved device states: " +
                str(map(self.state_filename_to_name, state_files))}


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
            state_filename = self.state_name_to_filename(state_name_index)
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
                self.write_metadata(state_filename)
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
        self.stop_time = int(self.param_default(stp, "seconds", self.stop_time))
        self.stop_percent = int(self.param_default(stp, "percent", 0))
        self.stop_cases = int(self.param_default(stp, "cases", 0))
        self.states = list(params.states)

    def perform(self):
        self.log.debug("config_explore_transitions() with device {0} states {1}"
                       .format(self.dev_name, self.states))
        state_files = self.get_state_files()
        if self.states == []:
            states = state_files
        else:
            states = [self.state_name_to_filename(state)
                      for state in self.states
                      if self.state_name_to_filename(state) in state_files]
        num_states = len(states)
        num_transitions = num_states * (num_states - 1)
        if(0 == num_transitions):
            return {'error': "No transitions to make. Run 'config record-state' or "
                    "'config import-state-files' several times "
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
        if stop_cases > 0:
            transitions = transitions[:stop_cases]
        stop_time = self.stop_time
        if stop_time:
            stop_time += time.time()
        self.log.debug("stop_cases = {0}, stop_time = {1}".format(stop_cases, stop_time))
        error_msgs = []
        prev_state = None
        failed_state = None
        for index, (from_state, to_state) in enumerate(transitions):
            if from_state == failed_state:
                continue
            if (stop_time and time.time() > stop_time):
                self.progress_msg("Requested stop-after limit reached\n")
                break

            from_name = self.state_filename_to_name(from_state)
            to_name = self.state_filename_to_name(to_state)
            if prev_state != from_state:
                self.progress_msg("Starting with state " + from_name)
                result = self.transition_to_state(from_state)
                if result is not True:
                    msg = "Failed to initialize state {0}: {1}"\
                          .format(from_name, result)
                    self.log.warning(msg)
                    error_msgs.append(msg)
                    failed_state = from_state
                    continue
                prev_state = from_state
            self.progress_msg("Transition {0}/{1}: {2} ==> {3}\n"
                              .format(index, num_transitions, from_name, to_name))
            result = self.transition_to_state(to_state, rollback=True)
            if result is not True:
                failed_transitions.append((from_name, to_name, result))
                self.progress_msg("   {0}\n".format(result))
        if failed_transitions == [] and error_msgs == []:
            return {'success': "Completed successfully"}
        result = {'failure':
                  "\n".join(["{0}: {1} ==> {2}".format(c, f, t)
                             for (f, t, c) in failed_transitions])}
        if error_msgs != []:
            result['error'] = '\n'.join(error_msgs)
        return result


class TransitionToStateOp(ConfigOp):
    def _init_params(self, params):
        self.state_name = self.param_default(params, "state_name", "")
        self.rollback = params.rollback

    def perform(self):
        msg = "config_transition_to_state() with device {0} to state {1}" \
              .format(self.dev_name, self.state_name)
        self.log.debug(msg)
        to_filename = self.state_name_to_filename(self.state_name)
        result = self.transition_to_state(to_filename, self.rollback)
        if result is True:
            return {'success': "Done"}
        else:
            return {'failure': result}


class ImportStateFiles(ConfigOp):
    def _init_params(self, params):
        self.pattern = params.file_path_pattern
        self.overwrite = params.overwrite

    def perform(self):
        filenames = glob.glob(self.pattern)
        if filenames == []:
            raise ActionError("no files found: " + self.pattern)
        states = [self.get_state_name(os.path.basename(filename))
                  for filename in filenames]
        if not self.overwrite:
            conflicts = [state for state in states
                         if os.path.exists(self.state_name_to_filename(state))]
            if conflicts != []:
                raise ActionError("States already exists: " + ", ".join(conflicts))
        for (source, target) in zip(filenames, states):
            self.import_file(source, target)
        return {"success": "Imported states: " + ", ".join(states)}

    def import_file(self, source_file, state):
        dirname = os.path.dirname(source_file)
        if dirname == self.states_dir:
            tmpfile = source_file
        else:
            tmpfile = os.path.join(self.states_dir, ".new_state_file")
            shutil.copyfile(source_file, tmpfile)
        os.rename(tmpfile, self.state_name_to_filename(state))
        self.write_metadata(self.state_name_to_filename(state))

    def get_state_name(self, origname):
        (base, ext) = os.path.splitext(origname)
        while ext != "":
            (base, ext) = os.path.splitext(base)
        return base
