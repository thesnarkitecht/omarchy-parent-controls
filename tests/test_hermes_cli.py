"""Sandbox policy, authority and persistent workspace regressions."""
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'kids'))
import coding
import hermes_cli as cli
import hermes_install
import native_policy


class HermesSandboxTests(unittest.TestCase):
    def argv(self, cwd='/workspace-source/story', extra=None):
        return cli.command(Path('/workspace-source'), Path('/agent-state'), cwd,
                           ['chat', 'literal; $(touch /tmp/escaped)'], extra or {})

    def test_only_explicit_filesystems_and_no_admin_or_desktop_sockets(self):
        argv = self.argv()
        binds = [(argv[i + 1], argv[i + 2]) for i, arg in enumerate(argv) if arg in ('--bind', '--ro-bind')]
        self.assertEqual([v for i, v in enumerate(binds) if v[0] in ('/workspace-source', '/agent-state')],
                         [('/agent-state', '/home/agent/.hermes'), ('/workspace-source', '/workspace')])
        self.assertNotIn(('/etc', '/etc'), binds)
        for source, target in binds:
            self.assertFalse(source.startswith(('/run/', '/home/', '/var/lib/omarchy-kids-control')))
        self.assertIn('--clearenv', argv)
        for flag in ('--unshare-user', '--unshare-pid', '--unshare-ipc', '--unshare-uts',
                     '--disable-userns', '--new-session', '--die-with-parent'):
            self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index('--cap-drop') + 1], 'ALL')

    def test_environment_drops_session_and_injection_settings(self):
        hostile = {name: 'sentinel-' + name for name in ('LD_PRELOAD', 'PYTHONPATH', 'BASH_ENV',
                    'DBUS_SESSION_BUS_ADDRESS', 'WAYLAND_DISPLAY', 'SSH_AUTH_SOCK', 'PARENT_TOKEN',
                    'HTTP_PROXY', 'HERMES_RUNTIME_DIR', 'HOME')}
        argv = self.argv(extra={**hostile, 'OPENAI_API_KEY': 'provider-test-key'})
        for value in hostile.values():
            self.assertNotIn(value, argv)
        self.assertIn('provider-test-key', argv)

    def test_paths_and_arguments_are_not_shell_interpolated(self):
        argv = self.argv()
        self.assertEqual(argv[argv.index('--chdir') + 1], '/workspace/story')
        self.assertEqual(argv[-2:], ['chat', 'literal; $(touch /tmp/escaped)'])
        outside = self.argv(cwd='/etc')
        self.assertEqual(outside[outside.index('--chdir') + 1], '/workspace')

    def test_children_keep_terminal_network_and_runtime_commands(self):
        self.assertNotIn('--unshare-net', self.argv())
        with patch.object(native_policy.Path, 'exists', return_value=False):
            self.assertFalse(native_policy.denied_commands() & {'npm', 'uv', 'pip', 'mise', 'yarn'})
        self.assertIn('run hermes_cli "$@"', hermes_install.launch_text())
        self.assertNotIn('/source/.hermes/bin/hermes', hermes_install.launch_text())

    def test_root_and_other_accounts_cannot_launch_agent(self):
        for uid in (0, 1001):
            with patch('native_runtime.account', return_value={'uid': 1000}), \
                 patch.object(cli.os, 'getuid', return_value=uid), \
                 patch.object(cli.os, 'geteuid', return_value=uid), patch.object(cli.os, 'execve') as execute:
                self.assertEqual(cli.main(), 1)
                execute.assert_not_called()

    def test_missing_sandbox_never_falls_back(self):
        with patch('native_runtime.account', return_value={'uid': 1000}), \
             patch.object(cli.os, 'getuid', return_value=1000), \
             patch.object(cli.os, 'geteuid', return_value=1000), \
             patch.object(cli.Path, 'is_file', return_value=False), patch.object(cli.os, 'execve') as execute:
            self.assertEqual(cli.main(), 1)
            execute.assert_not_called()

    def test_storage_rejects_symlinks_and_shared_or_foreign_directories(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(coding, 'trusted_parent'):
            base = Path(folder); userdir = base / str(os.getuid())
            userdir.mkdir(mode=0o700)
            self.assertEqual(coding.checked_storage(base, os.getuid()), userdir)
            userdir.chmod(0o755)
            with self.assertRaises(ValueError): coding.checked_storage(base, os.getuid())
            userdir.rmdir(); userdir.symlink_to(base)
            with self.assertRaises(ValueError): coding.checked_storage(base, os.getuid())

    def test_untrusted_parent_cannot_be_adopted(self):
        for uid, mode in ((1000, stat.S_IFDIR | 0o755), (0, stat.S_IFDIR | 0o777), (0, stat.S_IFLNK | 0o755)):
            with patch.object(coding.Path, 'lstat', return_value=SimpleNamespace(st_uid=uid, st_mode=mode)):
                with self.assertRaises(ValueError): coding.trusted_parent(Path('/var/lib/coding'))


if __name__ == '__main__':
    unittest.main()
