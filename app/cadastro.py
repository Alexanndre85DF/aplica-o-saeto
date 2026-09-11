from __future__ import annotations

import json
import re
from datetime import date, timedelta

from .regras import (
    REDES,
    TURNOS,
    dias_do_municipio,
    eh_segundo_ano_dia1,
    normalizar_dias,
    normalizar_serie,
    normalizar_texto,
    normalizar_turno,
    periodo_dias,
    serie_par_segundo_ano,
)

SERIES_PADRAO = [
    "2º ANO - DIA 1",
    "2º ANO - DIA 2",
    "5º ANO",
    "8º ANO",
    "9º ANO",
    "2ª SÉRIE",
    "3ª SÉRIE",
]


def opcoes() -> dict:
    return {"redes": list(REDES), "turnos": list(TURNOS), "series": SERIES_PADRAO}


def _data_iso(valor: str | None) -> str | None:
    if not valor:
        return None
    texto = str(valor).strip()[:10]
    date.fromisoformat(texto)
    return texto


UNSET = object()


def _nome_mun(valor: str) -> str:
    nome = normalizar_texto(valor).upper()
    if not nome:
        raise ValueError("Informe o nome do município.")
    return nome


def proximo_codigo(conn, prefixo: str, tabela: str, coluna: str) -> str:
    n = conn.execute(f"SELECT COUNT(*) n FROM {tabela}").fetchone()["n"] + 1
    while True:
        codigo = f"{prefixo}-{n:04d}"
        existe = conn.execute(
            f"SELECT 1 FROM {tabela} WHERE {coluna} = ?", (codigo,)
        ).fetchone()
        if not existe:
            return codigo
        n += 1


def _gravar_viagem(conn, municipio_id: int, saida, retorno, dias) -> None:
    lista = normalizar_dias(dias) if dias is not None else periodo_dias(saida, retorno)
    if lista:
        saida = lista[0]
        retorno = lista[-1]
        bruto = json.dumps(lista)
    else:
        saida = None
        retorno = None
        bruto = None
    existe = conn.execute(
        "SELECT 1 FROM viagens WHERE municipio_id = ?", (municipio_id,)
    ).fetchone()
    if existe:
        conn.execute(
            """UPDATE viagens SET data_saida = ?, data_retorno = ?, dias_aplicacao = ?
               WHERE municipio_id = ?""",
            (saida, retorno, bruto, municipio_id),
        )
    else:
        conn.execute(
            """INSERT INTO viagens(municipio_id, data_saida, data_retorno, dias_aplicacao)
               VALUES (?, ?, ?, ?)""",
            (municipio_id, saida, retorno, bruto),
        )


def criar_municipio(conn, nome: str, data_saida=None, data_retorno=None, dias=None) -> dict:
    nome = _nome_mun(nome)
    existente = conn.execute(
        "SELECT id FROM municipios WHERE nome = ?", (nome,)
    ).fetchone()
    if existente:
        raise ValueError("Este município já está cadastrado.")
    cur = conn.execute("INSERT INTO municipios(nome) VALUES (?)", (nome,))
    municipio_id = cur.lastrowid
    saida = _data_iso(data_saida)
    retorno = _data_iso(data_retorno)
    _gravar_viagem(conn, municipio_id, saida, retorno, dias)
    return obter_municipio(conn, municipio_id)


def _limpar_datas_vagas_municipio(conn, municipio_id: int) -> None:
    conn.execute(
        """UPDATE vagas SET data = NULL
           WHERE escola_id IN (SELECT id FROM escolas WHERE municipio_id = ?)""",
        (municipio_id,),
    )


