import json
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'kids'))
import hosts_policy
import native_policy
import managed_hermes

class Guards(unittest.TestCase):
    def test_busy_bind_restores_flags_without_hiding_nested_mounts(self):
        with patch.object(native_policy,'is_mountpoint',return_value=True),patch.object(native_policy,'command') as command,patch.object(native_policy.subprocess,'run',return_value=SimpleNamespace(returncode=32)):
            self.assertFalse(native_policy.release_mount('/home/child',['exec','nosuid','dev']))
            command.assert_called_once_with(['/usr/bin/mount','-o','remount,bind,exec,nosuid,dev','/home/child'])

    def test_hosts_file_takes_priority_and_removal_restores_nss_rule(self):
        with tempfile.TemporaryDirectory() as folder:
            nss=Path(folder)/'nsswitch.conf';backup=Path(folder)/'backup.json'
            original='passwd: files systemd\nhosts: mymachines resolve [!UNAVAIL=return] files myhostname dns\n'
            nss.write_text(original)
            with patch.object(hosts_policy,'NSS',nss),patch.object(hosts_policy,'NSS_BACKUP',backup):
                hosts_policy.configure_nss(True)
                self.assertIn('hosts: files mymachines resolve [!UNAVAIL=return] myhostname dns\n',nss.read_text())
                hosts_policy.configure_nss(True)
                hosts_policy.configure_nss(False)
                self.assertEqual(nss.read_text(),original)
                self.assertFalse(backup.exists())

    def test_nss_restore_preserves_later_administrator_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            nss=Path(folder)/'nsswitch.conf';backup=Path(folder)/'backup.json'
            nss.write_text('hosts: resolve files dns\n')
            with patch.object(hosts_policy,'NSS',nss),patch.object(hosts_policy,'NSS_BACKUP',backup):
                hosts_policy.configure_nss(True)
                nss.write_text('hosts: files myhostname dns\n')
                hosts_policy.configure_nss(False)
                self.assertEqual(nss.read_text(),'hosts: files myhostname dns\n')

    def test_mode_on_waits_for_resolver_to_observe_updated_hosts(self):
        stale=[(0,0,0,'',('1.2.3.4',443))]
        blocked=[(0,0,0,'',('0.0.0.0',443))]
        with patch.object(hosts_policy.socket,'getaddrinfo',side_effect=[stale,blocked]),patch.object(hosts_policy.time,'sleep') as sleep:
            hosts_policy.wait_until_applied()
            sleep.assert_called_once()
        with patch.object(hosts_policy.socket,'getaddrinfo',return_value=stale):
            with self.assertRaises(RuntimeError): hosts_policy.wait_until_applied(timeout=0)

    def test_previous_boot_mounts_are_never_unmounted(self):
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder)
            (state/'native-mounts.json').write_text('["/run/user/1000"]')
            (state/'native-mounts-boot-id').write_text('previous-boot')
            boot=state/'current-boot';boot.write_text('current-boot')
            with patch.object(native_policy,'STATE',state),patch.object(native_policy,'BOOT_ID',boot):
                self.assertEqual(native_policy.tracked_mounts(),[])
                (state/'native-mounts-boot-id').write_text('current-boot')
                self.assertEqual(native_policy.tracked_mounts(),['/run/user/1000'])

    def test_hosts_changes_are_idempotent_and_reversible(self):
        original = '127.0.0.1 localhost\n192.168.1.2 family-printer\n'
        enabled = hosts_policy.render(original, True)
        self.assertIn('0.0.0.0 brave.com\n', enabled)
        self.assertIn(':: brave.com\n', enabled)
        self.assertNotIn('0.0.0.0 github.com', enabled)
        self.assertEqual(hosts_policy.render(enabled, True), enabled)
        self.assertEqual(hosts_policy.render(enabled, False), original)

    def test_edits_outside_our_hosts_block_survive(self):
        enabled = hosts_policy.render('127.0.0.1 localhost\n', True)
        modified = enabled + '192.168.1.3 printer\n'
        self.assertIn('192.168.1.3 printer\n', hosts_policy.render(modified, False))

    def test_model_egress_is_specific_and_validated(self):
        value = native_policy.model_rule({'model_endpoint':{'host':'10.0.2.2','port':11434}}, 963)
        self.assertEqual(value, '  meta skuid 963 ip daddr 10.0.2.2 tcp dport 11434 accept\n')
        self.assertEqual(native_policy.model_rule({},963), '')
        for host,port in [('1.2.3.4; accept',80),('1.2.3.4',True),('1.2.3.4',65536)]:
            with self.assertRaises(ValueError):
                native_policy.model_rule({'model_endpoint':{'host':host,'port':port}},963)

    def test_managed_agent_rejects_other_accounts_before_launch(self):
        with patch.object(managed_hermes, 'account', return_value={'uid':1000}), \
             patch.object(managed_hermes.subprocess, 'run') as run:
            with self.assertRaises(ValueError):
                managed_hermes.launch(1001)
            run.assert_not_called()

    def test_runtime_tools_are_allowed_on_fresh_and_upgraded_installs(self):
        self.assertFalse(native_policy.RUNTIME_COMMANDS.intersection(native_policy.BANNED))
        # A stored beta.3 list must not keep old restrictions alive on upgrade.
        with patch.object(native_policy.Path,'exists',return_value=True), \
             patch.object(native_policy.Path,'read_text',return_value=json.dumps(
                 [*native_policy.RUNTIME_COMMANDS,'chromium','brave','pacman','custom-denied'])):
            denied=native_policy.denied_commands()
            self.assertEqual(denied,{'chromium','brave','pacman','custom-denied'})

    def test_invalid_saved_denylist_still_fails_closed(self):
        for value in [['mise','../chromium'],['uv',42],{'uv':True}]:
            with patch.object(native_policy.Path,'exists',return_value=True), \
                 patch.object(native_policy.Path,'read_text',return_value=json.dumps(value)):
                with self.assertRaises(ValueError):native_policy.denied_commands()

    def test_policy_refresh_restores_previous_denials_before_applying_current_rules(self):
        # The first part of apply must restore old ACLs even if no runtime tool
        # remains in the new denylist. Otherwise permitting mise has no effect.
        events=[]
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder);(state/'native-acls.txt').write_text('saved ACL')
            with patch.object(native_policy,'STATE',state), \
                 patch.object(native_policy,'account',return_value={'uid':1000,'user':'child'}), \
                 patch.object(native_policy.pwd,'getpwnam',return_value=SimpleNamespace(pw_dir='/home/child')), \
                 patch.object(native_policy,'targets',return_value=[Path('/usr/bin/chromium')]), \
                 patch.object(native_policy,'restore_acls',side_effect=lambda p:events.append('restore')), \
                 patch.object(native_policy,'command',side_effect=RuntimeError('stop before mutations')):
                with self.assertRaisesRegex(RuntimeError,'stop before mutations'):native_policy.apply()
                self.assertEqual(events,['restore'])
