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

    ######################################################################
    ## IMPORTS & GLOBALS

from __future__ import print_function
import os
import sys
import time
import select
import socket
import threading
import traceback
import inspect

assert sys.version_info >= (2,7)
# Not tested with anything lower

import _ncs
import _ncs.dp as dp
import _ncs.maapi as maapi
import drned_xmnr.namespaces.drned_xmnr_ns as ns

XT = _ncs.XmlTag
V = _ncs.Value
TV = _ncs.TagValue
from ncs_pyvm import NcsPyVM
_schemas_loaded = False

# operation modules
import op.config_op
from op.ex import ActionError

def param_default(params, tag, default):
    matching_param_list = [p.v for p in params if p.tag == tag]
    if len(matching_param_list) == 0:
        return default
    return str(matching_param_list[0])

class ActionHandler(threading.Thread):
    handlers = {
        ns.ns.drned_xmnr_delete_state: op.config_op.DeleteStateOp,
        ns.ns.drned_xmnr_explore_transitions: op.config_op.ExploreTransitionsOp,
        ns.ns.drned_xmnr_list_states: op.config_op.ListStatesOp,
        ns.ns.drned_xmnr_record_state: op.config_op.RecordStateOp,
        ns.ns.drned_xmnr_transition_to_state: op.config_op.TransitionToStateOp,
    }

    ######################################################################
    ##  CB_ACTION  #######################################################
    ######################################################################

    def cb_action(self, uinfo, op_name, kp, params):
        self.debug("========== drned_xmnr cb_action() ==========")
        dev_name = str(kp[-3][0])
        self.debug("thandle={0} usid={1}".format(uinfo.actx_thandle, uinfo.usid))

        os.environ['DRNED'] = '/Users/jlindbla/git/drned'
        sys.path = [os.environ['DRNED'], os.environ['NCS_DIR'] + '/lib/pyang'] + sys.path
        os.environ['PATH'] = os.environ['NCS_DIR'] + '/bin:' + os.environ['PATH']
        os.environ['DRNED_NCS'] = '../../..'
        ## FIXME jlindbla
        pycdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
        testdir = os.path.normpath(pycdir + "/../../../../../../test/drned-xmnr/" + dev_name)
        #/Users/jlindbla/git/virtual-mpls-vpn-xe-netconf/state/packages-in-use/1/drned-xmnr/python/drned_xmnr
        #../../../../../../test/drned-xmnr/<dev>
        os.chdir(testdir)
        #os.chdir('/Users/jlindbla/git/virtual-mpls-vpn-xe-netconf/test/drned-xmnr/ce0')

        ## ce0-nc.cfg
        #        admin@ncs# devices device ce0-nc sync-from 
        
        try:
            if op_name.tag not in self.handlers:
                raise ActionError({'error': "Operation not implemented: {0}".format(op_name)})
            
            handler_cls = self.handlers[op_name.tag]
            handler = handler_cls(self.msocket, uinfo, dev_name, params, self.debug)
            result = handler.perform()
            return self.action_response(uinfo, result)

        ##----------------------------------------------------------------
        except ActionError as ae:
            self.debug("ActionError exception")
            return self.action_response(uinfo, ae.get_info())
        except:
            self.debug("Other exception: " + repr(traceback.format_exception(*sys.exc_info())))
            msg = "Operation failed"
            dp.action_reply_values(uinfo, [TV(XT(ns.ns.hash, ns.ns.drned_xmnr_error), V(msg))])
            return _ncs.CONFD_OK

    def action_response(self, uinfo, result):
        reply = []

        if result.has_key('message'):
            reply += [TV(XT(ns.ns.hash, ns.ns.drned_xmnr_message), V(result['message']))]
        if result.has_key('error'):
            reply += [TV(XT(ns.ns.hash, ns.ns.drned_xmnr_error), V(result['error']))]
        if result.has_key('success'):
            reply += [TV(XT(ns.ns.hash, ns.ns.drned_xmnr_success), V(result['success']))]
        if result.has_key('failure'):
            reply += [TV(XT(ns.ns.hash, ns.ns.drned_xmnr_failure), V(result['failure']))]
        if result.has_key('filename'):
            reply += [TV(XT(ns.ns.hash, ns.ns.drned_xmnr_filename), V(result['filename']))]
        if result.has_key('ned-directory'):
            reply += [TV(XT(ns.ns.hash, ns.ns.drned_xmnr_ned_directory), V(result['ned-directory']))]
        if result.has_key('yang-directory'):
            reply += [TV(XT(ns.ns.hash, ns.ns.drned_xmnr_yang_directory), V(result['yang-directory']))]
        if result.has_key('missing'):
            reply += [TV(XT(ns.ns.hash, ns.ns.drned_xmnr_missing), V(result['missing']))]
        if result.has_key('enabled'):
            reply += [TV(XT(ns.ns.hash, ns.ns.drned_xmnr_enabled), V(result['enabled']))]
        if result.has_key('disabled'):
            reply += [TV(XT(ns.ns.hash, ns.ns.drned_xmnr_disabled), V(result['disabled']))]
        if result.has_key('marked'):
            reply += [TV(XT(ns.ns.hash, ns.ns.drned_xmnr_marked), V(result['marked']))]
        if result.has_key('get-config-reply'):
            reply += [TV(XT(ns.ns.hash, ns.ns.drned_xmnr_get_config_reply), V(result['get-config-reply']))]
        if result.has_key('get-reply'):
            reply += [TV(XT(ns.ns.hash, ns.ns.drned_xmnr_get_reply), V(result['get-reply']))]
        if result.has_key('hello-reply'):
            reply += [TV(XT(ns.ns.hash, ns.ns.drned_xmnr_hello_reply), V(result['hello-reply']))]
            self.debug("action reply={0}".format(reply))

        dp.action_reply_values(uinfo, reply)
        return _ncs.CONFD_OK
            
    ######################################################################
    ##  REGISTRATION  ####################################################
    ######################################################################
            
    def __init__(self, debug, pipe):
        threading.Thread.__init__(self)
        self.debug = debug
        self.pipe = pipe
        self.reconnect = 0
        
    def run(self):
        self.debug("Starting worker...")

        stop = False
        while not stop:
            self.init_daemon()

            _r = [self.csocket, self.wsocket, self.pipe]
            while True:
                (r, w, e) = select.select(_r, [], [])

                if self.pipe in r:
                    self.debug("Worker stop requested")
                    stop = True
                    break

                for s in r:
                    try:
                        dp.fd_ready(self.ctx, s)
                        self.reconnect = 0

                    except _ncs.error.EOF:
                        self.reconnect += 1
                        if self.reconnect >= 15:
                            self.debug("EOF in worker/control socket, giving up")
                            stop = True
                        else:
                            self.debug("EOF in worker/control socket, restarting")
                            time.sleep(2)
                        break
                    except Exception as e:
                        self.debug("Exception in fd_ready: %s" % (str(e), ))

            self.stop_daemon()

        self.debug("Worker stopped")

    def cb_init(self, uinfo):
        dp.action_set_fd(uinfo, self.wsocket)

    def init_daemon(self):
        self.csocket = socket.socket()
        self.wsocket = socket.socket()
        self.msocket = socket.socket()

        self.ctx = dp.init_daemon("drned_xmnr")

        dp.connect(
            dx=self.ctx,
            sock=self.csocket,
            type=dp.CONTROL_SOCKET,
            ip='127.0.0.1',
            port=_ncs.NCS_PORT
        )
        dp.connect(
            dx=self.ctx,
            sock=self.wsocket,
            type=dp.WORKER_SOCKET,
            ip='127.0.0.1',
            port=_ncs.NCS_PORT
        )
        maapi.connect(
            sock=self.msocket,
            ip='127.0.0.1',
            port=_ncs.NCS_PORT
        )

        dp.install_crypto_keys(self.ctx)
        dp.register_action_cbs(self.ctx, 'drned-xmnr', self)
        dp.register_done(self.ctx)

    def stop_daemon(self):
        self.wsocket.close()
        self.csocket.close()
        dp.release_daemon(self.ctx)

