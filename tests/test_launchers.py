"""Approved launchers stay readable, visible in both modes, and revocable."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'kids'))
import native_runtime as runtime


class LauncherTests(unittest.TestCase):
    def test_add_and_remove_in_both_launcher_directories(self):
        with tempfile.TemporaryDirectory() as folder:
            overlay, system = Path(folder) / 'overlay', Path(folder) / 'system'
            with patch.object(runtime, 'APPS', overlay), patch.object(runtime, 'LAUNCHERS', system), \
                 patch.object(runtime, 'browser_policy'), patch.object(runtime.subprocess, 'run'):
                old = os.umask(0o077)
                try:
                    runtime.desktop_entries({'webapps': [{'id': 'github', 'name': 'GitHub',
                                                         'url': 'https://github.com'}]})
                finally:
                    os.umask(old)
                controlled = overlay / 'omarchy-kids-webapp-github.desktop'
                normal = system / 'webapp-github.desktop'
                self.assertEqual(controlled.read_text(), normal.read_text())
                self.assertIn('Name=GitHub\n', normal.read_text())
                self.assertIn('Exec=/usr/local/bin/omarchy-kids-webapp github\n', normal.read_text())
                self.assertEqual(normal.stat().st_mode & 0o777, 0o644)
                self.assertEqual(system.stat().st_mode & 0o777, 0o755)
                unrelated = system / 'other.desktop'
                unrelated.write_text('keep')
                runtime.desktop_entries({'webapps': []})
                self.assertFalse(normal.exists())
                self.assertFalse(controlled.exists())
                self.assertEqual(unrelated.read_text(), 'keep')

    def test_observers_only_see_complete_readable_entries(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'github.desktop'
            original = os.replace
            observed = []
            def observe(source, dest):
                self.assertFalse(target.exists())
                self.assertEqual(Path(source).stat().st_mode & 0o777, 0o644)
                self.assertEqual(Path(source).read_text(), 'complete entry\n')
                observed.append(True)
                original(source, dest)
            old = os.umask(0o077)
            try:
                with patch.object(runtime.os, 'replace', side_effect=observe):
                    runtime.publish_entry(target, 'complete entry\n')
            finally:
                os.umask(old)
            self.assertEqual(observed, [True])
            before = target.stat().st_ino
            runtime.publish_entry(target, 'complete entry\n')
            self.assertEqual(target.stat().st_ino, before)
            self.assertEqual(list(Path(folder).iterdir()), [target])

    def test_mountinfo_detects_same_filesystem_bind_and_escaped_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            info = Path(folder) / 'mountinfo'
            info.write_text('42 1 0:1 / / rw - ext4 /dev/vda rw\n'
                            '43 42 0:1 /source /home/child/apps rw - ext4 /dev/vda rw\n'
                            '44 42 0:1 /source /home/child/with\\040space rw - ext4 /dev/vda rw\n')
            with patch.object(runtime, 'MOUNTINFO', info):
                self.assertTrue(runtime.is_mountpoint('/home/child/apps'))
                self.assertTrue(runtime.is_mountpoint('/home/child/with space'))
                self.assertFalse(runtime.is_mountpoint('/home/child'))

    def test_remove_all_owned_layers_but_not_unrelated_mounts(self):
        import native_policy
        with patch.object(native_policy, 'is_mountpoint', side_effect=[True, True, True]), \
             patch.object(native_policy.os.path, 'samefile', side_effect=[True, True, False]), \
             patch.object(native_policy, 'command') as command:
            native_policy.remove_launcher_mounts('/home/child/apps')
            self.assertEqual(command.call_count, 2)
            self.assertEqual(command.call_args.args[0], ['/usr/bin/umount', '--lazy', '/home/child/apps'])
