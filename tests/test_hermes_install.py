"""Regression coverage for an official runtime outside the noexec user home."""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'kids'))
import hermes_install as hermes
import parent_tools

class HermesInstallationTests(unittest.TestCase):
    def test_regular_user_cannot_install(self):
        with patch.object(hermes.os,'geteuid',return_value=1000), patch.object(hermes,'install_runtime') as install:
            with self.assertRaisesRegex(ValueError,'parent PIN'):hermes.ensure(None)
            install.assert_not_called()

    def test_checksum_mismatch_never_executes_download(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve()
            (root/'official-install.sh').write_text('untrusted')
            with patch.object(hermes,'ROOT',root), patch.object(hermes,'trusted_tree'), patch.object(hermes,'run') as run:
                with self.assertRaisesRegex(ValueError,'checksum'):hermes.install_runtime()
                self.assertEqual(run.call_count,1)
                self.assertEqual(run.call_args.args[0],'/usr/bin/curl')

    def test_installer_is_pinned_skips_browser_and_separates_user_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();key=hashlib.sha256(str(root/'source').encode()).hexdigest()[:16]
            venv=root/'data/installs'/key/'environments/generation';venv.mkdir(parents=True)
            (venv.parent.parent/'facts.json').write_text(json.dumps({'packages':{'venv':{'environment':str(venv)}}}))
            (root/'official-install.sh').write_text('verified')
            with patch.object(hermes,'ROOT',root), patch.object(hermes,'trusted_tree'), \
                 patch.object(hermes,'INSTALLER_SHA256',hashlib.sha256(b'verified').hexdigest()), \
                 patch.object(hermes,'run') as run:
                hermes.install_runtime()
                command=run.call_args.args
                self.assertIn('--skip-browser',command)
                self.assertIn('--non-interactive',command)
                self.assertIn(hermes.COMMIT,command)
                self.assertEqual(run.call_args.kwargs['env']['HERMES_HOME'],str(root/'data'))
                manifest=json.loads((root/'manifest.json').read_text())
                self.assertEqual((root/manifest['venv']).resolve(),venv.resolve())
                self.assertNotIn('HERMES_HOME=',hermes.launch_text())
                # Repeated updates reuse the verified runtime instead of downloading again.
                run.reset_mock();hermes.install_runtime();run.assert_not_called()

    def test_publish_preserves_previous_command_and_uses_user_for_home_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();command=root/'hermes';command.write_text('old launcher')
            user=SimpleNamespace(pw_name='child',pw_dir='/home/child')
            with patch.object(hermes,'ROOT',root),patch.object(hermes,'COMMAND',command),patch.object(hermes,'run') as run:
                hermes.publish(user)
                self.assertEqual((root/'previous-system-command').read_text(),'old launcher')
                self.assertIn(hermes.MARKER,command.read_text())
                self.assertEqual(command.stat().st_mode & 0o777,0o755)
                self.assertEqual(run.call_args.args[:4],('/usr/bin/runuser','-u','child','--'))
                hermes.publish(user)
                self.assertEqual((root/'previous-system-command').read_text(),'old launcher')

    def test_only_selected_hermes_triggers_installation(self):
        user=SimpleNamespace(pw_name='child',pw_dir='/home/child')
        for name,expected in [('hermes',True),('claude',False),('',False)]:
            with patch.object(hermes.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=name)):
                self.assertEqual(hermes.selected(user),expected)

    def test_repair_uses_fixed_privileged_command(self):
        with patch.object(parent_tools.Path,'exists',return_value=False),patch.object(parent_tools.subprocess,'Popen') as start:
            parent_tools.launch('hermes-repair')
            self.assertEqual(start.call_args.args[0][-1],
                '/usr/bin/sudo /usr/bin/python3 -I /usr/local/lib/omarchy-kids/hermes_install.py')
        with patch.object(parent_tools.Path,'exists',return_value=True):
            with self.assertRaises(ValueError):parent_tools.launch('hermes-repair')
