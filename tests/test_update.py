import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'kids'))
import update


class UpdateTests(unittest.TestCase):
    def setUp(self):
        stage = patch.object(update, 'STAGING', tempfile.gettempdir())
        stage.start()
        self.addCleanup(stage.stop)

    def archive(self, path, entries):
        with tarfile.open(path, 'w:gz') as bundle:
            for name, kind, content in entries:
                item = tarfile.TarInfo(name)
                item.type = kind
                data = content.encode()
                item.size = len(data) if kind == tarfile.REGTYPE else 0
                item.linkname = '/etc/passwd' if kind == tarfile.SYMTYPE else ''
                bundle.addfile(item, io.BytesIO(data) if item.isfile() else None)

    def test_versions_use_numeric_order_and_stable_supersedes_preview(self):
        values = ['0.5.0', '0.5.0-beta.1', '0.5.0-alpha.10', '0.5.0-alpha.4', '0.4.0', '0.5.0-rc.1']
        self.assertEqual(sorted(values, key=update.version_key),
                         ['0.4.0', '0.5.0-alpha.4', '0.5.0-alpha.10', '0.5.0-beta.1', '0.5.0-rc.1', '0.5.0'])
        for invalid in ['../0.5.0', '0.5.0;id', '0.5.0-alpha.1\n']:
            with self.assertRaises(ValueError):
                update.version_key(invalid)

    def test_release_selection_ignores_drafts_and_respects_channel(self):
        records = [{'tag_name':'v0.5.0-alpha.9','prerelease':True},
                   {'tag_name':'v0.5.0-alpha.10','prerelease':True},
                   {'tag_name':'v0.4.0','prerelease':False},
                   {'tag_name':'v1.0.0','draft':True}, {'tag_name':'../../escape'}]
        def fetch(url, path, limit):
            path.write_text(json.dumps(records))
        with tempfile.TemporaryDirectory() as folder, patch.object(update, 'download', side_effect=fetch):
            self.assertEqual(update.latest('0.5.0-alpha.4', Path(folder)), '0.5.0-alpha.10')
            self.assertEqual(update.latest('0.4.0', Path(folder)), '0.4.0')

    def test_archive_rejects_traversal_links_duplicates_and_special_files(self):
        bad = [('../outside', tarfile.REGTYPE, ''),
               ('/etc/passwd', tarfile.REGTYPE, ''),
               ('omarchy-parent-controls/../../outside', tarfile.REGTYPE, ''),
               ('omarchy-parent-controls/link', tarfile.SYMTYPE, ''),
               ('omarchy-parent-controls/link', tarfile.LNKTYPE, ''),
               ('omarchy-parent-controls/pipe', tarfile.FIFOTYPE, '')]
        good = ('omarchy-parent-controls/manifest.json', tarfile.REGTYPE, '{}')
        for entries in [[good, item] for item in bad] + [[good, good]]:
            with self.subTest(entries=entries), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                self.archive(root/'release.tar.gz', entries)
                with self.assertRaises(ValueError):
                    update.unpack(root/'release.tar.gz', root/'source')
                self.assertFalse((root/'source').exists())

    def test_valid_bundle_extracts_and_checks_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            version = '0.5.0-alpha.5'
            self.archive(root/'fixture.tar.gz', [
                ('omarchy-parent-controls/manifest.json', tarfile.REGTYPE,
                 json.dumps({'version':version, 'id':'thesnarkitecht.kids-lockdown'})),
                ('omarchy-parent-controls/packaging/setup.py', tarfile.REGTYPE, '# installer')])
            data = (root/'fixture.tar.gz').read_bytes()
            def fetch(url, path, limit=update.MAX_ARCHIVE):
                if url.endswith('release.json'):
                    path.write_text(json.dumps({'repository':update.REPOSITORY, 'version':version,
                        'archive':'omarchy-parent-controls-'+version+'.tar.gz',
                        'sha256':hashlib.sha256(data).hexdigest()}))
                else:
                    path.write_bytes(data)
            with patch.object(update, 'download', side_effect=fetch):
                source = update.verified_source(version, root)
            self.assertEqual((source/'packaging/setup.py').read_text(), '# installer')

    def test_bad_digest_never_extracts_or_runs_installer(self):
        def fetch(url, path, limit=update.MAX_ARCHIVE):
            if url.endswith('release.json'):
                path.write_text(json.dumps({'repository':update.REPOSITORY, 'version':'0.5.0',
                    'archive':'omarchy-parent-controls-0.5.0.tar.gz','sha256':'0'*64}))
            else:
                path.write_bytes(b'tampered')
        with tempfile.TemporaryDirectory() as folder, patch.object(update, 'download', side_effect=fetch), \
                patch.object(update, 'unpack') as unpack, patch.object(update.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'checksum'):
                update.verified_source('0.5.0', Path(folder))
            unpack.assert_not_called()
            run.assert_not_called()

    def test_metadata_cannot_redirect_download_to_another_repository(self):
        def fetch(url, path, limit):
            path.write_text(json.dumps({'repository':'evil/repo', 'version':'0.5.0',
                'archive':'https://evil.invalid/payload','sha256':'0'*64}))
        with tempfile.TemporaryDirectory() as folder, patch.object(update, 'download', side_effect=fetch) as download:
            with self.assertRaisesRegex(ValueError, 'metadata'):
                update.verified_source('0.5.0', Path(folder))
            self.assertEqual(download.call_count, 1)

    def test_download_ignores_user_curl_config_and_environment(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(update.subprocess, 'run') as run:
            destination = Path(folder)/'archive'
            destination.write_bytes(b'ok')
            update.download('https://github.com/example', destination)
            command = run.call_args.args[0]
            self.assertEqual(command[:2], ['/usr/bin/curl', '-q'])
            self.assertIn('--proto-redir', command)
            self.assertEqual(run.call_args.kwargs['env']['HOME'], '/root')
            self.assertNotIn('CURL_CA_BUNDLE', run.call_args.kwargs['env'])
            self.assertTrue(run.call_args.kwargs['check'])

    def test_check_and_same_or_older_release_never_install(self):
        with patch.object(update, 'installed', return_value='0.5.0-alpha.5'), \
                patch.object(update, 'latest') as latest, patch.object(update, 'verified_source') as source, \
                patch.object(update, 'backup_settings') as backup:
            for version in ('0.5.0-alpha.4', '0.5.0-alpha.5'):
                latest.return_value = version
                update.upgrade()
            latest.return_value = '0.5.0-alpha.6'
            update.upgrade(check=True)
            source.assert_not_called()
            backup.assert_not_called()

    def test_upgrade_uses_saved_child_account_and_preserves_apps(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'account.json').write_text(json.dumps({'user':'student'}))
            with patch.object(update, 'ETC', root), patch.object(update, 'installed', return_value='0.5.0-alpha.4'), \
                    patch.object(update, 'latest', return_value='0.5.0-alpha.5'), \
                    patch.object(update, 'verified_source', return_value=root/'source'), \
                    patch.object(update, 'backup_settings', return_value='/private/backup.tar.gz') as backup, \
                    patch.object(update.subprocess, 'run') as run:
                update.upgrade()
                backup.assert_called_once()
                self.assertEqual(run.call_args.args[0], ['/usr/bin/python3', '-I',
                    str(root/'source/packaging/setup.py'), '--user', 'student', '--skip-apps'])

    def test_failed_install_reports_backup_and_does_not_claim_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'account.json').write_text('{"user":"student"}')
            with patch.object(update, 'ETC', root), patch.object(update, 'installed', return_value='0.4.0'), \
                    patch.object(update, 'latest', return_value='0.5.0'), \
                    patch.object(update, 'verified_source', return_value=root), \
                    patch.object(update, 'backup_settings', return_value='/private/saved.tar.gz'), \
                    patch.object(update.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, ['setup'])):
                with self.assertRaisesRegex(ValueError, '/private/saved.tar.gz'):
                    update.upgrade()

    def test_child_update_and_restart_reenter_only_fixed_root_command(self):
        for action in ('update', 'restart'):
            with self.subTest(action=action), patch.object(sys, 'argv', ['cli', action]), \
                    patch.object(update.os, 'geteuid', return_value=1000), \
                    patch.object(update.os, 'execv', side_effect=SystemExit) as execute:
                with self.assertRaises(SystemExit):
                    update.main()
                execute.assert_called_once_with('/usr/bin/sudo',
                    ['sudo', '--', '/usr/local/bin/omarchy-parent-controls', action])

    def test_read_only_check_does_not_request_sudo(self):
        with patch.object(sys, 'argv', ['cli','update','--check']), \
                patch.object(update.os, 'geteuid', return_value=1000), \
                patch.object(update.os, 'execv') as execute, patch.object(update, 'upgrade') as upgrade:
            self.assertEqual(update.main(), 0)
            execute.assert_not_called()
            upgrade.assert_called_once_with(check=True)
