"""Build a deterministic source release and a checksum-pinned HTTPS bootstrap."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

ROOT=Path(__file__).resolve().parents[1]
FOLDERS={'bin','kids','native','integration','systemd','tests','packaging','.github','voice','docs'}
FILES={'manifest.json','Controls.qml','BarWidget.qml','install.sh','README.md','SECURITY.md','VALIDATION.md','FAMILY.md','FAMILY-VALIDATION.md','LICENSE'}

def source_files(root):
    for path in sorted(root.rglob('*')):
        relative=path.relative_to(root)
        if path.is_symlink(): raise ValueError('Release sources must not contain symlinks: '+str(relative))
        if not path.is_file() or '__pycache__' in relative.parts or path.suffix=='.pyc': continue
        if (len(relative.parts)==1 and relative.name in FILES) or (relative.parts[0] in FOLDERS):
            yield path,relative

def build(repository,output,root=ROOT):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9][A-Za-z0-9._-]{0,99}',repository):
        raise ValueError('Use a GitHub OWNER/REPOSITORY, without a URL or shell characters.')
    owner=repository.split('/')[0]
    manifest=json.loads((root/'manifest.json').read_text())
    version=manifest['version']
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.]+)?',version): raise ValueError('Invalid release version')
    plugin_id=owner.lower()+'.kids-lockdown'
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if output.resolve().is_relative_to(root.resolve()): raise ValueError('Write release artifacts outside the source tree.')
    archive=output/('omarchy-parent-controls-'+version+'.tar.gz')
    with archive.open('wb') as raw:
        with gzip.GzipFile(fileobj=raw,mode='wb',mtime=0,filename='') as compressed:
            with tarfile.open(fileobj=compressed,mode='w') as bundle:
                for path,relative in source_files(root):
                    text=path.read_text().replace(manifest['id'],plugin_id)
                    if relative.as_posix()=='manifest.json':
                        value=json.loads(text);value['author']=owner;text=json.dumps(value,indent=2)+'\n'
                    data=text.encode()
                    item=tarfile.TarInfo('omarchy-parent-controls/'+relative.as_posix())
                    item.size=len(data);item.mode=0o755 if relative.parts[0]=='bin' or relative.name=='install.sh' else 0o644
                    item.mtime=0;item.uid=item.gid=0;item.uname=item.gname='root'
                    bundle.addfile(item,io.BytesIO(data))
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (output/'SHA256SUMS').write_text(digest+'  '+archive.name+'\n')
    url='https://github.com/'+repository+'/releases/download/v'+version+'/'+archive.name
    bootstrap='''#!/usr/bin/bash
set -euo pipefail
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
curl -q --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --tlsv1.2 \\
  '@URL@' --output "$tmp/release.tar.gz"
printf '%s  %s\\n' '@SHA@' "$tmp/release.tar.gz" | sha256sum --check --status
tar --extract --gzip --file "$tmp/release.tar.gz" --directory "$tmp" --no-same-owner
bash "$tmp/omarchy-parent-controls/install.sh" "$@" </dev/tty
'''.replace('@URL@',url).replace('@SHA@',digest)
    (output/'bootstrap.sh').write_text(bootstrap)
    (output/'bootstrap.sh').chmod(0o755)
    (output/'release.json').write_text(json.dumps({'repository':repository,'version':version,'plugin_id':plugin_id,'archive':archive.name,'sha256':digest},indent=2)+'\n')
    return archive

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--repository',required=True)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    print(build(args.repository,args.output))
