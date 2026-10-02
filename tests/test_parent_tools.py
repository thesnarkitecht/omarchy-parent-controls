"""Parent actions must authorize before changing policy or deleting a profile."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'kids'))
import bridge
from control import Store
import parent_tools
import webapp_data

POLICY={'native':[], 'webapps':[{'id':'x-ai','name':'x.ai','url':'https://x.ai','origins':['https://x.ai']}]}

class ParentToolsTests(unittest.TestCase):
    def test_related_site_edit_keeps_id_and_sends_pin_to_broker(self):
        with patch.object(bridge,'request') as request:
            request.side_effect=[{'policy':copy.deepcopy(POLICY)}, {'ok':True}]
            result=bridge.dispatch({'action':'edit-webapp','id':'x-ai','name':'Grok','url':'https://x.ai',
                                    'origins':'https://grok.com','pin':'13579246'})
            self.assertEqual(result['policy']['webapps'][0]['id'],'x-ai')
            self.assertEqual(result['policy']['webapps'][0]['origins'],['https://grok.com','https://x.ai'])
            self.assertEqual(request.call_args.args,('save',))
            self.assertEqual(request.call_args.kwargs['pin'],'13579246')

    def test_clear_requires_pin_before_any_deletion(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);store.initialize('13579246')
            store.save('policy.json',POLICY)
            with patch.object(webapp_data,'clear') as clear:
                with self.assertRaises(ValueError):
                    store.dispatch({'action':'clear-webapp-data','id':'x-ai','pin':'00000000'})
                clear.assert_not_called()

    def test_reset_only_removes_selected_profile_and_does_not_follow_links(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);chosen=root/'chromium-x-ai';chosen.mkdir()
            (chosen/'History').write_text('history')
            other=root/'chromium-other';other.mkdir();(other/'Cookies').write_text('keep')
            with patch.object(webapp_data,'DATA',root):
                webapp_data.remove_profile('x-ai')
                self.assertFalse(chosen.exists())
                self.assertEqual((other/'Cookies').read_text(),'keep')
                chosen.symlink_to(other,target_is_directory=True)
                with self.assertRaises(ValueError):webapp_data.remove_profile('x-ai')
                for key in ['../other','x;id','*',None]:
                    with self.assertRaises(ValueError):webapp_data.remove_profile(key)
                self.assertEqual((other/'Cookies').read_text(),'keep')

    def test_parent_tools_refuse_controlled_mode_and_unknown_commands(self):
        with patch.object(parent_tools.Path,'exists',return_value=True), \
             patch.object(parent_tools.subprocess,'Popen') as launch:
            for tool in ['agent','windows-install','windows-launch','shell']:
                with self.assertRaises(ValueError):parent_tools.launch(tool)
            launch.assert_not_called()

    def test_agent_picker_does_not_install_or_select_an_agent(self):
        with patch.object(parent_tools.Path,'exists',return_value=False), \
             patch.object(parent_tools.subprocess,'Popen') as launch:
            parent_tools.launch('agent')
            self.assertEqual(launch.call_args.args[0],['/usr/bin/omarchy','menu','summon','setup.default.agent'])

    def test_active_webapp_still_receives_approved_links(self):
        from types import SimpleNamespace
        import native_runtime
        import display_access
        person=SimpleNamespace(pw_uid=964,pw_dir='/home/child')
        policy={'webapps':[{'id':'x-ai','url':'https://x.ai','origins':['https://x.ai','https://grok.com']}]}
        with patch.object(native_runtime,'account',return_value={'uid':1000,'user':'child'}), \
             patch.object(native_runtime.pwd,'getpwnam',return_value=person), \
             patch.object(display_access,'grant',return_value=Path('/run/user/1000/wayland-1')), \
             patch.object(native_runtime.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as run:
            native_runtime.launch_webapp('x-ai',1000,policy,'https://grok.com/')
            command=run.call_args.args[0]
            self.assertIn('--app=https://grok.com/',command)
            self.assertTrue(any(x.startswith('--unit=omarchy-kids-webapp-x-ai-open-') for x in command))
            unit=next(x.split('=',1)[1] for x in command if x.startswith('--unit='))
            self.assertIn('--setenv=PULSE_SERVER=unix:/run/'+unit+'/pulse-native',command)
            self.assertIn('--setenv=PULSE_CLIENTCONFIG=/usr/local/lib/omarchy-kids/pulse-client.conf',command)
            self.assertIn('--property=InaccessiblePaths=/run/user',command)
            mounts=next(x for x in command if x.startswith('--property=BindReadOnlyPaths='))
            self.assertIn('/run/omarchy-kids-audio/native:/run/'+unit+'/pulse-native',mounts)
            self.assertNotIn('/pulse/native',mounts)
            self.assertNotIn('--no-sandbox',command)

    def test_running_windows_prevents_activation_without_terminating_guest(self):
        from types import SimpleNamespace
        with patch.object(parent_tools.Path,'is_file',return_value=True), \
             patch.object(parent_tools.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='true\n')) as run:
            with self.assertRaisesRegex(ValueError,'Shut down Windows'):
                parent_tools.ensure_windows_stopped()
            self.assertEqual(run.call_count,1)
            self.assertIn('inspect',run.call_args.args[0])
            self.assertNotIn('stop',run.call_args.args[0])

    def test_windows_adapter_uses_parent_sudo_only_for_fixed_native_helper(self):
        import os, runpy
        script=Path(__file__).resolve().parents[1]/'native/windows-pkexec'
        with patch.object(Path,'exists',return_value=False), patch.object(os,'getuid',return_value=1000), \
             patch.object(os,'execv') as execute, \
             patch.object(sys,'argv',[str(script),'/usr/bin/omarchy-windows-vm','__priv','status']):
            runpy.run_path(str(script))
            self.assertEqual(execute.call_args.args,('/usr/bin/sudo',['sudo','--','/usr/bin/env','PKEXEC_UID=1000','/usr/bin/omarchy-windows-vm','__priv','status']))
        with patch.object(Path,'exists',return_value=False), patch.object(os,'execv') as execute, \
             patch.object(sys,'argv',[str(script),'/bin/sh','-c','id']):
            with self.assertRaises(SystemExit):runpy.run_path(str(script))
            execute.assert_not_called()
