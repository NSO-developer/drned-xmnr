import os
import glob
import sys
import traceback

import _ncs
from ncs import dp, application, experimental
import drned_xmnr.namespaces.drned_xmnr_ns as ns
from drned_xmnr import check_action  # noqa

# operation modules
from drned_xmnr.op import config_op
from drned_xmnr.op import transitions_op
from drned_xmnr.op import setup_op
from drned_xmnr.op import coverage_op
from drned_xmnr.op import common_op
from drned_xmnr.op.ex import ActionError

from typing import Dict, List, Optional, Tuple, Type
from drned_xmnr.typing_xmnr import OptArgs, ActionResult
from drned_xmnr.op.base_op import ActionBase
from ncs.log import Log
from ncs.maagic import Node

assert sys.version_info >= (3, 6)
# Not tested with anything lower


class ActionHandler(dp.Action):
    handlers: Dict[str, Type[ActionBase]] = {
        ns.ns.drned_xmnr_setup_xmnr_: setup_op.SetupOp,
        ns.ns.drned_xmnr_delete_state_: config_op.DeleteStateOp,
        ns.ns.drned_xmnr_disable_state_: config_op.DisableStateOp,
        ns.ns.drned_xmnr_enable_state_: config_op.EnableStateOp,
        ns.ns.drned_xmnr_list_states_: config_op.ListStatesOp,
        ns.ns.drned_xmnr_view_state_: config_op.ViewStateOp,
        ns.ns.drned_xmnr_record_state_: config_op.RecordStateOp,
        ns.ns.drned_xmnr_import_state_files_: config_op.ImportStateFiles,
        ns.ns.drned_xmnr_import_convert_cli_files_: config_op.ImportConvertCliFiles,
        ns.ns.drned_xmnr_check_states_: config_op.CheckStates,
        ns.ns.drned_xmnr_transition_to_state_: transitions_op.TransitionToStateOp,
        ns.ns.drned_xmnr_explore_transitions_: transitions_op.ExploreTransitionsOp,
        ns.ns.drned_xmnr_walk_states_: transitions_op.WalkTransitionsOp,
        ns.ns.drned_xmnr_reset_: coverage_op.ResetCoverageOp,
        ns.ns.drned_xmnr_collect_: coverage_op.CoverageOp,
        ns.ns.drned_xmnr_load_default_config_: common_op.LoadDefaultConfigOp,
        ns.ns.drned_xmnr_save_default_config_: common_op.SaveDefaultConfigOp,
        ns.ns.drned_xmnr_parse_log_errors_: common_op.ParseLogErrorsOp,
        ns.ns.drned_xmnr_compare_yang_sets_: common_op.CompareYangSetsOp,
    }

    def init(self) -> None:
        self.running_handler: Optional[ActionBase] = None

    @dp.Action.action
    def cb_action(self, uinfo: _ncs.UserInfo, op_name: str, kp: _ncs.HKeypathRef, input: Node, output: Node) -> None:
        self.log.debug("========== drned_xmnr cb_action() ==========")
        dev_name = str(kp[-3][0])
        self.log.debug("thandle={0} usid={1}".format(uinfo.actx_thandle, uinfo.usid))

        handler_error: ActionResult = {'failure': "Operation not implemented: {0}".format(op_name)}
        try:
            if op_name not in self.handlers:
                raise ActionError(handler_error)
            handler_cls = self.handlers[op_name]
            self.running_handler = handler_cls(uinfo, dev_name, input, self.log)
            if self.running_handler is None:
                raise ActionError(handler_error)
            result = self.running_handler.perform_action()
            return self.action_response(uinfo, result, output)

        except ActionError as ae:
            self.log.debug("ActionError exception")
            return self.action_response(uinfo, ae.get_info(), output)

        except Exception:
            self.log.debug("Other exception: " + repr(traceback.format_exception(*sys.exc_info())))
            output.failure = "Operation failed"

        finally:
            self.running_handler = None

    def cb_abort(self, uinfo: _ncs.UserInfo) -> None:
        self.log.debug('aborting the action')
        handler = self.running_handler
        if handler is not None:
            handler.abort_action()

    def action_response(self, uinfo: _ncs.UserInfo, result: ActionResult, output: Node) -> None:
        if result is None:
            return
        if 'error' in result:
            output.error = result['error']
        if 'success' in result:
            output.success = result['success']
        if 'failure' in result:
            output.failure = result['failure']


class CompletionHandler(dp.Action):

    # @dp.Action.completion
    # wrapper does not exist in PyAPI at the time of this implementation
    def cb_completion(self, uinfo: _ncs.UserInfo, cli_style: int, token: str, completion_char: int,
                      kp: _ncs.HKeypathRef, cmdpath: str, cmdparam_id: str,
                      simpleType: Optional[Tuple[str, str]], extra: str) -> int:
        self.log.debug("========== drned_xmnr cb_completion() ==========")
        self.log.debug("thandle={0} usid={1}".format(uinfo.actx_thandle,
                                                     uinfo.usid))

        def prep_path_str(path: str) -> str:
            """ Add trailing '/' to an input path it is a directory. """
            output = os.path.join(path, '') if os.path.isdir(path) else path
            return str(output)

        def hack_completions_list(completion_char: int, values: List[str]) -> None:
            """ Hack preventing CLI to add whitespace after the only
                completion value (would end file path completion).
                We don't want to see the '/CLONE' in '?' completions... """
            # TAB or space pressed for completion, and there's only one directory
            if completion_char in [9, 32] and len(values) == 1:
                the_only_one = values[0]
                if the_only_one.endswith('/'):
                    values.append(the_only_one + '/CLONE')

        try:
            matched_paths = glob.glob(str(token) + '*')
            output_strings = [prep_path_str(path) for path in matched_paths]
            if output_strings:
                hack_completions_list(completion_char, output_strings)
                tv = [(_ncs.dp.COMPLETION, item, None) for item in output_strings]
                _ncs.dp.action_reply_completion(uinfo, tv)
            return _ncs.CONFD_OK

        except Exception:
            self.log.error(traceback.format_exc())
            raise
        finally:
            # cleanup from @.action wrapper
            dp.return_worker_socket(self._state, self._make_key(uinfo))


class XmnrDataHandler(application.Service):
    def __init__(self, daemon: dp.Daemon, servicepoint: str, log: Optional[Log] = None,
                 init_args: OptArgs = None) -> None:
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

    def start(self) -> None:
        self.log.debug('started XMNR data')


# ---------------------------------------------
# COMPONENT THREAD THAT WILL BE STARTED BY NCS.
# ---------------------------------------------

class Xmnr(application.Application):
    def setup(self) -> None:
        self.register_action(ns.ns.actionpoint_drned_xmnr, ActionHandler)
        self.register_action('drned-xmnr-completion', CompletionHandler)
        self.register_service(ns.ns.callpoint_coverage_data, XmnrDataHandler)
        self.register_service(ns.ns.callpoint_xmnr_states, XmnrDataHandler)

    def finish(self) -> None:
        pass
