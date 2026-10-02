import hashlib
import importlib.util
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import os
import shutil
import subprocess
import sys

SOURCE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('build_release',SOURCE/'packaging/build_release.py')
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)

class ReleaseTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform=='linux' and shutil.which('sha256sum'),'Bootstrap targets Linux coreutils')
    def test_tampered_download_never_reaches_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            archive=release.build('example/parent-controls',root/'release')
            marker=root/'extracted'
            environment={**os.environ,'TEST_ARCHIVE':str(archive),'TEST_MARKER':str(marker)}
            harness='''curl() { cp "$TEST_ARCHIVE" "${@: -1}"; }; export -f curl
tar() { printf called > "$TEST_MARKER"; return 42; }; export -f tar
bash "$1"
'''
            command=['bash','-c',harness,'bootstrap-test',str(archive.parent/'bootstrap.sh')]
            valid=subprocess.run(command,env=environment,capture_output=True,text=True)
            self.assertEqual(valid.returncode,42,valid.stderr)
            self.assertTrue(marker.exists())
            marker.unlink()
            archive.write_bytes(archive.read_bytes()+b'changed')
            tampered=subprocess.run(command,env=environment,capture_output=True,text=True)
            self.assertNotEqual(tampered.returncode,0)
            self.assertFalse(marker.exists())

    def test_bundle_is_reproducible_and_bootstrap_pins_its_actual_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            one=release.build('example/parent-controls',Path(folder)/'one')
            two=release.build('example/parent-controls',Path(folder)/'two')
            self.assertEqual(one.read_bytes(),two.read_bytes())
            digest=hashlib.sha256(one.read_bytes()).hexdigest()
            bootstrap=(one.parent/'bootstrap.sh').read_text()
            self.assertIn(digest,bootstrap)
            self.assertLess(bootstrap.index('sha256sum --check'),bootstrap.index('tar --extract'))
            with tarfile.open(one) as bundle:
                names=bundle.getnames()
                self.assertTrue(all(n.startswith('omarchy-parent-controls/') and '..' not in Path(n).parts for n in names))
                self.assertFalse(any('__pycache__' in n for n in names))
                self.assertIn('omarchy-parent-controls/packaging/remove.py',names)
                for relative in ('kids/hermes_cli.py', 'kids/coding.py', 'kids/family.py',
                                 'systemd/omarchy-kids-remote.service', 'packaging/install_voice.py',
                                 'voice/school_voice/parent_controls.py', 'voice/scripts/setup-desktop.py',
                                 'FAMILY.md', 'docs/validation/url-approval-validation.json'):
                    self.assertIn('omarchy-parent-controls/' + relative, names)
                manifest=json.load(bundle.extractfile('omarchy-parent-controls/manifest.json'))
                self.assertEqual(manifest['id'],'example.kids-lockdown')
                launcher=bundle.extractfile('omarchy-parent-controls/bin/omarchy-kids').read()
                self.assertIn(b'example.kids-lockdown',launcher)
                setup=bundle.extractfile('omarchy-parent-controls/packaging/setup.py').read()
                self.assertIn(b"PLUGIN_ID = 'example.kids-lockdown'",setup)

    def test_repository_injection_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            for value in ['https://github.com/a/b','a/b; id','a/../b',"a/b'",'a/$(id)']:
                with self.assertRaises(ValueError): release.build(value,Path(folder))

    def test_release_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'escape').symlink_to('/etc/passwd')
            with self.assertRaises(ValueError): list(release.source_files(root))
