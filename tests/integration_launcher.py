import json, os, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'kids'))
import native_runtime as runtime
with tempfile.TemporaryDirectory(prefix='launcher-check-') as folder:
    root=Path(folder)
    user=root/'user'; system=root/'system'; overlay=root/'overlay'
    (user/'applications').mkdir(parents=True)
    runtime.LAUNCHERS=system/'applications/omarchy-kids'
    runtime.LAUNCHERS.mkdir(parents=True)
    overlay.mkdir()
    qml=root/'shell.qml'
    qml.write_text('''import QtQuick
import Quickshell
ShellRoot {
  Timer { interval: 200; running: true; repeat: true
    onTriggered: console.log("ENTRIES=" + JSON.stringify(DesktopEntries.applications.values.map(e => ({id: e.id, name: e.name}))))
  }
}
''')
    output=root/'observer.log'
    env={**os.environ,'QT_QPA_PLATFORM':'offscreen','XDG_DATA_HOME':str(user),'XDG_DATA_DIRS':str(system)}
    with output.open('w') as log:
        process=subprocess.Popen(['/usr/bin/qs','--no-color','-p',str(qml)],env=env,stdout=log,stderr=log)
        def entries():
            lines=[line.split('ENTRIES=',1)[1] for line in output.read_text().splitlines() if 'ENTRIES=' in line]
            return json.loads(lines[-1]) if lines else None
        def wait_for(wanted):
            until=time.monotonic()+10
            while time.monotonic()<until:
                value=entries()
                if value is not None and {x['name'] for x in value}==wanted: return value
                time.sleep(.1)
            raise AssertionError(output.read_text())
        try:
            wait_for(set())
            # Keep a watch on the original folder, as with a mounted overlay.
            (user/'applications').rename(user/'applications-old')
            (user/'applications').mkdir()
            runtime.APPS=user/'applications'
            runtime.CHROME_POLICY=root/'chrome.json'
            runtime.browser_policy=lambda p: None
            runtime.subprocess=type('NoIconFetch',(),{'run':staticmethod(lambda *a,**k:None)})
            runtime.desktop_entries({'webapps':[{'id':'github','name':'GitHub','url':'https://github.com'}]})
            observed=wait_for({'GitHub'})
            assert observed==[{'id':'omarchy-kids-webapp-github','name':'GitHub'}], observed
            print('PASS: running Quickshell discovers GitHub without restarting after application folder replacement')
            runtime.desktop_entries({'webapps':[]})
            wait_for(set())
            print('PASS: removal updates the same running launcher')
            # Off mode: no controlled overlay, normal system entry still works.
            runtime.APPS=overlay
            runtime.desktop_entries({'webapps':[{'id':'github','name':'GitHub','url':'https://github.com'}]})
            wait_for({'GitHub'})
            print('PASS: webapp visible with no controlled overlay')
            # Model the off transition: detach the hidden overlay and reconnect
            # the shell's watcher to the original installed application folder.
            normal = user/'applications-old'/'original-editor.desktop'
            normal.write_text('[Desktop Entry]\nType=Application\nName=Original editor\nExec=/usr/bin/true\n')
            (user/'applications').rename(user/'controlled-applications')
            (user/'applications-old').rename(user/'applications')
            process.terminate()
            process.wait(timeout=5)
            log.flush()
            process=subprocess.Popen(['/usr/bin/qs','--no-color','-p',str(qml)],env=env,stdout=log,stderr=log)
            wait_for({'Original editor', 'GitHub'})
            assert normal.with_name('original-editor.desktop').name in [p.name for p in (user/'applications').iterdir()]
            print('PASS: reconnecting launcher restores existing installed apps after removing overlay')
        finally:
            process.terminate()
            process.wait(timeout=5)
