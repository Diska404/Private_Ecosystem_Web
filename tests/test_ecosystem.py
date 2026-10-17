"""Regression coverage for service discovery and safe ownership checks."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import ecosystem as eco
import service_manager as manager


class RegistryTests(unittest.TestCase):
    def test_all_urls_are_loopback(self):
        self.assertTrue(all(v['url'].startswith('http://127.0.0.1:') for v in eco.registry().values()))

    def test_dynamic_ports(self):
        with patch.dict(os.environ, {'ECOSYSTEM_PORT':'18764','ECOSYSTEM_AI_PORT':'18765','ECOSYSTEM_SIGNALDECK_PORT':'18767'}):
            ports=eco.registry()
            self.assertEqual(ports['ai']['url'],'http://127.0.0.1:18765/')
            self.assertEqual(ports['hub']['port'],18764)

    def test_bad_ports_rejected(self):
        for value in ['0','65536','8080.5','invalid']:
            with self.subTest(value=value),patch.dict(os.environ,{'ECOSYSTEM_PORT':value}):
                with self.assertRaises(ValueError): eco.registry()

    def test_duplicate_ports_rejected(self):
        with patch.dict(os.environ,{'ECOSYSTEM_PORT':'19000','ECOSYSTEM_AI_PORT':'19000'}):
            with self.assertRaises(ValueError): eco.registry()

    def test_custom_registry(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'registry.json'
            path.write_text(json.dumps({'services':{k:{'name':k,'port':19000+i} for i,k in enumerate(eco.KINDS)}}))
            with patch.dict(os.environ,{'ECOSYSTEM_CONFIG':str(path)}):
                self.assertEqual(eco.registry()['ai']['port'],19001)


class IdentityTests(unittest.TestCase):
    def test_actual_http_probe_rejects_old_wrong_and_foreign_services(self):
        for health,expected in [
            ({'ok':True,'time':123},'conflict'),
            ({'service':'local-ai-control-center','version':'2.0.0'},'outdated'),
            ({**eco.identity('ai'),'ok':True,'workspace':'another-folder'},'outdated'),
            ({**eco.identity('ai'),'ok':True},'online')]:
            class Fixture(BaseHTTPRequestHandler):
                def do_GET(self):
                    data=json.dumps(health).encode();self.send_response(200);self.end_headers();self.wfile.write(data)
                def log_message(self,*args):pass
            with self.subTest(expected=expected),ThreadingHTTPServer(('127.0.0.1',0),Fixture) as server:
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                port=server.server_port
                try:
                    item={**eco.registry()['ai'],'port':port,'url':f'http://127.0.0.1:{port}/'}
                    self.assertEqual(eco.probe(item)['state'],expected)
                finally:
                    server.shutdown();thread.join()

    def test_identity_does_not_expose_secret(self):
        with patch.dict(os.environ,{'ECOSYSTEM_CONTROL_TOKEN':'test-secret'}):
            self.assertNotIn('test-secret',json.dumps(eco.identity('hub')))

    def test_shutdown_requires_token_and_no_origin(self):
        with patch.dict(os.environ,{'ECOSYSTEM_CONTROL_TOKEN':'test-secret'}):
            self.assertFalse(eco.authorized_shutdown({}))
            self.assertFalse(eco.authorized_shutdown({'X-Ecosystem-Token':'wrong'}))
            self.assertFalse(eco.authorized_shutdown({'X-Ecosystem-Token':'test-secret','Origin':'http://evil.example'}))
            self.assertTrue(eco.authorized_shutdown({'X-Ecosystem-Token':'test-secret'}))

    def test_unmanaged_service_cannot_be_stopped(self):
        with patch.dict(os.environ,{'ECOSYSTEM_CONTROL_TOKEN':''}):
            self.assertFalse(eco.authorized_shutdown({'X-Ecosystem-Token':'anything'}))

    def test_manager_refuses_foreign_instance(self):
        item=eco.registry()['ai']
        with patch.object(manager,'read_owner',return_value={'instance':'ours','token':'secret'}),patch.object(manager,'probe',return_value={'state':'online','compatible':True,'health':{'instance':'foreign'}}):
            with self.assertRaisesRegex(RuntimeError,'bukan instance'): manager.stop_service('ai',item)

    def test_manager_leaves_foreign_port_untouched(self):
        with patch.object(manager,'probe',return_value={'state':'conflict'}),patch.object(manager,'python_for') as prepare:
            with self.assertRaises(RuntimeError):manager.start_service('ai',eco.registry()['ai'],eco.registry())
            prepare.assert_not_called()


if __name__=='__main__':unittest.main()
