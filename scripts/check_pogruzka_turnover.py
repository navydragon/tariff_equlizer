from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CandidateColumn:
    table: str
    column: str


def _list_tables(cur: sqlite3.Cursor) -> list[str]:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    return [row[0] for row in cur.fetchall()]


def _table_info(cur: sqlite3.Cursor, table: str) -> list[tuple[int, str, str]]:
    safe = table.replace("'", "''")
    cur.execute("PRAGMA table_info('%s')" % safe)
    # cid, name, type, notnull, dflt_value, pk
    return [(int(row[0]), str(row[1]), str(row[2] or "")) for row in cur.fetchall()]


def _table_columns(cur: sqlite3.Cursor, table: str) -> list[str]:
    return [name for _cid, name, _typ in _table_info(cur, table)]


def _find_column(cols: list[str], pattern: str) -> str | None:
    rx = re.compile(pattern, flags=re.IGNORECASE)
    for c in cols:
        if rx.search(c):
            return c
    return None


def _sum(cur: sqlite3.Cursor, table: str, expr: str) -> float:
    # sqlite can store numbers as text; cast defensively
    safe = table.replace("'", "''")
    cur.execute(f"SELECT SUM(CAST({expr} AS REAL)) FROM '{safe}'")
    row = cur.fetchone()
    return float(row[0] or 0.0)


def _sum_where(cur: sqlite3.Cursor, table: str, expr: str, where_sql: str) -> float:
    safe = table.replace("'", "''")
    cur.execute(f"SELECT SUM(CAST({expr} AS REAL)) FROM '{safe}' WHERE {where_sql}")
    row = cur.fetchone()
    return float(row[0] or 0.0)


def _count_where(cur: sqlite3.Cursor, table: str, where_sql: str) -> int:
    safe = table.replace("'", "''")
    cur.execute(f"SELECT COUNT(1) FROM '{safe}' WHERE {where_sql}")
    row = cur.fetchone()
    return int(row[0] or 0)


