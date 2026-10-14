"""Patient signatures (drug collection, HMO claims form), kept in the database (royan_signatures).

In the database, not on disk, so the single database dump moved to the server carries them (Oct 2026). Files saved
on disk by older versions are still read, and copied into the database the first time they are served."""
import base64
import mimetypes
import os
import uuid
from typing import Optional, Tuple

_PERSISTENT = "/app/data"
_LEGACY_DIRS = [os.path.join(_PERSISTENT, "signatures"), os.path.join(os.path.dirname(__file__), "..", "data", "signatures")]
ALLOWED_SIGNATURE_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_SIGNATURE_BYTES = 5 * 1024 * 1024


def _db():
    from src.fin.db import ex, q1, tx
    return ex, q1, tx


def save_signature(contents: bytes, prefix: str, filename: Optional[str] = None, content_type: str = "image/png") -> str:
    """Store the image and return its URL (served by GET /pharmacy/signatures/{name})."""
    ex, _q1, tx = _db()
    name = f"{prefix}_{uuid.uuid4().hex[:8]}_{filename or 'signature.png'}".replace("/", "_").replace("\\", "_")
    with tx() as conn:
        ex(conn, "INSERT INTO royan_signatures (name, content, content_type) VALUES (%s, %s, %s)",
           (name, contents, content_type or "image/png"))
    return f"/pharmacy/signatures/{name}"


def load_signature(url_or_name: str) -> Optional[Tuple[bytes, str]]:
    """(bytes, content type) for a signature URL or name; None when it does not exist."""
    name = os.path.basename(url_or_name or "")
    if not name:
        return None
    ex, q1, tx = _db()
    with tx() as conn:
        r = q1(conn, "SELECT content, content_type FROM royan_signatures WHERE name=%s", (name,))
        if r:
            return bytes(r["content"]), r["content_type"]
        for folder in _LEGACY_DIRS:   # an older file on disk: serve it and keep a copy in the database
            p = os.path.join(folder, name)
            if os.path.isfile(p):
                with open(p, "rb") as fh:
                    data = fh.read()
                ctype = mimetypes.guess_type(p)[0] or "image/png"
                ex(conn, "INSERT INTO royan_signatures (name, content, content_type) VALUES (%s,%s,%s) ON CONFLICT (name) DO NOTHING",
                   (name, data, ctype))
                return data, ctype
    return None


def signature_data_url(url: Optional[str]) -> Optional[str]:
    """The image inline (data: URL), for printed forms - an <img> tag cannot send the auth token."""
    got = load_signature(url) if url else None
    if not got:
        return None
    data, ctype = got
    return f"data:{ctype};base64,{base64.b64encode(data).decode()}"
