import unittest
from unittest.mock import patch
from school_voice.desktop import Desktop


class ManagedWindowTests(unittest.TestCase):
    app = {'unit': 'omarchy-kids-webapp-school.service', 'classes': ['omarchy-webapp-school']}

    def test_wayland_url_class_matches_only_approved_system_service(self):
        window = {'pid': 42, 'class': 'chrome-school.example__lesson-Default'}
        for cgroup, allowed in [
            ('0::/system.slice/omarchy-kids-webapp-school.service\n', True),
            ('0::/system.slice/omarchy-kids-webapp-other.service\n', False),
            ('0::/user.slice/user-1000.slice/omarchy-kids-webapp-school.service\n', False),
            ('0::/system.slice/omarchy-kids-webapp-school.service-extra\n', False),
        ]:
            with patch('school_voice.desktop.Path.read_text', return_value=cgroup):
                self.assertEqual(Desktop.matches(self.app, window), allowed)

    def test_forged_class_missing_process_or_invalid_pid_does_not_match(self):
        with patch('school_voice.desktop.Path.read_text', side_effect=FileNotFoundError):
            self.assertFalse(Desktop.matches(self.app, {'pid': 42, 'class': 'omarchy-webapp-school'}))
        for pid in ('../../etc', True, -1, 0, None):
            with patch('school_voice.desktop.Path.read_text') as read:
                self.assertFalse(Desktop.matches(self.app, {'pid': pid}))
                read.assert_not_called()

    def test_native_apps_still_require_exact_class(self):
        app = {'classes': ['org.gnome.Calculator']}
        self.assertTrue(Desktop.matches(app, {'class': 'org.gnome.Calculator'}))
        self.assertFalse(Desktop.matches(app, {'class': 'org.gnome.Calculator.Fake'}))


if __name__ == '__main__':
    unittest.main()
