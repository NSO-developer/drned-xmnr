# -*- mode: python; python-indent: 4 -*-

import fcntl
import os
import sys
import select
import glob
import socket
import subprocess
from datetime import datetime as dt
from contextlib import contextmanager

import _ncs

import _ncs.dp as dp
import _ncs.maapi as _maapi
from ncs import maapi, maagic

from .ex import ActionError


if sys.version_info >= (3, 0):
    def text_data(data):
        return data.decode()
else:
    def text_data(data):
        return data


class XmnrBase(object):
    xml_statefile_extension = '.state.xml'
    cfg_statefile_extension = '.state.cfg'
    xml_extensions = [xml_statefile_extension, '.xml']
    cfg_extensions = [cfg_statefile_extension, '.cfg']

    def __init__(self, dev_name, log_obj):
        self.dev_name = dev_name
        self.log = log_obj

    def _setup_directories(self, trans):
        root = maagic.get_root(trans)
        self.xmnr_directory = root.drned_xmnr.xmnr_directory
        self.log_filename = root.drned_xmnr.xmnr_log_file
        self.dev_test_dir = os.path.join(self.xmnr_directory, self.dev_name, 'test')
        self.drned_run_directory = os.path.join(self.dev_test_dir, 'drned-skeleton')
        self.using_builtin_drned = root.drned_xmnr.drned_directory == "builtin"
        self.states_dir = os.path.join(self.dev_test_dir, 'states')
        try:
            os.makedirs(self.states_dir)
        except OSError:
            pass

    def format_state_filename(self, statename, format='xml', suffix=None):
        """Just convert the state name to the right filename."""
        if suffix is None:
            suffix = (self.cfg_statefile_extension if format == 'cfg'
                      else self.xml_statefile_extension)
        return os.path.join(self.states_dir, statename + suffix)

    def state_name_to_existing_filename(self, statename, format='any'):
        suffixes = []
        if format != 'cfg':
            suffixes += self.xml_extensions
        if format != 'xml':
            suffixes += self.cfg_extensions
        for suffix in suffixes:
            path = self.format_state_filename(statename, suffix=suffix)
            if os.path.exists(path):
                return path
        return None

    def state_name_to_filename(self, statename, format='any', existing=True):
        """Look for a state file.

        :param bool existing: if True, the file must exist, otherwise fail
            with `ActionError`
        :param str format: one of 'any', 'xml', 'cfg'; for 'any', the XML
            format is preferred
        """
        filename = self.state_name_to_existing_filename(statename, format)
        if filename is not None:
            return filename
        if existing:
            raise ActionError('No such state: ' + statename)
        return self.format_state_filename(statename,
                                          format=('xml' if format != 'cfg' else 'cfg'))

    def state_filename_to_name(self, filename):
        for extension in self.xml_extensions + self.cfg_extensions:
            if filename.endswith(extension):
                return os.path.basename(filename)[:-len(extension)]

    def get_states(self):
        return [self.state_filename_to_name(f) for f in self.get_state_files()]

    def get_state_files(self):
        return self.get_state_files_by_pattern('*')

    def get_state_files_by_pattern(self, pattern):
        xmls = glob.glob(os.path.join(self.states_dir, pattern + '.xml'))
        cfgs = glob.glob(os.path.join(self.states_dir, pattern + '.cfg'))
        return xmls + [cfg for cfg in cfgs if (cfg[:-3] + 'xml') not in xmls]