# ---------------------------------------------
# COMPONENT THREAD THAT WILL BE STARTED BY NCS.
# ---------------------------------------------

class Action(object):

    def __init__(self, *args, **kwds):
        # Setup the NCS object, containing mechanisms
        # for communicating between NCS and this User code.
        self._ncs = NcsPyVM(*args, **kwds)

        # Just checking if the NCS logging works...
        self.debug('Initalizing object')

        # Register our 'finish' callback
        self._finish_cb = lambda: self.finish()
        self._ncs.reg_finish(self._finish_cb)
        self.mypipe = os.pipe()

        self.waithere = threading.Semaphore(0)  # Create as blocked

    # This method starts the user application in a thread
    def run(self):
        global _schemas_loaded

        self.debug("action.py:run starting")

        self.debug("run: starting action handler...")
        w = ActionHandler(self.debug, self.mypipe[0])

        # Since the ActionHandler object above is a thread, when we call the
        # start method the Thread class will invoke the
        # ActionHandler.run-method.
        w.start()
        self.debug("action.py:run: starting worker...")
        self._ncs.add_running_thread('Worker')

        # Wait here until 'finish' gets called
        self.debug("action.py:run: waiting for work...")
        self.waithere.acquire()

        # Inform the 'subscriber' that it has to shutdown
        os.write(self.mypipe[1], 'finish')
        w.join()

        self.debug("action.py:run: finished...")

    # Just a convenient logging function
    def debug(self, line):
        self._ncs.debug(line)

    # Callback that will be invoked by NCS when the system is shutdown.
    # Make sure to shutdown the User code, including any User created threads.
    def finish(self):
        self.waithere.release()

    ######################################################################
