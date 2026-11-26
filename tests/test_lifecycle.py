import importlib, io, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

class LifecycleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        with patch('pathlib.Path.home', return_value=Path(cls.temp.name)):
            cls.app = importlib.import_module('app')
    @classmethod
    def tearDownClass(cls):
        cls.app.cleanup(); cls.app.LOCK.close(); cls.temp.cleanup()
    def setUp(self):
        self.app.PROC=None; self.app.SYSTEM_ACTIVE=False; self.app.LAST_ERROR=''
    def fake(self):
        proc=MagicMock(); proc.pid=1234; proc.poll.return_value=None; proc.stdout=io.BytesIO()
        return proc
    def test_start_stop(self):
        p=self.fake()
        with patch.object(self.app,'engine',return_value='/fake/mitmdump'),patch.object(self.app.socket,'socket'),patch.object(self.app.socket,'create_connection'),patch.object(self.app.subprocess,'Popen',return_value=p),patch.object(self.app.sp,'enable') as enable,patch.object(self.app.sp,'wait_restore',return_value=True) as restore:
            self.app.start(); enable.assert_called_once_with(1234,self.app.CONFIG['port']); self.assertTrue(self.app.SYSTEM_ACTIVE)
            self.app.stop(); p.terminate.assert_called_once(); restore.assert_called_once(); self.assertFalse(self.app.SYSTEM_ACTIVE)
    def test_engine_startup_error_is_reported_without_system_proxy(self):
        p=self.fake(); p.poll.return_value=1
        p.stdout=io.BytesIO(b'Addon error: regression sentinel\n')
        with patch.object(self.app,'engine',return_value='/fake/mitmdump'),patch.object(self.app.socket,'socket'),patch.object(self.app.subprocess,'Popen',return_value=p),patch.object(self.app.sp,'enable') as enable:
            with self.assertRaisesRegex(ValueError,'regression sentinel'):
                self.app.start()
            enable.assert_not_called()
            self.assertIsNone(self.app.PROC)
            self.assertIn('regression sentinel',self.app.LAST_ERROR)
    def test_cancel_permission_terminates_engine(self):
        p=self.fake()
        with patch.object(self.app,'engine',return_value='/fake/mitmdump'),patch.object(self.app.socket,'socket'),patch.object(self.app.socket,'create_connection'),patch.object(self.app.subprocess,'Popen',return_value=p),patch.object(self.app.sp,'enable',side_effect=ValueError('cancelled')):
            with self.assertRaisesRegex(ValueError,'cancelled'): self.app.start()
            p.terminate.assert_called_once(); self.assertIsNone(self.app.PROC); self.assertFalse(self.app.SYSTEM_ACTIVE)
    def test_restore_failure_reported(self):
        self.app.PROC=self.fake(); self.app.SYSTEM_ACTIVE=True
        with patch.object(self.app.sp,'wait_restore',return_value=False):
            with self.assertRaisesRegex(ValueError,'restore'): self.app.stop()
        self.assertIn('Recover',self.app.LAST_ERROR)
    def test_recover_command(self):
        with patch.object(self.app.sp,'helper',return_value=Path('/a b/ProxyHelper')),patch.object(self.app.sp,'admin') as admin:
            self.app.sp.recover(); admin.assert_called_once(); command=admin.call_args.args[0]; self.assertIn("'/a b/ProxyHelper'",command); self.assertIn('"$d/ProxyHelper" recover',command)
