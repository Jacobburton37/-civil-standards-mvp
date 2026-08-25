import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(os.environ.get('DATABASE_PATH', str(Path(__file__).with_name('standards.db'))))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    conn = connect()
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS jurisdictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        state TEXT NOT NULL,
        name TEXT NOT NULL,
        jurisdiction_type TEXT NOT NULL DEFAULT 'County',
        agency TEXT,
        official_url TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        UNIQUE(state, name)
    );

    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        jurisdiction_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        discipline TEXT NOT NULL,
        detail_number TEXT,
        source_url TEXT NOT NULL,
        file_type TEXT DEFAULT 'Web',
        revision_label TEXT,
        status TEXT NOT NULL DEFAULT 'Verified',
        last_verified TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        notes TEXT,
        FOREIGN KEY(jurisdiction_id) REFERENCES jurisdictions(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER NOT NULL,
        detected_at TEXT NOT NULL,
        revision_label TEXT,
        content_hash TEXT NOT NULL,
        content_type TEXT,
        content_length INTEGER,
        extracted_text TEXT,
        is_current INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS change_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER NOT NULL,
        detected_at TEXT NOT NULL,
        old_hash TEXT,
        new_hash TEXT,
        summary TEXT NOT NULL,
        review_status TEXT NOT NULL DEFAULT 'Needs review',
        FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_documents_jurisdiction ON documents(jurisdiction_id);
    CREATE INDEX IF NOT EXISTS idx_documents_discipline ON documents(discipline);
    CREATE INDEX IF NOT EXISTS idx_documents_category ON documents(category);
    CREATE INDEX IF NOT EXISTS idx_changes_document ON change_events(document_id);
    ''')
    conn.commit()
    seed(conn)
    conn.close()


def seed(conn):
    existing = conn.execute('SELECT COUNT(*) AS n FROM jurisdictions').fetchone()['n']
    if existing:
        return

    jurisdictions = [
        ('MD', 'Anne Arundel County', 'County', 'Department of Public Works',
         'https://www.aacounty.org/public-works/engineering/engineering-construction-standards'),
        ('MD', 'Harford County', 'County', 'Department of Public Works',
         'https://www.harfordcountymd.gov/'),
    ]
    conn.executemany('''
        INSERT INTO jurisdictions(state, name, jurisdiction_type, agency, official_url)
        VALUES (?, ?, ?, ?, ?)
    ''', jurisdictions)

    ids = {r['name']: r['id'] for r in conn.execute('SELECT id, name FROM jurisdictions')}
    now = utc_now()
    docs = [
        (
            ids['Anne Arundel County'],
            'Engineering & Construction Standards - 2024',
            'Standards Library',
            'General',
            None,
            'https://www.aacounty.org/public-works/engineering/engineering-construction-standards/2024-standards',
            'Web',
            '2024 Standards',
            'Verified',
            now,
            'Official county standards landing page. Includes design manual chapters, standard details, and specifications.'
        ),
        (
            ids['Anne Arundel County'],
            'Standard Details for Construction',
            'Standard Details',
            'Civil / Utilities',
            None,
            'https://www.aacounty.org/public-works/engineering/engineering-construction-standards/2024-standards',
            'Web',
            '2024 Standards',
            'Verified',
            now,
            'Official page lists drainage, water, sanitary sewer, paving, roadway/site improvements, traffic, electrical, landscaping, tunneling, and pedestrian details.'
        ),
        (
            ids['Anne Arundel County'],
            'Design Manual - General Instructions',
            'Design Manual',
            'General',
            'Chapter I',
            'https://www.aacounty.org/sites/default/files/2024-04/Chapter_I_General_Instructions.pdf',
            'PDF',
            '2024',
            'Verified',
            now,
            'Official county PDF.'
        ),
        (
            ids['Harford County'],
            'Harford County Book of Standard Details',
            'Standard Details',
            'Civil',
            None,
            'https://www.harfordcountymd.gov/DocumentCenter/View/1639',
            'PDF',
            'Current source',
            'Verified',
            now,
            'Official county standard detail book. Includes general, roads/streets, shoulders, drainage, structures, and additional sections.'
        ),
    ]
    conn.executemany('''
        INSERT INTO documents(
            jurisdiction_id, title, category, discipline, detail_number,
            source_url, file_type, revision_label, status, last_verified, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', docs)
    conn.commit()
