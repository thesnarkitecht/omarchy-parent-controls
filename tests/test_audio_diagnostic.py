"""Do not mistake speaker loopback devices for working microphones."""
import unittest

from integration_audio import is_microphone


class AudioDiagnosticTests(unittest.TestCase):
    def test_current_pactl_named_monitor_schema(self):
        self.assertFalse(is_microphone({'monitor_source': 'alsa_output.stereo'}))
        self.assertTrue(is_microphone({'monitor_source': ''}))

    def test_older_pactl_indexed_monitor_schema(self):
        self.assertFalse(is_microphone({'monitor_of_sink': 0}))
        self.assertTrue(is_microphone({'monitor_of_sink': 4294967295}))

    def test_monitor_metadata_overrides_missing_or_ambiguous_fields(self):
        self.assertFalse(is_microphone({'name': 'speaker.monitor', 'monitor_of_sink': None}))
        self.assertFalse(is_microphone({'properties': {'device.class': 'monitor'}}))
        self.assertFalse(is_microphone({}))
        self.assertTrue(is_microphone({'properties': {'media.class': 'Audio/Source'}}))


if __name__ == '__main__':
    unittest.main()
