"""Debug: test build with all pending files."""
import traceback
from db_builder.config import load_config
from db_builder.database import DatabaseManager

config = load_config()
db = DatabaseManager(config.db_path)
db.init_schema()

# Reset all files to pending for clean test
print("Resetting all files to pending...")
for f in db.list_files():
    db.delete_chunks_by_file(f["id"])
    db.update_file_status(f["id"], "pending")

pending = db.list_files(status="pending")
print(f"Pending: {len(pending)}")
for f in pending:
    print(f"  {f['file_path']} ({f['source_type']})")

# Build just the small files (skip the big xlsx for speed)
small_ids = [f["id"] for f in pending if f["file_size"] < 50000]
print(f"\nBuilding {len(small_ids)} small file(s)...")

from db_builder.ui.build_panel import BuildWorker

worker = BuildWorker(db, config, small_ids, max_concurrent=3)
worker.log.connect(lambda msg: print(f"  {msg}"))
worker.file_done.connect(lambda fid, st: print(f"  >> file {fid}: {st}"))

try:
    worker.run()
except Exception as e:
    print(f"\nERROR: {e}")
    traceback.print_exc()

print("\n=== Results ===")
for f in db.list_files():
    print(f"  [{f['status']}] {f['file_path']} chunks={f['chunk_count']}")

stats = db.get_build_stats()
print(f"\nTotal chunks: {stats['total_chunks']}, embedded: {stats['embedded']}")
db.close()
