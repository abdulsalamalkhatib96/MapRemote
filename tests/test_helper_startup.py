import subprocess, tempfile, unittest, os, time, shlex
from pathlib import Path
from unittest.mock import patch
import system_proxy as sp

class HelperStartupTest(unittest.TestCase):
    def run_helper(self, script):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); executable=root/'fake helper'
            executable.write_text('#!/bin/sh\n'+script+'\n'); executable.chmod(0o700)
            command=sp.startup_command(executable,os.getpid(),os.getpid(),9090,verify_signature=False)
            # The macOS script is exercised against a harmless fake helper, never real network settings.
            command=command.replace('/private/tmp/mapremote.XXXXXXXX',str(root/'mapremote.XXXXXXXX'))
            return subprocess.run(['/bin/sh','-c',command],capture_output=True,text=True,timeout=5)
    def test_preview_uses_system_pac_not_native_executable(self):
        with patch.object(sp,'helper',return_value=Path('/fake/ProxyHelper')),patch.object(sp,'developer_signed',return_value=False),patch.object(sp,'JOURNAL',Path('/nonexistent-mapremote-native-journal')),patch.object(sp,'pac_command',return_value='PAC') as pac,patch.object(sp,'admin',return_value='OK') as admin:
            self.assertEqual(sp.enable(123,9090,pac_port=49152),'pac')
            pac.assert_called_once_with('run',os.getpid(),123,9090,49152)
            admin.assert_called_once_with('PAC')
    def test_pac_fail_open(self):
        source=sp.pac_source(9090)
        self.assertIn('PROXY 127.0.0.1:9090; DIRECT',source)
        self.assertIn('localhost',source)
        self.assertIn('return "DIRECT"',source)
    def test_production_stage_verifies_both_copies(self):
        cmd=sp.startup_command(Path('/a b/ProxyHelper'),1,2,9090)
        self.assertEqual(cmd.count('/usr/bin/codesign --verify --strict'),2)
        self.assertIn('/usr/bin/ditto',cmd)
        self.assertIn('/usr/bin/cmp -s',cmd)
        self.assertIn('SIGKILL',cmd)
        self.assertNotIn('xattr',cmd)
        self.assertNotIn('codesign --sign',cmd)

    def test_probe_uses_identical_staging(self):
        cmd=sp.probe_command(Path('/a b/ProxyHelper'))
        self.assertTrue(cmd.endswith('"$d/ProxyHelper" self-test'))
        self.assertTrue(cmd.startswith(sp.stage_command(Path('/a b/ProxyHelper'))))

    def test_success(self):
        result=self.run_helper('printf OK > "$5"; sleep 0.3')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout,'OK')
    def test_early_exit_diagnostics(self):
        result=self.run_helper('echo "configuration denied" >&2; exit 7')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('status 7',result.stderr)
        self.assertIn('configuration denied',result.stderr)
    def test_structured_error(self):
        result=self.run_helper('printf "ERROR: invalid session" > "$5"; sleep 0.3')
        self.assertEqual(result.stdout,'ERROR: invalid session')
        with patch.object(sp,'helper',return_value=Path('/fake')),patch.object(sp,'admin',return_value=result.stdout):
            with self.assertRaisesRegex(ValueError,'invalid session'): sp.enable(123,9090)
    def test_timeout_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); executable=root/'fake'; executable.write_text('#!/bin/sh\necho "locking preferences" >&2\nsleep 1\n'); executable.chmod(0o700)
            cmd=sp.startup_command(executable,1,2,9090,verify_signature=False).replace('/private/tmp/mapremote.XXXXXXXX',str(root/'mapremote.XXXXXXXX')).replace('-lt 400','-lt 2')
            result=subprocess.run(['/bin/sh','-c',cmd],capture_output=True,text=True,timeout=4)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('locking preferences',result.stderr)
            self.assertIn('did not become ready',result.stderr)

    def test_no_external_nohup_and_survives_hangup(self):
        cmd = sp.startup_command(Path('/fake'), 1, 2, 9090)
        self.assertNotIn('/usr/bin/nohup ', cmd)
        result = self.run_helper('kill -HUP $$; printf OK > "$5"; sleep 0.3')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'OK')

    def test_helper_continues_after_launcher_exits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / 'fake helper'
            marker = root / 'finished'
            executable.write_text('#!/bin/sh\nprintf OK > "$5"\nsleep 0.7\nprintf survived > ' + shlex.quote(str(marker)) + '\n')
            executable.chmod(0o700)
            cmd = sp.startup_command(executable, os.getpid(), os.getpid(), 9090, verify_signature=False)
            cmd = cmd.replace('/private/tmp/mapremote.XXXXXXXX', str(root / 'mapremote.XXXXXXXX'))
            result = subprocess.run(['/bin/sh', '-c', cmd], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5, start_new_session=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, 'OK')
            deadline = time.monotonic() + 3
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertEqual(marker.read_text(), 'survived')