def atualizar_municipio(
    conn,
    municipio_id: int,
    nome=None,
    data_saida=UNSET,
    data_retorno=UNSET,
    dias=UNSET,
    limpar_datas_vagas: bool = False,
) -> dict:
    atual = conn.execute("SELECT * FROM municipios WHERE id = ?", (municipio_id,)).fetchone()
    if not atual:
        raise LookupError("Município não encontrado.")
    if nome is not None:
        nome = _nome_mun(nome)
        outro = conn.execute(
            "SELECT id FROM municipios WHERE nome = ? AND id != ?",
            (nome, municipio_id),
        ).fetchone()
        if outro:
            raise ValueError("Já existe outro município com esse nome.")
        conn.execute("UPDATE municipios SET nome = ? WHERE id = ?", (nome, municipio_id))
    viagem = conn.execute(
        "SELECT data_saida, data_retorno, dias_aplicacao FROM viagens WHERE municipio_id = ?",
        (municipio_id,),
    ).fetchone()
    if dias is not UNSET or data_saida is not UNSET or data_retorno is not UNSET:
        if dias is not UNSET:
            lista = normalizar_dias(dias)
            saida = lista[0] if lista else None
            retorno = lista[-1] if lista else None
        else:
            saida = (
                _data_iso(data_saida)
                if data_saida is not UNSET
                else (viagem["data_saida"] if viagem else None)
            )
            retorno = (
                _data_iso(data_retorno)
                if data_retorno is not UNSET
                else (viagem["data_retorno"] if viagem else None)
            )
            if saida and not retorno:
                retorno = saida
            lista = periodo_dias(saida, retorno)
        _gravar_viagem(conn, municipio_id, saida, retorno, lista)
        if not lista:
            limpar_datas_vagas = True
    if limpar_datas_vagas:
        _limpar_datas_vagas_municipio(conn, municipio_id)
    return obter_municipio(conn, municipio_id)


def excluir_municipio(conn, municipio_id: int) -> None:
    atual = conn.execute("SELECT id FROM municipios WHERE id = ?", (municipio_id,)).fetchone()
    if not atual:
        raise LookupError("Município não encontrado.")
    n_escolas = conn.execute(
        "SELECT COUNT(*) n FROM escolas WHERE municipio_id = ?", (municipio_id,)
    ).fetchone()["n"]
    if n_escolas:
        raise ValueError(
            f"Não dá para excluir: ainda há {n_escolas} escola(s) neste município."
        )
    conn.execute("DELETE FROM viagens WHERE municipio_id = ?", (municipio_id,))
    conn.execute("DELETE FROM municipios WHERE id = ?", (municipio_id,))


def obter_municipio(conn, municipio_id: int) -> dict:
    row = conn.execute(
        """SELECT m.*, v.data_saida, v.data_retorno, v.dias_aplicacao
           FROM municipios m
           LEFT JOIN viagens v ON v.municipio_id = m.id
           WHERE m.id = ?""",
        (municipio_id,),
    ).fetchone()
    if not row:
        raise LookupError("Município não encontrado.")
    dados = dict(row)
    dados["dias"] = dias_do_municipio(dados)
    return dados


def criar_escola(conn, municipio_id: int, nome: str, codigo=None, rede="MUNICIPAL", rural=False) -> dict:
    mun = conn.execute("SELECT id FROM municipios WHERE id = ?", (municipio_id,)).fetchone()
    if not mun:
        raise LookupError("Município não encontrado.")
    nome = normalizar_texto(nome)
    if not nome:
        raise ValueError("Informe o nome da escola.")
    codigo = normalizar_texto(codigo)
    if not codigo:
        codigo = proximo_codigo(conn, "CAD", "escolas", "codigo")
    if rede not in REDES:
        raise ValueError("Rede inválida.")
    existe = conn.execute("SELECT id FROM escolas WHERE codigo = ?", (codigo,)).fetchone()
    if existe:
        raise ValueError("Já existe escola com esse código.")
    cur = conn.execute(
        """INSERT INTO escolas(codigo, nome, municipio_id, rede, rural)
           VALUES (?, ?, ?, ?, ?)""",
        (codigo, nome.upper(), municipio_id, rede, 1 if rural else 0),
    )
    return dict(conn.execute("SELECT * FROM escolas WHERE id = ?", (cur.lastrowid,)).fetchone())


