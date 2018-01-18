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

import sys
import traceback

from ncs import dp, application
import drned_xmnr.namespaces.drned_xmnr_ns as ns

# operation modules
import op.config_op
import op.transitions_op
from op.ex import ActionError

assert sys.version_info >= (2, 7)
# Not tested with anything lower


def param_default(params, tag, default):
    matching_param_list = [p.v for p in params if p.tag == tag]
    if len(matching_param_list) == 0:
        return default
    return str(matching_param_list[0])


class ActionHandler(dp.Action):
    handlers = {
        ns.ns.drned_xmnr_delete_state_: op.config_op.DeleteStateOp,
        ns.ns.drned_xmnr_list_states_: op.config_op.ListStatesOp,
        ns.ns.drned_xmnr_record_state_: op.config_op.RecordStateOp,
        ns.ns.drned_xmnr_import_state_files_: op.config_op.ImportStateFiles,
        ns.ns.drned_xmnr_transition_to_state_: op.transitions_op.TransitionToStateOp,
        ns.ns.drned_xmnr_explore_transitions_: op.transitions_op.ExploreTransitionsOp,
    }

    @dp.Action.action
    def cb_action(self, uinfo, op_name, kp, params, output):
        self.log.debug("========== drned_xmnr cb_action() ==========")
        dev_name = str(kp[-3][0])
        self.log.debug("thandle={0} usid={1}".format(uinfo.actx_thandle, uinfo.usid))

        try:
            if op_name not in self.handlers:
                raise ActionError({'error': "Operation not implemented: {0}".format(op_name)})
            handler_cls = self.handlers[op_name]
            handler = handler_cls(uinfo, dev_name, params, self.log)
            result = handler.perform()
            return self.action_response(uinfo, result, output)

        except ActionError as ae:
            self.log.debug("ActionError exception")
            return self.action_response(uinfo, ae.get_info(), output)

        except:
            self.log.debug("Other exception: " + repr(traceback.format_exception(*sys.exc_info())))
            output.error = "Operation failed"

    def action_response(self, uinfo, result, output):
        if 'message' in result:
            output.message = result['message']
        if 'error' in result:
            output.error = result['error']
        if 'success' in result:
            output.success = result['success']
        if 'failure' in result:
            output.failure = result['failure']
        if 'filename' in result:
            output.filename = result['filename']


# ---------------------------------------------
# COMPONENT THREAD THAT WILL BE STARTED BY NCS.
# ---------------------------------------------

class Action(application.Application):

    def setup(self):
        self.register_action('drned-xmnr', ActionHandler)

    def finish(self):
        pass
