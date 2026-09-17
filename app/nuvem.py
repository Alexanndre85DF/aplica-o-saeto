from __future__ import annotations

import json

import httpx

from .config import SUPABASE_KEY, SUPABASE_URL

TABELAS = [
    ("municipios", ["id", "nome"]),
    ("escolas", ["id", "codigo", "nome", "municipio_id", "rede", "rural"]),
    ("aplicadores", ["id", "codigo", "nome", "cpf", "numero", "acesso_token", "ativo"]),
    ("viagens", ["id", "municipio_id", "data_saida", "data_retorno", "dias_aplicacao"]),
    ("vagas", [
        "id",
        "escola_id",
        "serie",
        "turno",
        "data",
        "ordem",
        "origem_linha",
        "aplicador_id",
        "status",
        "finalizado_em",
        "turma",
        "n_alunos",
        "n_presentes",
        "alocacao",
        "prova_recebida_em",
        "n_extras",
    ]),
    ("vaga_extras", ["id", "vaga_id", "aplicador_id"]),
    ("sessoes_acesso", ["token", "aplicador_id", "criado_em", "expira_em"]),
    ("meta", ["chave", "valor"]),
]

_CONFLITO = {
    "municipios": "id",
    "escolas": "id",
    "aplicadores": "id",
    "viagens": "id",
    "vagas": "id",
    "vaga_extras": "id",
    "sessoes_acesso": "token",
    "meta": "chave",
}


def _cabecalhos() -> dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal,resolution=merge-duplicates",
    }


def _cliente() -> httpx.Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Falta SUPABASE_URL ou SUPABASE_SERVICE_ROLE_KEY no .env.")
    return httpx.Client(
        base_url=SUPABASE_URL.rstrip("/") + "/rest/v1",
        headers=_cabecalhos(),
        timeout=60.0,
    )


def _json_row(row, colunas: list[str]) -> dict:
    dados = {}
    for col in colunas:
        try:
            valor = row[col]
        except (KeyError, IndexError):
            continue
        dados[col] = valor
    return dados


def contar_municipios_nuvem() -> int:
    with _cliente() as http:
        r = http.get(
            "/municipios",
            params={"select": "id"},
            headers={**_cabecalhos(), "Prefer": "count=exact", "Range": "0-0"},
        )
        r.raise_for_status()
        total = r.headers.get("content-range", "0/0").split("/")[-1]
        try:
            return int(total)
        except ValueError:
            return len(r.json())


def puxar_para_sqlite(conn) -> None:
    with _cliente() as http:
        blocos: dict[str, list[dict]] = {}
        for tabela, colunas in TABELAS:
            r = http.get(f"/{tabela}", params={"select": ",".join(colunas)})
            r.raise_for_status()
            blocos[tabela] = r.json()

    conn.execute("PRAGMA foreign_keys = OFF")
    for tabela, _colunas in reversed(TABELAS):
        conn.execute(f"DELETE FROM {tabela}")
    for tabela, colunas in TABELAS:
        linhas = blocos.get(tabela) or []
        if not linhas:
            continue
        existentes = [c for c in colunas if c in linhas[0] or True]
        ph = ", ".join("?" for _ in existentes)
        cols = ", ".join(existentes)
        for item in linhas:
            conn.execute(
                f"INSERT INTO {tabela} ({cols}) VALUES ({ph})",
                tuple(item.get(c) for c in existentes),
            )
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()


def enviar_do_sqlite(conn) -> dict:
    enviadas = {}
    with _cliente() as http:
        for tabela, colunas in TABELAS:
            try:
                rows = conn.execute(f"SELECT {', '.join(colunas)} FROM {tabela}").fetchall()
            except Exception:
                rows = []
                try:
                    todas = [r[1] for r in conn.execute(f"PRAGMA table_info({tabela})")]
                    usar = [c for c in colunas if c in todas]
                    if usar:
                        rows = conn.execute(f"SELECT {', '.join(usar)} FROM {tabela}").fetchall()
                        colunas = usar
                except Exception:
                    rows = []
            if not rows:
                enviadas[tabela] = 0
                continue
            payload = [_json_row(r, colunas) for r in rows]
            conflito = _CONFLITO.get(tabela, "id")
            total = 0
            for i in range(0, len(payload), 80):
                pedaco = payload[i : i + 80]
                r = http.post(
                    f"/{tabela}",
                    params={"on_conflict": conflito},
                    content=json.dumps(pedaco),
                )
                if r.status_code >= 400:
                    texto = r.text or ""
                    if "23502" in texto and "data" in texto:
                        raise RuntimeError(
                            "No Supabase a coluna data ainda não aceita vazio. "
                            "No SQL Editor rode: ALTER TABLE vagas ALTER COLUMN data DROP NOT NULL; "
                            "Depois clique de novo em Mandar tudo para o Supabase."
                        )
                    raise RuntimeError(
                        f"Supabase recusou {tabela}: {r.status_code} {texto[:240]}"
                    )
                total += len(pedaco)
            enviadas[tabela] = total
    return enviadas


def erro_nuvem(exc: Exception) -> RuntimeError:
    return RuntimeError(
        "Não foi possível gravar no Supabase pela internet. "
        "Rode o SQL da pasta supabase no painel e confira a chave no .env."
    )
