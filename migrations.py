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
            currency TEXT,
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
