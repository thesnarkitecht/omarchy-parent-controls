"""Chromium policy syntax and broker origin boundary regressions."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'kids'))
import native_runtime


class BrowserPolicyTests(unittest.TestCase):
    def test_exact_hosts_without_invalid_path_wildcards(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'policy.json'
            with patch.object(native_runtime, 'CHROME_POLICY', target):
                native_runtime.browser_policy({'webapps': [
                    {'origins': ['https://ollama.com', 'https://example.org:8443']},
                    {'origins': ['https://ollama.com']},
                ]})
            value = json.loads(target.read_text())
            self.assertEqual(value['URLAllowlist'],
                             ['https://.example.org:8443', 'https://.ollama.com'])
            self.assertIn('*', value['URLBlocklist'])
            self.assertIn('chrome://settings', value['URLBlocklist'])
            self.assertFalse(value['AllowDeletingBrowserHistory'])
            self.assertEqual(value['PopupsAllowedForUrls'], ['https://example.org:8443','https://ollama.com'])
            self.assertEqual(value['DownloadRestrictions'], 0)
            self.assertEqual(value['DeveloperToolsAvailability'], 2)

    def test_unapproved_url_rejected_before_any_launch(self):
        policy = {'webapps': [{'id': 'ollama', 'url': 'https://ollama.com',
                              'origins': ['https://ollama.com']}]}
        with patch.object(native_runtime, 'account', return_value={'uid': 1000}), \
             patch.object(native_runtime.subprocess, 'run') as run:
            for url in ['https://brave.com', 'https://ollama.com.evil.example',
                        'file:///etc/passwd', 'https://ollama.com@evil.example']:
                with self.assertRaises(ValueError):
                    native_runtime.launch_webapp('ollama', 1000, policy, url)
            run.assert_not_called()
