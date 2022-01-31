# -*- mode: python; python-indent: 4 -*-

import os
import time
import random
import re
import itertools
from contextlib import closing

import _ncs
from ncs import maagic

from . import base_op
from . import filtering


if _ncs.LIB_VSN < 0x07060000:
    def keyless_create(node, i):
        return node.create(i)
else:
    def keyless_create(node, _i):
        return node.create()


class TransitionsOp(base_op.ActionBase):
    def perform(self):
        '''Performs the transition action and process DrNED output.

        The DrNED output is filtered and sent to right destinations
        (CLI and/or a log file); also, `event_context` is populated
        with transition events that are stored in operational CDB.

        '''
        detail = self.run_with_trans(self.get_log_detail)
        self.filter_cr = None
        self.event_context = filtering.TransitionEventContext()
        with closing(self.event_context):
            with closing(self.build_filter(detail, self.cli_write)) as self.filter_cr:
                result = self.perform_transitions()
        self.run_with_trans(self.store_transition_events, write=True, db=_ncs.OPERATIONAL)
        return result

    def get_log_detail(self, trans):
        root = maagic.get_root(trans)
        return root.drned_xmnr.log_detail.cli

    def cli_filter(self, msg):
        if self.filter_cr is not None:
            self.filter_cr.send(msg)

    def build_filter(self, level, writer):
        '''Builds a pipe to process DrNED output lines.

        Lines from the DrNED output need all to be processed by the
        filtering event processor.  The event processor does two tasks:

        * reformat and filter the output according to the logging
          level (distinguishes "overview" and "drned-overview");

        * populate the `event_context` instance with test/transition
          events.

        '''
        if level in ('none', 'all'):
            sink = filtering.drop()
        else:
            sink = filtering.filter_sink(writer)
        events = filtering.EventGenerator(self.event_processor(level, sink))
        if level == 'all':
            return filtering.fork(events, filtering.filter_sink(writer))
        return events

    def drned_run(self, drned_args):
        args = ["-s", "--tb=short", "--device=" + self.dev_name] + drned_args
        if not self.using_builtin_drned:
            args.append("--unreserved")
        args.insert(0, self.pytest_executable())
        self.log.debug("drned: {0}".format(args))
        return self.run_in_drned_env(args)

    def transition_to_state(self, state_name, rollback=False):
        filename = self.state_name_to_filename(state_name)
        self.log.debug("Transition_to_state: {0}\n".format(state_name))
        filepath = os.path.relpath(filename, self.drned_run_directory)
        self.log.debug("Using file {0}\n".format(filepath))
        test = "test_template_single" if rollback else "test_template_raw"
        args = ["-k {0}[{1}]".format(test, os.path.basename(filepath))]
        result, _ = self.drned_run(args)
        self.log.debug("Test case completed\n")
        if result != 0:
            return "drned failed"
        return True

    failure_types = {'compare_config': 'compare',
                     'commit': 'commit',
                     'load': 'load',
                     'rollback': 'rollback'}

    def store_transition_events(self, trans):
        '''Cleanup and populate the `last_test_results` container.

        '''
        root = maagic.get_root(trans)
        results = root.drned_xmnr.last_test_results.create()
        results.device = self.dev_name
        results.transition.delete()
        for i, event in enumerate(self.event_context.test_events):
            tsinst = keyless_create(results.transition, i)
            tsinst['from'] = event.start
            tsinst.to = event.to
            if event.failure is not None:
                failure = tsinst.failure.create()
                failure.type = self.failure_types.get(event.failure, '')
                comment = event.comment
                msg = event.failure_message
                failure.comment = comment
                if msg != comment:
                    # not useful to have it twice
                    failure.message = msg
        trans.apply()


class TransitionToStateOp(TransitionsOp):
    action_name = 'transition to state'

    def _init_params(self, params):
        self.state_name = self.param_default(params, "state_name", "")
        self.rollback = params.rollback

    def event_processor(self, level, sink):
        return filtering.transition_output_filter(level, sink, self.event_context)

    def perform_transitions(self):
        msg = "config_transition_to_state() with device {0} to state {1}" \
              .format(self.dev_name, self.state_name)
        self.log.debug(msg)
        result = self.transition_to_state(self.state_name, self.rollback)
        if result is True:
            return {'success': "Done"}
        else:
            return {'failure': result}


