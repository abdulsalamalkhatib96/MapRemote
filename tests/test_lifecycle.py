import importlib, io, os, socket, tempfile, unittest
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
    def test_reusable_port_after_closed_connection(self):
        with socket.socket() as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(('127.0.0.1',0))
            server.listen()
            port=server.getsockname()[1]
            with socket.create_connection(('127.0.0.1',port)) as client:
                accepted,_=server.accept()
                with accepted:
                    accepted.shutdown(socket.SHUT_WR)
                    self.assertEqual(client.recv(1), b'')
                    client.shutdown(socket.SHUT_WR)
                    self.assertEqual(accepted.recv(1), b'')
        self.app.ensure_listener_available(port,timeout=0)

    def test_real_listener_is_not_overwritten(self):
        with socket.socket() as server:
            server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            server.bind(('127.0.0.1',0)); server.listen()
            port=server.getsockname()[1]
            with self.assertRaisesRegex(ValueError,'occupied by another listener'):
                self.app.ensure_listener_available(port,timeout=0)
            with socket.create_connection(('127.0.0.1',port)):
                accepted,_=server.accept()
                accepted.close()

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
