"""Source monitor for Civil Standards MVP.

Run manually:
    python monitor.py

In production, schedule it (e.g. every 6-24 hours) with cron, GitHub Actions,
or a cloud scheduler. It never auto-approves a changed engineering standard;
it records a change event for human review.
"""
from __future__ import annotations

import hashlib
import io
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from db import connect, init_db

USER_AGENT = 'CivilStandardsMonitor/0.1 (+standards-monitor)'
TIMEOUT = 30


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_html(content: bytes) -> str:
    soup = BeautifulSoup(content, 'html.parser')
    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()
    text = soup.get_text(' ', strip=True)
    return re.sub(r'\s+', ' ', text)


def extract_pdf_text(content: bytes, max_pages: int = 40) -> str:
    reader = PdfReader(io.BytesIO(content))
    chunks = []
    for page in reader.pages[:max_pages]:
        try:
            chunks.append(page.extract_text() or '')
        except Exception:
            pass
    return re.sub(r'\s+', ' ', ' '.join(chunks)).strip()


def fingerprint(content: bytes, content_type: str):
    ctype = (content_type or '').lower()
    if 'html' in ctype:
        normalized = normalize_html(content)
        digest = hashlib.sha256(normalized.encode('utf-8')).hexdigest()
        return digest, normalized[:200000]
    if 'pdf' in ctype or content[:4] == b'%PDF':
        try:
            text = extract_pdf_text(content)
            # Hash extracted text when possible to reduce false positives from PDF metadata.
            if text:
                digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
                return digest, text[:200000]
        except Exception:
            pass
    return hashlib.sha256(content).hexdigest(), ''


def summarize_change(old_text: str, new_text: str) -> str:
    if not old_text or not new_text:
        return 'Official source content changed. Human review required.'
    old_words = old_text.split()
    new_words = new_text.split()
    delta = len(new_words) - len(old_words)
    direction = 'more' if delta > 0 else 'fewer'
    if delta == 0:
        return 'Official source text changed with similar text length. Human review required.'
    return f'Official source text changed ({abs(delta):,} {direction} extracted words). Human review required.'


def check_document(conn, doc):
    print(f"Checking {doc['id']}: {doc['title']}")
    try:
        r = requests.get(doc['source_url'], timeout=TIMEOUT, headers={'User-Agent': USER_AGENT})
        r.raise_for_status()
    except Exception as exc:
        conn.execute("UPDATE documents SET status=? WHERE id=?", (f'Check failed: {type(exc).__name__}', doc['id']))
        conn.commit()
        print(f'  failed: {exc}')
        return

    content_type = r.headers.get('content-type', '').split(';')[0]
    digest, text = fingerprint(r.content, content_type)
    checked = now()
    previous = conn.execute('''
        SELECT * FROM versions WHERE document_id=? AND is_current=1 ORDER BY detected_at DESC LIMIT 1
    ''', (doc['id'],)).fetchone()

    if previous and previous['content_hash'] == digest:
        conn.execute("UPDATE documents SET last_verified=?, status='Verified' WHERE id=?", (checked, doc['id']))
        conn.commit()
        print('  unchanged')
        return

    if previous:
        conn.execute('UPDATE versions SET is_current=0 WHERE document_id=?', (doc['id'],))
        summary = summarize_change(previous['extracted_text'] or '', text)
        conn.execute('''
            INSERT INTO change_events(document_id, detected_at, old_hash, new_hash, summary, review_status)
            VALUES (?, ?, ?, ?, ?, 'Needs review')
        ''', (doc['id'], checked, previous['content_hash'], digest, summary))
        status = 'Change detected'
        print('  CHANGED - review required')
    else:
        status = 'Verified'
        print('  baseline created')

    conn.execute('''
        INSERT INTO versions(document_id, detected_at, revision_label, content_hash, content_type, content_length, extracted_text, is_current)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
    ''', (doc['id'], checked, doc['revision_label'], digest, content_type, len(r.content), text))
    conn.execute('UPDATE documents SET last_verified=?, status=? WHERE id=?', (checked, status, doc['id']))
    conn.commit()


def main():
    init_db()
    conn = connect()
    try:
        docs = conn.execute('SELECT * FROM documents WHERE active=1 ORDER BY id').fetchall()
        for doc in docs:
            check_document(conn, doc)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
