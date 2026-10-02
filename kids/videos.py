"""Videos: a finite parent-selected library, with no browser or feed."""
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import QObject, Signal, QTimer, QProcess, Qt, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QGridLayout, QLineEdit, QComboBox, QFrame)
from client import request
from family import VIDEO_ID

STYLE = '''
QWidget { background:#0f0f0f; color:#f1f1f1; font-family:DejaVu Sans; font-size:14px; }
QLabel#title { font-size:27px; font-weight:700; }
QLabel#muted { color:#aaa; }
QFrame#card { background:#181818; border-radius:12px; }
QFrame#card QLabel { background:transparent; }
QPushButton { background:#272727; border:0; border-radius:18px; padding:10px 18px; font-weight:600; }
QPushButton:hover { background:#3f3f3f; }
QPushButton:focus { border:2px solid #f1f1f1; }
QPushButton#primary { background:#f1f1f1; color:#0f0f0f; }
QPushButton:disabled { color:#777; background:#202020; }
QLineEdit, QComboBox { background:#121212; border:1px solid #3d3d3d; border-radius:18px; padding:10px 15px; }
QScrollArea { border:0; }
'''

def player_command(key, window_id=None):
    if not isinstance(key, str) or not VIDEO_ID.fullmatch(key):
        raise ValueError('Invalid video ID')
    args = ['/usr/bin/mpv', '--no-config', '--load-scripts=no', '--ytdl=yes',
            '--script-opts=ytdl_hook-ytdl_path=/usr/bin/yt-dlp',
            '--ytdl-raw-options=ignore-config=,no-playlist=',
            '--ytdl-format=bestvideo[height<=720]+bestaudio/best[height<=720]',
            '--input-default-bindings=no', '--input-conf=/usr/local/lib/omarchy-kids/video-input.conf',
            '--input-terminal=no', '--input-ipc-server=', '--osc=yes', '--osd-level=1',
            '--keep-open=no', '--force-window=yes', '--title=Videos',
            '--', 'https://www.youtube.com/watch?v=' + key]
    if window_id is not None:
        if type(window_id) is not int or window_id <= 0: raise ValueError('Invalid player window')
        args[1:1] = ['--wid=' + str(window_id), '--gpu-context=x11egl']
    return args

class Signals(QObject):
    result = Signal(object, str)

