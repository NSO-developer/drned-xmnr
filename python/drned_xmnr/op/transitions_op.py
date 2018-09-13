# -*- mode: python; python-indent: 4 -*-

import os
import time
import random
import itertools

from ncs import maagic

from . import base_op
from . import filtering
from .ex import ActionError


class TransitionsOp(base_op.ActionBase):
    def perform(self):
        detail, redirect = self.run_with_trans(self.get_log_detail)
        self.filter_cr = None
        if redirect is not None:
            with self.open_log_file(redirect) as rfile:
                self.filter_cr = self.build_filter(detail, rfile.write)
                result = self.perform_transitions()
                self.filter_cr.close()
        elif self.uinfo.context == 'cli':
            self.filter_cr = self.build_filter(detail, self.cli_write)
            result = self.perform_transitions()
            self.filter_cr.close()
        else:
            result = self.perform_transitions()
        return result

    def get_log_detail(self, trans):
        root = maagic.get_root(trans)
        detail = root.drned_xmnr.log_detail
        self.log.debug('CLI detail: ', detail.cli, detail.redirect)
        return detail.cli, detail.redirect

    def cli_filter(self, msg):
        if self.filter_cr is not None:
            self.filter_cr.send(msg)

    def build_filter(self, level, writer):
        if level == 'none':
            return filtering.drop()
        if level == 'all':
            return filtering.filter_sink(writer)
        return filtering.build_filter(self, level, writer)

    def drned_run(self, drned_args, timeout=120):
        args = ["-s", "--tb=short", "--device="+self.dev_name] + drned_args
        if not self.using_builtin_drned:
            args.append("--unreserved")
        args.insert(0, "py.test")
        self.log.debug("drned: {0}".format(args))
        return self.run_in_drned_env(args, timeout)

    def transition_to_state(self, filename, rollback=False):
        state_name = self.state_filename_to_name(filename)
        if not os.path.exists(filename):
            raise ActionError('No such state: {0}'.format(state_name))

        self.log.debug("Transition_to_state: {0}\n".format(state_name))
        # filename needs to use '~' instead of '-'
        # need to use relative path for DrNED to accept that
        filepath = os.path.relpath(self.state_name_to_filename(state_name.replace("-", "~")),
                                   self.drned_run_directory)

        self.log.debug("Using file {0}\n".format(filepath))
        # Max 120 seconds for executing DrNED
        self.extend_timeout(120)
        test = "test_template_single" if rollback else "test_template_raw"
        args = ["-k {0}[{1}]".format(test, filepath)]
        result, _ = self.drned_run(args)
        self.log.debug("Test case completed\n")
        if result != 0:
            return "drned failed"
        return True


class TransitionToStateOp(TransitionsOp):
    action_name = 'transition to state'

    def _init_params(self, params):
        self.state_name = self.param_default(params, "state_name", "")
        self.rollback = params.rollback

    def event_processor(self, level, sink):
        return filtering.transition_output_filter(level, sink)

    def perform_transitions(self):
        msg = "config_transition_to_state() with device {0} to state {1}" \
              .format(self.dev_name, self.state_name)
        self.log.debug(msg)
        to_filename = self.state_name_to_filename(self.state_name)
        result = self.transition_to_state(to_filename, self.rollback)
        if result is True:
            return {'success': "Done"}
        else:
            return {'failure': result}


class ExploringOp(TransitionsOp):
    def _init_params(self, params):
        state_files = self.get_state_files()
        pstates = list(params.states)
        if pstates == []:
            self.state_filenames = state_files
            random.shuffle(self.state_filenames)
        else:
            self.state_filenames = [self.state_name_to_filename(state)
                                    for state in pstates
                                    if self.state_name_to_filename(state) in state_files]


class ExploreTransitionsOp(ExploringOp):
    action_name = 'explore transitions'

    def event_processor(self, level, sink):
        return filtering.explore_output_filter(level, sink)

    def _init_params(self, params):
        super(ExploreTransitionsOp, self)._init_params(params)
        stp = params.stop_after
        self.stop_time = 24 * int(self.param_default(stp, "days", 0))
        self.stop_time = 60 * int(self.param_default(stp, "hours", self.stop_time))
        self.stop_time = 60 * int(self.param_default(stp, "minutes", self.stop_time))
        self.stop_time = int(self.param_default(stp, "seconds", self.stop_time))
        self.stop_percent = int(self.param_default(stp, "percent", 0))
        self.stop_cases = int(self.param_default(stp, "cases", 0))

    def perform_transitions(self):
        self.log.debug("config_explore_transitions() with device {0} states {1}"
                       .format(self.dev_name, self.state_filenames))
        states = self.state_filenames
        num_states = len(states)
        num_transitions = num_states * (num_states - 1)
        if(0 == num_transitions):
            return {'failure': "Could not process the request",
                    'error': "No transitions to make. Run 'config record-state' or "
                    "'config import-state-files' several times "
                    "before running this command."}
        msg = "Found {0} states recorded for device {1} which gives a total of {2} transitions.\n"
        self.progress_msg(msg.format(num_states, self.dev_name, num_transitions))

        failed_transitions = []
        transitions = list(itertools.permutations(states, 2))
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
                self.progress_msg("Starting with state {0}\n".format(from_name))
                result = self.transition_to_state(from_state)
                if result is not True:
                    msg = "Failed to initialize state {0}".format(from_name)
                    self.progress_msg(msg + '\n')
                    self.log.warning(msg)
                    error_msgs.append(msg)
                    failed_state = from_state
                    continue
                prev_state = from_state
            self.progress_msg("Transition {0}/{1}: {2} ==> {3}\n"
                              .format(index+1, num_transitions, from_name, to_name))
            result = self.transition_to_state(to_state, rollback=True)
            if result is not True:
                failed_transitions.append((from_name, to_name, result))
                self.progress_msg("Transition failed\n")
        if failed_transitions == [] and error_msgs == []:
            return {'success': "Completed successfully"}
        result = {'failure':
                  "\n".join(["{0}: {1} ==> {2}".format(c, f, t)
                             for (f, t, c) in failed_transitions])}
        if error_msgs != []:
            result['error'] = '\n'.join(error_msgs)
        return result


class WalkTransitionsOp(ExploringOp):
    action_name = 'walk states'

    def _init_params(self, params):
        super(WalkTransitionsOp, self)._init_params(params)
        self.rollback = params.rollback

    def perform_transitions(self):
        self.log.debug("walking states {0}"
                       .format([self.state_filename_to_name(filename)
                                for filename in self.state_filenames]))
        # the default for end_op is "rollback", "commit", "compare_config"
        # if rollback is not desired, we need to set it to an empty list
        fname_args = ["--fname=" + filename for filename in self.state_filenames]
        end_op = [] if self.rollback else ["--end-op", ""]
        result, _ = self.drned_run(fname_args + end_op + ["--unsorted", "-k", "test_template_set"])
        self.log.debug("DrNED completed: {0}".format(result))
        if result != 0:
            raise ActionError("drned failed")
        return {'success': "Completed successfully"}

    def event_processor(self, level, sink):
        return filtering.walk_output_filter(level, sink)
