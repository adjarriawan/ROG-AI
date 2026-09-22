from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False)

# Separate engine for the SQL agent tool: read-only DB role + hard statement
# timeout, so a prompt-injected query cannot mutate or hang the database.
readonly_engine = create_engine(
    settings.database_url_readonly,
    pool_pre_ping=True,
    connect_args={
        "options": f"-c statement_timeout={settings.sql_timeout_ms} -c default_transaction_read_only=on"
    },
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
