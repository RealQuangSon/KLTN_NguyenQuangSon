from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime, timezone

from .capabilities import CONSENT_TYPES
from .models import Actor, DomainError
from .organizations import ensure_bootstrap, record_audit, utc_now

logger = logging.getLogger("homematch.api")


SEED_USERS = (("renter-a", "renter"), ("renter-b", "renter"),
              ("owner-a", "owner"), ("owner-b", "owner"), ("owner-c", "owner"), ("owner-d", "owner"),
              ("manager-a", "manager"), ("manager-b", "manager"), ("admin-a", "admin"))

USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,49}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 10
VERIFICATION_TTL_SECONDS = 30 * 60
RESET_TTL_SECONDS = 30 * 60
DEV_STUB_LABEL = "dev_stub_log_only"


class DevDeliveryStub:
    """Explicit development fake for verification delivery.

    Log-only, clearly labeled, never sends a real email and never calls an
    external service. A production email provider is a separate integration;
    this stub must never be presented as real delivery.
    """

    label = DEV_STUB_LABEL

    def deliver(self, purpose: str, user_id: str, token: str) -> None:
        logger.warning(
            "DEV-STUB fake delivery (no real email, development only): "
            "purpose=%s user=%s verification_code=%s",
            purpose, user_id, token)


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    derived = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return f"scrypt${salt}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, salt, _ = encoded.split("$")
        return scheme == "scrypt" and hmac.compare_digest(password_hash(password, salt), encoded)
    except (ValueError, TypeError):
        return False


def token_public_id(token_hash: str) -> str:
    """Stable public session identifier derived from the stored token hash.

    Exposing it reveals neither the raw token nor the stored hash.
    """
    return hashlib.sha256(("hm-session:" + token_hash).encode()).hexdigest()[:16]


