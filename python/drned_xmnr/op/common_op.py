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

    def perform(self):
        args = [
            'python', 'load-default-config.py',
            self.dev_name, self.driver_name,
        ]
        workdir = 'drned-ncs' # TODO - make this global across XMNR actions!

        try:
            self.run_in_drned_env(args, NC_WORKDIR=workdir)
        except:
            raise ActionError('Failed to load default configuration!')

        return {"success": "Loaded initial config."}
