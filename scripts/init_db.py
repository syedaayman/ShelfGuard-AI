import os
import sys

# Add src and scripts to sys.path so we can import shelfguard and sibling scripts
scripts_dir = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(scripts_dir, "../src")))
sys.path.insert(0, os.path.abspath(scripts_dir))

try:
    from scripts.generate_mock_inventory import generate_mock_inventory_csv
except ImportError:
    from generate_mock_inventory import generate_mock_inventory_csv  # noqa: E402

from sqlalchemy import func  # noqa: E402

from shelfguard.database import (  # noqa: E402
    InventoryBatch,
    Product,
    compute_dynamic_status,
    get_db,
    init_db,
    load_csv_to_db,
)


def reset_and_seed_db(mock_csv_path="data/mock_inventory.csv"):
    if not os.path.exists(mock_csv_path):
        print(f"{mock_csv_path} not found. Generating mock inventory dataset...")
        generate_mock_inventory_csv(output_path=mock_csv_path)

    print("Clearing old historical database records...")
    db_gen = get_db()
    db = next(db_gen)
    try:
        # Clear existing batches and products so live DB only contains mock_inventory.csv data
        db.query(InventoryBatch).delete()
        db.query(Product).delete()
        db.commit()
    except Exception as e:
        print(f"Warning during DB clear: {e}")
        db.rollback()

    print("Initializing database schema...")
    init_db()

    print(f"Loading live inventory from {mock_csv_path}...")
    try:
        stats = load_csv_to_db(db, mock_csv_path)
        print("\n=== Live Inventory CSV Ingestion Complete ===")
        print(f"Total Rows Read:   {stats['read']}")
        print(f"Products Inserted: {stats['products_inserted']}")
        print(f"Batches Inserted:  {stats['batches_inserted']}")
        print(f"Rows Rejected:     {stats['rejected']}")

        # Verification stats
        total_batches = db.query(InventoryBatch).count()
        total_products = db.query(Product).count()

        # Count products with multiple batches
        multi_batch_prods = (
            db.query(InventoryBatch.product_id)
            .group_by(InventoryBatch.product_id)
            .having(func.count(InventoryBatch.id) > 1)
            .count()
        )

        # Lifecycle stage breakdown
        stage_counts = {
            "SAFE": 0,
            "WARNING": 0,
            "CRITICAL": 0,
            "DONATION": 0,
            "EXPIRED": 0,
            "NGO_DISPATCH": 0,
        }
        all_batches = db.query(InventoryBatch).all()
        for b in all_batches:
            st, _ = compute_dynamic_status(b.expiry_date, b.status)
            stage_counts[st] = stage_counts.get(st, 0) + 1

        print("\n=== Live Inventory Verification ===")
        print(f"Total Products in DB:            {total_products}")
        print(f"Total Inventory Batches in DB:   {total_batches}")
        print(f"Products with Multiple Batches:  {multi_batch_prods}")
        print("Lifecycle Status Breakdown:")
        for stage, count in stage_counts.items():
            print(f"  - {stage:12s}: {count}")

    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


if __name__ == "__main__":
    reset_and_seed_db()