def atualizar_escola(conn, escola_id: int, **campos) -> dict:
    atual = conn.execute("SELECT * FROM escolas WHERE id = ?", (escola_id,)).fetchone()
    if not atual:
        raise LookupError("Escola não encontrada.")
    nome = normalizar_texto(campos["nome"]) if campos.get("nome") is not None else atual["nome"]
    codigo = normalizar_texto(campos["codigo"]) if campos.get("codigo") is not None else atual["codigo"]
    municipio_id = campos.get("municipio_id") if campos.get("municipio_id") is not None else atual["municipio_id"]
    rede = campos.get("rede") if campos.get("rede") is not None else atual["rede"]
    rural = atual["rural"] if campos.get("rural") is None else (1 if campos["rural"] else 0)
    if not nome:
        raise ValueError("Informe o nome da escola.")
    if not codigo:
        raise ValueError("Informe o código da escola.")
    if rede not in REDES:
        raise ValueError("Rede inválida.")
    mun = conn.execute("SELECT id FROM municipios WHERE id = ?", (municipio_id,)).fetchone()
    if not mun:
        raise LookupError("Município não encontrado.")
    outro = conn.execute(
        "SELECT id FROM escolas WHERE codigo = ? AND id != ?", (codigo, escola_id)
    ).fetchone()
    if outro:
        raise ValueError("Já existe outra escola com esse código.")
    conn.execute(
        """UPDATE escolas SET codigo=?, nome=?, municipio_id=?, rede=?, rural=?
           WHERE id=?""",
        (codigo, nome.upper(), municipio_id, rede, rural, escola_id),
    )
    return dict(conn.execute("SELECT * FROM escolas WHERE id = ?", (escola_id,)).fetchone())


def excluir_escola(conn, escola_id: int) -> None:
    atual = conn.execute("SELECT id FROM escolas WHERE id = ?", (escola_id,)).fetchone()
    if not atual:
        raise LookupError("Escola não encontrada.")
    n = conn.execute("SELECT COUNT(*) n FROM vagas WHERE escola_id = ?", (escola_id,)).fetchone()["n"]
    if n:
        raise ValueError(f"Não dá para excluir: ainda há {n} aplicação(ões) nesta escola.")
    conn.execute("DELETE FROM escolas WHERE id = ?", (escola_id,))


def criar_lote_aplicadores(conn, quantidade: int) -> dict:
    qtd = int(quantidade or 0)
    if qtd < 1:
        raise ValueError("Informe quantos aplicadores criar, por exemplo 15.")
    if qtd > 200:
        raise ValueError("No máximo 200 de uma vez.")
    from .db import sincronizar_sequencias

    sincronizar_sequencias(conn)
    max_n = 0
    for r in conn.execute("SELECT codigo, numero FROM aplicadores"):
        n = r["numero"] if r["numero"] is not None else numero_do_codigo(r["codigo"])
        if n and n > max_n:
            max_n = n
    inicio = max_n + 1
    criados = []
    for n in range(inicio, inicio + qtd):
        codigo = codigo_do_numero(n)
        if conn.execute("SELECT id FROM aplicadores WHERE codigo = ?", (codigo,)).fetchone():
            continue
        try:
            conn.execute(
                """INSERT INTO aplicadores(codigo, nome, numero, ativo)
                   VALUES (?, ?, ?, 1)""",
                (codigo, codigo, n),
            )
        except Exception as exc:
            texto = str(exc).lower()
            if "unique" in texto or "duplicate" in texto:
                sincronizar_sequencias(conn)
                if conn.execute("SELECT id FROM aplicadores WHERE codigo = ?", (codigo,)).fetchone():
                    continue
                try:
                    conn.execute(
                        """INSERT INTO aplicadores(codigo, nome, numero, ativo)
                           VALUES (?, ?, ?, 1)""",
                        (codigo, codigo, n),
                    )
                except Exception as retry:
                    raise ValueError(
                        "Não deu para criar o próximo aplicador no banco. "
                        "O número de ID pode estar desalinhado no Supabase. Tente de novo."
                    ) from retry
            else:
                raise ValueError("Não deu para criar o aplicador: " + str(exc)) from exc
        criados.append({"numero": n, "codigo": codigo})
    if not criados:
        raise ValueError("Esses números já existem.")
    return {
        "inicio": criados[0]["numero"],
        "fim": criados[-1]["numero"],
        "quantidade": len(criados),
        "criados": criados,
    }


