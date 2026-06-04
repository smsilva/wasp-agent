from sqlalchemy import Column, Engine, Integer, MetaData, Table, Text, UniqueConstraint

metadata = MetaData()

resource_watches = Table(
    "resource_watches",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("kind", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("session_id", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("notified_at", Text),
    UniqueConstraint("kind", "name"),
)


def init_schema(engine: Engine) -> None:
    metadata.create_all(engine)
