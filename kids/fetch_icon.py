"""Fetch same-origin webapp icons as the unprivileged webapp worker."""
from html.parser import HTMLParser
import os
from pathlib import Path
import re
import sys
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

def main():
    key, url = sys.argv[1:]
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,31}',key): raise SystemExit(1)
    origin = urlsplit(url)
    def allowed(value):
        p=urlsplit(value)
        return p.scheme=='https' and p.netloc==origin.netloc
    class Redirects(HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            if not allowed(newurl): raise ValueError('Cross-origin icon redirect')
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    opener=build_opener(Redirects())
    def fetch(value):
        if not allowed(value): raise ValueError('Unapproved icon origin')
        with opener.open(Request(value,headers={'User-Agent':'Mozilla/5.0'}),timeout=8) as r:
            data=r.read(1024*1024+1)
            if len(data)>1024*1024: raise ValueError('Icon too large')
            return data
    icons=[]
    class Links(HTMLParser):
        def handle_starttag(self,tag,attrs):
            a=dict(attrs)
            if tag=='link' and 'icon' in a.get('rel','').lower() and a.get('href'):
                value=urljoin(url,a['href'])
                if allowed(value): icons.append(value)
    try: Links().feed(fetch(url).decode('utf-8',errors='replace'))
    except Exception: pass
    from PySide6.QtGui import QImage
    for value in list(reversed(icons))+[urljoin(url,'/favicon.ico')]:
        try:
            image=QImage.fromData(fetch(value))
            if image.isNull(): continue
            path=Path('/var/lib/omarchy-kids/icons')/(key+'.png')
            temporary=path.with_suffix('.tmp.png')
            if not image.scaled(192,192).save(str(temporary),'PNG'): continue
            temporary.chmod(0o644); os.replace(temporary,path)
            return
        except Exception: continue
    raise SystemExit(1)

if __name__=='__main__': main()
