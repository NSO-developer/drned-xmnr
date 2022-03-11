import os
import re
import shutil
import errno
import subprocess
from lxml import etree

import _ncs
from ncs import maagic

from typing import Optional
from drned_xmnr.typing_xmnr import ActionResult
from ncs.maagic import Node
from ncs.maapi import Transaction

from . import base_op
from .ex import ActionError


class DevcliLogMatch(object):
    """Common matching of Devcli messages.

    Can be extended for more specific purposes; extending classess
    should call the `match` method of this class.

    """
    matchexpr = (
        r'(?:(?P<devcli>.*DevcliException: No device definition found)'
        r'|(?P<traceback>Traceback [(]most recent call last[)]:)'
        r'|(?P<newstate>^STATE: (?P<state>[^ ]*) : .*)'
        r'|(?P<match>^MATCHED \'(?P<matchstate>.*)\', SEND: .*)'
        r'|(?P<closed>device communication failure: .*EOF.*)'
        r'|(?P<timeout>device communication failure: .*Timeout.*)'
        r'|(?P<authfailed>failed to authenticate)'
        r')$')
    matchrx = re.compile(matchexpr)

    def __init__(self) -> None:
        self.waitstate: Optional[str] = None
        self.devcli_error: Optional[str] = None

    def match(self, msg: str) -> Optional[str]:
        match = DevcliLogMatch.matchrx.match(msg)
        if match is None:
            return None
        if match.lastgroup == 'traceback':
            self.devcli_error = 'the device driver appears to be broken'
            return 'device driver failed'
        elif match.lastgroup == 'newstate':
            self.waitstate = match.groupdict()['state']
            return None
        elif match.lastgroup == 'match':
            self.waitstate = None
            return None
        elif match.lastgroup == 'closed':
            self.devcli_error = 'connection closed'
            return 'Could not connect to the device or device connection closed'
        elif match.lastgroup == 'timeout':
            self.devcli_error = 'device communication timeout'
            return 'Device communication timeout'
        elif match.lastgroup == 'authfailed':
            self.devcli_error = 'failed to authenticate'
            return 'Failed to authenticate to the device CLI'
        return None


