# -*- mode: python; python-indent: 4 -*-

import fcntl
import os
import select
import subprocess
import sys
import time
import traceback

import _ncs.dp as dp
import _ncs.maapi as _maapi
from ncs import maapi

from ex import ActionError
import drned_xmnr.namespaces.drned_xmnr_ns as ns

class BaseOp(object):
    ncs_dir = os.environ['NCS_DIR']
    pkg_root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    ncs_run_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(pkg_root_dir))))
    ncs_rollback_dir = os.path.join(ncs_run_dir, "logs")
    #states_dir = os.path.join(ncs_run_dir, "test", "drned", dev_name)
    
    def __init__(self, uinfo, dev_name, params, debug_func):
        self.uinfo = uinfo
        self.dev_name = dev_name
        self.maapi = maapi.Maapi()
        self.debug = debug_func
        self.states_dir = os.path.join(self.ncs_run_dir, "test", "drned-xmnr", dev_name) ## FIXME: correct?
        try:
            os.makedirs(self.states_dir)
        except:
            pass
        
        self._init_params(params)

    def _init_params(self, params):
        # Implement in subclasses
        pass


    def param_default(self, params, name, default):
        value = getattr(params, name)
        if value is None:
            return default
        return value


    def extend_timeout(self, timeout_extension):
        dp.action_set_timeout(self.uinfo, timeout_extension)
        
    def proc_run(self, proc, outputfun, timeout):
        fd = proc.stdout.fileno()
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        state = None
        stdoutdata = ""
        while proc.poll() is None:
            rlist, wlist, xlist = select.select([fd], [], [fd], timeout)
            if rlist:
                buf = proc.stdout.read()
                if buf != "":
                    self.debug("run_outputfun, output len=" + str(len(buf)))
                    state = outputfun(state, buf)
                    stdoutdata += buf
            else:
                self.progress_msg("Silence timeout, terminating process\n")
                proc.kill()
                proc.wait()

        self.debug("run_finished, output len=" + str(len(stdoutdata)))
        return stdoutdata

    def progress_msg(self, msg):
        self.debug(msg)
        if self.uinfo.context == 'cli':
            _maapi.cli_write(self.maapi.msock, self.uinfo.usid, msg)

    def get_exe_path(self, exe):
        path = self.get_exe_path_from_PATH(exe)
        if not os.path.exists(path):
            raise ActionError({'error':'Unable to execute {0}, command no found in PATH {1}'.format(exe, os.environ['PATH'])})

        return path

    def get_exe_path_from_PATH(self, exe):
        parts = (os.environ['PATH'] or '/bin').split(os.path.pathsep)
        for part in parts:
            path = os.path.join(part, exe)
            if os.path.exists(path):
                return path
        return None
