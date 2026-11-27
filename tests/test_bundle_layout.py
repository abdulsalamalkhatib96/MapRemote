import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from bundle_layout import normalize_links, validate_links

class BundleLayoutTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "bin").mkdir()
        (self.root / "lib").mkdir()

    def test_relative_runtime_link_preserved(self):
        target = self.root / "bin" / "python3.12"
        target.touch()
        link = self.root / "bin" / "python3"
        link.symlink_to("python3.12")
        normalize_links(self.root)
        validate_links(self.root)
        self.assertEqual(os.readlink(link), "python3.12")

    def test_absolute_internal_link_rebased(self):
        target = self.root / "lib" / "real.dylib"
        target.touch()
        link = self.root / "lib" / "alias.dylib"
        link.symlink_to(target)
        normalize_links(self.root)
        validate_links(self.root)
        self.assertEqual(os.readlink(link), "real.dylib")

    def test_removed_launcher_alias(self):
        link = self.root / "bin" / "pip"
        link.symlink_to("pip3")
        self.assertEqual(normalize_links(self.root), ["bin/pip"])
        self.assertFalse(link.is_symlink())

    def test_missing_runtime_binary_is_fatal(self):
        (self.root / "bin" / "python3").symlink_to("missing")
        with self.assertRaisesRegex(RuntimeError, "Unresolved runtime symlink"):
            normalize_links(self.root)

    def test_escaping_link_is_fatal(self):
        (self.root / "lib" / "external").symlink_to(sys.executable)
        with self.assertRaisesRegex(RuntimeError, "escapes bundle"):
            normalize_links(self.root)
