# -*- mode: python; python-indent: 4 -*-

import fnmatch
import os
import random
import socket
import subprocess
import sys
import time
import traceback
import inspect

import _ncs
import _ncs.maapi as maapi

import base_op
import drned_xmnr.namespaces.drned_xmnr_ns as ns
from ex import ActionError


# py.test -s --tb=short -k test_template_set --device=ce0 --init=simple_tests/init_state.cfg --fname=simple_tests/skoda0_state.cfg --unreserved
# py.test -s --tb=short -k 'test_coverage' --device ce0 --yangpath=src/yang/ --fname=src/yang/Cisco-IOS-XE-native.yang --fname=src/yang/Cisco-IOS-XE-bgp.yang 


class ConfigOp(base_op.BaseOp):
    statefile_extension = '.state.cfg'
    def state_name_to_filename(self, statename, devname):
        #return devname + '--' + statename + '.state.cfg'
        return statename + self.statefile_extension

    def state_filename_to_name(self, filename, devname):
        return filename[:-len(self.statefile_extension)]

    def transition_to_state(self, to_state_filename):
        filename = os.path.join(self.states_dir, to_state_filename)
        if not os.path.exists(filename):
            state_name = self.state_filename_to_name(to_state_filename, self.dev_name)
            raise ActionError({'error': 'No such state: {0}'.format(state_name)})

        try:
            self.debug("Transition_to_state: #{0}\n".format(filename))
            self.debug("sys.path: #{0}\n".format(sys.path))
            self.debug("os.environ: #{0}\n".format(os.environ))
            self.debug("I live at: {0}\n".format(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))

            def progress_fun(state, stdout):
                self.progress_msg(stdout)
                self.extend_timeout(120)
                return None

            self.extend_timeout(120) # Max 120 seconds for executing the transaction and a compare-config
            #self.state_file = ""
            command = [
                "py.test", "-s", "--tb=short", "-k", "test_template_set",
                "--device="+self.dev_name, 
                "--fname=" +filename, 
                "--unreserved"]
            result = self.proc_run(command, timeout=120, outputfun=progress_fun)
            #self.debug("Test case result\n"+str(result))
            self.debug("Test case completed\n")
            thandle = maapi.start_trans2(self.msocket, _ncs.RUNNING, _ncs.READ_WRITE, self.uinfo.usid)
            result = maapi.request_action(self.msocket, [], 0, "/ncs:devices/device{" + self.dev_name + "}/compare-config")
            if [] == result:
                self.debug("In sync\n")
                return True
            else:
                return "out-of-sync"
        except:
            self.debug("Exception: " + repr(traceback.format_exception(*sys.exc_info())))
            return "transaction-failed"
        finally:
            maapi.finish_trans(self.msocket, thandle)
            pass

class DeleteStateOp(ConfigOp):
    def _init_params(self, params):
        self.state_name = self.param_default(params, ns.ns.drned_xmnr_state_name, "")

    def perform(self):
        self.debug("config_delete_state() with device {0}".format(self.dev_name))
        state_filename = self.states_dir + "/" + self.state_name_to_filename(self.state_name, self.dev_name)
        try:
            os.remove(state_filename)
        except:
            return {'error':"Could not delete " + state_filename}
        return {'success':"Deleted " + self.state_name}
        
class ImportIntoFileOp(ConfigOp):
    def _init_params(self, params):
        self.file_name = str(params[0].v)

    def perform(self):
        self.debug("config_import_into_file() with device {0}".format(self.dev_name))
        tempfile_stem = "/tmp/" + os.path.basename(self.file_name)
        tempfile_l_name = tempfile_stem + ".ncsload.xml"
        log_name = tempfile_stem + ".log"

        log = self.proc_run_xsltproc('ncs-import-from-top.xsl', self.file_name, tempfile_l_name, log_name)

        #self.attach_load_file(self.file_name)
        self.debug("config-snippet import done")
        return {'filename':tempfile_l_name}

    def attach_load_file(self, file_name):
        self.debug("31")
        maapi.attach2(self.msocket, 0, self.uinfo.usid, self.uinfo.actx_thandle)
        self.debug("32 "+str(maapi.CONFIG_XML)+" "+str(self.uinfo.actx_thandle))
        maapi.load_config(self.msocket, self.uinfo.actx_thandle, maapi.CONFIG_XML+maapi.CONFIG_XML_LOAD_LAX, file_name)
        self.debug("33")

class ListStatesOp(ConfigOp):
    def _init_params(self, params):
        pass

    def perform(self):
        self.debug("config_list_states() with device {0}".format(self.dev_name))
        state_files = [self.state_filename_to_name(f, self.dev_name) for f in os.listdir(self.states_dir) if fnmatch.fnmatch(f, self.state_name_to_filename('*', self.dev_name))]
        return {'success':"Saved device states: " + str(state_files)}

