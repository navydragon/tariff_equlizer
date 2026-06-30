import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import sqlite3
from core.management.rzd_paths import RZD_TABLE, get_rzd_db_path

conn = sqlite3.connect(get_rzd_db_path())
cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{RZD_TABLE}")')]
out = Path(__file__).with_name("rzd_columns.txt")
out.write_text("\n".join(cols), encoding="utf-8")
print(f"wrote {len(cols)} columns to {out}")
