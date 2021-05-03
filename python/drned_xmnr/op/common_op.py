from __future__ import print_function

from ncs import maagic

from .base_op import ActionBase
from .ex import ActionError


class LoadDefaultConfigOp(ActionBase):
    """ Action handler used to "reset" device configuration to a default by
        loading specified device CLI configuration file from the filesystem
        of a device.
    """
    action_name = 'xmnr load-default-config'

    def _init_params(self, params):
        super(LoadDefaultConfigOp, self)._init_params(params)
        self.device_timeout = params.device_timeout

    def perform(self):
        args = [
            'python', 'load-default-config.py',
            self.dev_name, self.driver_file, str(self.device_timeout)
        ]
        workdir = 'drned-ncs'

        try:
            self.run_in_drned_env(args, timeout=self.device_timeout,
                                  NC_WORKDIR=workdir)
        except BaseException as e:
            self.log.debug("Exception: " + repr(e))
            raise ActionError('Failed to load default configuration!')

        return {'success': 'Loaded initial config.'}