class ActionBase(XmnrBase):
    _pytest_executable = None

    def __init__(self, uinfo, dev_name, params, log_obj):
        super(ActionBase, self).__init__(dev_name, log_obj)
        self.uinfo = uinfo
        self.maapi = maapi.Maapi()
        self.run_with_trans(self._setup_directories)
        self._init_params(params)

    def _init_params(self, params):
        # Implement in subclasses
        pass

    @contextmanager
    def open_log_file(self, path):
        with open(os.path.join(self.dev_test_dir, path), 'a') as lf:
            msg = '{} - {}'.format(dt.now(), self.action_name)
            lf.write('\n{}\n{}\n{}\n'.format('-'*len(msg), msg, '-'*len(msg)))
            yield lf

    def perform_action(self):
        if self.log_filename is not None:
            with self.open_log_file(self.log_filename) as self.log_file:
                return self.perform()
        else:
            self.log_file = None
            return self.perform()

    def param_default(self, params, name, default):
        value = getattr(params, name)
        if value is None:
            return default
        return value

    def run_with_trans(self, callback, write=False):
        if write:
            # we do not want to write to the user's transaction
            with maapi.single_write_trans(self.uinfo.username, self.uinfo.context) as trans:
                return callback(trans)
        elif self.uinfo.actx_thandle == -1:
            with maapi.single_read_trans(self.uinfo.username, self.uinfo.context) as trans:
                return callback(trans)
        else:
            mp = maapi.Maapi()
            return callback(mp.attach(self.uinfo.actx_thandle))

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
                if buf is not None and len(buf) != 0:
                    data = text_data(buf)
                    self.log.debug("run_outputfun, output len=" + str(len(data)))
                    state = outputfun(state, data)
                    stdoutdata += data
            else:
                self.progress_msg("Silence timeout, terminating process\n")
                proc.kill()

        self.log.debug("run_finished, output len=" + str(len(stdoutdata)))
        return proc.wait(), stdoutdata

    def cli_write(self, msg):
        _maapi.cli_write(self.maapi.msock, self.uinfo.usid, msg)

    def cli_filter(self, msg):
        if self.uinfo.context == 'cli':
            self.cli_write(msg)

    def progress_msg(self, msg):
        self.log.debug(msg)
        self.cli_filter(msg)
        if self.log_file is not None:
            self.log_file.write(msg)

    def setup_drned_env(self, trans):
        """Build a dictionary that is supposed to be passed to `Popen` as the
        environment.
        """
        env = dict(os.environ)
        root = maagic.get_root(trans)
        drdir = root.drned_xmnr.drned_directory
        if drdir == "env":
            try:
                drdir = env['DRNED']
            except KeyError:
                raise ActionError('DrNED installation directory not set; ' +
                                  'set /drned-xmnr/drned-directory or the ' +
                                  'environment variable DRNED')
        elif drdir == "builtin" or drdir is None:
            drdir = os.path.join(self.dev_test_dir, 'drned')
        drdir = os.path.abspath(drdir)
        env['DRNED'] = drdir
        if 'PYTHONPATH' in env:
            env['PYTHONPATH'] += os.pathsep + drdir
        else:
            env['PYTHONPATH'] = drdir
        try:
            env['PYTHONPATH'] += os.pathsep + env['NCS_DIR'] + '/lib/pyang'
        except KeyError:
            raise ActionError('NCS_DIR not set')
        env['PYTHONUNBUFFERED'] = '1'
        path = env['PATH']
        # need to remove exec path inserted by NSO
        env['PATH'] = os.pathsep.join(ppart for ppart in path.split(os.pathsep)
                                      if 'ncs/erts' not in ppart)
        return env

    def check_which(self, executable):
        with open('/dev/null', 'wb') as devnull:
            return subprocess.call(['which', executable], stdout=devnull) == 0

    def pytest_executable(self):
        if ActionBase._pytest_executable is None:
            ActionBase._pytest_executable = self.find_pytest_executable()
        return ActionBase._pytest_executable

    def find_pytest_executable(self):
        suffix = str(sys.version_info[0])  # '2' or '3'
        execs = ['pytest', 'py.test', 'pytest-' + suffix, 'py.test-' + suffix]
        for executable in execs:
            if self.check_which(executable):
                self.log.debug('found pytest executable: ' + executable)
                return executable
        raise ActionError('PyTest not installed - pytest executable not found')

    def run_in_drned_env(self, args, timeout=120, outputfun=None, **envdict):
        env = self.run_with_trans(self.setup_drned_env)
        env.update(envdict)
        self.log.debug("using env {0}\n".format(env))
        self.log.debug("running", args)
        try:
            proc = subprocess.Popen(args,
                                    env=env,
                                    cwd=self.drned_run_directory,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
            self.log.debug("run_outputfun, going in")
        except OSError:
            msg = 'PyTest not installed or DrNED running directory ({0}) not set up'
            raise ActionError(msg.format(self.drned_run_directory))
        if outputfun is None:
            outputfun = self.progress_fun
        return self.proc_run(proc, outputfun, timeout)

    def progress_fun(self, state, stdout):
        self.progress_msg(stdout)
        self.extend_timeout(120)
        return None

    def save_config(self, trans, config_type, path):
        save_id = trans.save_config(config_type, path)
        try:
            ssocket = socket.socket()
            _ncs.stream_connect(
                sock=ssocket,
                id=save_id,
                flags=0,
                ip='127.0.0.1',
                port=_ncs.PORT)
            while True:
                config_data = ssocket.recv(4096)
                if not config_data:
                    return
                yield config_data
                self.log.debug("Data: "+str(config_data))
        finally:
            ssocket.close()


class XmnrDeviceData(XmnrBase):
    """Base for XMNR data providers."""
    @classmethod
    def get_data(clazz, tctx, device, log, data_cb):
        with maapi.Maapi() as mp:
            with mp.attach(tctx) as trans:
                dd = clazz(device, log, trans)
                data = data_cb(dd)
                return data

    def __init__(self, device, log, trans):
        super(XmnrDeviceData, self).__init__(device, log)
        self._setup_directories(trans)
