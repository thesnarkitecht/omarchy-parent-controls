"""Authorization, isolation and interrupted PIN update regressions."""
import test_family
from unittest.mock import patch
import family

class MobileSettingsTests(test_family.FamilyTests):
    # Reuse fixture helpers, not the inherited suite.
    def test_profiles_and_permissions_stay_on_the_addressed_computer(self):
        import tempfile
        from control import Store
        with tempfile.TemporaryDirectory() as directory:
            other=Store(directory,clock=lambda:self.now);other.initialize('24681357')
            result=family.remote(self.store,self.envelope('set-profile',{'name':'Lindsey','computer_name':'Lindsey’s laptop'}))
            family.remote(self.store,self.envelope('add-webapp',{'url':'scratch.mit.edu'}))
            self.assertEqual(result['child_name'],'Lindsey')
            self.assertEqual(result['name'],'Lindsey’s laptop')
            self.assertEqual(other.read('policy.json')['webapps'],[])
            self.assertEqual(family.public(other)['child_name'],'')
    def test_change_pin_requires_encryption_and_current_pin(self):
        fields={'current_pin':'13579246','new_pin':'97531864','confirm':'97531864'}
        with self.assertRaises(ValueError):family.remote(self.store,self.envelope('change-pin',fields))
        self.store.authenticate('13579246')
        fields['current_pin']='00000000'
        with self.assertRaises(ValueError):family.remote(self.store,self.envelope('change-pin',fields),encrypted=True)
        self.now+=100
        self.store.authenticate('13579246')
    def test_pin_retry_survives_receipt_expiry_without_reauthenticating_old_pin(self):
        body=self.envelope('change-pin',{'current_pin':'13579246','new_pin':'97531864','confirm':'97531864'})
        family.remote(self.store,body,encrypted=True)
        self.now+=86400;body['issued']=self.now
        family.remote(self.store,body,encrypted=True)
        self.store.authenticate('97531864')
        body['fields']['new_pin']='11111111'
        with self.assertRaises(ValueError):family.remote(self.store,body,encrypted=True)
    def temporary(self):
        self.pair=family.enroll(self.store,'https://school.example.ts.net','Laptop',temporary=True)
        family.remote(self.store,self.envelope())
    def test_fresh_pairing_can_set_phone_pin_once(self):
        self.temporary()
        body=self.envelope('setup-pin',{'new_pin':'97531864'})
        family.remote(self.store,body,encrypted=True)
        self.store.authenticate('97531864')
        self.assertNotIn('setup_expires',family.read(self.store)['phones'][-1])
        family.remote(self.store,body,encrypted=True)
        with self.assertRaises(ValueError):family.remote(self.store,self.envelope('setup-pin',{'new_pin':'11111111'}),encrypted=True)
    def test_existing_phone_cannot_reset_pin_without_current_pin(self):
        with self.assertRaises(ValueError):family.remote(self.store,self.envelope('setup-pin',{'new_pin':'97531864'}),encrypted=True)
    def test_setup_grant_expires_even_after_initial_status(self):
        self.temporary();self.now+=301
        with self.assertRaises(ValueError):family.remote(self.store,self.envelope('setup-pin',{'new_pin':'97531864'}),encrypted=True)
        self.store.authenticate('13579246')
    def test_setup_rejects_plaintext_and_invalid_pin(self):
        self.temporary()
        with self.assertRaises(ValueError):family.remote(self.store,self.envelope('setup-pin',{'new_pin':'97531864'}))
        for pin in ['1234','a'*8,None]:
            with self.assertRaises(ValueError):family.remote(self.store,self.envelope('setup-pin',{'new_pin':pin}),encrypted=True)
        self.store.authenticate('13579246')
    def test_edit_webapp_replaces_origins_and_rejects_broad_hosts(self):
        result=family.remote(self.store,self.envelope('add-webapp',{'url':'scratch.mit.edu'}))
        app=result['policy']['webapps'][0]
        fields={'app_id':app['id'],'name':'Learning','url':'example.org/start','origins':['https://login.example.org']}
        result=family.remote(self.store,self.envelope('edit-webapp',fields))
        self.assertEqual(result['policy']['webapps'][0]['origins'],['https://example.org','https://login.example.org'])
        fields['origins']=['https://youtube.com']
        with self.assertRaises(ValueError):family.remote(self.store,self.envelope('edit-webapp',fields))

# Keep inherited tests in their original module, while retaining fixture methods.
for name in list(test_family.FamilyTests.__dict__):
    if name.startswith('test_') and name not in MobileSettingsTests.__dict__:
        setattr(MobileSettingsTests,name,None)
