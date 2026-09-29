"""m010_promo_source_axis regression test.

Runs the real migration body against a throwaway SQLite database (the same
engine LNbits uses) with the ``events.events`` schema prefix stripped, since
that prefix only resolves inside LNbits' ATTACHed connection.

Asserts the legacy ``type`` axis is fully converted, the "TICKETID" sentinel
code is cleared, codes/counters survive, and a second run is a no-op.
15 assertions across three tests.
"""
import asyncio
import json
import sqlite3
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
MIGRATIONS = TESTS_DIR.parent / "migrations.py"


class MappingRow(dict):
    """Mimics SQLAlchemy's RowMapping, which is what ``db.fetchall`` returns when
    no ``model=`` is passed: values are read BY COLUMN NAME, and iterating the
    row yields column NAMES rather than values. A plain-tuple stub hides the
    bug where a migration unpacks rows positionally and silently converts
    nothing."""


class DB:
    """Minimal stand-in for the migration's ``db`` handle."""

    def __init__(self, conn):
        self.conn = conn

    async def fetchall(self, query):
        cur = self.conn.execute(query)
        cols = [d[0] for d in cur.description]
        return [MappingRow(zip(cols, values)) for values in cur.fetchall()]

    async def execute(self, query, params=None):
        self.conn.execute(query, params or {})
        self.conn.commit()


def load_migration():
    src = MIGRATIONS.read_text()
    body = src.split("async def m010_promo_source_axis(db):", 1)[1]
    body = body.replace("events.events", "events")
    # Deliberately do NOT seed the namespace with anything: the real
    # migrations module has no module-level imports, so a migration that
    # relies on a name it never imports must fail here too.
    namespace = {}
    exec("async def m010(db):" + body, namespace)  # noqa: S102 - test harness
    return namespace["m010"]


EVENTS = {
    "EV-A": {
        "promo_codes": [
            {"code": "SAVE21", "discount_percent": 21.0, "active": True,
             "combinable": False, "max_uses": 50, "used_count": 7, "type": "code",
             "redemptions_per_ticket": 1, "ticket_type_ids": ["tt1"],
             "max_tickets": None},
            {"code": "TICKETID", "discount_percent": 50.0, "active": True,
             "combinable": False, "max_uses": None, "used_count": 0,
             "type": "ticket", "redemptions_per_ticket": 1,
             "ticket_type_ids": None, "max_tickets": 1},
        ]
    },
    # A hand-written promo with no `type` at all (missing type meant "code").
    "EV-B": {"promo_codes": [{"code": "WELOVEJAM", "discount_percent": 100.0,
                              "active": True, "combinable": True, "max_uses": 1,
                              "used_count": 1}]},
    # Already on the final axis: must be left exactly as-is.
    "EV-C": {"promo_codes": [{"code": "NEW", "source": {"require_ticket": True,
                                                       "move": True}}]},
    # The INTERMEDIATE revision (`source.kind`) — what the live DB holds after
    # the first deploy. Must convert to require_ticket.
    "EV-E": {"promo_codes": [{"code": "UPGRADE50", "discount_percent": 10.0,
                              "active": True, "combinable": False,
                              "source": {"kind": "ticket", "event_ids": ["X"],
                                         "ticket_type_ids": None,
                                         "move": True, "credit": "paid"}},
                             {"code": "PLAIN", "discount_percent": 5.0,
                              "active": True, "combinable": True,
                              "source": {"kind": "code", "event_ids": None,
                                         "ticket_type_ids": None,
                                         "move": False, "credit": "none"}}]},
    "EV-D": {},
}


def _seed_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE events (id TEXT PRIMARY KEY, extra TEXT)")
    for eid, extra in EVENTS.items():
        conn.execute("INSERT INTO events VALUES (?, ?)", (eid, json.dumps(extra)))
    conn.commit()
    return conn


def _rows(conn):
    return dict(conn.execute("SELECT id, extra FROM events").fetchall())


def _run_migration(conn):
    m010 = load_migration()
    asyncio.run(m010(DB(conn)))


def test_migration_removes_legacy_and_intermediate_axes():
    conn = _seed_conn()
    _run_migration(conn)
    rows = _rows(conn)
    all_promos = [p for ev in rows.values() for p in json.loads(ev).get("promo_codes", [])]

    assert not any("type" in p for p in all_promos), (
        "no promo is left on the legacy type axis"
    )
    assert all("source" in p for p in all_promos), "every promo now has a source"
    assert not any("kind" in p["source"] for p in all_promos), (
        "no promo is left on the intermediate 'kind' discriminator"
    )


def test_migration_converts_type_values_and_preserves_settings():
    conn = _seed_conn()
    _run_migration(conn)
    rows = _rows(conn)
    a = json.loads(rows["EV-A"])
    b = json.loads(rows["EV-B"])
    c = json.loads(rows["EV-C"])
    e = json.loads(rows["EV-E"])

    code_promo, ticket_promo = a["promo_codes"]
    assert code_promo["source"]["require_ticket"] is False, (
        f"type=code -> require_ticket False ({json.dumps(code_promo['source'])})"
    )
    assert ticket_promo["source"]["require_ticket"] is True, (
        f"type=ticket -> require_ticket True ({json.dumps(ticket_promo['source'])})"
    )
    assert (ticket_promo["source"]["move"] is False
            and ticket_promo["source"]["credit"] == "none"
            and ticket_promo["source"]["event_ids"] is None), (
        "legacy ticket rule gets move=False, credit='none', same-event scope"
    )
    assert ticket_promo["code"] == "", (
        f"TICKETID sentinel code cleared ({ticket_promo['code']!r})"
    )
    assert (code_promo["max_uses"] == 50 and code_promo["used_count"] == 7
            and code_promo["ticket_type_ids"] == ["tt1"]
            and ticket_promo["max_tickets"] == 1), (
        "promo settings preserved (max_uses/used_count/target scope)"
    )
    assert b["promo_codes"][0]["source"]["require_ticket"] is False, (
        f"hand-written promo with no type -> require_ticket False "
        f"({json.dumps(b['promo_codes'][0].get('source'))})"
    )
    assert c["promo_codes"][0]["source"] == {"require_ticket": True, "move": True}, (
        f"promo already on the final axis is untouched "
        f"({json.dumps(c['promo_codes'][0]['source'])})"
    )

    upg, _plain = e["promo_codes"]
    assert upg["source"]["require_ticket"] is True, (
        f"intermediate kind='ticket' -> require_ticket True ({json.dumps(upg['source'])})"
    )
    assert (upg["source"]["move"] is True
            and upg["source"]["credit"] == "paid"
            and upg["source"]["event_ids"] == ["X"]
            and upg["code"] == "UPGRADE50"), (
        f"intermediate conversion keeps the rule's ticket settings ({json.dumps(upg)})"
    )
    assert e["promo_codes"][1]["source"]["require_ticket"] is False, (
        f"intermediate kind='code' -> require_ticket False "
        f"({json.dumps(e['promo_codes'][1]['source'])})"
    )


def test_migration_leaves_empty_event_and_is_idempotent():
    conn = _seed_conn()
    _run_migration(conn)
    rows = _rows(conn)
    assert json.loads(rows["EV-D"]) == {}, "event with no promos is left alone"

    snapshot = json.dumps({k: json.loads(v) for k, v in rows.items()}, sort_keys=True)
    _run_migration(conn)
    again = json.dumps(
        {k: json.loads(v) for k, v in _rows(conn).items()}, sort_keys=True
    )
    assert again == snapshot, "re-running the migration is a no-op"
