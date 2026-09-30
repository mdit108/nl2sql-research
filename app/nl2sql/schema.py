"""Structured schema context (E1-E3). Read from PostgreSQL's catalog, never retrieved by similarity.

The whole schema (9 tables) fits comfortably in a prompt, so E1-E3 always show all of it.
"""

from dataclasses import dataclass, field
from functools import lru_cache

import yaml
from sqlalchemy import text

from app.database import owner_engine
from app.retrieval.knowledge import SEMANTIC_DIR


@dataclass
class Column:
    name: str
    data_type: str
    is_pk: bool = False
    references: str | None = None  # "table.column"


@dataclass
class Table:
    name: str
    columns: list[Column] = field(default_factory=list)


@lru_cache
def load_schema() -> tuple[Table, ...]:
    with owner_engine().connect() as conn:
        cols = conn.execute(text("""
            SELECT table_name, column_name,
                   CASE WHEN data_type = 'character' THEN 'char(' || character_maximum_length || ')'
                        WHEN data_type = 'numeric' THEN 'numeric(' || numeric_precision || ',' || numeric_scale || ')'
                        WHEN data_type = 'timestamp without time zone' THEN 'timestamp'
                        ELSE data_type END AS data_type
            FROM information_schema.columns
            WHERE table_schema = 'olist'
            ORDER BY table_name, ordinal_position""")).all()
        pks = {(r.table_name, r.column_name) for r in conn.execute(text("""
            SELECT tc.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu USING (constraint_schema, constraint_name)
            WHERE tc.table_schema = 'olist' AND tc.constraint_type = 'PRIMARY KEY'"""))}
        fks = {(r.src_table, r.src_col): f"{r.dst_table}.{r.dst_col}" for r in conn.execute(text("""
            SELECT cl.relname AS src_table, a.attname AS src_col, fcl.relname AS dst_table, fa.attname AS dst_col
            FROM pg_constraint c
            JOIN pg_class cl ON cl.oid = c.conrelid
            JOIN pg_class fcl ON fcl.oid = c.confrelid
            JOIN pg_namespace n ON n.oid = cl.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
            JOIN pg_attribute fa ON fa.attrelid = c.confrelid AND fa.attnum = c.confkey[1]
            WHERE c.contype = 'f' AND n.nspname = 'olist'"""))}
    tables: dict[str, Table] = {}
    for r in cols:
        tables.setdefault(r.table_name, Table(r.table_name)).columns.append(
            Column(r.column_name, r.data_type, (r.table_name, r.column_name) in pks,
                   fks.get((r.table_name, r.column_name))))
    return tuple(tables.values())


@lru_cache
def load_descriptions() -> dict:
    return yaml.safe_load((SEMANTIC_DIR / "descriptions.yaml").read_text())["tables"]


@lru_cache
def load_relationships() -> list[dict]:
    return yaml.safe_load((SEMANTIC_DIR / "relationships.yaml").read_text())["relationships"]


def table_names() -> set[str]:
    return {t.name for t in load_schema()}


def render_schema(tables: tuple[Table, ...], relational: bool, descriptive: bool,
                  descriptions: dict | None = None, relationships: list[dict] | None = None) -> str:
    """E1: names + types. E2: + PK/FK markers and a relationships list. E3: + descriptions."""
    descriptions = descriptions or {}
    lines = ["All tables are in schema `olist` (the search_path is set, so `orders` works)."]
    for t in tables:
        lines.append("")
        header = f"TABLE {t.name}"
        if descriptive and t.name in descriptions:
            header += f"  -- {descriptions[t.name]['description']}"
        lines.append(header)
        for c in t.columns:
            line = f"  {c.name} {c.data_type}"
            if relational and c.is_pk:
                line += " PK"
            if relational and c.references:
                line += f" FK -> {c.references}"
            if descriptive:
                desc = descriptions.get(t.name, {}).get("columns", {}).get(c.name)
                if desc:
                    line += f"  -- {desc}"
            lines.append(line)
    if relational and relationships:
        lines += ["", "RELATIONSHIPS (from -> to, cardinality):"]
        for r in relationships:
            line = f"  {r['from']} -> {r['to']} ({r['cardinality']})"
            if r.get("note"):
                line += f"  -- {r['note']}"
            lines.append(line)
    return "\n".join(lines)
