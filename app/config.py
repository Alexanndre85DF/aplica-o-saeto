from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "saeto.db"

load_dotenv(ROOT / ".env")

# Postgres direto (porta 5432/6543) — nesta rede da SEDUC costuma travar.
# O sistema usa a API HTTPS (SUPABASE_URL + chave).
def _limpar_url(valor: str) -> str:
    texto = (valor or "").strip().strip('"').strip("'")
    if "=" in texto:
        chave, resto = texto.split("=", 1)
        if chave.strip().upper() in {"DATABASE_URL", "DIRECT_URL", "SUPABASE_DB_URL"}:
            texto = resto.strip().strip('"').strip("'")
    return texto


DATABASE_URL = _limpar_url(os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL") or "")
# Na SEDUC o Postgres costuma travar. No Render (RENDER=true) usa o banco da nuvem.
USAR_POSTGRES = os.getenv("SUPABASE_USE_POSTGRES", "").strip() in {"1", "true", "sim"} or (
    bool(DATABASE_URL) and bool(os.getenv("RENDER"))
)

SUPABASE_URL = (
    os.getenv("SUPABASE_URL") or "https://oudpmxtlfgpyrrwfzqbd.supabase.co"
).strip().strip('"').strip("'")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_SECRET_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
    or ""
).strip().strip('"').strip("'")


def usando_postgres() -> bool:
    return bool(USAR_POSTGRES and DATABASE_URL)


def usando_nuvem() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def usando_supabase() -> bool:
    return usando_postgres()


def localizar_planilha() -> Path | None:
    atual = DATA_DIR / "planilha-atual.xlsx"
    if atual.exists():
        return atual
    arquivos = sorted(ROOT.glob("*.xlsx"))
    return arquivos[0] if arquivos else None