def main() -> None:
    db_path = Path("databases/02_2026-06-22.db")
    if not db_path.is_file():
        raise SystemExit(f"DB not found: {db_path.resolve()}")

    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        tables = _list_tables(cur)

        # Heuristics: look for tables that contain both "Погруз" and "% L"
        candidates: list[tuple[str, str, str]] = []
        for t in tables:
            cols = _table_columns(cur, t)
            pogruz = _find_column(cols, r"^20(25|26)\s*погруз|погруз")
            coef25 = _find_column(cols, r"2025.*% *l|2025.*год\\год|2025.*год/год|turnover_change_coef_2025")
            coef26 = _find_column(cols, r"2026.*% *l|2026.*год\\год|2026.*год/год|turnover_change_coef_2026")
            if pogruz and (coef25 or coef26):
                candidates.append((t, pogruz, coef26 or coef25 or ""))

        print(f"Tables: {len(tables)}; candidates: {len(candidates)}")
        for t, pogruz, coef in candidates[:30]:
            print(f"- {t}: pogruz_col='{pogruz}', coef_col='{coef}'")

        # Preferred table name if present
        preferred = None
        for name in tables:
            if re.search(r"RZD_2026|routes|route|марш|rzd", name, re.IGNORECASE):
                preferred = name
                break

        table = preferred or (candidates[0][0] if candidates else None)
        if table is None:
            raise SystemExit("No table candidates found (no columns matching Погруз/%L).")

        cols = _table_columns(cur, table)
        pogruz_2025 = _find_column(cols, r"^2025\s*погруз")
        pogruz_2026 = _find_column(cols, r"^2026\s*погруз")
        coef_2025 = _find_column(cols, r"2025.*% *l|2025.*год\\год|2025.*год/год|turnover_change_coef_2025")
        coef_2026 = _find_column(cols, r"2026.*% *l|2026.*год\\год|2026.*год/год|turnover_change_coef_2026")

        print(f"\nUsing table: {table}")
        print("Resolved columns:")
        print("- pogruz_2025:", pogruz_2025)
        print("- pogruz_2026:", pogruz_2026)
        print("- coef_2025:", coef_2025)
        print("- coef_2026:", coef_2026)

        if not pogruz_2025 or not pogruz_2026:
            raise SystemExit(
                "Could not resolve both '2025 Погрузка' and '2026 Погрузка' columns in chosen table."
            )

        # Try to auto-detect a column that contains 'уголь' (for coal filter).
        # Avoid expensive COUNT scans per column: sample a few thousand rows and look for matches.
        info = _table_info(cur, table)
        all_cols = [name for _cid, name, _typ in info]
        sample_limit = 5000
        safe_table = table.replace("'", "''")
        cur.execute(f"SELECT * FROM '{safe_table}' LIMIT {sample_limit}")
        rows = cur.fetchall()
        coal_hits: dict[str, int] = {}
        for row in rows:
            for idx, value in enumerate(row):
                if not isinstance(value, str):
                    continue
                if "уголь" in value.lower():
                    col = all_cols[idx] if idx < len(all_cols) else f"col_{idx}"
                    coal_hits[col] = coal_hits.get(col, 0) + 1

        coal_col = max(coal_hits.items(), key=lambda kv: kv[1])[0] if coal_hits else None
        coal_where = f'LOWER(\"{coal_col}\") LIKE \"%уголь%\"' if coal_col else None

        if coal_col:
            print("\nCoal filter detected:")
            print(f"- coal_col: {coal_col}")
            print(f"- sample_hits (in first {sample_limit} rows): {coal_hits.get(coal_col, 0)}")
        else:
            print("\nCoal filter detected: NONE (no TEXT columns matched 'уголь').")

        s25 = _sum(cur, table, f"\"{pogruz_2025}\"")
        s26 = _sum(cur, table, f"\"{pogruz_2026}\"")

        # "умноженные на соотв. коэффициент": interpret as row-wise multiplication
        # sum(Погрузка_год * coef_год)
        s25c = _sum(cur, table, f"\"{pogruz_2025}\" * \"{coef_2025}\"") if coef_2025 else None
        s26c = _sum(cur, table, f"\"{pogruz_2026}\" * \"{coef_2026}\"") if coef_2026 else None

        # Also compute "2025 * coef_2026" as common interpretation for projecting 2026
        s25_to_26 = _sum(cur, table, f"\"{pogruz_2025}\" * \"{coef_2026}\"") if coef_2026 else None

        print("\nSums:")
        print(f"- sum(pogruz_2025) = {s25:.6f}")
        print(f"- sum(pogruz_2026) = {s26:.6f}")
        if s25c is not None:
            print(f"- sum(pogruz_2025 * coef_2025) = {s25c:.6f}")
        if s26c is not None:
            print(f"- sum(pogruz_2026 * coef_2026) = {s26c:.6f}")
        if s25_to_26 is not None:
            print(f"- sum(pogruz_2025 * coef_2026) = {s25_to_26:.6f}")

        print("\nComparisons:")
        if s25_to_26 is not None:
            diff = s26 - s25_to_26
            rel = (diff / s26 * 100.0) if s26 else 0.0
            print(
                f"- sum(pogruz_2026) ?= sum(pogruz_2025 * coef_2026): "
                f"diff={diff:.6f} ({rel:.4f}%)"
            )
        if s26c is not None and s26:
            diff2 = s26c - s26
            print(f"- sum(pogruz_2026 * coef_2026) - sum(pogruz_2026): {diff2:.6f}")

        if coal_where is not None:
            print("\n=== COAL ONLY (уголь) ===")
            s25_coal = _sum_where(cur, table, f"\"{pogruz_2025}\"", coal_where)
            s26_coal = _sum_where(cur, table, f"\"{pogruz_2026}\"", coal_where)
            s25_to_26_coal = (
                _sum_where(cur, table, f"\"{pogruz_2025}\" * \"{coef_2026}\"", coal_where)
                if coef_2026
                else None
            )
            print(f"- sum(pogruz_2025) = {s25_coal:.6f}")
            print(f"- sum(pogruz_2026) = {s26_coal:.6f}")
            if s25_to_26_coal is not None:
                diffc = s26_coal - s25_to_26_coal
                relc = (diffc / s26_coal * 100.0) if s26_coal else 0.0
                print(
                    f"- sum(pogruz_2026) ?= sum(pogruz_2025 * coef_2026): "
                    f"diff={diffc:.6f} ({relc:.4f}%)"
                )
    finally:
        con.close()


if __name__ == "__main__":
    main()

