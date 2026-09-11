"""Minimal local storage health check."""
import sqlite3
from pathlib import Path
db=Path(__file__).resolve().parents[1] / 'data' / 'helios.db'
if not db.exists(): raise SystemExit('Database missing; run scripts/init_database.py')
with sqlite3.connect(db) as con: print({'database':'healthy','cameras':con.execute('SELECT count(*) FROM cameras').fetchone()[0]})