def criar_aplicador(conn, nome: str, codigo=None, cpf=None, numero=None) -> dict:
    nome = normalizar_texto(nome)
    if not nome:
        raise ValueError("Informe o nome do aplicador.")
    return vincular_pessoa(conn, nome=nome, cpf=cpf, numero=numero, codigo=codigo)


def numero_do_codigo(codigo: str | None) -> int | None:
    m = re.search(r"(\d+)", codigo or "")
    return int(m.group(1)) if m else None


def codigo_do_numero(numero: int) -> str:
    return f"Aplicador {int(numero):02d}"


def formatar_cpf(digitos: str | None) -> str:
    if not digitos:
        return ""
    d = re.sub(r"\D", "", digitos)
    if len(d) != 11:
        return digitos
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def normalizar_cpf(valor) -> str | None:
    if valor is None or str(valor).strip() == "":
        return None
    d = re.sub(r"\D", "", str(valor))
    if not d:
        return None
    if len(d) != 11:
        raise ValueError("CPF deve ter 11 dígitos.")
    if d == d[0] * 11:
        raise ValueError("CPF inválido.")
    return d


def _eh_placeholder(nome: str | None, codigo: str | None) -> bool:
    texto = (nome or "").strip()
    if not texto:
        return True
    if codigo and texto.upper() == codigo.upper():
        return True
    return bool(re.match(r"^(aplicador|ap)\s*\d+$", texto, re.I))


def achar_por_numero(conn, numero: int):
    rows = list(
        conn.execute(
            "SELECT * FROM aplicadores WHERE numero = ? ORDER BY codigo", (numero,)
        )
    )
    if not rows:
        rows = [
            r
            for r in conn.execute("SELECT * FROM aplicadores")
            if numero_do_codigo(r["codigo"]) == numero
        ]
    if not rows:
        return None
    alvo = codigo_do_numero(numero).upper()
    for r in rows:
        if (r["codigo"] or "").upper() == alvo:
            return r
    return rows[0]


def vincular_pessoa(conn, nome: str, cpf=None, numero=None, codigo=None) -> dict:
    nome = normalizar_texto(nome)
    if not nome:
        raise ValueError("Informe o nome do aplicador.")
    codigo = normalizar_texto(codigo) if codigo else None
    if numero is None or numero == "":
        numero = numero_do_codigo(codigo) if codigo else None
    else:
        numero = int(numero)
    if numero is None:
        raise ValueError("Informe o número do aplicador, por exemplo 3.")
    if numero < 1:
        raise ValueError("Número do aplicador inválido.")

    cpf_n = normalizar_cpf(cpf)
    alvo = None
    if codigo:
        alvo = conn.execute(
            "SELECT * FROM aplicadores WHERE codigo = ?", (codigo,)
        ).fetchone()
    if not alvo:
        alvo = achar_por_numero(conn, numero)

    if cpf_n:
        outro = conn.execute(
            "SELECT id, nome, codigo FROM aplicadores WHERE cpf = ?", (cpf_n,)
        ).fetchone()
        if outro and (alvo is None or outro["id"] != alvo["id"]):
            raise ValueError(f"Este CPF já está em {outro['nome'] or outro['codigo']}.")

    if not alvo:
        cur = conn.execute(
            """INSERT INTO aplicadores(codigo, nome, cpf, numero, ativo)
               VALUES (?, ?, ?, ?, 1)""",
            (codigo or codigo_do_numero(numero), nome, cpf_n, numero),
        )
        aplicador_id = cur.lastrowid
    else:
        conn.execute(
            "UPDATE aplicadores SET nome = ?, cpf = ?, numero = ? WHERE id = ?",
            (nome, cpf_n, numero, alvo["id"]),
        )
        aplicador_id = alvo["id"]

    from .acesso import garantir_token_acesso

    if cpf_n:
        garantir_token_acesso(conn, aplicador_id)
    return dict(
        conn.execute("SELECT * FROM aplicadores WHERE id = ?", (aplicador_id,)).fetchone()
    )


