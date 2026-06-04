from sqlalchemy import Column, Engine, ForeignKey, Index, MetaData, Table, Text

metadata = MetaData()

auth_users = Table(
    "auth_users",
    metadata,
    Column("user_id", Text, primary_key=True),
    Column("display_name", Text, nullable=False),
    Column("created_at", Text, nullable=False),
)

auth_identities = Table(
    "auth_identities",
    metadata,
    Column("channel", Text, nullable=False, primary_key=True),
    Column("channel_id", Text, nullable=False, primary_key=True),
    Column("user_id", Text, ForeignKey("auth_users.user_id"), nullable=False),
    Column("linked_at", Text, nullable=False),
)

Index("auth_identities_user_idx", auth_identities.c.user_id)

auth_invites = Table(
    "auth_invites",
    metadata,
    Column("token", Text, primary_key=True),
    Column("user_id", Text, ForeignKey("auth_users.user_id"), nullable=False),
    Column("channel", Text),
    Column("channel_id", Text),
    Column("created_by", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("expires_at", Text, nullable=False),
    Column("used_at", Text),
)


def init_schema(engine: Engine) -> None:
    metadata.create_all(engine)
