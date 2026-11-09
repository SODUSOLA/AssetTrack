"""The admin's rule (SPEC v1.1): the system records no monetary values anywhere.

These tests fail if a price, cost, amount, invoice or currency ever reappears in the database
schema or in the public API, so reintroducing money has to be a deliberate, visible decision.
"""

import re

from sqlalchemy import Engine, text

from app.main import app

PRICING = re.compile(
    r"cost|price|pricing|invoice|amount|currency|spend|naira|payment|billing", re.IGNORECASE
)


def test_database_has_no_pricing_objects(engine: Engine) -> None:
    queries = {
        "table": "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'",
        "column": "SELECT table_name || '.' || column_name FROM information_schema.columns "
        "WHERE table_schema = 'public'",
        "type": "SELECT typname FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
        "WHERE n.nspname = 'public' AND t.typtype = 'e'",
        "enum value": "SELECT enumlabel FROM pg_enum",
        "function": "SELECT proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public'",
        "constraint": "SELECT conname FROM pg_constraint c JOIN pg_namespace n "
        "ON n.oid = c.connamespace WHERE n.nspname = 'public'",
        "index": "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'",
        "trigger": "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal",
    }
    offenders = []
    with engine.connect() as conn:
        for kind, sql in queries.items():
            for (name,) in conn.execute(text(sql)):
                if PRICING.search(name):
                    offenders.append(f"{kind}: {name}")
    assert offenders == []


def _names_in_openapi(node, found: list[str]) -> None:
    """Collect property, parameter, schema and path names (not free-text descriptions)."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"properties", "schemas", "paths"} and isinstance(value, dict):
                found.extend(value.keys())
            if key == "parameters" and isinstance(value, list):
                found.extend(p.get("name", "") for p in value if isinstance(p, dict))
            _names_in_openapi(value, found)
    elif isinstance(node, list):
        for item in node:
            _names_in_openapi(item, found)


def test_api_exposes_no_pricing_fields_or_routes() -> None:
    names: list[str] = []
    _names_in_openapi(app.openapi(), names)
    assert len(names) > 20  # sanity: the walker really found names
    assert [n for n in names if PRICING.search(n)] == []
