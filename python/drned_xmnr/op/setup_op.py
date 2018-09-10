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

    def perform(self):
        # device and states directory should have been already created
        self.run_with_trans(self.prepare_setup)
        try:
            shutil.copy(self.pkg_file,
                        os.path.join(os.path.dirname(self.dev_test_dir), 'package-meta-data.xml'))
        except OSError:
            raise ActionError("Failed to copy package-meta-data file.")
        target = os.path.join(self.dev_test_dir, "drned-skeleton")
        if self.overwrite and os.path.exists(target):
            try:
                shutil.rmtree(target, ignore_errors=True)
                os.remove(target)
            except OSError:
                pass
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
                os.remove(target)
            except OSError:
                pass
        try:
            shutil.copytree(self.drned_submod, target)
        except OSError as ose:
            if ose.errno == errno.EEXIST:
                msg = "The target {0} already exists. Did you use `overwrite' parameter?" \
                      .format(target)
            else:
                msg = "Failed to copy the `drned' directory."
            raise ActionError(msg)
        self.setup_drned()
        return {'success': "XMNR set up for device " + self.dev_name}

    def prepare_setup(self, trans):
        root = maagic.get_root(trans)
        self.pkg_file = self.get_package(root)
        xmnr_pkg = root.packages.package['drned-xmnr'].directory
        self.drned_skeleton = os.path.join(xmnr_pkg, 'drned-skeleton')
        self.drned_submod = os.path.join(xmnr_pkg, 'drned')
    def get_package(self, root):
        devtype = root.devices.device[self.dev_name].device_type
        if devtype.ne_type in (devtype.netconf, devtype.snmp):
            # for netconf/snmp devices, there is (usually) no package
            return '/dev/null'
        elif devtype.ne_type == devtype.generic:
            ned_id = devtype.generic.ned_id
            ned_type = 'generic'
        else:
            ned_id = devtype.cli.ned_id
            ned_type = 'cli'
        package = self.find_ned_package(root, ned_id, ned_type)
        if package is None:
            self.log.warning("Could not find the device NED package, NED id {0}".format(ned_id))
            return '/dev/null'
        return os.path.join(package.directory, 'package-meta-data.xml')

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
        proc = subprocess.Popen(['make', 'env.sh'],
                                env=env,
                                cwd=self.drned_run_directory,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        result, _ = self.proc_run(proc, self.progress_fun, 120)
        if result != 0:
            raise ActionError("Failed to set up env.sh for DrNED")
        self.cfg_file = os.path.join(self.drned_run_directory, self.dev_name + '.cfg')
        if self.overwrite or not os.path.exists(self.cfg_file):
            self.run_with_trans(self.format_device_cfg)
        ncs_target = os.path.join(self.drned_run_directory, 'drned-ncs')
        if self.overwrite or not os.path.exists(ncs_target):
            try:
                os.remove(ncs_target)
            except OSError:
                pass
            os.symlink(os.getcwd(), ncs_target)

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
