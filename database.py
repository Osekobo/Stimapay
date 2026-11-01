import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/stimapay"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db():
  with engine.connect() as conn:
    conn.execute(
        text("""
            CREATE TABLE IF NOT EXISTS users (
                phone VARCHAR(20) PRIMARY KEY,
                meter_number VARCHAR(50) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
    )
    conn.execute(
        text("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                phone VARCHAR(20) NOT NULL,
                meter_number VARCHAR(50) NOT NULL,
                amount INTEGER NOT NULL,
                checkout_request_id VARCHAR(100),
                merchant_request_id VARCHAR(100),
                mpesa_receipt VARCHAR(100),
                result_code VARCHAR(50),
                result_desc TEXT,
                status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
    )
    conn.execute(
        text("""
            CREATE INDEX IF NOT EXISTS idx_pay_checkout ON payments(checkout_request_id);
        """)
    )
    conn.execute(
        text("""
            CREATE INDEX IF NOT EXISTS idx_pay_status ON payments(status);
        """)
    )
    conn.commit()


def get_db():
  db = SessionLocal()
  try:
    yield db
  finally:
    db.close()
