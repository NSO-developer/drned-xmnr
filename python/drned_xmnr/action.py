# -*- mode: python; python-indent: 4 -*-
"""
*********************************************************************
* (C) 2016 Tail-f Systems                                           *
* NETCONF/YANG drned_xmnr                                           *
*                                                                   *
* Your Swiss army knife when it somes to basic NETCONF,             *
* YANG module collection, NSO NETCONF NED building, installation    *
* and testing.                                                      *
*********************************************************************
"""

from __future__ import print_function

import glob
import sys
import traceback

import _ncs
from ncs import dp, application, experimental
import drned_xmnr.namespaces.drned_xmnr_ns as ns

# operation modules
from drned_xmnr.op import config_op
from drned_xmnr.op import transitions_op
from drned_xmnr.op import setup_op
from drned_xmnr.op import coverage_op
from drned_xmnr.op.ex import ActionError

assert sys.version_info >= (2, 7)
# Not tested with anything lower


def param_default(params, tag, default):
    matching_param_list = [p.v for p in params if p.tag == tag]
    if len(matching_param_list) == 0:
        return default
    return str(matching_param_list[0])


class ActionHandler(dp.Action):
    handlers = {
        ns.ns.drned_xmnr_setup_xmnr_: setup_op.SetupOp,
        ns.ns.drned_xmnr_delete_state_: config_op.DeleteStateOp,
        ns.ns.drned_xmnr_list_states_: config_op.ListStatesOp,
        ns.ns.drned_xmnr_view_state_: config_op.ViewStateOp,
        ns.ns.drned_xmnr_record_state_: config_op.RecordStateOp,
        ns.ns.drned_xmnr_import_state_files_: config_op.ImportStateFiles,
        ns.ns.drned_xmnr_check_states_: config_op.CheckStates,
        ns.ns.drned_xmnr_transition_to_state_: transitions_op.TransitionToStateOp,
        ns.ns.drned_xmnr_explore_transitions_: transitions_op.ExploreTransitionsOp,
        ns.ns.drned_xmnr_walk_states_: transitions_op.WalkTransitionsOp,
        ns.ns.drned_xmnr_reset_: coverage_op.ResetCoverageOp,
        ns.ns.drned_xmnr_collect_: coverage_op.CoverageOp,
    }

    @dp.Action.action
    def cb_action(self, uinfo, op_name, kp, params, output):
        self.log.debug("========== drned_xmnr cb_action() ==========")
        dev_name = str(kp[-3][0])
        self.log.debug("thandle={0} usid={1}".format(uinfo.actx_thandle, uinfo.usid))

        try:
            if op_name not in self.handlers:
                raise ActionError({'failure': "Operation not implemented: {0}".format(op_name)})
            handler_cls = self.handlers[op_name]
            handler = handler_cls(uinfo, dev_name, params, self.log)
            result = handler.perform_action()
            return self.action_response(uinfo, result, output)

        except ActionError as ae:
            self.log.debug("ActionError exception")
            return self.action_response(uinfo, ae.get_info(), output)

        except Exception:
            self.log.debug("Other exception: " + repr(traceback.format_exception(*sys.exc_info())))
            output.failure = "Operation failed"

    def action_response(self, uinfo, result, output):
        if 'error' in result:
            output.error = result['error']
        if 'success' in result:
            output.success = result['success']
        if 'failure' in result:
            output.failure = result['failure']


class CompletionHandler(dp.Action):

    # @dp.Action.completion
    # wrapper does not exist in PyAPI at the time of this implementation
    def cb_completion(self, uinfo, cli_style, token, completion_char,
                      kp, cmdpath, cmdparam_id, simpleType, extra):
        self.log.debug("========== drned_xmnr cb_completion() ==========")
        self.log.debug("thandle={0} usid={1}".format(uinfo.actx_thandle,
                                                     uinfo.usid))
        try:
            # TODO - escape/sanitize input "token"
            pattern_to_match = str(token)
            if '*' not in pattern_to_match:
                pattern_to_match += '*'
            matched_paths = glob.glob(pattern_to_match)
            tv = [(dp.COMPLETION, str(path), None) for path in matched_paths]
            if tv:
                _ncs.dp.action_reply_completion(uinfo, tv)
            return _ncs.CONFD_OK

        except Exception as e:
            self.log.error(e)
            self.log.error(traceback.format_exc())
            raise
        finally:
            # cleanup from @.action wrapper
            dp.return_worker_socket(self._state, self._make_key(uinfo))


class XmnrDataHandler(object):
    def __init__(self, daemon, actionpoint, log=None, init_args=None):
        # FIXME: really experimental
        self._state = dp._daemon_as_dict(daemon)
        ctx = self._state['ctx']
        self.log = log or self._state['log']
        dcb = experimental.DataCallbacks(self.log)
        dcb.register('/ncs:devices/ncs:device', coverage_op.DataHandler(self.log))
        _ncs.dp.register_data_cb(ctx, ns.ns.callpoint_coverage_data, dcb)
        scb = experimental.DataCallbacks(self.log)
        scb.register('/ncs:devices/ncs:device/drned-xmnr:drned-xmnr/drned-xmnr:state',
                     config_op.StatesProvider(self.log))
        _ncs.dp.register_data_cb(ctx, ns.ns.callpoint_xmnr_states, scb)

    def start(self):
        self.log.debug('started XMNR data')


# ---------------------------------------------
# COMPONENT THREAD THAT WILL BE STARTED BY NCS.
# ---------------------------------------------

class Xmnr(application.Application):

    def setup(self):
        self.register_action(ns.ns.actionpoint_drned_xmnr, ActionHandler)
        self.register_action('drned-xmnr-completion', CompletionHandler)
        self.register_service(ns.ns.callpoint_coverage_data, XmnrDataHandler)
        self.register_service(ns.ns.callpoint_xmnr_states, XmnrDataHandler)

    def finish(self):
        pass
