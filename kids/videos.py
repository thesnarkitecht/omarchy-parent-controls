"""Little Screen: a finite parent-selected library, with no browser or feed."""
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import QObject, Signal, QTimer, QProcess, Qt
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QGridLayout, QLineEdit, QComboBox, QFrame)
from client import request
from family import VIDEO_ID

STYLE = '''
QWidget { background:#F6F3EB; color:#263B32; font-family:DejaVu Sans; font-size:15px; }
QLabel#title { font-size:36px; font-weight:700; }
QLabel#eyebrow { color:#557567; font-size:12px; font-weight:700; }
QLabel#muted { color:#647369; }
QFrame#card { background:white; border:1px solid #E3E5DB; border-radius:22px; }
QFrame#card QLabel { background:transparent; }
QPushButton { background:#E7E9DD; border:0; border-radius:14px; padding:12px 20px; font-weight:600; }
QPushButton:hover { background:#DBE5D6; }
QPushButton:focus { border:2px solid #39785E; }
QPushButton#primary { background:#275B43; color:white; }
QPushButton:disabled { color:#929B94; background:#E7E9DD; }
QLineEdit, QComboBox { background:white; border:1px solid #D7DDD0; border-radius:12px; padding:12px; }
QScrollArea { border:0; }
'''

def player_command(key):
    if not isinstance(key, str) or not VIDEO_ID.fullmatch(key):
        raise ValueError('Invalid video ID')
    return ['/usr/bin/mpv', '--no-config', '--load-scripts=no', '--ytdl=yes',
            '--script-opts=ytdl_hook-ytdl_path=/usr/bin/yt-dlp',
            '--ytdl-raw-options=ignore-config=,no-playlist=',
            '--ytdl-format=bestvideo[height<=720]+bestaudio/best[height<=720]',
            '--input-default-bindings=no', '--input-conf=/usr/local/lib/omarchy-kids/video-input.conf',
            '--input-terminal=no', '--input-ipc-server=', '--osc=yes', '--osd-level=1',
            '--keep-open=no', '--force-window=yes', '--title=Little Screen',
            '--', 'https://www.youtube.com/watch?v=' + key]

class Signals(QObject):
    result = Signal(object, str)