class Library(QWidget):
    def __init__(self, api=request, thumbnails=True):
        super().__init__()
        self.api, self.pool, self.signals = api, ThreadPoolExecutor(max_workers=1), Signals()
        self.signals.result.connect(self.complete, Qt.ConnectionType.QueuedConnection)
        self.network = QNetworkAccessManager(self)
        self.thumbnails = thumbnails
        self.art_cache = {}
        self.art_requests = set()
        self.pending = False
        self.state = {'videos': [], 'requests': []}
        self.playing = None
        self.player = QProcess(self)
        self.player.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedErrorChannel)
        self.player.finished.connect(self.play_finished)
        self.player.errorOccurred.connect(lambda _: self.message.setText('Could not start the player. Ask your parent to check the installation.'))
        self.setWindowTitle('Videos')
        self.resize(1180, 820)
        self.setStyleSheet(STYLE)
        root = QVBoxLayout(self); root.setContentsMargins(28, 20, 28, 20); root.setSpacing(18)
        row = QHBoxLayout()
        mark = QLabel('▶'); mark.setStyleSheet('background:#ff0033;color:white;border-radius:10px;padding:5px 12px;font-size:24px;'); row.addWidget(mark)
        title = QLabel('Videos'); title.setObjectName('title'); row.addWidget(title)
        row.addSpacing(32)
        self.search = QLineEdit(); self.search.setPlaceholderText('Search your approved videos'); self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _: self.render(self.state['videos'])); row.addWidget(self.search,1)
        row.addSpacing(24)
        ask_toggle = QPushButton('＋ Ask my parent'); row.addWidget(ask_toggle)
        root.addLayout(row)
        navigation = QHBoxLayout()
        home = QPushButton('⌂ Home'); home.clicked.connect(self.stop_video); navigation.addWidget(home)
        subtitle = QLabel('Your library · Picked by your parent'); subtitle.setObjectName('muted'); navigation.addWidget(subtitle); navigation.addStretch()
        self.stop = QPushButton('Close video'); self.stop.clicked.connect(self.stop_video); self.stop.setEnabled(False); navigation.addWidget(self.stop)
        root.addLayout(navigation)
        self.watch = QWidget(); watch_layout = QVBoxLayout(self.watch); watch_layout.setContentsMargins(0,0,0,0)
        self.screen = QFrame(); self.screen.setStyleSheet('background:black;'); self.screen.setMinimumHeight(360)
        self.screen.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        watch_layout.addWidget(self.screen,1)
        self.watch_title = QLabel(); self.watch_title.setTextFormat(Qt.TextFormat.PlainText); self.watch_title.setWordWrap(True); self.watch_title.setStyleSheet('font-size:22px;font-weight:700;'); watch_layout.addWidget(self.watch_title)
        tip = QLabel('Move your pointer over the video for play, volume and seeking controls.'); tip.setObjectName('muted'); watch_layout.addWidget(tip)
        root.addWidget(self.watch,3); self.watch.hide()
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.cards = QWidget(); self.grid = QGridLayout(self.cards); self.grid.setSpacing(20); self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.cards); root.addWidget(self.scroll,2)
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
        root.addWidget(form); form.hide()
        ask_toggle.clicked.connect(lambda: form.setVisible(not form.isVisible()))
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
            embedded = sys.platform.startswith('linux') and QApplication.platformName() == 'xcb'
            self.watch.setVisible(embedded)
            self.watch_title.setText(next(v['name'] for v in state['videos'] if v['id'] == state['play']))
            argv = player_command(state['play'], int(self.screen.winId()) if embedded else None)
            self.player.start(argv[0], argv[1:])
            self.playing = state['play']; self.stop.setEnabled(True)
            self.message.setText('Only videos in your approved library appear here.' if embedded else 'Your video is opening in the player. Close it to return to Videos.')
        self.history.setText('  •  '.join(r['name'] + ': ' + {'pending':'waiting for your parent','allowed':'allowed ✓','denied':'not this time'}[r['status']] for r in state['requests'][-3:]))
        if not self.playing:
            self.message.setText(f"{len(state['videos'])} videos chosen for you. Nothing plays automatically.")

    def render(self, videos):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        if not videos:
            empty = QLabel('Your next favorite is on its way.\nAsk your parent to add your first video.'); empty.setAlignment(Qt.AlignmentFlag.AlignCenter); self.grid.addWidget(empty, 0, 0); return
        visible = [v for v in videos if self.search.text().casefold() in v['name'].casefold()]
        if not visible:
            self.grid.addWidget(QLabel('No approved videos match your search.'),0,0)
        for n, video in enumerate(visible):
            card = QFrame(); card.setObjectName('card'); box = QVBoxLayout(card); box.setContentsMargins(0,0,0,12); box.setSpacing(10)
            art = QLabel('▶'); art.setAlignment(Qt.AlignmentFlag.AlignCenter); art.setFixedHeight(160); art.setMinimumWidth(220)
            art.setStyleSheet('background:#252525;border-radius:12px;font-size:36px;color:white;'); box.addWidget(art)
            self.thumbnail(video['id'],art)
            title = QLabel(video['name']); title.setWordWrap(True); title.setTextFormat(Qt.TextFormat.PlainText); title.setStyleSheet('font-size:16px;font-weight:700;padding:0 12px;'); box.addWidget(title)
            caption = QLabel('Approved by your parent'); caption.setStyleSheet('color:#aaa;padding:0 12px;font-size:12px;'); box.addWidget(caption)
            button = QPushButton('▶ Watch'); button.clicked.connect(lambda checked=False, key=video['id']: self.play(key)); box.addWidget(button)
            self.grid.addWidget(card,n//3,n%3)

    def thumbnail(self, key, label):
        if not VIDEO_ID.fullmatch(key): return
        def display(pixmap):
            label.setPixmap(pixmap.scaled(300,160,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        if key in self.art_cache: display(self.art_cache[key]); return
        if not self.thumbnails or key in self.art_requests: return
        self.art_requests.add(key)
        query = QNetworkRequest(QUrl('https://i.ytimg.com/vi/' + key + '/hqdefault.jpg'))
        query.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        query.setTransferTimeout(6000)
        reply = self.network.get(query); reply.setReadBufferSize(524289)
        reply.downloadProgress.connect(lambda got,total: reply.abort() if got > 524288 or total > 524288 else None)
        def ready():
            self.art_requests.discard(key)
            data = reply.read(524289)
            if reply.error() == reply.NetworkError.NoError and len(data) <= 524288:
                pixmap = QPixmap()
                if pixmap.loadFromData(data):
                    if len(self.art_cache) >= 100: self.art_cache.clear()
                    self.art_cache[key] = pixmap
                    # Cards may have been rebuilt while the network request was in flight.
                    self.render(self.state['videos'])
            reply.deleteLater()
        reply.finished.connect(ready)

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
        self.playing = None; self.stop.setEnabled(False); self.watch.hide()

    def play_finished(self, *args):
        self.playing = None; self.stop.setEnabled(False); self.watch.hide()
        self.message.setText('All done. Pick another whenever you’re ready.')

    def closeEvent(self, event):
        self.timer.stop(); self.stop_video(); self.pool.shutdown(wait=False, cancel_futures=True); event.accept()


def main():
    # mpv embeds into X11 windows; Omarchy supplies Xwayland for this purpose.
    if sys.platform.startswith('linux') and os.environ.get('DISPLAY'):
        os.environ['QT_QPA_PLATFORM'] = 'xcb'
    app = QApplication(sys.argv); app.setApplicationName('little-screen'); app.setDesktopFileName('little-screen')
    window = Library(); window.show(); app.exec()

if __name__ == '__main__': main()