def excluir_aplicador(conn, aplicador_id: int) -> None:
    atual = conn.execute("SELECT id FROM aplicadores WHERE id = ?", (aplicador_id,)).fetchone()
    if not atual:
        raise LookupError("Aplicador não encontrado.")
    conn.execute("DELETE FROM sessoes_acesso WHERE aplicador_id = ?", (aplicador_id,))
    conn.execute(
        """UPDATE vagas SET aplicador_id = NULL, alocacao = NULL, prova_recebida_em = NULL
           WHERE aplicador_id = ?""",
        (aplicador_id,),
    )
    conn.execute("DELETE FROM aplicadores WHERE id = ?", (aplicador_id,))


def criar_vaga(conn, escola_id: int, serie: str, turno: str, data: str, quantidade: int = 1, criar_par: bool = True) -> list[int]:
    escola = conn.execute("SELECT id FROM escolas WHERE id = ?", (escola_id,)).fetchone()
    if not escola:
        raise LookupError("Escola não encontrada.")
    serie = normalizar_serie(serie)
    turno = normalizar_turno(turno)
    data_iso = _data_iso(data)
    if not serie or not data_iso:
        raise ValueError("Informe série e data.")
    if turno not in TURNOS:
        raise ValueError("Turno inválido.")
    qtd = max(1, int(quantidade or 1))
    ids = []
    for _ in range(qtd):
        ordem = conn.execute(
            """SELECT COALESCE(MAX(ordem), 0) n FROM vagas
               WHERE escola_id = ? AND serie = ? AND turno = ?""",
            (escola_id, serie, turno),
        ).fetchone()["n"] + 1
        cur = conn.execute(
            """INSERT INTO vagas(escola_id, serie, turno, data, ordem, origem_linha, status)
               VALUES (?, ?, ?, ?, ?, NULL, 'PREVISTA')""",
            (escola_id, serie, turno, data_iso, ordem),
        )
        ids.append(cur.lastrowid)
        if criar_par and eh_segundo_ano_dia1(serie):
            par = serie_par_segundo_ano(serie)
            data_par = (date.fromisoformat(data_iso) + timedelta(days=1)).isoformat()
            ordem_par = conn.execute(
                """SELECT COALESCE(MAX(ordem), 0) n FROM vagas
                   WHERE escola_id = ? AND serie = ? AND turno = ?""",
                (escola_id, par, turno),
            ).fetchone()["n"] + 1
            conn.execute(
                """INSERT INTO vagas(escola_id, serie, turno, data, ordem, origem_linha, status)
                   VALUES (?, ?, ?, ?, ?, NULL, 'PREVISTA')""",
                (escola_id, par, turno, data_par, ordem_par),
            )
    return ids


def excluir_vaga(conn, vaga_id: int) -> None:
    atual = conn.execute("SELECT id FROM vagas WHERE id = ?", (vaga_id,)).fetchone()
    if not atual:
        raise LookupError("Vaga não encontrada.")
    conn.execute("DELETE FROM vagas WHERE id = ?", (vaga_id,))


def origem_manual(conn) -> bool:
    row = conn.execute("SELECT valor FROM meta WHERE chave = 'origem_manual'").fetchone()
    return bool(row and row["valor"] == "1")


def zerar_tudo(conn) -> None:
    conn.execute("DELETE FROM sessoes_acesso")
    conn.execute("DELETE FROM vagas")
    conn.execute("DELETE FROM viagens")
    conn.execute("DELETE FROM escolas")
    conn.execute("DELETE FROM aplicadores")
    conn.execute("DELETE FROM municipios")
    conn.execute("INSERT OR REPLACE INTO meta(chave, valor) VALUES ('origem_manual', '1')")
