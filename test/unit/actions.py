from .mocklib import mock, system_mock, ncs_mock, xtest_patch
from drned_xmnr import action


class TestBase(object):
    def test_registry(self):
        xmnr = action.Xmnr()
        xmnr.setup()
        xmnr.register_action.assert_called_once_with('drned-xmnr', action.ActionHandler)
        xmnr.register_service.assert_called_once_with('coverage-data', action.XmnrDataHandler)

    @xtest_patch(system_mock, ncs_mock)
    def test_setup(self, xpatch):
        ah = action.ActionHandler()
        ah.log = mock.Mock()
        # ah.log.debug = print
        output = mock.Mock()
        kp = [['mock-device'], None, None]
        params = mock.Mock(overwrite=True)
        ah.cb_action(mock.Mock(), 'setup-xmnr', kp, params, output)
        print('result:', output.error, output.failure)
        print('create:', xpatch.system.patches['os']['makedirs'].call_args_list)
