import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'kids'))
from control import Store, peer_action
import family

class FamilyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.now=1000
        self.store=Store(self.tmp.name,clock=lambda:self.now);self.store.initialize('13579246')
        self.pair=family.enroll(self.store,'https://school.example.ts.net','School laptop')
        self.native=patch('native_runtime.configured',return_value=False);self.native.start();self.addCleanup(self.native.stop)
    def envelope(self,op='status',fields=None):
        return dict(token=self.pair['token'],id=__import__('secrets').token_hex(16),issued=self.now,operation=op,fields=fields or {})
    def ask(self,kind='video',target='abcdefghijk',name='Butterflies'):
        return family.submit(self.store,dict(kind=kind,target=target,name=name,reason='For school'))['request']
    def test_pairing_hash_only_and_public_never_leaks_credentials(self):
        self.assertNotIn(self.pair['token'],json.dumps(family.read(self.store)))
        public=family.remote(self.store,self.envelope())
        self.assertNotIn('phones',public);self.assertNotIn('receipts',public)
    def test_token_required_for_every_remote_operation(self):
        for op in ['status','review','add-video','add-webapp','set-voice','remove-webapp']:
            body=self.envelope(op);body['token']='x'*43
            with self.subTest(op=op),self.assertRaises(ValueError): family.remote(self.store,body)
    def test_enrollment_and_revocation_require_root_peer(self):
        for action in ['remote-enroll','remote-revoke']:
            with self.assertRaises(ValueError): peer_action(self.store,dict(action=action),1000)
    def test_other_accounts_cannot_submit_child_requests(self):
        with patch('native_runtime.account',return_value={'uid':1000}),self.assertRaises(ValueError):
            peer_action(self.store,{'action':'ask-parent'},1001)
    def test_revocation_invalidates_existing_phone_immediately(self):
        family.revoke(self.store)
        with self.assertRaises(ValueError): family.remote(self.store,self.envelope())
    def test_old_or_future_operations_fail(self):
        for offset in [-61,61]:
            body=self.envelope();body['issued']+=offset
            with self.assertRaises(ValueError): family.remote(self.store,body)
    def test_unapproved_video_is_not_in_library(self):
        self.ask();self.assertEqual(family.public(self.store)['videos'],[])
    def test_allow_video_changes_only_exact_id(self):
        req=self.ask();body=self.envelope('review',dict(request_id=req['id'],allow=True))
        result=family.remote(self.store,body)
        self.assertEqual(result['videos'],[{'id':'abcdefghijk','name':'Butterflies'}])
        self.assertEqual(result['policy']['webapps'],[])
        self.assertEqual(result['requests'][0]['status'],'allowed')
    def test_deny_changes_no_permissions(self):
        req=self.ask();result=family.remote(self.store,self.envelope('review',dict(request_id=req['id'],allow=False)))
        self.assertEqual(result['videos'],[]);self.assertEqual(result['requests'][0]['status'],'denied')
    def test_duplicate_approval_is_idempotent_and_different_replay_rejected(self):
        req=self.ask();body=self.envelope('review',dict(request_id=req['id'],allow=True))
        first=family.remote(self.store,body);second=family.remote(self.store,body)
        self.assertEqual(first,second)
        body['fields']['allow']=False
        with self.assertRaises(ValueError): family.remote(self.store,body)
    def test_stale_conflicting_review_rejected(self):
        req=self.ask();family.remote(self.store,self.envelope('review',dict(request_id=req['id'],allow=True)))
        with self.assertRaises(ValueError): family.remote(self.store,self.envelope('review',dict(request_id=req['id'],allow=False)))
    def test_child_cannot_inject_approval_or_command(self):
        request=dict(kind='video',name='X',target='abcdefghijk',reason='',status='allowed')
        with self.assertRaises(ValueError): family.submit(self.store,request)
        for op in ['exec','save','disable-controls','change-pin','remote-enroll']:
            with self.assertRaises(ValueError): family.remote(self.store,self.envelope(op,dict(command='sh')))
    def test_website_is_exact_origin_and_managed_launcher(self):
        req=self.ask('website','https://scratch.mit.edu/projects','Scratch')
        result=family.remote(self.store,self.envelope('review',dict(request_id=req['id'],allow=True)))
        self.assertEqual(result['policy']['webapps'][0]['origins'],['https://scratch.mit.edu'])
        catalog=family.voice_catalog(self.store)['apps'];app=next(v for k,v in catalog.items() if k.startswith('web_'))
        self.assertEqual(app['argv'][0],'/usr/local/bin/omarchy-kids-webapp')
        self.assertNotIn('https://scratch.mit.edu',app['argv'])
    def test_website_removal_removes_voice_app(self):
        req=self.ask('website','https://scratch.mit.edu','Scratch')
        result=family.remote(self.store,self.envelope('review',dict(request_id=req['id'],allow=True)))
        family.remote(self.store,self.envelope('remove-webapp',dict(app_id=result['policy']['webapps'][0]['id'])))
        self.assertFalse(any(k.startswith('web_') for k in family.voice_catalog(self.store)['apps']))
    def test_child_cannot_approve_whole_youtube(self):
        with self.assertRaises(ValueError): self.ask('website','https://www.youtube.com','YouTube')
    def test_video_url_rules(self):
        for value in ['abcdefghijk','https://youtu.be/abcdefghijk','https://www.youtube.com/watch?v=abcdefghijk&t=12s','https://youtube.com/shorts/abcdefghijk']:
            self.assertEqual(family.video_id(value),'abcdefghijk')
        for value in ['https://youtube.com/@channel','https://youtube.com/playlist?list=x','https://youtube.com/watch?v=abcdefghijk&list=x','https://youtube.com.evil.org/watch?v=abcdefghijk','http://youtu.be/abcdefghijk','https://u:p@youtu.be/abcdefghijk','https://youtu.be/abcdefghijk/extra','file:///etc/passwd']:
            with self.subTest(value=value),self.assertRaises(ValueError): family.video_id(value)
    def test_video_removal_and_stale_approval_dont_reapprove(self):
        req=self.ask();approve=self.envelope('review',dict(request_id=req['id'],allow=True));family.remote(self.store,approve)
        family.remote(self.store,self.envelope('remove-video',dict(video_id='abcdefghijk')))
        result=family.remote(self.store,approve)
        self.assertEqual(result['videos'],[])
    def test_queue_deduplicates_and_bounds_spam(self):
        self.assertEqual(self.ask(),self.ask())
        for i in range(4): self.ask('website',f'https://a{i}.example.org','Website')
        with self.assertRaises(ValueError): self.ask('website','https://extra.example.org','Website')
    def test_voice_changes_use_typed_settings_and_do_not_expand_apps(self):
        fields=dict(enabled=True,wake_enabled=True,phrase='Hey Laya')
        with patch('family.Path.is_file',return_value=True):
            result=family.remote(self.store,self.envelope('set-voice',fields))
        self.assertTrue(result['voice']['enabled'])
        fields['command']='sh'
        with self.assertRaises(ValueError): family.remote(self.store,self.envelope('set-voice',fields))
    def test_local_parent_changes_still_need_pin(self):
            with self.assertRaises(ValueError): self.store.dispatch(dict(action='family-change',operation='add-video',fields={'url':'abcdefghijk','name':'X'}))
    def test_disallow_uninstalled_native_app_and_arbitrary_binary(self):
        with self.assertRaises(ValueError): self.ask('app','bash','Shell')
        req=self.ask('app','tuxpaint','Paint')
        with patch('sandbox.trusted_executable',side_effect=ValueError('not installed')):
            with self.assertRaises(ValueError): family.remote(self.store,self.envelope('review',dict(request_id=req['id'],allow=True)))
        self.assertEqual(family.read(self.store)['requests'][-1]['status'],'pending')

    def test_paste_only_website_keeps_path_and_approves_exact_host(self):
        result = family.remote(self.store, self.envelope('add-webapp', {'url': ' scratch.mit.edu/projects/123?view=full#top '}))
        app = result['policy']['webapps'][0]
        self.assertEqual(app['name'], 'scratch.mit.edu')
        self.assertEqual(app['url'], 'https://scratch.mit.edu/projects/123?view=full#top')
        self.assertEqual(app['origins'], ['https://scratch.mit.edu'])
        self.assertTrue(any(a['label'] == 'scratch.mit.edu' for a in family.voice_catalog(self.store)['apps'].values()))

    def test_repeated_paste_updates_name_without_duplicate_or_new_origins(self):
        family.remote(self.store, self.envelope('add-webapp', {'url': 'scratch.mit.edu'}))
        result = family.remote(self.store, self.envelope('add-webapp', {'url': 'https://scratch.mit.edu/', 'name': 'Scratch'}))
        self.assertEqual(len(result['policy']['webapps']), 1)
        self.assertEqual(result['policy']['webapps'][0]['name'], 'Scratch')
        self.assertEqual(result['policy']['webapps'][0]['origins'], ['https://scratch.mit.edu'])

    def test_invalid_or_broad_links_cannot_change_policy(self):
        for url in ('file:///etc/shadow', 'http://example.org', 'https://u:p@example.org',
                    '127.0.0.1', 'school.local', 'https://example.org:8443',
                    'https://example.org/\nattack', 'youtube.com', 'music.youtube.com', 'youtu.be/abcdefghijk'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                family.remote(self.store, self.envelope('add-webapp', {'url': url}))
        self.assertEqual(self.store.read('policy.json')['webapps'], [])

    def test_direct_website_approval_requires_parent_pin_locally(self):
        value = dict(action='family-change', operation='add-webapp', fields={'url': 'scratch.mit.edu'})
        with self.assertRaises(ValueError): self.store.dispatch(value)
        self.assertEqual(self.store.read('policy.json')['webapps'], [])
        self.now += 100
        result = self.store.dispatch({**value, 'pin': '13579246'})
        self.assertEqual(len(result['policy']['webapps']), 1)

    def test_video_name_is_optional_but_exact_video_rule_remains(self):
        result = family.remote(self.store, self.envelope('add-video', {'url': ' https://youtu.be/abcdefghijk '}))
        self.assertEqual(result['videos'], [{'id': 'abcdefghijk', 'name': 'Video abcdefghijk'}])
        with self.assertRaises(ValueError):
            family.remote(self.store, self.envelope('add-video', {'url': 'https://youtube.com/@channel'}))

    def test_extra_website_fields_cannot_grant_other_hosts_or_commands(self):
        for extra in ({'origins': ['https://other.example.org']}, {'argv': ['sh']}, {'name': None}):
            with self.assertRaises(ValueError):
                family.remote(self.store, self.envelope('add-webapp', {'url': 'example.org', **extra}))

if __name__=='__main__': unittest.main()
