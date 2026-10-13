async def m001_initial(db):
    await db.execute(
        """
        CREATE TABLE events.events (
            id TEXT PRIMARY KEY,
            wallet TEXT NOT NULL,
            name TEXT NOT NULL,
            info TEXT NOT NULL,
            closing_date TEXT NOT NULL,
            event_start_date TEXT NOT NULL,
            event_end_date TEXT NOT NULL,
            amount_tickets INTEGER NOT NULL,
            price_per_ticket INTEGER NOT NULL,
            sold INTEGER NOT NULL,
            time TIMESTAMP NOT NULL DEFAULT """
        + db.timestamp_now
        + """
        );
    """
    )

    await db.execute(
        """
        CREATE TABLE events.tickets (
            id TEXT PRIMARY KEY,
            wallet TEXT NOT NULL,
            event TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            registered BOOLEAN NOT NULL,
            time TIMESTAMP NOT NULL DEFAULT """
        + db.timestamp_now
        + """
        );
    """
    )


async def m002_changed(db):
    await db.execute(
        """
        CREATE TABLE events.ticket (
            id TEXT PRIMARY KEY,
            wallet TEXT NOT NULL,
            event TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            registered BOOLEAN NOT NULL,
            paid BOOLEAN NOT NULL,
            time TIMESTAMP NOT NULL DEFAULT """
        + db.timestamp_now
        + """
        );
    """
    )

    for row in [list(row) for row in await db.fetchall("SELECT * FROM events.tickets")]:
        usescsv = ""

        for i in range(row[5]):
            if row[7]:
                usescsv += "," + str(i + 1)
            else:
                usescsv += "," + str(1)
        usescsv = usescsv[1:]
        await db.execute(
            """
            INSERT INTO events.ticket (
                id,
                wallet,
                event,
                name,
                email,
                registered,
                paid
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (row[0], row[1], row[2], row[3], row[4], row[5], True),
        )
    await db.execute("DROP TABLE events.tickets")


async def m003_add_register_timestamp(db):
    """
    Add a column to register the timestamp of ticket register
    """
    await db.execute(
        "ALTER TABLE events.ticket ADD COLUMN reg_timestamp TIMESTAMP;"
    )  # NULL means not registered, or old ticket


async def m004_add_currency(db):
    """
    Add a currency table to allow fiat denomination
    of tickets. Make price a float.
    """
    await db.execute("ALTER TABLE events.events RENAME TO events_old")
    await db.execute(
        """
        CREATE TABLE events.events (
            id TEXT PRIMARY KEY,
            wallet TEXT NOT NULL,
            name TEXT NOT NULL,
            info TEXT NOT NULL,
            closing_date TEXT NOT NULL,
            event_start_date TEXT NOT NULL,
            event_end_date TEXT NOT NULL,
            currency TEXT NOT NULL,
            amount_tickets INTEGER NOT NULL,
            price_per_ticket REAL NOT NULL,
            sold INTEGER NOT NULL,
            time TIMESTAMP NOT NULL DEFAULT """
        + db.timestamp_now
        + """
        );
    """
    )

    for row in [
        list(row) for row in await db.fetchall("SELECT * FROM events.events_old")
    ]:
        await db.execute(
            """
                    INSERT INTO events.events (
                        id,
                        wallet,
                        name,
                        info,
                        closing_date,
                        event_start_date,
                        event_end_date,
                        currency,
                        amount_tickets,
                        price_per_ticket,
                        sold
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
            (
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
                row[5],
                row[6],
                "sat",
                row[7],
                row[8],
                row[9],
            ),
        )

    await db.execute("DROP TABLE events.events_old")


async def m005_add_image_banner(db):
    """
    Add a column to allow an image banner for the event
    """
    await db.execute("ALTER TABLE events.events ADD COLUMN banner TEXT;")


async def m006_add_extra_fields(db):
    """
    Add a canceled and 'extra' column to events and ticket tables
    to support promo codes and ticket metadata.
    """
    # Add canceled and 'extra' columns to events table
    await db.execute(
        "ALTER TABLE events.events ADD COLUMN canceled BOOLEAN NOT NULL DEFAULT FALSE;"
    )
    await db.execute("ALTER TABLE events.events ADD COLUMN extra TEXT;")

    # Add 'extra' column to ticket table
    await db.execute("ALTER TABLE events.ticket ADD COLUMN extra TEXT;")


async def m007_add_allow_fiat(db):
    """
    Add an allow_fiat column so event owners can explicitly enable fiat checkout.
    """
    await db.execute("""
        ALTER TABLE events.events
        ADD COLUMN allow_fiat BOOLEAN NOT NULL DEFAULT FALSE;
        """)


async def m008_add_fiat_currency(db):
    """
    Add a fiat_currency column for sat-denominated events using fiat checkout.
    """
    await db.execute("""
        ALTER TABLE events.events
        ADD COLUMN fiat_currency TEXT NOT NULL DEFAULT 'GBP';
        """)


async def m009_ticket_types_and_baskets(db):
    from sqlalchemy.exc import OperationalError

    await db.execute("""
        CREATE TABLE IF NOT EXISTS events.ticket_types (
            id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            image_url TEXT,
            price REAL NOT NULL DEFAULT 0,
            max_tickets INTEGER NOT NULL DEFAULT 0,
            sold INTEGER NOT NULL DEFAULT 0,
            available_from TEXT NOT NULL,
            available_to TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            extra TEXT
        );
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS events.baskets (
            id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL,
            wallet TEXT NOT NULL,
            email TEXT NOT NULL,
            name TEXT NOT NULL,
            promo_codes TEXT,
            payment_method TEXT,
            fiat_provider TEXT,
            nostr_identifier TEXT,
            refund_address TEXT,
            satspay_charge_id TEXT,
            paid BOOLEAN NOT NULL DEFAULT FALSE,
            time TIMESTAMP NOT NULL DEFAULT """
        + db.timestamp_now
        + """
        );
    """)
    for alter in [
        "ALTER TABLE events.events ADD COLUMN admin_email TEXT;",
        "ALTER TABLE events.events DROP COLUMN closing_date;",
        "ALTER TABLE events.ticket ADD COLUMN ticket_type_id TEXT;",
        "ALTER TABLE events.ticket ADD COLUMN basket_id TEXT;",
    ]:
        try:
            await db.execute(alter)
        except OperationalError:
            pass

    import json

    events_rows = await db.fetchall("SELECT id, extra FROM events.events")
    for row in events_rows:
        event_id = row["id"]
        extra_str = row["extra"]
        if not extra_str:
            continue
        try:
            extra = json.loads(extra_str)
        except (json.JSONDecodeError, TypeError):
            continue
        ticket_waves = extra.get("ticket_waves", []) or []
        sort_order = 0
        for wave in ticket_waves:
            await db.execute(
                """
                INSERT INTO events.ticket_types (
                    id, event_id, name, description,
                    image_url, price, max_tickets, sold,
                    available_from, available_to,
                    sort_order, extra
                )
                VALUES (:id, :event_id, :name, :description,
                    :image_url, :price, :max_tickets, :sold,
                    :available_from, :available_to,
                    :sort_order, :extra)
                """,
                {
                    "id": wave.get("id", ""),
                    "event_id": event_id,
                    "name": wave.get("title", "General Admission"),
                    "description": "",
                    "image_url": wave.get("ticket_image_id"),
                    "price": wave.get("price_per_ticket", 0),
                    "max_tickets": wave.get("amount_tickets", 0),
                    "sold": 0,
                    "available_from": wave.get("opening_date", ""),
                    "available_to": wave.get("closing_date", ""),
                    "sort_order": sort_order,
                    "extra": "{}",
                },
            )
            sort_order += 1

        extra.pop("ticket_waves", None)
        await db.execute(
            "UPDATE events.events SET extra = :extra WHERE id = :id",
            {"extra": json.dumps(extra), "id": event_id},
        )


async def m010_promo_source_axis(db):
    """
    Move promo codes onto the offer-code + ticket-requirement axis.

    Three shapes are normalised onto `source: {require_ticket, event_ids,
    ticket_type_ids, move, credit}`:

      * pre-axis rows, `type: "code"`   -> require_ticket=False
      * pre-axis rows, `type: "ticket"` -> require_ticket=True, move=False,
        credit="none", event_ids=None (same event only), and the "TICKETID"
        sentinel code cleared because it was never a real code
      * pre-axis rows with no `type` (hand-written config) -> require_ticket=False
      * the intermediate revision's `source.kind` -> `source.require_ticket`

    Handling `kind` as well as `type` makes this safe to re-run over either
    revision, which matters because the intermediate one was deployed.

    Promos already on the final axis are left untouched.
    """
    import json

    # NOTE: db.fetchall returns SQLAlchemy RowMappings (no model= passed), so
    # rows must be read BY COLUMN NAME. Unpacking them (`for a, b in rows`)
    # yields the column names instead of the values, and the JSON decode error
    # that follows is swallowed below as if it were bad data — which silently
    # converts nothing while still recording the migration as applied.
    rows = await db.fetchall("SELECT id, extra FROM events.events")
    for row in rows:
        event_id = row["id"]
        raw = row["extra"]
        if not raw:
            continue
        try:
            extra = json.loads(raw)
        except (TypeError, ValueError):
            continue
        promos = extra.get("promo_codes")
        if not isinstance(promos, list) or not promos:
            continue

        changed = False
        for promo in promos:
            if not isinstance(promo, dict):
                continue
            source = promo.get("source")
            if isinstance(source, dict):
                # Already on an axis revision. `kind` was the intermediate
                # discriminator; normalise it onto `require_ticket` so this
                # migration is safe to re-run over either revision.
                if "kind" in source:
                    is_ticket = source.pop("kind") == "ticket"
                    source["require_ticket"] = is_ticket
                    changed = True
                else:
                    is_ticket = bool(source.get("require_ticket", False))
            else:
                # Pre-axis rows: `type` was the discriminator, and a missing
                # `type` meant "code".
                is_ticket = promo.pop("type", None) == "ticket"
                promo["source"] = {
                    "require_ticket": is_ticket,
                    "event_ids": None,
                    "ticket_type_ids": None,
                    "move": False,
                    "credit": "none",
                }
                changed = True
            if is_ticket and promo.get("code") == "TICKETID":
                promo["code"] = ""
                changed = True

        if changed:
            await db.execute(
                "UPDATE events.events SET extra = :extra WHERE id = :id",
                {"extra": json.dumps(extra), "id": event_id},
            )


async def m011_basket_total(db):
    """
    Add ``Basket.total`` — the amount actually charged for the basket.

    This is a TOP-LEVEL COLUMN, not `extra` JSON config, so adding the field to
    the model is not enough: without this ALTER every basket INSERT fails with
    "table events.baskets has no column named total" and checkout 500s.
    The migration runner only applies versions above the recorded one, so this
    runs once on a database that predates the column.

    Existing baskets keep a NULL total; `_recompute_basket_total` reconstructs
    it from the tickets when a legacy row needs it.
    """
    from sqlalchemy.exc import OperationalError

    # NOTE: no column introspection here. `PRAGMA table_info(events.baskets)` is
    # NOT valid SQLite (schema-qualified pragmas are `PRAGMA events.table_info`),
    # and it fails as a syntax error that the runner reports and retries forever.
    # The runner only applies versions above the recorded one, so a plain guarded
    # ALTER (the m003/m009 idiom) is both sufficient and safest.
    try:
        await db.execute("ALTER TABLE events.baskets ADD COLUMN total REAL;")
    except OperationalError:
        # Column already present (fresh schema, or a re-run) — nothing to do.
        pass
