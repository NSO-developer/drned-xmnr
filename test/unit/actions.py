from .mocklib import mock, system_mock, ncs_mock, open_mock, xtest_patch
from drned_xmnr import action


device_data = '''
    <config xmlns="http://tail-f.com/ns/config/1.0">
      <devices xmlns="http://tail-f.com/ns/ncs">
        <device>
          <name>mock-device</name>
          <address>127.0.0.1</address>
          <port>2022</port>
          <ssh/>
          <connect-timeout/>
          <read-timeout/>
          <trace/>
          <config/>
        </device>
      </devices>
    </config>
'''


class TestBase(object):
    def test_registry(self):
        xmnr = action.Xmnr()
        xmnr.setup()
        xmnr.register_action.assert_called_once_with('drned-xmnr', action.ActionHandler)
        xmnr.register_service.assert_called_once_with('coverage-data', action.XmnrDataHandler)

    @xtest_patch(system_mock, ncs_mock, open_mock('setup_op'))
    def test_setup(self, xpatch):
        ah = action.ActionHandler()
        ah.log = mock.Mock()
        import functools
        ah.log.debug = functools.partial(print, file=open('/tmp/unit.log', 'w'))
        output = mock.Mock(error=None, failure=None)
        kp = [['mock-device'], None, None]
        params = mock.Mock(overwrite=True)
        xpatch.system.socket_data(device_data)
        ah.cb_action(mock.Mock(), 'setup-xmnr', kp, params, output)
        print('tree', xpatch.system.tree)
        assert output.error is None
        assert output.failure is None