class RecordStateOp(ConfigOp):
    def _init_params(self, params):
        self.state_name = self.param_default(params, ns.ns.drned_xmnr_state_name, "")
        self.include_rollbacks = self.param_default(params, ns.ns.drned_xmnr_including_rollbacks, 0)

    def perform(self):
        self.debug("config_record_state() with device {0}".format(self.dev_name))
        state_name = self.state_name
        self.debug("incl_rollbacks="+str(self.include_rollbacks))
        try:
            ## list_rollbacks() returns one less rollback than the second argument,
            ## i.e. send 2 to get 1 rollback. Therefore the +1
            rollbacks = maapi.list_rollbacks(self.msocket, int(self.include_rollbacks)+1)
            ## rollbacks are returned 'most recent first', i.e. reverse chronological order
        except:
            rollbacks = []
        self.debug("rollbacks="+str([r.fixed_nr for r in rollbacks]))
        maapi.attach2(self.msocket, 0, 0, self.uinfo.actx_thandle)
        index = 0
        state_filenames = []
        for rb in [None] + rollbacks:
            if None == rb:
                self.debug("Recording current transaction state")
            else:
                self.debug("Recording rollback"+str(rb.fixed_nr))
                self.debug("Recording rollback"+str(rb.nr))
                maapi.load_rollback(self.msocket, self.uinfo.actx_thandle, 3)#rb.nr)

            save_id = maapi.save_config(self.msocket, self.uinfo.actx_thandle, maapi.CONFIG_C,
                                        "/ncs:devices/device{"+self.dev_name+"}/config")

            state_name_index = state_name
            if index > 0:
                state_name_index = state_name+"-"+str(index)
            state_filename = self.states_dir + "/" + self.state_name_to_filename(state_name_index, self.dev_name)
            with file(state_filename, "w") as state_file:
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
                        self.debug("Data: "+str(config_data))
                finally:
                    ssocket.close()
            state_filenames += [state_name_index]
                
            ##maapi.save_config_result(sock, id) -> None
                            
            index += 1
            maapi.revert(self.msocket, self.uinfo.actx_thandle)
        return {'success':"Recorded states " + str(state_filenames)}

class ExploreTransitionsOp(ConfigOp):
    def _init_params(self, params):
        self.stop_time = 24 * int(self.param_default(params, ns.ns.drned_xmnr_days, 0))
        self.stop_time = 60 * int(self.param_default(params, ns.ns.drned_xmnr_hours, self.stop_time))
        self.stop_time = 60 * int(self.param_default(params, ns.ns.drned_xmnr_minutes, self.stop_time))
        self.stop_time =      int(self.param_default(params, ns.ns.drned_xmnr_seconds, self.stop_time))
        self.stop_percent =   int(self.param_default(params, ns.ns.drned_xmnr_percent, 0))
        self.stop_cases =     int(self.param_default(params, ns.ns.drned_xmnr_cases, 0))

    def perform(self):
        self.debug("config_explore_transitions() with device {0}".format(self.dev_name))
        state_files = [f for f in os.listdir(self.states_dir) if fnmatch.fnmatch(f, self.state_name_to_filename('*', self.dev_name))]
        num_states = len(state_files)
        num_transitions = num_states * (num_states - 1)
        if(0 == num_transitions):
            return {'error':"No transitions to make. Run 'config record-state' several times, "
                    "with some device configuration changes in between each recorded state before running this command."}
        self.progress_msg("Found {0} states recorded for device {1} which gives a total of {2} transitions.\n".
                          format(num_states, self.dev_name, num_transitions))

        failed_transitions = []
        remaining_transitions = {}
        stop_cases = self.stop_cases
        if self.stop_percent:
            stop_cases = int(self.stop_percent / 100.0 * num_transitions + .999) ## Round upwards
        stop_time = self.stop_time
        if stop_time:
            stop_time += time.time()
        self.debug("stop_cases = {0}, stop_time = {1}".format(stop_cases, stop_time))
        index = 0
        for from_state in xrange(0, num_states):
            remaining_transitions[from_state] = {}
            for to_state in xrange(0, num_states):
                if to_state == from_state:
                    continue ## Can't transition to same state
                remaining_transitions[from_state][to_state] = 1
        from_state = None ## Start in undefined state
        error_msg = None
        while remaining_transitions:
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
                    from_name = self.state_filename_to_name(state_files[from_state], self.dev_name)
                    self.progress_msg("\nStarting from known state {0}\n".format(from_name))
                    result = self.transition_to_state(state_files[from_state])
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
            
            from_name = self.state_filename_to_name(state_files[from_state], self.dev_name)
            to_name = self.state_filename_to_name(state_files[to_state], self.dev_name)
            self.progress_msg("Transition {0}/{1}: {2} ==> {3}\n".format(index, num_transitions, from_name, to_name))
            result = self.transition_to_state(state_files[to_state])
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
        self.state_name = self.param_default(params, ns.ns.drned_xmnr_state_name, "")

    def perform(self):
        self.debug("config_transition_to_state() with device {0} to state {1}".format(self.dev_name, self.state_name))
        to_filename = self.state_name_to_filename(self.state_name, self.dev_name)
        result = self.transition_to_state(to_filename)
        if True == result:
            return {'success':"Done"}
        else:
            return {'failure':result}

