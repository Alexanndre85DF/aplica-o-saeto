from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from .cadastro import formatar_cpf, normalizar_cpf
from .regras import fmt_data


def garantir_token_acesso(conn, aplicador_id: int) -> str:
    row = conn.execute(
        "SELECT acesso_token FROM aplicadores WHERE id = ?", (aplicador_id,)
    ).fetchone()
    if row and row["acesso_token"]:
        return row["acesso_token"]
    token = secrets.token_urlsafe(16)
    while conn.execute(
        "SELECT 1 FROM aplicadores WHERE acesso_token = ?", (token,)
    ).fetchone():
        token = secrets.token_urlsafe(16)
    conn.execute(
        "UPDATE aplicadores SET acesso_token = ? WHERE id = ?",
        (token, aplicador_id),
    )
    return token


def entrar_por_cpf(conn, cpf, token_link: str | None = None) -> dict:
    cpf_n = normalizar_cpf(cpf)
    if not cpf_n:
        raise ValueError("Informe um CPF válido.")
    pessoa = conn.execute(
        "SELECT * FROM aplicadores WHERE cpf = ? AND ativo = 1", (cpf_n,)
    ).fetchone()
    if not pessoa:
        raise LookupError("CPF não cadastrado. Peça o vínculo na SRE.")
    if token_link:
        if not pessoa["acesso_token"] or pessoa["acesso_token"] != token_link:
            raise LookupError("Este link não corresponde a este CPF.")
    garantir_token_acesso(conn, pessoa["id"])
    sessao = secrets.token_urlsafe(24)
    agora = datetime.now(timezone.utc)
    expira = agora + timedelta(hours=12)
    conn.execute(
        """INSERT INTO sessoes_acesso(token, aplicador_id, criado_em, expira_em)
           VALUES (?, ?, ?, ?)""",
        (sessao, pessoa["id"], agora.isoformat(), expira.isoformat()),
    )
    pessoa = conn.execute(
        "SELECT * FROM aplicadores WHERE id = ?", (pessoa["id"],)
    ).fetchone()
    return {
        "sessao": sessao,
        "aplicador": _publico(pessoa),
        "expira_em": expira.isoformat(),
    }


def aplicador_da_sessao(conn, sessao: str | None) -> dict:
    if not sessao:
        raise LookupError("Entre com seu CPF.")
    agora = datetime.now(timezone.utc).isoformat()
    row = conn.execute(
        """SELECT a.* FROM sessoes_acesso s
           JOIN aplicadores a ON a.id = s.aplicador_id
           WHERE s.token = ? AND s.expira_em > ? AND a.ativo = 1""",
        (sessao, agora),
    ).fetchone()
    if not row:
        raise LookupError("Sessão expirada. Entre de novo com o CPF.")
    return dict(row)


def encerrar_sessao(conn, sessao: str | None) -> None:
    if sessao:
        conn.execute("DELETE FROM sessoes_acesso WHERE token = ?", (sessao,))


def _publico(pessoa) -> dict:
    return {
        "id": pessoa["id"],
        "nome": pessoa["nome"] or pessoa["codigo"],
        "codigo": pessoa["codigo"],
        "numero": pessoa["numero"],
        "cpf_fmt": formatar_cpf(pessoa["cpf"]),
    }


def minhas_aplicacoes(conn, aplicador_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT v.id, v.serie, v.turno, v.data, v.ordem, v.status, v.turma, v.n_alunos,
                  e.nome AS escola, e.codigo AS escola_codigo, e.rede, e.rural,
                  m.nome AS municipio, vi.data_saida, vi.data_retorno
           FROM vagas v
           JOIN escolas e ON e.id = v.escola_id
           JOIN municipios m ON m.id = e.municipio_id
           LEFT JOIN viagens vi ON vi.municipio_id = m.id
           WHERE v.aplicador_id = ?
           ORDER BY v.data, v.turno, e.nome, v.serie""",
        (aplicador_id,),
    ).fetchall()
    lista = []
    for r in rows:
        item = dict(r)
        item["data_fmt"] = fmt_data(item["data"])
        item["saida_fmt"] = fmt_data(item["data_saida"])
        item["retorno_fmt"] = fmt_data(item["data_retorno"])
        item["finalizada"] = item["status"] == "FINALIZADA"
        lista.append(item)
    return lista
