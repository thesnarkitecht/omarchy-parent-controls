import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'kids'))
from videos import Library, player_command
from PySide6.QtWidgets import QApplication

class VideoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    def test_player_has_one_exact_video_and_no_user_config(self):
        argv=player_command('abcdefghijk')
        self.assertEqual(argv[-1],'https://www.youtube.com/watch?v=abcdefghijk')
        self.assertIn('--no-config',argv);self.assertIn('--load-scripts=no',argv)
        self.assertIn('--ytdl-raw-options=ignore-config=,no-playlist=',argv)
        for key in ['sh','--script=bad','https://youtube.com/watch?v=abcdefghijk']:
            with self.assertRaises(ValueError):player_command(key)
    def test_embedded_player_keeps_single_video_and_rejects_bad_window(self):
        args=player_command('abcdefghijk',123)
        self.assertIn('--wid=123',args)
        self.assertIn('--gpu-context=x11egl',args)
        self.assertEqual(args[-2:],["--","https://www.youtube.com/watch?v=abcdefghijk"])
        with self.assertRaises(ValueError):player_command('abcdefghijk','--script=bad')
    def test_revocation_and_broker_failure_stop_playback(self):
        window=Library(api=lambda *a,**k:{'videos':[],'requests':[]},thumbnails=False);window.timer.stop()
        self.addCleanup(window.close)
        for value,error in [({'videos':[],'requests':[]},''),(None,'broker unavailable')]:
            window.playing='abcdefghijk'
            with patch.object(window,'stop_video') as stop:
                window.complete(value,error);stop.assert_called_once()

if __name__=='__main__':unittest.main()
