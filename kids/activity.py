"""Local desktop-time totals. No window titles, URLs, audio or screenshots."""
import datetime as dt
import json
from pathlib import Path
import re
import subprocess
import time
from control import atomic_json

STATE = Path('/var/lib/omarchy-kids-control')


def properties(command):
    reply = subprocess.run(command, check=True, capture_output=True, text=True, timeout=5)
    return dict(line.split('=', 1) for line in reply.stdout.splitlines() if '=' in line)


def sessions(uid):
    data = properties(['/usr/bin/loginctl', 'show-user', str(uid), '--property=Sessions'])
    result = []
    for session in data.get('Sessions', '').split()[:32]:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', session):
            continue
        info = properties(['/usr/bin/loginctl', 'show-session', session,
                           '--property=User', '--property=Type', '--property=Active',
                           '--property=LockedHint', '--property=IdleHint', '--property=VTNr'])
        if info.get('User') == str(uid):
            result.append((session, info))
    return result


def active(uid):
    return any(info.get('Type') in ('wayland', 'x11') and info.get('Active') == 'yes'
               and info.get('LockedHint') == 'no' and info.get('IdleHint') == 'no'
               for _, info in sessions(uid))


def read(directory=STATE):
    try:
        return json.loads((directory/'screen-time.json').read_text())
    except FileNotFoundError:
        return {'days': {}, 'updated': None}


def summary(directory=STATE, today=None):
    today = today or dt.date.today()
    data = read(directory)
    days = [{'date': (today-dt.timedelta(days=n)).isoformat(),
             'seconds': data['days'].get((today-dt.timedelta(days=n)).isoformat(), 0)} for n in range(6, -1, -1)]
    return {'today_seconds': days[-1]['seconds'], 'week_seconds': sum(d['seconds'] for d in days),
            'days': days, 'updated': data['updated'], 'available': data['updated'] is not None,
            'measurement': 'Unlocked, non-idle desktop time; approximate.'}


class Meter:
    def __init__(self, directory=STATE):
        self.directory = directory
        self.previous = None

    def sample(self, using, monotonic, wall):
        data = read(self.directory)
        if self.previous:
            before_using, before_mono, before_wall = self.previous
            elapsed = monotonic-before_mono
            # No sleep/offline catch-up, clock-jump catch-up, or double counting
            # for multiple sessions. Unknown or failed samples break the interval.
            if using and before_using and 0 <= elapsed <= 45 and abs((wall-before_wall)-elapsed) <= 2:
                start = wall-int(elapsed)
                while start < wall:
                    date = dt.datetime.fromtimestamp(start).date()
                    midnight = dt.datetime.combine(date+dt.timedelta(days=1), dt.time()).timestamp()
                    end = min(wall, midnight)
                    key = date.isoformat()
                    data['days'][key] = min(86400, data['days'].get(key, 0)+int(end-start))
                    start = end
        self.previous = (using, monotonic, wall)
        cutoff = (dt.datetime.fromtimestamp(wall).date()-dt.timedelta(days=30)).isoformat()
        data['days'] = {k:v for k,v in data['days'].items() if k >= cutoff}
        data['updated'] = int(wall)
        atomic_json(self.directory/'screen-time.json', data)


def main():
    from native_runtime import account
    uid = account()['uid']
    meter = Meter()
    while True:
        try:
            from access_control import desired
            using = not desired() and active(uid)
            meter.sample(using, time.monotonic(), time.time())
        except (OSError, ValueError, subprocess.SubprocessError):
            meter.previous = None
        time.sleep(15)


if __name__ == '__main__':
    main()
