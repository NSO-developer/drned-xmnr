from __future__ import print_function

import os
import sys
import shutil
import errno
import subprocess
from lxml import etree

import _ncs
from ncs import maagic

from . import base_op
from .ex import ActionError

if sys.version_info >= (3, 3):
    import functools
    et_tostring = functools.partial(etree.tostring, encoding='unicode')
else:
    et_tostring = etree.tostring


class SetupOp(base_op.ActionBase):
    action_name = 'xmnr setup'

    def _init_params(self, params):
        self.overwrite = params.overwrite
        self.queue = params.use_commit_queue
        self.save_default_config = params.save_default_config

    def perform(self):
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

        return {'success': "XMNR set up for device " + self.dev_name}

    def prepare_setup(self, trans):
        root = maagic.get_root(trans)
        xmnr_pkg = root.packages.package['drned-xmnr'].directory
        self.drned_skeleton = os.path.join(xmnr_pkg, 'drned-skeleton')
        self.drned_submod = os.path.join(xmnr_pkg, 'drned')

    def find_ned_package(self, root, ned_id, ned_type):
        for package in root.packages.package:
            for component in package.component:
                try:
                    if getattr(component.ned, ned_type).ned_id == ned_id:
                        return package
                except AttributeError:
                    continue
        return None

    def setup_drned(self):
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

    def format_device_cfg(self, trans):
        def del_element(elem, name):
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
            cfg.write(et_tostring(devices))
