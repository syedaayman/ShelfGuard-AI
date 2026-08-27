import concurrent.futures
import hashlib
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shelfguard.database import Base, TaxAuditLedger
from shelfguard.tax_ledger import TaxCalculator, TaxLedgerManager, from_cents, to_cents


# Test DB Setup
@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class TestCurrencyConversion:
    def test_to_cents(self):
        assert to_cents(Decimal("10.50")) == 1050
        assert to_cents(Decimal("10.505")) == 1051  # ROUND_HALF_UP
        assert to_cents(Decimal("10.504")) == 1050

    def test_from_cents(self):
        assert from_cents(1050) == Decimal("10.50")
        assert from_cents(1051) == Decimal("10.51")


class TestTaxCalculator:
    def test_normal_tax(self):
        tax = TaxCalculator.calculate_tax(Decimal("100.00"), Decimal("0.05"))
        assert tax == Decimal("5.00")

    def test_zero_tax(self):
        tax = TaxCalculator.calculate_tax(Decimal("100.00"), Decimal("0.00"))
        assert tax == Decimal("0.00")

    def test_round_half_up_edge_cases(self):
        # 10.005 -> 10.01
        assert TaxCalculator.calculate_tax(Decimal("100.05"), Decimal("0.10")) == Decimal("10.01")
        # 10.004 -> 10.00
        assert TaxCalculator.calculate_tax(Decimal("100.04"), Decimal("0.10")) == Decimal("10.00")

    def test_invalid_amounts(self):
        with pytest.raises(ValueError, match="Taxable amount cannot be negative."):
            TaxCalculator.calculate_tax(Decimal("-10.00"), Decimal("0.05"))

    def test_invalid_rates(self):
        with pytest.raises(ValueError, match="Tax rate cannot be negative."):
            TaxCalculator.calculate_tax(Decimal("10.00"), Decimal("-0.05"))


class TestTaxLedgerManager:
    def test_canonical_serialization_and_hash(self):
        # Format: {id}|{total_cents}|{tax_cents}|{timestamp}|{prev}
        expected_str = (
            "txn-123|1050|50|2023-10-01T12:00:00+00:00|"
            "0000000000000000000000000000000000000000000000000000000000000000"
        )
        expected_hash = hashlib.sha256(expected_str.encode("utf-8")).hexdigest()

        computed_hash = TaxLedgerManager._compute_hash(
            "txn-123", 1050, 50, "2023-10-01T12:00:00+00:00", "0" * 64
        )
        assert computed_hash == expected_hash

    def test_missing_required_values(self, db_session):
        with pytest.raises(ValueError, match="Transaction ID is required."):
            TaxLedgerManager.insert_ledger_entry(db_session, "", Decimal("10.00"), Decimal("0.05"))

    def test_genesis_hash_and_persistence(self, db_session):
        entry = TaxLedgerManager.insert_ledger_entry(
            db_session, "txn-1", Decimal("100.00"), Decimal("0.05")
        )
        assert entry.transaction_id == "txn-1"
        assert entry.tax_collected_cents == 500
        assert entry.total_sale_amount_cents == 10500
        assert entry.previous_hash == "0" * 64

        # Verify hash was calculated correctly
        computed_hash = TaxLedgerManager._compute_hash(
            "txn-1", 10500, 500, entry.timestamp.isoformat(), entry.previous_hash
        )
        assert entry.record_hash == computed_hash

    def test_multi_entry_hash_chaining(self, db_session):
        entry1 = TaxLedgerManager.insert_ledger_entry(
            db_session, "txn-1", Decimal("100.00"), Decimal("0.05")
        )
        entry2 = TaxLedgerManager.insert_ledger_entry(
            db_session, "txn-2", Decimal("200.00"), Decimal("0.10")
        )
        assert entry2.previous_hash == entry1.record_hash

    def test_append_only_behavior(self):
        # Ensure there are no update or delete methods
        methods = dir(TaxLedgerManager)
        assert "update" not in methods
        assert "delete" not in methods
        assert "update_entry" not in methods
        assert "delete_entry" not in methods

    def test_concurrent_insertion(self, db_session):
        # Test that concurrent inserts don't branch the chain (i.e., no multiple entries
        # having the same previous_hash).
        # We simulate concurrency using ThreadPoolExecutor

        def insert_task(txn_id):
            # Using the same db_session across threads is technically unsafe in standard SQLAlchemy
            # without scoped_session, but since SQLite EXCLUSIVE lock protects the DB, we want to
            # ensure no database corruption or branched chains occur.
            # To avoid threading issues with the session itself, we'll create a new
            # session per thread.
            engine = db_session.get_bind()
            Session = sessionmaker(bind=engine)
            local_session = Session()
            try:
                TaxLedgerManager.insert_ledger_entry(
                    local_session, txn_id, Decimal("100.00"), Decimal("0.05")
                )
            except Exception:
                # OperationalError: database is locked might happen if timeout occurs,
                # but our goal is to check chain integrity for successful inserts.
                pass
            finally:
                local_session.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(insert_task, f"txn-concurrent-{i}") for i in range(10)]
            concurrent.futures.wait(futures)

        # Verify chain integrity
        entries = db_session.query(TaxAuditLedger).order_by(TaxAuditLedger.audit_id.asc()).all()
        assert len(entries) > 0, "No entries were inserted"

        for i in range(1, len(entries)):
            assert entries[i].previous_hash == entries[i - 1].record_hash, (
                f"Chain broken at entry {entries[i].audit_id}!"
            )
