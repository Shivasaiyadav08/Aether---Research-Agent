"""Explicitly assign old, unowned workspaces to a Clerk user. Creates a SQLite backup first."""

import argparse
import sqlite3
from datetime import datetime, timezone

from app.core.config import config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("user_id", help="Your Clerk user ID, starting with user_")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--workspace", help="One unowned workspace ID")
    group.add_argument("--all", action="store_true", help="Explicitly claim all unowned workspaces")
    args = parser.parse_args()
    if not args.user_id.startswith("user_") or len(args.user_id) > 200:
        parser.error("Use the actual Clerk user ID from your Clerk dashboard.")
    path = config.data_dir / "aether.db"
    if not path.exists():
        parser.error("No existing SQLite database to claim.")
    with sqlite3.connect(path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(workspaces)")}
        if "owner_id" not in columns:
            parser.error(
                "Start the updated backend once to run the ownership migration, then stop it before claiming."
            )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        backup = path.with_name(f"aether-before-claim-{stamp}.db")
        with sqlite3.connect(backup) as target:
            db.backup(target)
        if args.all:
            result = db.execute("UPDATE workspaces SET owner_id=? WHERE owner_id IS NULL", (args.user_id,))
        else:
            result = db.execute(
                "UPDATE workspaces SET owner_id=? WHERE owner_id IS NULL AND id=?",
                (args.user_id, args.workspace),
            )
        db.commit()
        print(
            f"Assigned {result.rowcount} previously unowned workspace(s). Existing owners were not changed. Backup: {backup.name}"
        )


if __name__ == "__main__":
    main()
