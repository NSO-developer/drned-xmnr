from __future__ import print_function

from .base_op import ActionBase
from .ex import ActionError


import re


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

    def __init__(self):
        self.waitstate = None
        self.devcli_error = None

    def match(self, msg):
        match = DevcliLogMatch.matchrx.match(msg)
        if match is None:
            return
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


class LoadDefaultConfigOp(ActionBase):
    """ Action handler used to "reset" device configuration to a default by
        loading specified device CLI configuration file from the filesystem
        of a device.
    """
    action_name = 'xmnr load-default-config'

    def __init__(self, *args):
        super(LoadDefaultConfigOp, self).__init__(*args)
        self.filter = DevcliLogMatch()

    def cli_filter(self, msg):
        report = self.filter.match(msg)
        if report is not None:
            super(LoadDefaultConfigOp, self).cli_filter(report + '\n')

    def perform(self):
        result, _ = self.devcli_run('load-default-config.py', [])
        if result != 0:
            raise ActionError('Failed to load default configuration!')

        if self.filter.devcli_error is None:
            return {'success': 'Loaded initial config.'}
        return {'failure': 'Device driver failed.'}


class SaveDefaultConfigOp(ActionBase):
    """ Action handler used to save/create default device configuration
        by saving running configuration to the filesystem of the device.
    """
    action_name = 'xmnr save-default-config'

    def __init__(self, *args):
        super(SaveDefaultConfigOp, self).__init__(*args)
        self.filter = DevcliLogMatch()

    def cli_filter(self, msg):
        report = self.filter.match(msg)
        if report is not None:
            super(SaveDefaultConfigOp, self).cli_filter(report + '\n')

    def perform(self):
        result, _ = self.devcli_run('save-default-config.py', [])
        if result != 0:
            self.log.debug("Exception: " + repr(e))
            raise ActionError('Failed to save default configuration!')

        if self.filter.devcli_error is None:
            return {'success': 'Saved initial config.'}
        return {'failure': 'Could not save config.'}
