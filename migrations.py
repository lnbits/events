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


async def _alter_add_column_safe(db, sql: str) -> None:
    """ALTER TABLE ADD COLUMN that swallows duplicate-column errors.

    Earlier aiolabs/events forks added some of these columns under different
    migration names (e.g. our former m007). Skipping the error keeps the
    migration log monotonic for both fresh installs and pre-rebase upgrades.
    """
    try:
        await db.execute(sql)
    except Exception as exc:
        msg = str(exc).lower()
        if "duplicate column" in msg or "already exists" in msg:
            return
        raise


async def m006_add_extra_fields(db):
    """
    Add a canceled and 'extra' column to events and ticket tables
    to support promo codes and ticket metadata.
    """
    await _alter_add_column_safe(
        db,
        "ALTER TABLE events.events ADD COLUMN canceled BOOLEAN NOT NULL DEFAULT FALSE",
    )
    await _alter_add_column_safe(db, "ALTER TABLE events.events ADD COLUMN extra TEXT")
    await _alter_add_column_safe(db, "ALTER TABLE events.ticket ADD COLUMN extra TEXT")


async def m007_add_user_id_support(db):
    """
    Add user_id column to ticket table so a ticket can reference an LNbits
    user id instead of (name, email). Application logic enforces that exactly
    one identifier scheme is used per ticket.
    """
    await _alter_add_column_safe(
        db, "ALTER TABLE events.ticket ADD COLUMN user_id TEXT"
    )


async def m008_add_event_status(db):
    """
    Add status column to events table for the proposal/approval workflow.
    Values: 'proposed', 'approved', 'rejected'. Existing rows default to
    'approved' so they stay visible after upgrade.
    """
    await _alter_add_column_safe(
        db,
        "ALTER TABLE events.events ADD COLUMN status TEXT NOT NULL DEFAULT 'approved'",
    )


async def m009_add_nostr_columns(db):
    """
    Track the most recent NIP-52 calendar event we published for this event
    (used for replaceable updates and NIP-09 deletes).
    """
    await _alter_add_column_safe(
        db, "ALTER TABLE events.events ADD COLUMN nostr_event_id TEXT"
    )
    await _alter_add_column_safe(
        db, "ALTER TABLE events.events ADD COLUMN nostr_event_created_at INTEGER"
    )


async def m010_add_events_settings(db):
    """
    Create the extension settings singleton row used by the admin UI to
    toggle e.g. auto_approve.
    """
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS events.settings (
            id INTEGER PRIMARY KEY DEFAULT 1,
            auto_approve BOOLEAN NOT NULL DEFAULT FALSE
        )
        """
    )
    await db.execute(
        "INSERT INTO events.settings (id, auto_approve) "
        "SELECT 1, FALSE WHERE NOT EXISTS "
        "(SELECT 1 FROM events.settings WHERE id = 1)"
    )


async def m011_add_location_and_categories(db):
    """
    Add NIP-52 calendar metadata (location and a JSON-encoded category list).
    """
    await _alter_add_column_safe(
        db, "ALTER TABLE events.events ADD COLUMN location TEXT"
    )
    await _alter_add_column_safe(
        db, "ALTER TABLE events.events ADD COLUMN categories TEXT"
    )
