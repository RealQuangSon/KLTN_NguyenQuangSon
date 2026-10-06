"""Versioned, transactional ledger migrations for SQLite and PostgreSQL.

Version 1 adopts existing MVP databases without deleting records. Version 2
backfills profile snapshots. Version 3 adds the four-role foundation:
organizations, memberships, room ownership, an audit log and account
lifecycle tables (email verification / password reset). Version 4 adds the
consent-gated preference memory and the persistent query-embedding cache.
Version 5 moves human review to landlords (one review per landlord per run)
and adds offline/online viewing modes. Version 6 records listing views and
lets a renter book a viewing straight from a published listing (no AI run).
Version 7 adds renter-landlord live chat with handover context and the
PII-masked AI chat transcript kept for admin audit. Version 8 adds in-app
notifications (deduplicated) and the automation job log. Version 9 adds the
landlord PMS/CRM: leases, meter readings, invoices, payments and claims,
maintenance tickets and the lead pipeline. LangGraph
and optional pgvector tables remain owned by their respective adapters.
"""
from __future__ import annotations

from datetime import datetime, timezone


MIGRATIONS = (
    (1, "initial_ledger", """
        CREATE TABLE IF NOT EXISTS hm_sessions (
            id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, manager_id TEXT NOT NULL,
            draft_revision INTEGER NOT NULL DEFAULT 0, draft_json TEXT NOT NULL,
            profile_version INTEGER NOT NULL DEFAULT 0, profile_json TEXT,
            active_run_id TEXT
        );
        CREATE TABLE IF NOT EXISTS hm_runs (
            id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES hm_sessions(id),
            profile_version INTEGER NOT NULL, catalog_version TEXT NOT NULL,
            profile_json TEXT NOT NULL, status TEXT NOT NULL,
            items_json TEXT NOT NULL DEFAULT '[]', diagnostics_json TEXT NOT NULL DEFAULT '{}',
            decision_json TEXT, created_at TEXT NOT NULL, published_at TEXT
        );
        CREATE TABLE IF NOT EXISTS hm_viewings (
            id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES hm_sessions(id),
            run_id TEXT NOT NULL REFERENCES hm_runs(id), owner_id TEXT NOT NULL,
            manager_id TEXT NOT NULL, room_id TEXT NOT NULL, requested_at TEXT NOT NULL,
            status TEXT NOT NULL, idempotency_key TEXT NOT NULL, payload_json TEXT NOT NULL,
            UNIQUE(owner_id, idempotency_key)
        );
        CREATE TABLE IF NOT EXISTS hm_support (
            id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES hm_sessions(id),
            manager_id TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hm_users (
            id TEXT PRIMARY KEY, role TEXT NOT NULL, password_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hm_tokens (
            token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES hm_users(id),
            expires_at DOUBLE PRECISION NOT NULL, revoked INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS hm_catalog_meta (
            id TEXT PRIMARY KEY, version TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hm_rooms (
            id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload_json TEXT NOT NULL
        );
        
        INSERT INTO hm_catalog_meta(id,version) VALUES('catalog','') ON CONFLICT(id) DO NOTHING;
    """),
    (2, "profile_snapshots_and_indexes", """
        CREATE TABLE IF NOT EXISTS hm_profile_snapshots (
            session_id TEXT NOT NULL REFERENCES hm_sessions(id),
            profile_version INTEGER NOT NULL CHECK(profile_version > 0),
            profile_json TEXT NOT NULL, confirmed_at TEXT NOT NULL,
            PRIMARY KEY(session_id, profile_version)
        );
        INSERT INTO hm_profile_snapshots(session_id,profile_version,profile_json,confirmed_at)
            SELECT session_id,profile_version,profile_json,MIN(created_at) FROM hm_runs
            WHERE profile_version > 0 GROUP BY session_id,profile_version,profile_json
            ON CONFLICT(session_id,profile_version) DO NOTHING;
        INSERT INTO hm_profile_snapshots(session_id,profile_version,profile_json,confirmed_at)
            SELECT id,profile_version,profile_json,'legacy_unknown' FROM hm_sessions
            WHERE profile_version > 0 AND profile_json IS NOT NULL
            ON CONFLICT(session_id,profile_version) DO NOTHING;
        CREATE INDEX IF NOT EXISTS hm_sessions_owner ON hm_sessions(owner_id);
        CREATE INDEX IF NOT EXISTS hm_sessions_manager ON hm_sessions(manager_id);
        CREATE INDEX IF NOT EXISTS hm_runs_session_status ON hm_runs(session_id,status);
        CREATE INDEX IF NOT EXISTS hm_viewings_manager ON hm_viewings(manager_id,status);
        CREATE INDEX IF NOT EXISTS hm_tokens_user ON hm_tokens(user_id);
        CREATE INDEX IF NOT EXISTS hm_support_manager ON hm_support(manager_id,status);
    """),
    (3, "organizations_membership_ownership_audit_accounts", """
        CREATE TABLE IF NOT EXISTS hm_organizations (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hm_memberships (
            id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES hm_organizations(id),
            user_id TEXT NOT NULL REFERENCES hm_users(id),
            role TEXT NOT NULL CHECK(role IN ('owner','manager','admin')),
            status TEXT NOT NULL DEFAULT 'active', revision INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(organization_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS hm_room_ownership (
            room_id TEXT PRIMARY KEY REFERENCES hm_rooms(id),
            organization_id TEXT NOT NULL REFERENCES hm_organizations(id),
            owner_id TEXT REFERENCES hm_users(id),
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hm_audit_log (
            id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, actor_role TEXT NOT NULL,
            organization_id TEXT, action TEXT NOT NULL, resource_type TEXT NOT NULL,
            resource_id TEXT NOT NULL, detail_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hm_account_profiles (
            user_id TEXT PRIMARY KEY REFERENCES hm_users(id),
            email TEXT, display_name TEXT, status TEXT NOT NULL DEFAULT 'active',
            email_verified INTEGER NOT NULL DEFAULT 0,
            consents_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hm_verification_tokens (
            token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES hm_users(id),
            purpose TEXT NOT NULL CHECK(purpose IN ('email_verification','password_reset')),
            expires_at DOUBLE PRECISION NOT NULL, used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS hm_account_profiles_email ON hm_account_profiles(email) WHERE email IS NOT NULL;
        CREATE INDEX IF NOT EXISTS hm_memberships_org ON hm_memberships(organization_id,status);
        CREATE INDEX IF NOT EXISTS hm_memberships_user ON hm_memberships(user_id,status);
        CREATE INDEX IF NOT EXISTS hm_audit_resource ON hm_audit_log(resource_type,resource_id);
        CREATE INDEX IF NOT EXISTS hm_audit_actor ON hm_audit_log(actor_id,created_at);
        CREATE INDEX IF NOT EXISTS hm_verification_user ON hm_verification_tokens(user_id,purpose);
    """),
    (4, "preference_memory_and_query_embedding_cache", """
        CREATE TABLE IF NOT EXISTS hm_preference_memory (
            user_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL,
            source_session TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hm_query_embeddings (
            cache_key TEXT PRIMARY KEY, model TEXT NOT NULL, dimensions INTEGER NOT NULL,
            embedding_json TEXT NOT NULL, created_at TEXT NOT NULL
        );
    """),
    (5, "landlord_reviews_and_viewing_modes", """
        CREATE TABLE IF NOT EXISTS hm_run_reviews (
            run_id TEXT NOT NULL REFERENCES hm_runs(id), landlord_id TEXT NOT NULL,
            event_json TEXT NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY(run_id, landlord_id)
        );
        ALTER TABLE hm_viewings ADD COLUMN landlord_id TEXT;
        ALTER TABLE hm_viewings ADD COLUMN mode TEXT NOT NULL DEFAULT 'offline';
        ALTER TABLE hm_viewings ADD COLUMN meeting_url TEXT;
        UPDATE hm_viewings SET landlord_id=manager_id WHERE landlord_id IS NULL;
        CREATE INDEX IF NOT EXISTS hm_viewings_landlord ON hm_viewings(landlord_id,status);
    """),
    (6, "listing_views_and_direct_viewings", """
        CREATE TABLE IF NOT EXISTS hm_room_views (
            id TEXT PRIMARY KEY, room_id TEXT NOT NULL, user_id TEXT, viewed_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS hm_room_views_room ON hm_room_views(room_id,viewed_at);
        CREATE INDEX IF NOT EXISTS hm_room_views_user ON hm_room_views(user_id,viewed_at);
        CREATE TABLE hm_viewings_v6 (
            id TEXT PRIMARY KEY, session_id TEXT REFERENCES hm_sessions(id),
            run_id TEXT REFERENCES hm_runs(id), owner_id TEXT NOT NULL,
            manager_id TEXT NOT NULL, room_id TEXT NOT NULL, requested_at TEXT NOT NULL,
            status TEXT NOT NULL, idempotency_key TEXT NOT NULL, payload_json TEXT NOT NULL,
            landlord_id TEXT, mode TEXT NOT NULL DEFAULT 'offline', meeting_url TEXT,
            UNIQUE(owner_id, idempotency_key)
        );
        INSERT INTO hm_viewings_v6(id,session_id,run_id,owner_id,manager_id,room_id,requested_at,status,
            idempotency_key,payload_json,landlord_id,mode,meeting_url)
            SELECT id,session_id,run_id,owner_id,manager_id,room_id,requested_at,status,
            idempotency_key,payload_json,landlord_id,mode,meeting_url FROM hm_viewings;
        DROP TABLE hm_viewings;
        ALTER TABLE hm_viewings_v6 RENAME TO hm_viewings;
        CREATE INDEX IF NOT EXISTS hm_viewings_manager ON hm_viewings(manager_id,status);
        CREATE INDEX IF NOT EXISTS hm_viewings_landlord ON hm_viewings(landlord_id,status);
        CREATE INDEX IF NOT EXISTS hm_viewings_owner ON hm_viewings(owner_id,status);
    """),
    (7, "live_chat_handover_and_chat_audit", """
        CREATE TABLE IF NOT EXISTS hm_conversations (
            id TEXT PRIMARY KEY, renter_id TEXT NOT NULL, landlord_id TEXT NOT NULL,
            room_id TEXT, session_id TEXT, status TEXT NOT NULL DEFAULT 'open',
            context_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
            last_message_at TEXT NOT NULL, first_response_at TEXT,
            renter_read_at TEXT, landlord_read_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS hm_conversations_pair
            ON hm_conversations(renter_id, landlord_id, room_id);
        CREATE INDEX IF NOT EXISTS hm_conversations_landlord ON hm_conversations(landlord_id,last_message_at);
        CREATE TABLE IF NOT EXISTS hm_messages (
            id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES hm_conversations(id),
            sender_id TEXT NOT NULL, sender_role TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS hm_messages_conversation ON hm_messages(conversation_id,created_at);
        CREATE TABLE IF NOT EXISTS hm_chat_transcripts (
            id TEXT PRIMARY KEY, session_id TEXT NOT NULL, user_id TEXT NOT NULL,
            speaker TEXT NOT NULL, text TEXT NOT NULL, intent TEXT, agent TEXT, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS hm_chat_transcripts_session ON hm_chat_transcripts(session_id,created_at);
        CREATE INDEX IF NOT EXISTS hm_chat_transcripts_created ON hm_chat_transcripts(created_at);
    """),
    (8, "notifications_and_automation", """
        CREATE TABLE IF NOT EXISTS hm_notifications (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL,
            body TEXT NOT NULL, link TEXT, dedup_key TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL, read_at TEXT
        );
        CREATE INDEX IF NOT EXISTS hm_notifications_user ON hm_notifications(user_id,created_at);
        CREATE TABLE IF NOT EXISTS hm_job_runs (
            id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, summary_json TEXT
        );
    """),
    (9, "property_management_crm", """
        CREATE TABLE IF NOT EXISTS hm_leases (
            id TEXT PRIMARY KEY, landlord_id TEXT NOT NULL, renter_id TEXT NOT NULL, room_id TEXT NOT NULL,
            start_date TEXT NOT NULL, end_date TEXT NOT NULL, rent_vnd INTEGER NOT NULL, deposit_vnd INTEGER NOT NULL,
            payment_day INTEGER NOT NULL, occupants INTEGER NOT NULL, vehicles INTEGER NOT NULL,
            terms TEXT NOT NULL, status TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
            renter_accepted_version INTEGER, renewal_of TEXT, quote_json TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, ended_at TEXT, settlement_note TEXT
        );
        CREATE INDEX IF NOT EXISTS hm_leases_landlord ON hm_leases(landlord_id,status);
        CREATE INDEX IF NOT EXISTS hm_leases_renter ON hm_leases(renter_id,status);
        CREATE INDEX IF NOT EXISTS hm_leases_room ON hm_leases(room_id,status);
        CREATE TABLE IF NOT EXISTS hm_meter_readings (
            id TEXT PRIMARY KEY, lease_id TEXT NOT NULL REFERENCES hm_leases(id), period TEXT NOT NULL,
            electricity_start NUMERIC, electricity_end NUMERIC, water_start NUMERIC, water_end NUMERIC,
            recorded_by TEXT NOT NULL, recorded_at TEXT NOT NULL, UNIQUE(lease_id, period)
        );
        CREATE TABLE IF NOT EXISTS hm_invoices (
            id TEXT PRIMARY KEY, lease_id TEXT NOT NULL REFERENCES hm_leases(id), period TEXT NOT NULL,
            lines_json TEXT NOT NULL, total_vnd INTEGER NOT NULL, paid_vnd INTEGER NOT NULL DEFAULT 0,
            due_date TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
            UNIQUE(lease_id, period)
        );
        CREATE TABLE IF NOT EXISTS hm_payments (
            id TEXT PRIMARY KEY, invoice_id TEXT NOT NULL REFERENCES hm_invoices(id), amount_vnd INTEGER NOT NULL,
            method TEXT NOT NULL, reference TEXT, receipt_no TEXT NOT NULL UNIQUE, claim_id TEXT,
            recorded_by TEXT NOT NULL, recorded_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hm_payment_claims (
            id TEXT PRIMARY KEY, invoice_id TEXT NOT NULL REFERENCES hm_invoices(id), renter_id TEXT NOT NULL,
            amount_vnd INTEGER NOT NULL, reference TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL,
            decided_at TEXT
        );
        CREATE TABLE IF NOT EXISTS hm_maintenance (
            id TEXT PRIMARY KEY, room_id TEXT NOT NULL, lease_id TEXT, renter_id TEXT NOT NULL,
            landlord_id TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL, priority TEXT NOT NULL,
            status TEXT NOT NULL, assignee TEXT, cost_vnd INTEGER, timeline_json TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS hm_maintenance_landlord ON hm_maintenance(landlord_id,status);
        CREATE TABLE IF NOT EXISTS hm_leads (
            id TEXT PRIMARY KEY, landlord_id TEXT NOT NULL, renter_id TEXT NOT NULL, room_id TEXT NOT NULL,
            stage TEXT NOT NULL, score INTEGER NOT NULL DEFAULT 0, sources_json TEXT NOT NULL DEFAULT '[]',
            notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(landlord_id, renter_id, room_id)
        );
    """),
)
SCHEMA_VERSION = MIGRATIONS[-1][0]


def schema_version(db) -> int:
    row = db.execute("SELECT MAX(version) AS version FROM hm_schema_migrations").fetchone()
    return row["version"] or 0


def migrate(db) -> int:
    with db:
        db.execute("CREATE TABLE IF NOT EXISTS hm_schema_migrations ("
                   "version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)")
        current = schema_version(db)
        if current > SCHEMA_VERSION:
            raise ValueError("Database schema is newer than this backend; upgrade the application")
        for version, name, sql in MIGRATIONS:
            if version <= current:
                continue
            db.executescript(sql)
            db.execute("INSERT INTO hm_schema_migrations VALUES(?,?,?)",
                       (version, name, datetime.now(timezone.utc).isoformat()))
    return SCHEMA_VERSION
