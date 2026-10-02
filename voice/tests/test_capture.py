import subprocess
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from school_voice.capture import CaptureStopped, PulseInput, input_rate


class PulseCaptureTests(unittest.TestCase):
    def launch(self, stream, producer):
        real_popen = subprocess.Popen
        self.commands = []
        def spawn(argv, **kwargs):
            self.commands.append(argv)
            return real_popen([sys.executable, '-c', producer], **kwargs)
        with patch('school_voice.capture.subprocess.run', return_value=SimpleNamespace(stdout='selected-microphone\n')), \
             patch('school_voice.capture.subprocess.Popen', side_effect=spawn):
            stream.start()
        self.addCleanup(stream.close)
        return stream

    def test_fragmented_pcm_retains_samples_and_stops_at_callback_limit(self):
        blocks = []
        def callback(data, count, timing, status):
            self.assertFalse(status)
            self.assertEqual(count, 3)
            blocks.extend(data[:, 0].tolist())
            if len(blocks) == 6:
                raise CaptureStopped
        producer = "import os,struct,time;data=struct.pack('<6f',1,2,3,4,5,6)\nfor i in range(0,len(data),2):\n os.write(1,data[i:i+2]);time.sleep(.005)\ntime.sleep(10)"
        stream = self.launch(PulseInput(callback, 3), producer)
        stream.thread.join(timeout=3)
        self.assertFalse(stream.thread.is_alive())
        self.assertEqual(blocks, [1, 2, 3, 4, 5, 6])
        self.assertIsNone(stream.error)
        self.assertFalse(stream.active)
        self.assertIn('--device=selected-microphone', self.commands[0])
        self.assertIn('--rate=16000', self.commands[0])

    def test_disconnection_reports_error_instead_of_silent_partial_audio(self):
        statuses = []
        stream = self.launch(PulseInput(lambda d, n, t, s: statuses.append(s)),
                             "import os;os.write(1,b'xx')")
        stream.thread.join(timeout=3)
        self.assertEqual(statuses, [True])
        self.assertIn('disconnected', stream.error)
        self.assertFalse(stream.active)

    def test_cancel_reaps_a_process_blocked_before_first_audio(self):
        statuses = []
        stream = self.launch(PulseInput(lambda d, n, t, s: statuses.append(s)),
                             'import time;time.sleep(30)')
        start = time.monotonic()
        stream.abort()
        stream.close()
        self.assertLess(time.monotonic() - start, 3)
        self.assertIsNotNone(stream.process.poll())
        self.assertFalse(stream.thread.is_alive())
        self.assertEqual(statuses, [])

    def test_linux_rate_does_not_depend_on_alsa_device_metadata(self):
        with patch('school_voice.capture.sys.platform', 'linux'):
            self.assertEqual(input_rate(), 16000)

    def test_unavailable_source_fails_before_recording(self):
        with patch('school_voice.capture.subprocess.run', return_value=SimpleNamespace(stdout='')), \
             patch('school_voice.capture.subprocess.Popen') as process:
            with self.assertRaises(ValueError):
                PulseInput(lambda *a: None).start()
            process.assert_not_called()


if __name__ == '__main__':
    unittest.main()
