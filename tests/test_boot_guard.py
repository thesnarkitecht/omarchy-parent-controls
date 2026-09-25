"""Do not start a controlled session before its launcher restrictions exist."""
from pathlib import Path
from types import SimpleNamespace
import sys
import subprocess
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'kids'))
import boot_guard

class BootGuardTests(unittest.TestCase):
    def test_off_mode_needs_no_policy_or_mount(self):
        with patch.object(boot_guard.Path, 'exists', return_value=False), \
             patch.object(boot_guard.subprocess, 'run') as run:
            boot_guard.main()
            run.assert_not_called()

    def test_active_service_without_correct_mount_is_not_enough(self):
        with patch.object(boot_guard.Path, 'exists', return_value=True), \
             patch.object(boot_guard.subprocess, 'run'), \
             patch.object(boot_guard, 'account', return_value={'user':'child'}), \
             patch.object(boot_guard.pwd, 'getpwnam', return_value=SimpleNamespace(pw_dir='/home/child')):
            for mounted, correct in [(False,False), (True,False)]:
                with patch.object(boot_guard, 'is_mountpoint', return_value=mounted), \
                     patch.object(boot_guard.os.path, 'samefile', return_value=correct):
                    with self.assertRaisesRegex(RuntimeError,'Controlled launcher'):
                        boot_guard.main()
            with patch.object(boot_guard, 'is_mountpoint', return_value=True), \
                 patch.object(boot_guard.os.path, 'samefile', return_value=True):
                boot_guard.main()

    def test_failed_policy_blocks_session(self):
        with patch.object(boot_guard.Path, 'exists', return_value=True), \
             patch.object(boot_guard.subprocess, 'run', side_effect=subprocess.CalledProcessError(3,'systemctl')):
            with self.assertRaises(subprocess.CalledProcessError):
                boot_guard.main()
