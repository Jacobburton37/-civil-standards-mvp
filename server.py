from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import json
import mimetypes
import socket
import os
import sqlite3
from datetime import datetime, timezone

from db import connect, init_db

BASE = Path(__file__).resolve().parent
STATIC = BASE / 'static'


def rowdict(row):
    return dict(row) if row is not None else None


def json_bytes(obj):
    return json.dumps(obj, ensure_ascii=False).encode('utf-8')


class AppHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        clean = urlparse(path).path
        if clean == '/':
            clean = '/index.html'
        target = (STATIC / clean.lstrip('/')).resolve()
        if STATIC.resolve() not in target.parents and target != STATIC.resolve():
            return str(STATIC / 'index.html')
        return str(target)

    def send_json(self, obj, status=200):
        data = json_bytes(obj)
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def read_json(self):
        length = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(length) if length else b'{}'
        return json.loads(raw.decode('utf-8'))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        if path.startswith('/api/'):
            try:
                return self.handle_api_get(path, qs)
            except Exception as exc:
                return self.send_json({'error': str(exc)}, 500)
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if not parsed.path.startswith('/api/'):
            return self.send_error(404)
        try:
            return self.handle_api_post(parsed.path)
        except json.JSONDecodeError:
            return self.send_json({'error': 'Invalid JSON body.'}, 400)
        except Exception as exc:
            return self.send_json({'error': str(exc)}, 500)

    def handle_api_get(self, path, qs):
        conn = connect()
        try:
            if path == '/api/stats':
                stats = {
                    'jurisdictions': conn.execute('SELECT COUNT(*) n FROM jurisdictions WHERE active=1').fetchone()['n'],
                    'documents': conn.execute('SELECT COUNT(*) n FROM documents WHERE active=1').fetchone()['n'],
                    'verified': conn.execute("SELECT COUNT(*) n FROM documents WHERE active=1 AND status='Verified'").fetchone()['n'],
                    'changes': conn.execute("SELECT COUNT(*) n FROM change_events WHERE review_status='Needs review'").fetchone()['n'],
                }
                return self.send_json(stats)

            if path == '/api/jurisdictions':
                rows = conn.execute('''
                    SELECT j.*,
                           COUNT(d.id) AS document_count,
                           MAX(d.last_verified) AS last_verified
                    FROM jurisdictions j
                    LEFT JOIN documents d ON d.jurisdiction_id=j.id AND d.active=1
                    WHERE j.active=1
                    GROUP BY j.id
                    ORDER BY j.state, j.name
                ''').fetchall()
                return self.send_json([rowdict(r) for r in rows])

            if path == '/api/documents':
                where = ['d.active=1']
                args = []
                q = (qs.get('q', [''])[0] or '').strip()
                if q:
                    like = f'%{q}%'
                    where.append('(d.title LIKE ? OR d.category LIKE ? OR d.discipline LIKE ? OR d.detail_number LIKE ? OR j.name LIKE ?)')
                    args += [like, like, like, like, like]
                jurisdiction_id = (qs.get('jurisdiction_id', [''])[0] or '').strip()
                if jurisdiction_id:
                    where.append('d.jurisdiction_id=?')
                    args.append(jurisdiction_id)
                discipline = (qs.get('discipline', [''])[0] or '').strip()
                if discipline:
                    where.append('d.discipline=?')
                    args.append(discipline)
                category = (qs.get('category', [''])[0] or '').strip()
                if category:
                    where.append('d.category=?')
                    args.append(category)
                sql = f'''
                    SELECT d.*, j.name AS jurisdiction, j.state, j.agency
                    FROM documents d
                    JOIN jurisdictions j ON j.id=d.jurisdiction_id
                    WHERE {' AND '.join(where)}
                    ORDER BY j.name, d.category, d.title
                '''
                rows = conn.execute(sql, args).fetchall()
                return self.send_json([rowdict(r) for r in rows])

            if path.startswith('/api/documents/'):
                doc_id = int(path.rsplit('/', 1)[1])
                doc = conn.execute('''
                    SELECT d.*, j.name AS jurisdiction, j.state, j.agency, j.official_url
                    FROM documents d JOIN jurisdictions j ON j.id=d.jurisdiction_id
                    WHERE d.id=?
                ''', (doc_id,)).fetchone()
                if not doc:
                    return self.send_json({'error': 'Document not found.'}, 404)
                versions = conn.execute('''SELECT * FROM versions WHERE document_id=? ORDER BY detected_at DESC''', (doc_id,)).fetchall()
                changes = conn.execute('''SELECT * FROM change_events WHERE document_id=? ORDER BY detected_at DESC''', (doc_id,)).fetchall()
                payload = rowdict(doc)
                payload['versions'] = [rowdict(r) for r in versions]
                payload['changes'] = [rowdict(r) for r in changes]
                return self.send_json(payload)

            if path == '/api/changes':
                rows = conn.execute('''
                    SELECT c.*, d.title, d.source_url, j.name AS jurisdiction, j.state
                    FROM change_events c
                    JOIN documents d ON d.id=c.document_id
                    JOIN jurisdictions j ON j.id=d.jurisdiction_id
                    ORDER BY c.detected_at DESC
                    LIMIT 100
                ''').fetchall()
                return self.send_json([rowdict(r) for r in rows])

            if path == '/api/filters':
                disciplines = [r['discipline'] for r in conn.execute('SELECT DISTINCT discipline FROM documents WHERE active=1 ORDER BY discipline')]
                categories = [r['category'] for r in conn.execute('SELECT DISTINCT category FROM documents WHERE active=1 ORDER BY category')]
                return self.send_json({'disciplines': disciplines, 'categories': categories})

            return self.send_json({'error': 'Not found.'}, 404)
        finally:
            conn.close()

    def handle_api_post(self, path):
        conn = connect()
        try:
            if path == '/api/jurisdictions':
                body = self.read_json()
                required = ['state', 'name']
                missing = [k for k in required if not body.get(k)]
                if missing:
                    return self.send_json({'error': f"Missing: {', '.join(missing)}"}, 400)
                try:
                    cur = conn.execute('''
                        INSERT INTO jurisdictions(state, name, jurisdiction_type, agency, official_url)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (body['state'].upper(), body['name'], body.get('jurisdiction_type', 'County'), body.get('agency'), body.get('official_url')))
                    conn.commit()
                except sqlite3.IntegrityError:
                    return self.send_json({'error': 'That jurisdiction already exists.'}, 409)
                return self.send_json({'id': cur.lastrowid, 'ok': True}, 201)

            if path == '/api/documents':
                body = self.read_json()
                required = ['jurisdiction_id', 'title', 'category', 'discipline', 'source_url']
                missing = [k for k in required if not body.get(k)]
                if missing:
                    return self.send_json({'error': f"Missing: {', '.join(missing)}"}, 400)
                cur = conn.execute('''
                    INSERT INTO documents(
                        jurisdiction_id, title, category, discipline, detail_number,
                        source_url, file_type, revision_label, status, last_verified, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    body['jurisdiction_id'], body['title'], body['category'], body['discipline'],
                    body.get('detail_number'), body['source_url'], body.get('file_type', 'Web'),
                    body.get('revision_label'), body.get('status', 'Needs verification'), None,
                    body.get('notes')
                ))
                conn.commit()
                return self.send_json({'id': cur.lastrowid, 'ok': True}, 201)

            if path.startswith('/api/changes/') and path.endswith('/review'):
                change_id = int(path.split('/')[3])
                body = self.read_json()
                status = body.get('review_status')
                if status not in {'Approved', 'Rejected', 'Needs review'}:
                    return self.send_json({'error': 'Invalid review_status.'}, 400)
                conn.execute('UPDATE change_events SET review_status=? WHERE id=?', (status, change_id))
                conn.commit()
                return self.send_json({'ok': True})

            return self.send_json({'error': 'Not found.'}, 404)
        finally:
            conn.close()


if __name__ == '__main__':
    init_db()
    mimetypes.add_type('application/manifest+json', '.webmanifest')
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', '8000'))
    print(f'CivilStandards running on this Mac at http://127.0.0.1:{port}')
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(('8.8.8.8', 80))
        lan_ip = sock.getsockname()[0]
        sock.close()
        print(f'iPhone/iPad on the same Wi-Fi: http://{lan_ip}:{port}')
    except OSError:
        pass
    ThreadingHTTPServer((host, port), AppHandler).serve_forever()
