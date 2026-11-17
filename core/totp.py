"""
Engångskoder (TOTP, RFC 6238) för lokala konton — F0-13, förlaga pe-portal/core/totp.py. Standardbiblioteket räcker: HMAC-SHA1,
30 sekunders steg, 6 siffror, ett steg bakåt och framåt godtas (klockdrift). Hemligheten är 20 slumpbyte som base32
(32 tecken, det som appar tar emot) och sparas krypterad med Fernet :
`TOTP_KEY` i miljön, annars en nyckel härledd ur SECRET_KEY.
"""

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken

STEP_SECONDS = 30
DIGITS = 6
DRIFT_STEPS = 1


def new_secret():
    return base32_secret(secrets.token_bytes(20))


def base32_secret(raw):
    return base64.b32encode(raw).decode('ascii').rstrip('=')


def _raw(secret):
    padded = secret.strip().replace(' ', '').upper()
    padded += '=' * (-len(padded) % 8)
    return base64.b32decode(padded)


def code(secret, at=None):
    """Koden för tidpunkten `at` (sekunder sedan epoken; nu om None)."""
    counter = int((time.time() if at is None else at) // STEP_SECONDS)
    digest = hmac.new(_raw(secret), struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(number % (10 ** DIGITS)).zfill(DIGITS)


def verify(secret, given, at=None):
    given = (given or '').strip().replace(' ', '')
    if not given.isdigit() or len(given) != DIGITS:
        return False
    now = time.time() if at is None else at
    return any(hmac.compare_digest(code(secret, at=now + step * STEP_SECONDS), given)
               for step in range(-DRIFT_STEPS, DRIFT_STEPS + 1))


def otpauth_uri(secret, username, issuer='PDF-studio'):
    """Adressen en autentiseringsapp läser (som text eller QR-kod)."""
    return (f'otpauth://totp/{quote(issuer)}:{quote(username)}?secret={secret}&issuer={quote(issuer)}'
            f'&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}')


def grouped(secret):
    """Nyckeln i grupper om fyra, för att skriva in för hand."""
    return ' '.join(secret[i:i + 4] for i in range(0, len(secret), 4))


# ── Kryptering ───────────────────────────────────────────────────────────────

def _fernet():
    key = os.environ.get('TOTP_KEY')
    if not key:
        digest = hashlib.sha256(b'pdf-studio/totp/' + os.environ['SECRET_KEY'].encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key)


def encrypt(secret):
    return _fernet().encrypt(secret.encode()).decode()


def decrypt(stored):
    if not stored:
        return None
    try:
        return _fernet().decrypt(stored.encode()).decode()
    except InvalidToken:
        return None   # nyckeln har bytts — appen måste registreras på nytt
