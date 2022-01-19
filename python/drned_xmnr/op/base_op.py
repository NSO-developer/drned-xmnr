# -*- mode: python; python-indent: 4 -*-

import fcntl
import os
import sys
import select
import glob
import socket
import subprocess
import threading
import signal
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

TIMEOUT_MARGIN = 5
'''Number of seconds between the device timeout and action timeout.
When XMNR gets any output from a DrNED test, it extends the action
timeout by device-timeout increased by this value.

There are several layers, each having it's own timeout. It is
desirable and less disruptive that if the lower layer is able to
somehow abort whatever is going on because it takes too long, the
higher level waits for it to do so, so the higher layer's timeout
should be at least somewhat bigger than that of the lower layer, to
avoid nasty race conditions.

There is only one parameter now, /devices/device/read-timeout, used by
all three layers with increasing margin:

 1. the lowest layer, DrNED, needs to use the timeout value to abort
    waiting for ncs_cli response if that does not come;
 2. XMNR uses timeout+margin to wait for DrNED's output; this might
    not be needed, if we could be sure that DrNED always aborts if it
    takes too long, but we cannot, or at least I am not sure we can
    rely on DrNED in this respect;
 3. finally, NCS is repeatedly told to wait another timeout+2*margin
    for the action to complete; we need to do that, since otherwise
    NCS might simply abort the action.
'''


class XmnrBase(object):
    xml_statefile_extension = '.state.xml'
    cfg_statefile_extension = '.state.cfg'
    metadata_extension = '.load'
    flag_file_extension = '.disabled'
    xml_extensions = [xml_statefile_extension, '.xml']
    cfg_extensions = [cfg_statefile_extension, '.cfg']

    def __init__(self, dev_name, log_obj):
        self.dev_name = dev_name
        self.log = log_obj

    def _setup_xmnr(self, trans):
        root = maagic.get_root(trans)
        self.xmnr_directory = os.path.abspath(root.drned_xmnr.xmnr_directory)
        self.log_filename = root.drned_xmnr.xmnr_log_file
        self.dev_test_dir = os.path.join(self.xmnr_directory, self.dev_name, 'test')
        self.drned_run_directory = os.path.join(self.dev_test_dir, 'drned-skeleton')
        self.using_builtin_drned = root.drned_xmnr.drned_directory == "builtin"
        self.states_dir = os.path.join(self.dev_test_dir, 'states')
        device_node = root.devices.device[self.dev_name]
        self.device_timeout = device_node.read_timeout
        if self.device_timeout is None:
            self.device_timeout = 120
        device_xmnr_node = device_node.drned_xmnr
        self.cleanup_timeout = device_xmnr_node.cleanup_timeout
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

    def get_disabled_state_files(self):
        return [filename for filename in self.get_state_files()
                if os.path.exists(filename + self.flag_file_extension)]

    def is_state_disabled(self, state):
        return os.path.exists(self.state_name_to_filename(state) + self.flag_file_extension)

    def get_state_files_by_pattern(self, pattern):
        files = {}
        for suff in ['.xml', '.cfg']:
            files[suff] = set()
            for part in ['.state', '']:
                files[suff].update(glob.glob(os.path.join(self.states_dir, pattern + part + suff)))
        return list(files['.xml']) + [cfg for cfg in files['.cfg']
                                      if (cfg[:-3] + 'xml') not in files['.xml']]


class Progressor(object):
    """Track progress messages.

    Progress messages come in chunks and need to be re-chunked into
    lines.  This class is not directly related to The Noon Universe.
    """
    def __init__(self, action):
        self.buf = ""
        self.action = action

    def progress(self, chunk):
        lines = chunk.split('\n')
        lines[0] = self.buf + lines[0]
        for line in lines[:-1]:
            self.action.progress_msg(line)
        self.buf = lines[-1]