class Library(QWidget):
    def __init__(self, api=request):
        super().__init__()
        self.api, self.pool, self.signals = api, ThreadPoolExecutor(max_workers=1), Signals()
        self.signals.result.connect(self.complete, Qt.ConnectionType.QueuedConnection)
        self.pending = False
        self.state = {'videos': [], 'requests': []}
        self.playing = None
        self.player = QProcess(self)
        self.player.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedErrorChannel)
        self.player.finished.connect(self.play_finished)
        self.player.errorOccurred.connect(lambda _: self.message.setText('Could not start the player. Ask your parent to check the installation.'))
        self.setWindowTitle('Little Screen')
        self.resize(990, 740)
        self.setStyleSheet(STYLE)
        root = QVBoxLayout(self); root.setContentsMargins(38, 32, 38, 28); root.setSpacing(18)
        eyebrow = QLabel('A LITTLE LIBRARY. A BIG WORLD.'); eyebrow.setObjectName('eyebrow'); root.addWidget(eyebrow)
        row = QHBoxLayout()
        title = QLabel('Little Screen'); title.setObjectName('title'); row.addWidget(title); row.addStretch()
        self.stop = QPushButton('Stop video'); self.stop.clicked.connect(self.stop_video); self.stop.setEnabled(False); row.addWidget(self.stop)
        root.addLayout(row)
        subtitle = QLabel('Picked by your parent. Ready for you.'); subtitle.setObjectName('muted'); root.addWidget(subtitle)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.cards = QWidget(); self.grid = QGridLayout(self.cards); self.grid.setSpacing(18)
        self.scroll.setWidget(self.cards); root.addWidget(self.scroll, 1)
        self.message = QLabel('Checking your library…'); self.message.setWordWrap(True); root.addWidget(self.message)
        form = QFrame(); form.setObjectName('card'); fields = QVBoxLayout(form); fields.setContentsMargins(22, 18, 22, 18)
        label = QLabel('Something you’d like to try?'); label.setStyleSheet('font-size:20px;font-weight:700'); fields.addWidget(label)
        first = QHBoxLayout()
        self.kind = QComboBox(); self.kind.addItems(['Video', 'Website', 'School app']); first.addWidget(self.kind)
        self.name = QLineEdit(); self.name.setPlaceholderText('Give it a name'); self.name.setMaxLength(60); first.addWidget(self.name, 1)
        self.target = QLineEdit(); self.target.setPlaceholderText('Paste the video link'); self.target.setMaxLength(2048); first.addWidget(self.target, 2)
        self.app_picker = QComboBox(); self.app_picker.setVisible(False); first.addWidget(self.app_picker, 2)
        def change_kind(i):
            self.target.setVisible(i != 2); self.name.setVisible(i != 2); self.app_picker.setVisible(i == 2)
            self.target.setPlaceholderText('Paste the video link' if i == 0 else 'https://example.org')
        self.kind.currentIndexChanged.connect(change_kind)
        fields.addLayout(first)
        second = QHBoxLayout()
        self.reason = QLineEdit(); self.reason.setPlaceholderText('Tell your parent why (optional)'); self.reason.setMaxLength(240); second.addWidget(self.reason, 1)
        self.ask = QPushButton('Ask my parent  →'); self.ask.setObjectName('primary'); self.ask.clicked.connect(self.submit); second.addWidget(self.ask); fields.addLayout(second)
        root.addWidget(form)
        self.history = QLabel(''); self.history.setWordWrap(True); self.history.setObjectName('muted'); root.addWidget(self.history)
        self.timer = QTimer(self); self.timer.setInterval(2000); self.timer.timeout.connect(self.refresh); self.timer.start()
        QTimer.singleShot(0, self.refresh)

    def run(self, function):
        if self.pending: return
        self.pending = True; self.ask.setEnabled(False)
        future = self.pool.submit(function)
        def done(f):
            try: self.signals.result.emit(f.result(), '')
            except Exception as error: self.signals.result.emit(None, str(error))
        future.add_done_callback(done)

    def refresh(self):
        self.run(lambda: self.api('family-status', timeout=3))

    def submit(self):
        value = {'kind': ['video','website','app'][self.kind.currentIndex()], 'name':self.name.text(),
                 'target':self.target.text().strip(), 'reason':self.reason.text()}
        if value['kind'] == 'app':
            value.update(name=self.app_picker.currentText(),target=self.app_picker.currentData())
        def send():
            self.api('ask-parent', request=value, timeout=3)
            return self.api('family-status', timeout=3)
        self.run(send)

    def complete(self, state, error):
        self.pending = False; self.ask.setEnabled(True)
        if error:
            self.stop_video()
            self.message.setText('Could not check your permissions. ' + error[:160])
            return
        if self.playing and self.playing not in {v['id'] for v in state['videos']}:
            self.stop_video(); self.message.setText('Your parent updated the library. This video is no longer available.')
        if state['videos'] != self.state['videos'] or not self.grid.count():
            self.render(state['videos'])
        self.state = state
        entries = state.get('requestable_apps', [])
        if [(self.app_picker.itemData(i),self.app_picker.itemText(i)) for i in range(self.app_picker.count())] != [(a['id'],a['name']) for a in entries]:
            selected=self.app_picker.currentData();self.app_picker.clear()
            for app in entries: self.app_picker.addItem(app['name'],app['id'])
            index=self.app_picker.findData(selected)
            if index>=0: self.app_picker.setCurrentIndex(index)
        if state.get('play'):
            self.stop_video()
            # Starting a fresh process does not inherit user mpv/yt-dlp configuration.
            from PySide6.QtCore import QProcessEnvironment
            env = QProcessEnvironment.systemEnvironment()
            for key in ('PYTHONPATH', 'PYTHONHOME', 'LD_PRELOAD', 'LD_LIBRARY_PATH', 'YTDL_FORMAT'):
                env.remove(key)
            env.insert('PATH', '/usr/bin:/bin')
            self.player.setProcessEnvironment(env)
            argv = player_command(state['play'])
            self.player.start(argv[0], argv[1:])
            self.playing = state['play']; self.stop.setEnabled(True)
            self.message.setText('Your video is opening. Close the player to come back here.')
        self.history.setText('  •  '.join(r['name'] + ': ' + {'pending':'waiting for your parent','allowed':'allowed ✓','denied':'not this time'}[r['status']] for r in state['requests'][-3:]))
        if not self.playing:
            self.message.setText(f"{len(state['videos'])} videos chosen for you. Nothing plays automatically.")

    def render(self, videos):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        if not videos:
            empty = QLabel('Your next favorite is on its way.\nAsk your parent to add your first video.'); empty.setAlignment(Qt.AlignmentFlag.AlignCenter); self.grid.addWidget(empty, 0, 0); return
        colors = ['#DAE8CB','#E9DBF0','#F7DFB1','#CEE5EA']
        for n, video in enumerate(videos):
            card = QFrame(); card.setObjectName('card'); box = QVBoxLayout(card); box.setContentsMargins(18,18,18,18); box.setSpacing(12)
            art = QLabel('▶'); art.setAlignment(Qt.AlignmentFlag.AlignCenter); art.setFixedHeight(110); art.setStyleSheet(f'background:{colors[n%4]};border-radius:14px;font-size:42px;color:#345342;'); box.addWidget(art)
            title = QLabel(video['name']); title.setWordWrap(True); title.setTextFormat(Qt.TextFormat.PlainText); title.setStyleSheet('font-size:18px;font-weight:700;'); box.addWidget(title)
            button = QPushButton('Watch this'); button.setObjectName('primary'); button.clicked.connect(lambda checked=False, key=video['id']: self.play(key)); box.addWidget(button)
            self.grid.addWidget(card, n//3, n%3)

    def play(self, key):
        # Reload authorization immediately before launch, not just when drawing cards.
        def check():
            state = self.api('family-status', timeout=3)
            if key not in {v['id'] for v in state['videos']}: raise ValueError('This video is no longer approved.')
            return {**state, 'play': key}
        self.run(check)
        # complete() is the only GUI-thread entry point; the worker never starts a player.

    def stop_video(self):
        if self.player.state() != QProcess.ProcessState.NotRunning:
            self.player.kill()
            self.player.waitForFinished(1000)
        self.playing = None; self.stop.setEnabled(False)

    def play_finished(self, *args):
        self.playing = None; self.stop.setEnabled(False)
        self.message.setText('All done. Pick another whenever you’re ready.')

    def closeEvent(self, event):
        self.timer.stop(); self.stop_video(); self.pool.shutdown(wait=False, cancel_futures=True); event.accept()


def main():
    app = QApplication(sys.argv); app.setDesktopFileName('little-screen')
    window = Library(); window.show(); app.exec()

if __name__ == '__main__': main()