def _account_profile(repo, user_id: str) -> dict | None:
    row = repo.db.execute("SELECT * FROM hm_account_profiles WHERE user_id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _validate_registration(username: str, password: str, email: str):
    if not USERNAME_PATTERN.fullmatch(username):
        raise DomainError("invalid_username",
                          "Tên đăng nhập cần 3–50 ký tự thường, số hoặc gạch ngang.", 422)
    if len(password) < MIN_PASSWORD_LENGTH or password == username:
        raise DomainError("weak_password",
                          f"Mật khẩu cần ít nhất {MIN_PASSWORD_LENGTH} ký tự và khác tên đăng nhập.", 422)
    if not EMAIL_PATTERN.fullmatch(email):
        raise DomainError("invalid_email", "Địa chỉ email chưa hợp lệ.", 422)


def _issue_verification_token(repo, user_id: str, purpose: str, ttl_seconds: int) -> str:
    """Single-use token; issuing a new one invalidates previous unused tokens."""
    raw = secrets.token_urlsafe(24)
    with repo.db:
        repo.db.execute("UPDATE hm_verification_tokens SET used=1 "
                        "WHERE user_id=? AND purpose=? AND used=0", (user_id, purpose))
        repo.db.execute(
            "INSERT INTO hm_verification_tokens(token_hash,user_id,purpose,expires_at,used,created_at) "
            "VALUES(?,?,?,?,0,?)",
            (_hash_token(raw), user_id, purpose, time.time() + ttl_seconds, utc_now()))
    return raw


def _consume_token(repo, user_id: str, raw_token: str, purpose: str) -> None:
    row = repo.db.execute("SELECT * FROM hm_verification_tokens WHERE token_hash=?",
                          (_hash_token(raw_token),)).fetchone()
    if row is None or row["user_id"] != user_id or row["purpose"] != purpose:
        raise DomainError("invalid_token", "Mã xác minh không đúng.", 409)
    if row["used"]:
        raise DomainError("token_used", "Mã xác minh đã được dùng.", 409)
    if row["expires_at"] <= time.time():
        raise DomainError("token_expired", "Mã xác minh đã hết hạn; hãy yêu cầu mã mới.", 409)
    # Conditional update so two concurrent requests cannot both consume the token.
    if repo.db.execute("UPDATE hm_verification_tokens SET used=1 WHERE token_hash=? AND used=0",
                       (_hash_token(raw_token),)).rowcount != 1:
        raise DomainError("token_used", "Mã xác minh đã được dùng.", 409)


def register_account(repo, username: str, password: str, email: str,
                     display_name: str | None = None, delivery: DevDeliveryStub | None = None) -> dict:
    """Self-registration always creates an unverified renter account."""
    _validate_registration(username, password, email)
    with repo.db:
        if repo.db.execute("SELECT id FROM hm_users WHERE id=?", (username,)).fetchone():
            raise DomainError("account_exists", "Tài khoản này đã tồn tại.", 409)
        if repo.db.execute("SELECT user_id FROM hm_account_profiles WHERE email=?",
                           (email,)).fetchone():
            raise DomainError("email_in_use", "Địa chỉ email đã được dùng cho tài khoản khác.", 409)
        repo.db.execute("INSERT INTO hm_users(id,role,password_hash) VALUES(?,'renter',?)",
                        (username, password_hash(password)))
        now = utc_now()
        repo.db.execute(
            "INSERT INTO hm_account_profiles(user_id,email,display_name,status,email_verified,"
            "consents_json,created_at,updated_at) VALUES(?,?,?,'unverified',0,'{}',?,?)",
            (username, email, display_name, now, now))
        actor = Actor(id=username, role="renter")
        record_audit(repo, actor, "account.registered", "account", username)
        token = _issue_verification_token(repo, username, "email_verification",
                                          VERIFICATION_TTL_SECONDS)
    if delivery is not None:
        delivery.deliver("email_verification", username, token)
    return {"status": "pending_verification", "user": actor.model_dump(), "delivery": DEV_STUB_LABEL}


def verify_account(repo, username: str, token: str) -> dict:
    with repo.db:
        profile = _account_profile(repo, username)
        # A token issued before an account was disabled must not re-enable it.
        if profile is None or profile["status"] == "disabled":
            raise DomainError("invalid_token", "Mã xác minh không đúng.", 409)
        _consume_token(repo, username, token, "email_verification")
        repo.db.execute("UPDATE hm_account_profiles SET status='active',email_verified=1,updated_at=? "
                        "WHERE user_id=?", (utc_now(), username))
        record_audit(repo, Actor(id=username, role="renter"), "account.verified", "account", username)
    return {"status": "verified"}


def request_password_reset(repo, username: str, delivery: DevDeliveryStub | None = None) -> dict:
    """Uniform response: unknown, seed and disabled accounts look identical.

    Seed-provisioned accounts (no profile row) deliberately cannot reset
    through this flow so the seed/public-mode credential contract stays intact.
    """
    profile = _account_profile(repo, username)
    if profile is not None and profile["status"] != "disabled":
        token = _issue_verification_token(repo, username, "password_reset", RESET_TTL_SECONDS)
        if delivery is not None:
            delivery.deliver("password_reset", username, token)
    return {"status": "reset_requested"}


def confirm_password_reset(repo, username: str, token: str, new_password: str,
                           delivery: DevDeliveryStub | None = None) -> dict:
    if len(new_password) < MIN_PASSWORD_LENGTH or new_password == username:
        raise DomainError("weak_password",
                          f"Mật khẩu cần ít nhất {MIN_PASSWORD_LENGTH} ký tự và khác tên đăng nhập.", 422)
    with repo.db:
        profile = _account_profile(repo, username)
        if profile is None or profile["status"] == "disabled":
            raise DomainError("invalid_token", "Mã xác minh không đúng.", 409)
        _consume_token(repo, username, token, "password_reset")
        repo.db.execute("UPDATE hm_users SET password_hash=? WHERE id=?",
                        (password_hash(new_password), username))
        # Possessing the email token proves control of the address.
        repo.db.execute("UPDATE hm_account_profiles SET status='active',email_verified=1,updated_at=? "
                        "WHERE user_id=?", (utc_now(), username))
        repo.db.execute("UPDATE hm_tokens SET revoked=1 WHERE user_id=?", (username,))
        record_audit(repo, Actor(id=username, role="renter"), "account.password_reset",
                     "account", username)
    return {"status": "password_reset"}


def account_profile(repo, user_id: str) -> dict:
    user = repo.db.execute("SELECT id,role FROM hm_users WHERE id=?", (user_id,)).fetchone()
    if user is None:
        raise DomainError("not_found", "Không tìm thấy tài khoản.", 404)
    profile = _account_profile(repo, user_id)
    consents = {name: False for name in CONSENT_TYPES}
    if profile is not None:
        stored = json.loads(profile["consents_json"])
        consents.update({key: bool(value) for key, value in stored.items() if key in consents})
    memberships = repo.db.execute(
        "SELECT m.organization_id,m.role,m.status,o.name FROM hm_memberships m "
        "JOIN hm_organizations o ON o.id=m.organization_id "
        "WHERE m.user_id=? AND m.status='active' ORDER BY m.organization_id", (user_id,)).fetchall()
    return {"id": user["id"], "role": user["role"],
            "display_name": profile["display_name"] if profile else None,
            "email": profile["email"] if profile else None,
            "email_verified": (bool(profile["email_verified"]) if profile["email"] else None)
                              if profile else None,
            "status": profile["status"] if profile else "active",
            "consents": consents,
            "organizations": [dict(row) for row in memberships]}


def update_account_profile(repo, user_id: str, updates: dict,
                           delivery: DevDeliveryStub | None = None) -> dict:
    """Patch display_name/email/consents. Role and organization are not patchable."""
    unknown = set(updates.get("consents", {})) - set(CONSENT_TYPES)
    if unknown:
        raise DomainError("invalid_consent", "Tùy chọn lưu trữ không được hỗ trợ.", 422)
    if "email" in updates and updates["email"] is None:
        raise DomainError("invalid_request", "Không thể xóa email khỏi tài khoản.", 422)
    user = repo.db.execute("SELECT id,role FROM hm_users WHERE id=?", (user_id,)).fetchone()
    if user is None:
        raise DomainError("not_found", "Không tìm thấy tài khoản.", 404)
    new_token = None
    with repo.db:
        current = _account_profile(repo, user_id)
        now = utc_now()
        email = updates.get("email")
        display_name = updates.get("display_name")
        consents = updates.get("consents")
        merged = json.loads(current["consents_json"]) if current else \
            {name: False for name in CONSENT_TYPES}
        if consents is not None:
            merged.update(consents)
        needs_verification = current is None and email is not None
        if current is None:
            status = "unverified" if needs_verification else "active"
            repo.db.execute(
                "INSERT INTO hm_account_profiles(user_id,email,display_name,status,email_verified,"
                "consents_json,created_at,updated_at) VALUES(?,?,?,?,0,?,?,?)",
                (user_id, email, display_name, status,
                 json.dumps(merged, ensure_ascii=False), now, now))
        else:
            if email is not None and (email != current["email"] or not current["email_verified"]):
                needs_verification = True
            status = "unverified" if needs_verification else current["status"]
            email_verified = 0 if needs_verification else current["email_verified"]
            repo.db.execute(
                "UPDATE hm_account_profiles SET email=COALESCE(?,email),"
                "display_name=COALESCE(?,display_name),status=?,email_verified=?,"
                "consents_json=?,updated_at=? WHERE user_id=?",
                (email, display_name, status, email_verified,
                 json.dumps(merged, ensure_ascii=False), now, user_id))
        if needs_verification:
            new_token = _issue_verification_token(repo, user_id, "email_verification",
                                                  VERIFICATION_TTL_SECONDS)
        # Audit records field names only, never values (no PII in the audit log).
        record_audit(repo, Actor(id=user_id, role=user["role"]), "profile.updated",
                     "account", user_id, detail={"fields": sorted(updates)})
    if new_token and delivery is not None:
        delivery.deliver("email_verification", user_id, new_token)
    return account_profile(repo, user_id)


def list_sessions(repo, user_id: str) -> list[dict]:
    rows = repo.db.execute("SELECT token_hash,expires_at,revoked FROM hm_tokens "
                           "WHERE user_id=? ORDER BY expires_at,token_hash", (user_id,)).fetchall()
    return [{"token_id": token_public_id(row["token_hash"]),
             "expires_at": datetime.fromtimestamp(row["expires_at"], timezone.utc),
             "revoked": bool(row["revoked"])} for row in rows]


def revoke_session(repo, user_id: str, token_id: str) -> dict:
    rows = repo.db.execute("SELECT token_hash,revoked FROM hm_tokens WHERE user_id=?",
                           (user_id,)).fetchall()
    match = next((row for row in rows if token_public_id(row["token_hash"]) == token_id), None)
    if match is None:
        raise DomainError("not_found", "Không tìm thấy phiên đăng nhập.", 404)
    if match["revoked"]:
        raise DomainError("session_revoked", "Phiên này đã bị thu hồi trước đó.", 409)
    with repo.db:
        repo.db.execute("UPDATE hm_tokens SET revoked=1 WHERE token_hash=?",
                        (match["token_hash"],))
        record_audit(repo, Actor(id=user_id, role="renter"), "session.revoked", "session", token_id)
    return {"status": "revoked"}


class SeedAuth:
    def __init__(self, repo, lock, ttl_seconds: int = 3600, public: bool = False):
        self.repo, self.lock, self.ttl = repo, lock, ttl_seconds
        with self.lock, self.repo.db:
            for username, role in SEED_USERS:
                variable = "HOMEMATCH_PASSWORD_" + username.upper().replace("-", "_")
                password = os.getenv(variable) or f"local-{username}-password"
                self.repo.db.execute("INSERT INTO hm_users(id,role,password_hash) VALUES(?,?,?) "
                                     "ON CONFLICT(id) DO NOTHING", (username, role, password_hash(password)))
                if public:
                    stored = self.repo.db.execute("SELECT password_hash FROM hm_users WHERE id=?", (username,)).fetchone()
                    if not verify_password(password, stored["password_hash"]):
                        raise ValueError("Stored seed credentials differ; run seed-users --rotate-passwords before public startup")
        # Newly seeded staff accounts need their default-organization memberships.
        ensure_bootstrap(repo)

    def rotate_passwords(self):
        with self.lock, self.repo.guard():
            for username, _ in SEED_USERS:
                variable = "HOMEMATCH_PASSWORD_" + username.upper().replace("-", "_")
                value = os.getenv(variable)
                if not value or len(value) < 16 or value == f"local-{username}-password":
                    raise ValueError("Rotation requires explicit non-default passwords of at least 16 characters")
                self.repo.db.execute("UPDATE hm_users SET password_hash=? WHERE id=?", (password_hash(value), username))
                self.repo.db.execute("UPDATE hm_tokens SET revoked=1 WHERE user_id=?", (username,))

    def login(self, username: str, password: str) -> dict:
        with self.lock:
            row = self.repo.db.execute("SELECT * FROM hm_users WHERE id=?", (username,)).fetchone()
        encoded = row["password_hash"] if row else password_hash("unused-auth-padding")
        if not verify_password(password, encoded) or row is None:
            # Wrong credentials never reveal whether the account exists.
            raise DomainError("invalid_credentials", "Tên đăng nhập hoặc mật khẩu không đúng.", 401)
        raw = secrets.token_urlsafe(32)
        expires = time.time() + self.ttl
        with self.lock, self.repo.db:
            # A password rotation may have happened while scrypt ran outside the lock.
            current = self.repo.db.execute("SELECT role,password_hash FROM hm_users WHERE id=?", (username,)).fetchone()
            if current is None or current["password_hash"] != encoded:
                raise DomainError("invalid_credentials", "Tên đăng nhập hoặc mật khẩu không đúng.", 401)
            self._require_active_account(username)
            self.repo.db.execute("INSERT INTO hm_tokens(token_hash,user_id,expires_at,revoked) VALUES(?,?,?,0)",
                                 (hashlib.sha256(raw.encode()).hexdigest(), username, expires))
        return {"access_token": raw, "token_type": "bearer",
                "expires_at": datetime.fromtimestamp(expires, timezone.utc).isoformat(),
                "actor": Actor(id=username, role=current["role"]).model_dump()}

    def _require_active_account(self, username: str):
        """Registered accounts must be verified and enabled; seed accounts
        without a profile row stay active. The check only runs after the
        correct password, so it leaks nothing to credential guessing."""
        profile = self.repo.db.execute(
            "SELECT status,email_verified,email FROM hm_account_profiles WHERE user_id=?",
            (username,)).fetchone()
        if profile is None:
            return
        if profile["status"] == "disabled":
            raise DomainError("account_disabled", "Tài khoản đã bị vô hiệu hóa.", 403)
        if profile["status"] == "unverified" or (profile["email"] and not profile["email_verified"]):
            raise DomainError("account_unverified",
                              "Tài khoản chưa xác minh email; hãy kiểm tra mã xác minh.", 403)

    def actor(self, token: str) -> Actor:
        with self.lock:
            row = self.repo.db.execute("SELECT u.id,u.role,t.expires_at,t.revoked FROM hm_tokens t "
                                      "JOIN hm_users u ON u.id=t.user_id WHERE token_hash=?",
                                      (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if row is None or row["revoked"] or row["expires_at"] <= time.time():
            raise DomainError("unauthorized", "Phiên đăng nhập không hợp lệ hoặc đã hết hạn.", 401)
        return Actor(id=row["id"], role=row["role"])

    def logout(self, token: str):
        with self.lock, self.repo.db:
            self.repo.db.execute("UPDATE hm_tokens SET revoked=1 WHERE token_hash=?",
                                 (hashlib.sha256(token.encode()).hexdigest(),))
