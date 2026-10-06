"""Explicit operator commands. Indexing requires --allow-live and may incur API costs."""
import argparse
import json
import os
from pathlib import Path

from backend.app.catalog import Catalog, StoredCatalog
from backend.app.service import HomeMatchService
from backend.app.auth import SeedAuth
from backend.app.repository import Repository


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["setup", "migrate", "import", "index", "seed-users", "jobs"])
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--rotate-passwords", action="store_true")
    arguments = parser.parse_args()
    if arguments.command == "index" and not arguments.allow_live:
        parser.error("index requires --allow-live; embedding API calls may incur costs")
    storage = os.getenv("HOMEMATCH_DATABASE_URL") or os.getenv("HOMEMATCH_DB_PATH", ".local/homematch.sqlite")
    if arguments.command == "migrate":
        repo = Repository(storage)
        try:
            print(json.dumps({"status": "migrated", "schema_version": repo.schema_version,
                              "storage": "postgresql" if repo.db.postgres else "sqlite"}))
        finally:
            repo.close()
        return
    service = HomeMatchService(storage)
    try:
        if arguments.command == "seed-users":
            auth = SeedAuth(service.repo, service.lock)
            if arguments.rotate_passwords:
                auth.rotate_passwords()
            result = {"status": "seeded", "passwords_rotated": arguments.rotate_passwords}
        elif arguments.command == "import":
            if not arguments.catalog or not isinstance(service.catalog, StoredCatalog):
                parser.error("import requires --catalog JSON and stored catalog")
            with service.lock:
                version = service.catalog.import_rooms(Catalog(arguments.catalog).rooms())
            result = {"catalog_version": version, "rooms": len(service.catalog.rooms())}
        elif arguments.command == "jobs":
            # Same idempotent automation run the API's background thread performs.
            result = service.run_jobs()
        elif arguments.command == "index":
            scorer = getattr(service.catalog, "semantic_scorer", None)
            if scorer is None:
                parser.error("index requires PostgreSQL and HOMEMATCH_EMBEDDING_MODE=openai")
            result = scorer.index()
        else:
            result = {"storage": "postgresql" if service.repo.db.postgres else "sqlite",
                      "schema_version": service.repo.schema_version, "rooms": len(service.catalog.rooms())}
        print(json.dumps(result, ensure_ascii=False))
    finally:
        service.close()


if __name__ == "__main__":
    main()
