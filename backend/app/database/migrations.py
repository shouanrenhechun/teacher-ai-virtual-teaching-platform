"""Versioned, transactional SQLite upgrades with an online backup before edits."""
from datetime import datetime, UTC
from pathlib import Path
import sqlite3
from hashlib import sha256


def _content_digest(conn, table, columns):
    quoted = ','.join('"' + name.replace('"', '""') + '"' for name in columns)
    table = table.replace('"', '""')
    digest = sha256()
    for row in conn.execute(f'SELECT {quoted} FROM "{table}" ORDER BY {quoted}'):
        digest.update(repr(row).encode('utf-8'))
        digest.update(b'\n')
    return digest.digest()


def migrate(engine):
    from ..models import Evaluation
    path = engine.url.database
    if not path or path == ':memory:':
        return
    path = Path(path)
    if not path.exists():
        return
    with sqlite3.connect(path) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'teaching_sessions' not in tables:
            return
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        if version > 2:
            raise RuntimeError('数据库版本高于当前程序支持版本，请使用兼容版本启动')
        if version == 2:
            return
        backup = path.with_name(path.name + '.' + datetime.now(UTC).strftime('%Y%m%d%H%M%S%f') + '.v1.bak')
        with sqlite3.connect(backup) as destination:
            conn.backup(destination)
        counts = {table: conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] for table in tables if not table.startswith('sqlite_')}
        original_columns = {table: [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')] for table in counts}
        digests = {table: _content_digest(conn, table, columns) for table, columns in original_columns.items()}
        conn.execute('PRAGMA foreign_keys=OFF')
        conn.execute('BEGIN IMMEDIATE')
        try:
            for table, definitions in {
                'teaching_sessions': {'owner_hash': 'VARCHAR(64)', 'version': 'INTEGER NOT NULL DEFAULT 0'},
                'dialogue_records': {'request_id': 'VARCHAR(64)', 'response_metadata': 'TEXT'},
            }.items():
                columns = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
                for name, definition in definitions.items():
                    if name not in columns:
                        conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
            conn.execute('CREATE INDEX IF NOT EXISTS ix_teaching_sessions_owner_hash ON teaching_sessions(owner_hash)')
            conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_dialogue_request ON dialogue_records(session_id, request_id)')
            if 'evaluations' in tables:
                from sqlalchemy.schema import CreateTable
                ddl = str(CreateTable(Evaluation.__table__).compile(engine))
                conn.execute(ddl.replace('CREATE TABLE evaluations', 'CREATE TABLE evaluations_v2', 1))
                old = [r[1] for r in conn.execute('PRAGMA table_info(evaluations)')]
                added = [name for name in ('rubric_version', 'evidence_json') if name not in old]
                fields = ','.join(old + added)
                expressions = ','.join(old + ['1' if name == 'rubric_version' else "'{}'" for name in added])
                conn.execute(f'INSERT INTO evaluations_v2 ({fields}) SELECT {expressions} FROM evaluations')
                conn.execute('DROP TABLE evaluations')
                conn.execute('ALTER TABLE evaluations_v2 RENAME TO evaluations')
            for table, count in counts.items():
                if conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] != count:
                    raise RuntimeError('Migration row count changed: ' + table)
                if _content_digest(conn, table, original_columns[table]) != digests[table]:
                    raise RuntimeError('Migration changed original records: ' + table)
            if list(conn.execute('PRAGMA foreign_key_check')):
                raise RuntimeError('Migration foreign key validation failed')
            conn.execute('PRAGMA user_version=2')
            conn.commit()
        except Exception:
            conn.rollback()
            raise
