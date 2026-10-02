import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'kids'))
import activity
import access_control
from control import Store, peer_action
import family


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.meter=activity.Meter(self.root)
        self.wall=dt.datetime(2026,10,2,12).timestamp()

    def test_only_contiguous_unlocked_active_intervals_count(self):
        for on,mono in [(True,0),(True,15),(False,30),(True,45),(True,60)]:
            self.meter.sample(on,mono,self.wall+mono)
        self.assertEqual(activity.read(self.root)['days']['2026-10-02'],30)

    def test_sleep_gaps_clock_changes_and_restart_do_not_add_time(self):
        self.meter.sample(True,0,self.wall)
        self.meter.sample(True,600,self.wall+600)
        self.meter.sample(True,615,self.wall+7200)
        activity.Meter(self.root).sample(True,630,self.wall+7215)
        self.assertEqual(activity.read(self.root)['days'],{})

    def test_midnight_is_split_and_last_week_includes_empty_days(self):
        midnight=dt.datetime(2026,10,3).timestamp()
        self.meter.sample(True,0,midnight-5)
        self.meter.sample(True,15,midnight+10)
        report=activity.summary(self.root,today=dt.date(2026,10,3))
        self.assertEqual(report['today_seconds'],10)
        self.assertEqual(report['week_seconds'],15)
        self.assertEqual(len(report['days']),7)
        self.assertEqual(report['days'][-2]['seconds'],5)

    def test_unknown_locked_idle_and_tty_sessions_do_not_count(self):
        base={'User':'1000','Type':'wayland','Active':'yes','LockedHint':'no','IdleHint':'no'}
        for change,expected in [({},True),({'Type':'tty'},False),({'Active':'no'},False),({'LockedHint':'yes'},False),({'IdleHint':'yes'},False),({'LockedHint':''},False)]:
            with patch.object(activity,'sessions',return_value=[('2',{**base,**change})]):
                self.assertEqual(activity.active(1000),expected)


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.statepatch=patch.object(access_control,'STATE',self.root);self.statepatch.start();self.addCleanup(self.statepatch.stop)
        self.store=Store(self.root,clock=lambda:1000);self.store.initialize('13579246')

    def test_children_cannot_pause_or_resume_without_pin_or_phone_token(self):
        with patch.object(access_control,'change') as change:
            for paused in (True,False):
                with self.assertRaises(ValueError):
                    peer_action(self.store,{'action':'access-admin','paused':paused},1000)
                with self.assertRaises(ValueError):
                    self.store.dispatch({'action':'family-change','operation':'set-paused','fields':{'paused':paused}})
            change.assert_not_called()

    def test_paired_phone_can_pause_and_resume_but_cannot_disable_controls(self):
        paired=family.enroll(self.store,'https://school.parents.example.org','Laptop')
        def envelope(operation,fields):
            return {'token':paired['token'],'id':__import__('secrets').token_hex(16),'issued':1000,'operation':operation,'fields':fields}
        with patch.object(access_control,'change') as change:
            family.remote(self.store,envelope('set-paused',{'paused':True}))
            family.remote(self.store,envelope('set-paused',{'paused':False}))
            self.assertEqual([c.args for c in change.call_args_list],[(True,),(False,)])
            for fields in ({'paused':'false'},{'paused':False,'command':'sh'}):
                with self.assertRaises(ValueError): family.remote(self.store,envelope('set-paused',fields))
            with self.assertRaises(ValueError): family.remote(self.store,envelope('disable-controls',{}))

    def test_failed_enforcement_is_not_reported_as_applied(self):
        (self.root/'access.json').write_text('{"paused":true}')
        self.assertEqual(access_control.status(),{'paused':True,'enforced':False,'error':None})
        (self.root/'access-applied.json').write_text('{"paused":true,"error":"failed"}')
        self.assertFalse(access_control.status()['enforced'])

    def test_pause_intent_is_persisted_before_enforcement_and_survives_failure(self):
        import subprocess
        with patch.object(access_control.subprocess,'run',side_effect=subprocess.CalledProcessError(1,['systemctl'])):
            with self.assertRaises(subprocess.CalledProcessError): access_control.change(True)
        self.assertTrue(access_control.desired())

    def test_pam_account_gate_only_blocks_controlled_child(self):
        (self.root/'account.json').write_text('{"user":"student"}')
        (self.root/'access.json').write_text('{"paused":true}')
        with patch.object(access_control,'ETC',self.root):
            for user,expected in [('student',1),('parent',0),('root',0)]:
                with patch.dict('os.environ',{'PAM_USER':user,'PAM_TYPE':'account'}):
                    self.assertEqual(access_control.pam(),expected)
            (self.root/'access.json').write_text('{"paused":false}')
            with patch.dict('os.environ',{'PAM_USER':'student','PAM_TYPE':'account'}):
                self.assertEqual(access_control.pam(),0)


class PairingTests(unittest.TestCase):
    def test_tunnel_and_existing_private_origins_are_supported(self):
        for endpoint in ('https://school.parents.example.org','https://device.ngrok-free.app','https://school.example.ts.net'):
            self.assertEqual(family.parent_origin(endpoint),endpoint)
        for endpoint in ('http://school.example.org','https://u:p@school.example.org','https://school.example.org/path','https://school.example.org?x=y','https://127.0.0.1','https://school.local','https://school.example.org:8443'):
            with self.assertRaises(ValueError): family.parent_origin(endpoint)

    def test_pairing_saves_origin_and_enables_only_loopback_relay(self):
        import pair_parent
        with tempfile.TemporaryDirectory() as folder, patch.object(pair_parent,'CONFIG',Path(folder)/'remote.json'), patch.object(pair_parent,'command') as run:
            endpoint=pair_parent.prepare_remote('https://school.parents.example.org')
            self.assertEqual(endpoint,'https://school.parents.example.org')
            self.assertEqual(pair_parent.prepare_remote(),endpoint)
            self.assertTrue(all(c.args==('/usr/bin/systemctl','enable','--now','omarchy-kids-remote.service') for c in run.call_args_list))
