import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import system_proxy as sp

class CertificateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cert = Path(self.temp.name) / 'ca.pem'
        self.cert.write_text('-----BEGIN CERTIFICATE-----\nYWJj\n-----END CERTIFICATE-----\n')
    def test_install_in_user_session(self):
        with patch.object(sp.sys,'platform','darwin'), patch.object(sp,'cert_trusted',side_effect=[False,True]), patch.object(sp,'_security') as security, patch.object(sp,'admin') as admin:
            sp.cert_action(self.cert,True)
            args=security.call_args.args[0]
            self.assertEqual(args[:2], ['add-trusted-cert','-r'])
            self.assertNotIn('-d',args)
            self.assertTrue(args[-2].endswith('login.keychain-db'))
            admin.assert_not_called()
    def test_install_verifies_trust(self):
        with patch.object(sp.sys,'platform','darwin'), patch.object(sp,'cert_trusted',return_value=False), patch.object(sp,'_security'):
            with self.assertRaisesRegex(ValueError,'trust verification failed'):
                sp.cert_action(self.cert,True)
    def test_authorization_failure_explains_interactive_fallback(self):
        with patch.object(sp.sys,'platform','darwin'), patch.object(sp,'cert_trusted',return_value=False), patch.object(sp,'_security',side_effect=ValueError('authorization denied')):
            with self.assertRaisesRegex(ValueError,'Keychain Access'):
                sp.cert_action(self.cert,True)
    def test_legacy_system_trust_not_reported_removed(self):
        with patch.object(sp.sys,'platform','darwin'), patch.object(sp,'cert_trusted',return_value=True), patch.object(sp,'_security',return_value=''):
            with self.assertRaisesRegex(ValueError,'still trusted'):
                sp.cert_action(self.cert,False)