class ActionBase(XmnrBase):
    _pytest_executable = None

    def __init__(self, uinfo, dev_name, params, log_obj):
        super(ActionBase, self).__init__(dev_name, log_obj)
        self.uinfo = uinfo
        self.drned_process = None
        self.aborted = False
        self.abort_lock = threading.Lock()
        self.maapi = maapi.Maapi()
        self.run_with_trans(self._setup_xmnr)
        self._init_params(params)

    def _init_params(self, params):
        # Implement in subclasses
        pass

    @contextmanager
    def open_log_file(self, path):
        with open(os.path.join(self.dev_test_dir, path), 'a') as lf:
            msg = '{} - {}'.format(dt.now(), self.action_name)
            lf.write('\n{}\n{}\n{}\n'.format('-' * len(msg), msg, '-' * len(msg)))
            yield lf

    def perform_action(self):
        if self.log_filename is not None:
            with self.open_log_file(self.log_filename) as self.log_file:
                return self.perform()
        else:
            self.log_file = None
            return self.perform()

    def abort_action(self):
        with self.abort_lock:
            self.aborted = True
            self.terminate_drned_process()

    def param_default(self, params, name, default):
        value = getattr(params, name, None)
        if value is None:
            return default
        return value

    def run_with_trans(self, callback, write=False, db=_ncs.RUNNING):
        if write:
            # we do not want to write to the user's transaction
            with maapi.single_write_trans(self.uinfo.username, self.uinfo.context, db=db) as trans:
                return callback(trans)
        elif self.uinfo.actx_thandle == -1:
            with maapi.single_read_trans(self.uinfo.username, self.uinfo.context, db=db) as trans:
                return callback(trans)
        else:
            mp = maapi.Maapi()
            return callback(mp.attach(self.uinfo.actx_thandle))

    def extend_timeout(self):
        '''Tell NSO to wait a bit longer.  See also `TIMEOUT_MARGIN`.
        '''
        extension = self.device_timeout + 2 * TIMEOUT_MARGIN
        dp.action_set_timeout(self.uinfo, extension)

    def proc_run(self, outputfun):
        fd = self.drned_process.stdout.fileno()
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        stdoutdata = ""
        timeout = self.device_timeout
        while self.drned_process.poll() is None:
            rlist, wlist, xlist = select.select([fd], [], [fd], timeout + TIMEOUT_MARGIN)
            if rlist:
                buf = self.drned_process.stdout.read()
                if buf is not None and len(buf) != 0:
                    data = text_data(buf)
                    self.log.debug("run_outputfun, output len=" + str(len(data)))
                    outputfun(data)
                    self.extend_timeout()
                    stdoutdata += data
            else:
                self.progress_msg("Silence timeout, terminating process")
                self.terminate_drned_process()

        self.log.debug("run_finished, output len=" + str(len(stdoutdata)))
        return self.drned_process.wait(), stdoutdata

    def terminate_drned_process(self):
        if self.drned_process is None:
            return
        try:
            self.drned_process.send_signal(signal.SIGINT)
            self.drned_process.wait(self.cleanup_timeout)
        except subprocess.TimeoutExpired:
            self.log.debug("process not responding to SIGINT - killing instead")
            self.drned_process.kill()

    def cli_write(self, msg):
        if not self.aborted:
            # cannot write to CLI after an abort
            _maapi.cli_write(self.maapi.msock, self.uinfo.usid, msg)

    def cli_filter(self, msg):
        if self.uinfo.context == 'cli':
            self.cli_write(msg)

    def progress_msg(self, msg):
        self.log.debug(msg)
        self.cli_filter(msg)
        if self.log_file is not None:
            self.log_file.write(msg + '\n')
            self.log_file.flush()

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
                raise ActionError('DrNED installation directory not set; '
                                  + 'set /drned-xmnr/drned-directory or the '
                                  + 'environment variable DRNED')
        elif drdir == "builtin" or drdir is None:
            drdir = os.path.join(self.dev_test_dir, 'drned')
        drdir = os.path.abspath(drdir)
        env['DRNED'] = drdir
        if 'PYTHONPATH' in env:
            env['PYTHONPATH'] += os.pathsep + drdir
        else:
            env['PYTHONPATH'] = drdir
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

    def get_authgroup_info(self, trans, root, locuser, authmap):
        if authmap.same_user.exists():
            username = locuser
        else:
            username = authmap.remote_name
        if username is None:
            return None, None
        if authmap.same_pass.exists():
            upwd = root.aaa.authentication.users.user[locuser].password
        else:
            upwd = authmap.remote_password
        if upwd is None:
            return username, None
        trans.maapi.install_crypto_keys()
        return username, _ncs.decrypt(upwd)

    def get_devcli_params(self, trans):
        root = maagic.get_root(trans)
        device_node = root.devices.device[self.dev_name]
        ip = device_node.address
        port = device_node.drned_xmnr.cli_port
        if port is None:
            port = device_node.port
        driver = device_node.drned_xmnr.driver
        if driver is None:
            raise ActionError('device driver not configured, cannot continue')
        authgroup_name = device_node.authgroup
        authgroup = root.devices.authgroups.group[authgroup_name]
        locuser = self.uinfo.username
        if locuser in authgroup.umap:
            authmap = authgroup.umap[locuser]
        else:
            authmap = authgroup.default_map
        user, passwd = self.get_authgroup_info(trans, root, locuser, authmap)
        return driver, user, passwd, ip, port

    def devcli_run(self, script, script_args):
        driver, username, passwd, ip, port = self.run_with_trans(self.get_devcli_params)
        runner = os.environ.get('PYTHON_RUNNER', 'python')
        runner_args = runner.split()
        args = runner_args + [script, '--devname', self.dev_name,
                              '--driver', driver,
                              '--ip', ip, '--port', str(port),
                              '--workdir', 'drned-ncs', '--timeout', str(self.device_timeout)]
        if username is not None:
            args.extend(['--username', username])
            if passwd is not None:
                args.extend(['--password', passwd])
        args.extend(script_args)
        return self.run_in_drned_env(args)

    def run_in_drned_env(self, args, **envdict):
        env = self.run_with_trans(self.setup_drned_env)
        env.update(envdict)
        self.log.debug("using env {0}\n".format(env))
        self.log.debug("running", args)
        try:
            with self.abort_lock:
                if self.aborted:
                    raise ActionError("action aborted")
                self.drned_process = subprocess.Popen(args,
                                                      env=env,
                                                      cwd=self.drned_run_directory,
                                                      stdout=subprocess.PIPE,
                                                      stderr=subprocess.STDOUT)
            self.log.debug("run_in_drned_env, going in")
            return self.proc_run(Progressor(self).progress)
        except OSError:
            msg = 'PyTest not installed or DrNED running directory ({0}) not set up'
            raise ActionError(msg.format(self.drned_run_directory))
        finally:
            self.drned_process = None

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
                self.log.debug("Data: " + str(config_data))
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
        self._setup_xmnr(trans)
