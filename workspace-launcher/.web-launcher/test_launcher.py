"""Read-only identity checks and safe reuse of running services."""
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.error

spec = importlib.util.spec_from_file_location('workspace_launcher', Path(__file__).with_name('launch_workspace.py'))
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    def root_response(self, title='DevPulse Portfolio'):
        return io.BytesIO(f'<html><title>{title}</title></html>'.encode())

    def denied(self, payload=b'{"error":"unauthenticated"}'):
        return urllib.error.HTTPError('http://127.0.0.1:3100/api/owner/check', 401, 'Unauthorized', {}, io.BytesIO(payload))

    def test_identifies_devpulse_with_protected_api(self):
        with patch.object(launcher.OPENER, 'open', side_effect=[self.root_response(), self.denied()]):
            self.assertEqual(launcher.devpulse_status('http://127.0.0.1:3100/', 3100), 'online')

    def test_unrelated_web_server_is_conflict(self):
        with patch.object(launcher.OPENER, 'open', return_value=self.root_response('Other app')):
            self.assertEqual(launcher.devpulse_status('http://127.0.0.1:3100/', 3100), 'conflict')

    def test_malformed_identity_is_conflict(self):
        with patch.object(launcher.OPENER, 'open', side_effect=[self.root_response(), self.denied(b'[]')]):
            self.assertEqual(launcher.devpulse_status('http://127.0.0.1:3100/', 3100), 'conflict')

    def test_unresponsive_listener_is_not_replaced(self):
        with patch.object(launcher.OPENER, 'open', side_effect=OSError('unhealthy')), patch.object(launcher, 'occupied', return_value=True):
            self.assertEqual(launcher.devpulse_status('http://127.0.0.1:3100/', 3100), 'conflict')

    def test_unused_port_is_offline(self):
        with patch.object(launcher.OPENER, 'open', side_effect=OSError('refused')), patch.object(launcher, 'occupied', return_value=False):
            self.assertEqual(launcher.devpulse_status('http://127.0.0.1:3100/', 3100), 'offline')

    def test_online_service_is_reused(self):
        with patch.object(launcher, 'devpulse_status', return_value='online'), patch.object(launcher.subprocess, 'Popen') as spawn:
            launcher.start_devpulse('http://127.0.0.1:3100/', 3100)
            spawn.assert_not_called()

    def test_conflict_never_starts_process(self):
        with patch.object(launcher, 'devpulse_status', return_value='conflict'), patch.object(launcher.subprocess, 'Popen') as spawn:
            with self.assertRaises(RuntimeError):
                launcher.start_devpulse('http://127.0.0.1:3100/', 3100)
            spawn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
