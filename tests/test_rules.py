import unittest, tempfile
from pathlib import Path
from rules import normalize, map_url, save, load

def rule(source='https://api.example.com/v1',destination='http://127.0.0.1:8000/api',**kw):
    return dict(name='',enabled=True,source=source,destination=destination,method='*',match='prefix',query='preserve',preserve_host=False)|kw

def cfg(*rules,enabled=True): return normalize(dict(enabled=enabled,port=9090,rules=list(rules)))
class RulesTest(unittest.TestCase):
    def test_prefix(self): self.assertEqual(map_url(cfg(rule()),'https://api.example.com/v1/users?a=1','POST')[0],'http://127.0.0.1:8000/api/users?a=1')
    def test_boundary(self): self.assertIsNone(map_url(cfg(rule()),'https://api.example.com/v10','GET'))
    def test_root(self): self.assertEqual(map_url(cfg(rule(source='https://api.example.com',destination='http://localhost:8000')),'https://api.example.com/a/b','GET')[0],'http://localhost:8000/a/b')
    def test_exact(self): self.assertIsNone(map_url(cfg(rule(match='exact')),'https://api.example.com/v1/a','GET'))
    def test_method(self): self.assertIsNone(map_url(cfg(rule(method='POST')),'https://api.example.com/v1','GET'))
    def test_order(self): self.assertEqual(map_url(cfg(rule(),rule(destination='http://localhost:9000')),'https://api.example.com/v1','GET')[2],0)
    def test_disabled(self): self.assertIsNone(map_url(cfg(rule(),enabled=False),'https://api.example.com/v1','GET'))
    def test_disabled_rule(self): self.assertEqual(map_url(cfg(rule(enabled=False),rule()),'https://api.example.com/v1','GET')[2],1)
    def test_wildcard(self):
        c=cfg(rule(source='https://*.example.com'))
        self.assertIsNotNone(map_url(c,'https://x.example.com/test','GET'))
        self.assertIsNone(map_url(c,'https://example.com/test','GET'))
        self.assertIsNone(map_url(c,'https://badexample.com/test','GET'))
    def test_query(self): self.assertEqual(map_url(cfg(rule(destination='http://localhost:8000/a?b=2',query='replace')),'https://api.example.com/v1?a=1','GET')[0],'http://localhost:8000/a?b=2')
    def test_port_scheme(self):
        self.assertIsNone(map_url(cfg(rule()),'https://api.example.com:444/v1','GET'))
        self.assertIsNone(map_url(cfg(rule()),'http://api.example.com/v1','GET'))
    def test_keep_host(self): self.assertTrue(map_url(cfg(rule(preserve_host=True)),'https://api.example.com/v1','GET')[1])
    def test_bad_destination(self):
        for dest in ('ftp://example.com','http://user:pass@example.com','http://localhost:9090','http://*.example.com','http://example.com/#x'):
            with self.subTest(dest=dest), self.assertRaises(ValueError): cfg(rule(destination=dest))
    def test_persist(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'rules.json'; c=cfg(rule());save(p,c);self.assertEqual(load(p),c)
    def test_encoded(self): self.assertEqual(map_url(cfg(rule()),'https://api.example.com/v1/a%2Fb?q=x%20y','GET')[0],'http://127.0.0.1:8000/api/a%2Fb?q=x%20y')
if __name__=='__main__': unittest.main()
