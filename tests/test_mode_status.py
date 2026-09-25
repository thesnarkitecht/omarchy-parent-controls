"""A failed stop must not be reported as an unrestricted desktop."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'kids'))
import bridge
import native_mode
import native_policy
import native_runtime


class ModeStatusTests(unittest.TestCase):
    def test_failed_service_with_enabled_marker_is_not_reported_off(self):
        with patch.object(bridge, 'request', return_value={'ok':True,'policy':{}}), \
             patch.object(native_runtime, 'configured', return_value=True), \
             patch.object(bridge.Path, 'exists', return_value=True), \
             patch.object(bridge.subprocess, 'run', return_value=SimpleNamespace(returncode=3)):
            value=bridge.status()
            self.assertTrue(value['active'])
            self.assertFalse(value['healthy'])

    def test_off_without_service_is_normal(self):
        with patch.object(bridge, 'request', return_value={'ok':True,'policy':{}}), \
             patch.object(native_runtime, 'configured', return_value=True), \
             patch.object(bridge.Path, 'exists', return_value=False), \
             patch.object(bridge.subprocess, 'run', return_value=SimpleNamespace(returncode=3)):
            value=bridge.status()
            self.assertFalse(value['active'])
            self.assertTrue(value['healthy'])

    def test_cleanup_retries_even_after_failed_stop_job(self):
        events=[]
        with patch.object(native_mode.subprocess, 'run', side_effect=lambda *a,**k: events.append('stop')), \
             patch.object(native_policy, 'remove', side_effect=lambda: events.append('cleanup')), \
             patch.object(native_mode, 'run', side_effect=lambda *a: events.append('reset')):
            native_mode.disable_policy()
        self.assertEqual(events,['stop','cleanup','reset'])

    def test_cleanup_error_is_not_hidden(self):
        with patch.object(native_mode.subprocess, 'run'), \
             patch.object(native_policy, 'remove', side_effect=RuntimeError('Restore failed')), \
             patch.object(native_mode, 'run') as reset:
            with self.assertRaisesRegex(RuntimeError,'Restore failed'):
                native_mode.disable_policy()
            reset.assert_not_called()
