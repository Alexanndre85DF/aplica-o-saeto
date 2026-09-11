from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

COOKIE_ADMIN = "saeto_admin"
_SALT = "saeto-admin-gurupi-2026"
_SECRET = os.getenv("ADMIN_SESSION_SECRET") or "saeto-sre-gurupi-admin-sessao-2026"
_VALIDADE = 12 * 3600

ADMINS = {
    "karitalemos@professor.to.gov.br": {
        "nome": "KARITA SANTOS LEMOS",
        "senha": "277e66c5232f17d5f61050dd42f4f46272b6861512731cb23d5efe8969022d98",
    },
    "alexandre_royal@seduc.to.gov.br": {
        "nome": "ALEXANDRE PEREIRA TOLENTINO",
        "senha": "c729ddde1aa47eea178daeabe56dbb716e976852ac18f2ffafbe2f9fdf0f55a3",
    },
}


def _digest(senha: str) -> str:
    return hashlib.sha256(f"{_SALT}:{senha}".encode("utf-8")).hexdigest()


def autenticar(email: str | None, senha: str | None) -> dict:
    chave = (email or "").strip().lower()
    pessoa = ADMINS.get(chave)
    if not pessoa or not senha:
        raise LookupError("E-mail ou senha inválidos.")
    if not hmac.compare_digest(_digest(senha), pessoa["senha"]):
        raise LookupError("E-mail ou senha inválidos.")
    return {"email": chave, "nome": pessoa["nome"]}


def criar_token(admin: dict) -> str:
    payload = {
        "email": admin["email"],
        "nome": admin["nome"],
        "exp": int(time.time()) + _VALIDADE,
    }
    bruto = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    assinatura = hmac.new(_SECRET.encode(), bruto.encode(), hashlib.sha256).hexdigest()
    return f"{bruto}.{assinatura}"


def admin_do_token(token: str | None) -> dict:
    if not token or "." not in token:
        raise LookupError("Entre com e-mail e senha.")
    bruto, assinatura = token.rsplit(".", 1)
    esperada = hmac.new(_SECRET.encode(), bruto.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(assinatura, esperada):
        raise LookupError("Sessão inválida. Entre de novo.")
    try:
        payload = json.loads(base64.urlsafe_b64decode(bruto.encode()))
    except Exception as exc:
        raise LookupError("Sessão inválida. Entre de novo.") from exc
    if int(payload.get("exp") or 0) < int(time.time()):
        raise LookupError("Sessão expirada. Entre de novo.")
    email = str(payload.get("email") or "").strip().lower()
    pessoa = ADMINS.get(email)
    if not pessoa:
        raise LookupError("Entre com e-mail e senha.")
    return {"email": email, "nome": pessoa["nome"]}
