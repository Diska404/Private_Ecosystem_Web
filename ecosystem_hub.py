"""Local Work & Setting ecosystem landing page, localhost-only, read-only status."""
from __future__ import annotations
import json, mimetypes, os, urllib.request, urllib.parse, threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT=Path(__file__).resolve().parent
WEB=(ROOT/'hub').resolve()
from ecosystem import registry, apps_status, identity, authorized_shutdown
PORT=registry()['hub']['port']
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}))

class Handler(BaseHTTPRequestHandler):
    server_version='LocalWorkHub/2.1.0'
    def do_GET(self):
        path=urllib.parse.urlsplit(self.path).path
        if path=='/api/health': return self.send_json({'ok':True,**identity('hub')})
        if path=='/ecosystem-nav.js':
            return self.reply((ROOT/'ecosystem-nav.js').read_bytes(),200,'text/javascript; charset=utf-8')
        if path=='/ecosystem-nav.css':
            return self.reply((ROOT/'ecosystem-nav.css').read_bytes(),200,'text/css; charset=utf-8')
        if path=='/api/apps':
            return self.send_json(apps_status())
        if path=='/': path='/index.html'
        target=(WEB/path.lstrip('/')).resolve()
        if not target.is_relative_to(WEB) or not target.is_file(): return self.send_json({'error':'Not found'},404)
        typ=mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
        if target.suffix in ('.html','.js','.css','.svg'):typ+='; charset=utf-8'
        self.reply(target.read_bytes(),200,typ)
    def do_POST(self):
        if self.path!='/api/ecosystem/shutdown': return self.send_json({'error':'Not found'},404)
        if not authorized_shutdown(self.headers): return self.send_json({'error':'Launcher ownership required'},403)
        self.send_json({'ok':True},202)
        threading.Thread(target=self.server.shutdown,daemon=True).start()
    def send_json(self,obj,status=200):self.reply(json.dumps(obj,separators=(',',':')).encode(),status,'application/json; charset=utf-8')
    def reply(self,data,status,ctype):
        self.send_response(status)
        for name,val in [('Content-Type',ctype),('Content-Length',str(len(data))),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),('X-Frame-Options','DENY'),('Referrer-Policy','no-referrer'),('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:")]:self.send_header(name,val)
        self.end_headers()
        try:self.wfile.write(data)
        except (ConnectionError,BrokenPipeError):pass
    def log_message(self,format,*args):pass

if __name__=='__main__':
    print(f'\nLOCAL WORK & SETTING | http://127.0.0.1:{PORT} | Ctrl+C untuk menutup',flush=True)
    with ThreadingHTTPServer(('127.0.0.1',PORT),Handler) as server:
        server.serve_forever()
