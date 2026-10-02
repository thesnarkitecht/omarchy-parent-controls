"""Record a verified permanent deployment in the next laptop release."""
import json
from pathlib import Path
import sys
from urllib.request import build_opener, HTTPSHandler, HTTPRedirectHandler, ProxyHandler

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'kids'))
from family import parent_origin

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Deployment redirects are not allowed')

def main():
    endpoint = parent_origin(sys.argv[1])
    opener = build_opener(ProxyHandler({}), HTTPSHandler(), NoRedirect())
    with opener.open(endpoint+'/health', timeout=15) as response:
        body = response.read(4097)
    if len(body) > 4096 or json.loads(body) != {'service': 'parent-pocket-relay', 'version': 2}:
        raise ValueError('The address is not the expected deployed relay')
    (ROOT/'remote-service.json').write_text(json.dumps({'version': 2, 'endpoint': endpoint})+'\n')
    print('Recorded verified relay address. Run live acceptance before publishing the laptop release.')

if __name__ == '__main__': main()
