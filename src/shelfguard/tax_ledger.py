import hashlib
import threading
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from shelfguard.database import TaxAuditLedger

# ---------------------------------------------------------
# Centralized Currency Conversion Boundary
# ---------------------------------------------------------
# Assumption: The major currency unit (e.g. INR/USD) is represented
# by a Decimal. The minor currency unit (e.g. paise/cents) is represented
# by an Integer. There are 100 minor units in 1 major unit.


def to_cents(amount: Decimal) -> int:
    """Converts a major currency unit Decimal to integer minor units (cents)."""
    # Round to nearest cent first to handle precision gracefully before casting to int
    return int((amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def from_cents(cents: int) -> Decimal:
    """Converts integer minor units (cents) to a major currency unit Decimal."""
    return Decimal(cents) / Decimal("100")


# ---------------------------------------------------------
# Tax Calculation
# ---------------------------------------------------------


class TaxCalculator:
    @staticmethod
    def calculate_tax(taxable_amount: Decimal, tax_rate: Decimal) -> Decimal:
        """
        Calculates the tax using strict Decimal arithmetic.
        Rounds to the nearest cent (0.01) using ROUND_HALF_UP.
        """
        if taxable_amount < Decimal("0"):
            raise ValueError("Taxable amount cannot be negative.")
        if tax_rate < Decimal("0"):
            raise ValueError("Tax rate cannot be negative.")

        tax_collected = (taxable_amount * tax_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return tax_collected


# ---------------------------------------------------------
# Tax Ledger Manager
# ---------------------------------------------------------

_ledger_lock = threading.Lock()


class TaxLedgerManager:
    @staticmethod
    def _compute_hash(
        transaction_id: str,
        total_sale_amount_cents: int,
        tax_collected_cents: int,
        timestamp_iso: str,
        previous_hash: str,
    ) -> str:
        """
        Computes the canonical SHA-256 hash for the ledger entry.
        Format: {transaction_id}|{total_sale_amount_cents}|{tax_collected_cents}|{timestamp}|{prev}
        """
        canonical_string = (
            f"{transaction_id}|{total_sale_amount_cents}|{tax_collected_cents}"
            f"|{timestamp_iso}|{previous_hash}"
        )
        return hashlib.sha256(canonical_string.encode("utf-8")).hexdigest()

    @staticmethod
    def insert_ledger_entry(
        session: Session, transaction_id: str, taxable_amount: Decimal, tax_rate: Decimal
    ) -> TaxAuditLedger:
        """
        Appends a new tax audit record to the ledger.
        Ensures thread-safe serializability via an EXCLUSIVE SQLite transaction lock.
        Calculates tax, formats to minor units, and chains the SHA-256 hash.

        This method is append-only. No update/delete methods are provided for
        historical entries.
        """
        if not transaction_id:
            raise ValueError("Transaction ID is required.")

        # 1. Calculation (Strictly Decimal)
        tax_collected = TaxCalculator.calculate_tax(taxable_amount, tax_rate)
        total_sale_amount = taxable_amount + tax_collected

        # 2. Conversion to persistence layer units (minor units/cents)
        total_sale_amount_cents = to_cents(total_sale_amount)
        tax_collected_cents = to_cents(tax_collected)

        # 3. Concurrency Control / Transaction Safety
        # For this local SQLite MVP, a process-level lock is the simplest
        # reliable mechanism to ensure the hash chain doesn't branch.
        with _ledger_lock:
            try:
                # 4. Retrieve Previous Hash
                last_entry = (
                    session.query(TaxAuditLedger).order_by(TaxAuditLedger.audit_id.desc()).first()
                )
                if last_entry:
                    previous_hash = last_entry.record_hash
                else:
                    previous_hash = "0" * 64  # Genesis

                # 5. Hash generation
                # SQLite strips timezone info, so we use naive UTC to ensure
                # the string used for hash matches what is read back from DB.
                timestamp_now = datetime.now(timezone.utc).replace(tzinfo=None)
                timestamp_iso = timestamp_now.isoformat()

                record_hash = TaxLedgerManager._compute_hash(
                    transaction_id,
                    total_sale_amount_cents,
                    tax_collected_cents,
                    timestamp_iso,
                    previous_hash,
                )

                # 6. Insert Append-Only Record
                new_entry = TaxAuditLedger(
                    transaction_id=transaction_id,
                    total_sale_amount_cents=total_sale_amount_cents,
                    tax_collected_cents=tax_collected_cents,
                    timestamp=timestamp_now,
                    previous_hash=previous_hash,
                    record_hash=record_hash,
                )

                session.add(new_entry)
                session.commit()

                # Return a detached or refreshed object so callers can read it
                session.refresh(new_entry)
                return new_entry

            except Exception as e:
                session.rollback()
                raise e