class SetupOp(base_op.ActionBase):
    action_name = 'xmnr setup'

    def _init_params(self, params: Node) -> None:
        self.overwrite: bool = params.overwrite
        self.queue: bool = params.use_commit_queue
        self.save_default_config = params.save_default_config
        # super(SetupOp, self).__init__()
        self.filter = DevcliLogMatch()

    def cli_filter(self, msg: str) -> None:
        report = self.filter.match(msg)
        if report is not None:
            super(SetupOp, self).cli_filter(report + '\n')

    def perform(self) -> ActionResult:
        # device and states directory should have been already created
        self.run_with_trans(self.prepare_setup)
        try:
            with open(os.path.join(os.path.dirname(self.dev_test_dir),
                                   'package-meta-data.xml'),
                      'w') as meta:
                if not self.queue:
                    print('<requires-transaction-states/>', file=meta)
        except OSError as ose:
            msg = "Failed to set up package-meta-data file {0}".format(os.strerror(ose.errno))
            raise ActionError(msg)
        target = os.path.join(self.dev_test_dir, "drned-skeleton")
        if self.overwrite and os.path.exists(target):
            try:
                shutil.rmtree(target, ignore_errors=True)
                os.remove(target)
            except OSError as ose:
                if ose.errno != errno.ENOENT:
                    msg = "Failed to remove the old drned-skeleton directory {0}" \
                          .format(os.strerror(ose.errno))
                    raise ActionError(msg)
        try:
            shutil.copytree(self.drned_skeleton, target)
        except OSError as ose:
            if ose.errno == errno.EEXIST:
                msg = "The target {0} already exists. Did you use `overwrite' parameter?" \
                      .format(target)
            else:
                msg = "Failed to copy the `drned-skeleton' directory."
            raise ActionError(msg)
        target = os.path.join(self.dev_test_dir, "drned")
        if self.overwrite and os.path.exists(target):
            try:
                shutil.rmtree(target, ignore_errors=True)
            except OSError as ose:
                if ose.errno != errno.ENOENT:
                    msg = "Failed to remove the old drned directory {0}" \
                          .format(os.strerror(ose.errno))
                    raise ActionError(msg)
        try:
            shutil.copytree(self.drned_submod, target)
        except OSError as ose:
            if ose.errno == errno.EEXIST:
                msg = "The target {0} already exists. Did you use `overwrite' parameter?" \
                      .format(target)
            else:
                msg = "Failed to copy the `drned' directory: " + ose.strerror
            raise ActionError(msg)
        self.setup_drned()
        # store initial device config for later state traversals
        if self.save_default_config:
            result, _ = self.devcli_run('save-default-config.py', [])
            if result != 0:
                raise ActionError("Failed saving initial device configuration.")

            if self.filter.devcli_error is not None:
                return {'failure': 'Could not save config.'}

        return {'success': "XMNR set up for device " + self.dev_name}

    def prepare_setup(self, trans: Transaction) -> None:
        root = maagic.get_root(trans)
        xmnr_pkg = root.packages.package['drned-xmnr'].directory
        self.drned_skeleton = os.path.join(xmnr_pkg, 'drned-skeleton')
        self.drned_submod = os.path.join(xmnr_pkg, 'drned')

    def find_ned_package(self, root: Node, ned_id: str, ned_type: str) -> Node:
        for package in root.packages.package:
            for component in package.component:
                try:
                    if getattr(component.ned, ned_type).ned_id == ned_id:
                        return package
                except AttributeError:
                    continue
        return None

    def setup_drned(self) -> None:
        env = self.run_with_trans(self.setup_drned_env)
        self.drned_process = subprocess.Popen(['make', 'env.sh'],
                                              env=env,
                                              cwd=self.drned_run_directory,
                                              stdout=subprocess.PIPE,
                                              stderr=subprocess.STDOUT)
        result, _ = self.proc_run(lambda *ignore: None)
        if result != 0:
            raise ActionError("Failed to set up env.sh for DrNED")
        self.cfg_file = os.path.join(self.drned_run_directory, self.dev_name + '.cfg')
        if self.overwrite or not os.path.exists(self.cfg_file):
            self.run_with_trans(self.format_device_cfg)
        ncs_target = os.path.join(self.drned_run_directory, 'drned-ncs')
        if self.overwrite and os.path.exists(ncs_target):
            try:
                os.remove(ncs_target)
            except OSError as ose:
                if ose.errno != errno.ENOENT:
                    msg = "Failed to remove the old drned-ncs directory {0}" \
                          .format(os.strerror(ose.errno))
                    raise ActionError(msg)
        try:
            os.symlink(os.getcwd(), ncs_target)
        except OSError as ose:
            if ose.errno == errno.EEXIST:
                msg = "The target {0} already exists. Did you use `overwrite' parameter?" \
                      .format(ncs_target)
            else:
                msg = "Failed to symlink the the target {}".format(ncs_target)
            raise ActionError(msg)

    def format_device_cfg(self, trans: Transaction) -> None:
        def del_element(elem: Node, name: str) -> None:
            subel = elem.find('{http://tail-f.com/ns/ncs}' + name)
            if subel is not None:
                elem.remove(subel)
        cfg_iter = self.save_config(trans,
                                    _ncs.maapi.CONFIG_XML_PRETTY,
                                    '/devices/device{{{0}}}'.format(self.dev_name))
        config_tree = etree.fromstring(b''.join(cfg_iter))
        # need to delete some elements
        devices = config_tree[0]
        dev = devices[0]
        for name in ['ssh', 'connect-timeout', 'read-timeout', 'trace', 'config']:
            del_element(dev, name)
        with open(self.cfg_file, 'w') as cfg:
            cfg.write(etree.tostring(devices, encoding='unicode'))