class StatesTransitionsOp(TransitionsOp):
    """Simple extension for transition operation involving multiple
    states.  Adds support for retrieving the `transition-states`
    grouping.
    """

    def filter_states(self, states):
        return states

    def get_transition_filenames(self, params):
        states = list(params.states)
        if states == []:
            states = [state for state in self.get_states()
                      if state not in params.ignore_states
                      and not self.is_state_disabled(state)]
            states = self.filter_states(states)
            random.shuffle(states)
        else:
            states = self.filter_states(params.states)
        self.state_filenames = [self.state_name_to_filename(state)
                                for state in states]


class ExploreTransitionsOp(StatesTransitionsOp):
    action_name = 'explore transitions'

    def event_processor(self, level, sink):
        return filtering.explore_output_filter(level, sink, self.event_context)

    def _init_params(self, params):
        self.get_transition_filenames(params)
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
        msg = "Found {0} states recorded for device {1} which gives a total of {2} transitions."
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
                self.progress_msg("Requested stop-after limit reached")
                break

            from_name = self.state_filename_to_name(from_state)
            to_name = self.state_filename_to_name(to_state)
            if prev_state != from_state:
                self.progress_msg("Starting with state {0}".format(from_name))
                result = self.transition_to_state(from_name)
                if result is not True:
                    msg = "Failed to initialize state {0}".format(from_name)
                    self.progress_msg(msg)
                    self.log.warning(msg)
                    error_msgs.append(msg)
                    failed_state = from_state
                    continue
                prev_state = from_state
            self.progress_msg("Transition {0}/{1}: {2} ==> {3}"
                              .format(index + 1, num_transitions, from_name, to_name))
            result = self.transition_to_state(to_name, rollback=True)
            if result is not True:
                failed_transitions.append((from_name, to_name, result))
                self.progress_msg("Transition failed")
        if failed_transitions == [] and error_msgs == []:
            return {'success': "Completed successfully"}
        result = {'failure':
                  "\n".join(["{0}: {1} ==> {2}".format(c, f, t)
                             for (f, t, c) in failed_transitions])}
        if error_msgs != []:
            result['error'] = '\n'.join(error_msgs)
        return result


class WalkTransitionsOp(StatesTransitionsOp):
    action_name = 'walk states'

    def _init_params(self, params):
        self.get_transition_filenames(params)
        self.rollback = params.rollback

    def filter_states(self, states):
        return list(self.filter_state_sets(states))

    def filter_state_sets(self, states):
        """Filter out duplicate representatives of "state sets".

        For all states of the form state_name:N make sure that only
        one such state is present.

        """
        sets = set()
        sfx = re.compile(r'(.*):\d+$')
        for state in states:
            mm = sfx.match(state)
            if mm is None:
                yield state
            else:
                base = mm.groups()[0]
                if base not in sets:
                    sets.add(base)
                    yield state

    def perform_transitions(self):
        self.log.debug("walking states {0}"
                       .format([self.state_filename_to_name(filename)
                                for filename in self.state_filenames]))
        # the default for end_op is "rollback", "commit", "compare_config"
        # if rollback is not desired, we need to set it to an empty list
        fname_args = ["--fname=" + filename for filename in self.state_filenames]
        end_op = [] if self.rollback else ["--end-op", ""]
        result, _ = self.drned_run(
            fname_args + end_op + ["--ordered=false", "-k", "test_template_set"])
        self.log.debug("DrNED completed: {0}".format(result))
        ops = [tr.to for tr in self.event_context.test_events if tr.failure is not None]
        if result != 0 or ops:
            return {'failure': "failed to transition to states: " + ", ".join(ops)}
        return {'success': "Completed successfully"}

    def event_processor(self, level, sink):
        return filtering.walk_output_filter(level, sink, self.event_context)
