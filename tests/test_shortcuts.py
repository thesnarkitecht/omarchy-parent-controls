from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'kids'))
from shortcut_policy import overrides, restore_default_loading, LEGACY_FLAGS, LEGACY_IMPORTS

class ShortcutTests(unittest.TestCase):
    def test_migrate_without_disabling_defaults_or_duplicating_imports(self):
        original='-- personal settings\nrequire("default.hypr.omarchy")\nrequire("bindings")\n'
        old=LEGACY_FLAGS+original.replace('require("default.hypr.omarchy")','require("default.hypr.omarchy")\n'+LEGACY_IMPORTS)
        self.assertEqual(restore_default_loading(old),original)
        self.assertEqual(restore_default_loading(original),original)

    def test_shortcuts_are_rebound_and_websites_go_through_approval(self):
        stock='''o.bind("SUPER + RETURN", "Terminal", { omarchy = "terminal" })
o.bind("SUPER + SHIFT + B", "Browser", { omarchy = "browser" })
o.bind("SUPER + SHIFT + ALT + A", "Grok", { webapp = "https://grok.com" })
o.bind("SUPER + SHIFT + G", "Signal", { omarchy = "signal" })'''
        value=overrides(stock,'')
        self.assertNotIn('SUPER + RETURN',value)
        self.assertIn('o.bind("SUPER + SHIFT + B", "Approved apps", "omarchy-menu toggle apps")',value)
        self.assertIn('/usr/local/bin/omarchy-kids-open-url https://grok.com',value)
        self.assertIn('Signal · parent approval',value)
        self.assertEqual(value.count('hl.unbind('),value.count('o.bind('))
