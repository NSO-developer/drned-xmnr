from __future__ import print_function

from .base_op import ActionBase
from .ex import ActionError


class LoadDefaultConfigOp(ActionBase):
    """ Action handler used to "reset" device configuration to a default by
        loading specified device CLI configuration file from the filesystem
        of a device.
    """
    action_name = 'xmnr load-default-config'

    def perform(self):
        try:
            self.devcli_run('load-default-config.py', [])
        except BaseException as e:
            self.log.debug("Exception: " + repr(e))
            raise ActionError('Failed to load default configuration!')

        return {'success': 'Loaded initial config.'}
