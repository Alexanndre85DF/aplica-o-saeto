from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import random

from .regras import (
    dia_vizinho,
    dias_do_municipio,
    eh_segundo_ano_dia1,
    eh_segundo_ano_dia2,
    serie_par_segundo_ano,
)


def _nome_aplicador(row) -> str | None:
    if row is None:
        return None
    return row["nome"] or row["codigo"]


def problemas_da_vaga(conn, vaga: dict) -> list[dict]:
    problemas = []
    aplicador_id = vaga.get("aplicador_id")
    if not aplicador_id:
        problemas.append(
            {
                "tipo": "vago",
                "grau": "vago",
                "mensagem": "Sem aplicador nesta vaga.",
            }
        )
        return problemas

    outros = conn.execute(
        """
        SELECT v.*, e.nome AS escola_nome, e.codigo AS escola_codigo,
               m.nome AS municipio_nome, m.id AS municipio_id
        FROM vagas v
        JOIN escolas e ON e.id = v.escola_id
        JOIN municipios m ON m.id = e.municipio_id
        WHERE v.aplicador_id = ? AND v.id != ?
        """,
        (aplicador_id, vaga["id"]),
    ).fetchall()

    mun_atual = vaga.get("municipio_id")
    mesma_data = bool(vaga.get("data"))
    for o in outros:
        if not mesma_data or not o["data"]:
            if o["municipio_id"] != mun_atual:
                problemas.append(
                    {
                        "tipo": "municipio_outro",
                        "grau": "aviso",
                        "mensagem": f"Também alocado em {o['municipio_nome']}.",
                    }
                )
            continue
        if o["data"] == vaga["data"] and o["turno"] == vaga["turno"] and o["escola_id"] != vaga["escola_id"]:
            problemas.append(
                {
                    "tipo": "choque",
                    "grau": "choque",
                    "mensagem": (
                        f"Choque: já está em {o['escola_nome']} "
                        f"({o['turno'].title()}) no mesmo dia."
                    ),
                }
            )
        elif o["data"] == vaga["data"] and o["municipio_id"] != mun_atual:
            problemas.append(
                {
                    "tipo": "municipio_mesmo_dia",
                    "grau": "choque",
                    "mensagem": f"Já está em {o['municipio_nome']} neste dia.",
                }
            )
        elif o["municipio_id"] != mun_atual:
            problemas.append(
                {
                    "tipo": "municipio_outro",
                    "grau": "aviso",
                    "mensagem": f"Também alocado em {o['municipio_nome']}.",
                }
            )
        elif (
            o["data"] == vaga["data"]
            and o["escola_id"] != vaga["escola_id"]
            and {o["turno"], vaga["turno"]} == {"MATUTINO", "VESPERTINO"}
        ):
            problemas.append(
                {
                    "tipo": "dois_turnos",
                    "grau": "aviso",
                    "mensagem": (
                        f"Manhã e tarde em escolas diferentes: {o['escola_nome']}."
                    ),
                }
            )
        elif (
            o["data"] == vaga["data"]
            and "INTEGRAL" in (o["turno"], vaga["turno"])
            and o["turno"] != vaga["turno"]
        ):
            problemas.append(
                {
                    "tipo": "integral",
                    "grau": "aviso",
                    "mensagem": "Turno integral no mesmo dia de outro turno.",
                }
            )

    par = serie_par_segundo_ano(vaga["serie"])
    if par:
        par_row = conn.execute(
            """SELECT v.aplicador_id, a.codigo, a.nome
               FROM vagas v
               LEFT JOIN aplicadores a ON a.id = v.aplicador_id
               WHERE v.escola_id = ? AND v.turno = ? AND v.serie = ? AND v.ordem = ?""",
            (vaga["escola_id"], vaga["turno"], par, vaga.get("ordem") or 1),
        ).fetchone()
        if par_row and par_row["aplicador_id"] and par_row["aplicador_id"] != aplicador_id:
            problemas.append(
                {
                    "tipo": "par_2ano",
                    "grau": "aviso",
                    "mensagem": (
                        "2º ano Dia 1 e Dia 2 com aplicadores diferentes "
                        f"({par_row['nome'] or par_row['codigo']})."
                    ),
                }
            )
        elif par_row and not par_row["aplicador_id"] and eh_segundo_ano_dia1(vaga["serie"]):
            problemas.append(
                {
                    "tipo": "par_2ano_vago",
                    "grau": "aviso",
                    "mensagem": "O Dia 2 desta turma ainda está vago.",
                }
            )

    vistos = set()
    unicos = []
    for p in problemas:
        chave = (p["tipo"], p["mensagem"])
        if chave in vistos:
            continue
        vistos.add(chave)
        unicos.append(p)
    return unicos


def enriquecer_vaga(conn, vaga: dict) -> dict:
    problemas = problemas_da_vaga(conn, vaga)
    vaga["problemas"] = problemas
    vaga["tem_choque"] = any(p["grau"] == "choque" for p in problemas)
    vaga["tem_aviso"] = any(p["grau"] == "aviso" for p in problemas)
    vaga["vago"] = vaga.get("aplicador_id") is None
    return vaga


def pode_alocar(conn, vaga_id: int, aplicador_id: int) -> dict:
    vaga = conn.execute(
        """SELECT v.*, e.nome AS escola_nome, e.municipio_id, m.nome AS municipio_nome
           FROM vagas v
           JOIN escolas e ON e.id = v.escola_id
           JOIN municipios m ON m.id = e.municipio_id
           WHERE v.id = ?""",
        (vaga_id,),
    ).fetchone()
    if not vaga:
        return {"ok": False, "erro": "Vaga não encontrada."}

    simulada = dict(vaga)
    simulada["aplicador_id"] = aplicador_id
    problemas = problemas_da_vaga(conn, simulada)
    choques = [p for p in problemas if p["grau"] == "choque"]
    return {
        "ok": len(choques) == 0,
        "choques": choques,
        "avisos": [p for p in problemas if p["grau"] == "aviso"],
        "problemas": problemas,
    }


def candidatos_para_vaga(conn, vaga_id: int) -> list[dict]:
    vaga = conn.execute(
        """SELECT v.*, e.municipio_id
           FROM vagas v
           JOIN escolas e ON e.id = v.escola_id
           WHERE v.id = ?""",
        (vaga_id,),
    ).fetchone()
    if not vaga:
        return []

    aplicadores = conn.execute(
        "SELECT * FROM aplicadores WHERE ativo = 1 ORDER BY codigo"
    ).fetchall()

    cargas = {
        r["aplicador_id"]: r["n"]
        for r in conn.execute(
            """SELECT aplicador_id, COUNT(*) n FROM vagas
               WHERE aplicador_id IS NOT NULL GROUP BY aplicador_id"""
        )
    }
    muns = defaultdict(set)
    for r in conn.execute(
        """SELECT v.aplicador_id, e.municipio_id
           FROM vagas v JOIN escolas e ON e.id = v.escola_id
           WHERE v.aplicador_id IS NOT NULL"""
    ):
        muns[r["aplicador_id"]].add(r["municipio_id"])

    lista = []
    for a in aplicadores:
        checagem = pode_alocar(conn, vaga_id, a["id"])
        ja_no_mun = vaga["municipio_id"] in muns[a["id"]]
        lista.append(
            {
                "id": a["id"],
                "codigo": a["codigo"],
                "nome": a["nome"] or a["codigo"],
                "carga": cargas.get(a["id"], 0),
                "no_municipio": ja_no_mun,
                "ok": checagem["ok"],
                "choques": checagem["choques"],
                "avisos": checagem["avisos"],
                "selecionado": a["id"] == vaga["aplicador_id"],
            }
        )

    lista.sort(key=lambda x: (not x["ok"], not x["no_municipio"], x["carga"], x["nome"]))
    return lista


def alocar(
    conn,
    vaga_id: int,
    aplicador_id: int | None,
    repetir_par: bool = True,
    data: str | None = None,
    forcar: bool = False,
) -> dict:
    vaga = conn.execute(
        """SELECT v.*, e.municipio_id
           FROM vagas v JOIN escolas e ON e.id = v.escola_id WHERE v.id = ?""",
        (vaga_id,),
    ).fetchone()
    if not vaga:
        return {"ok": False, "erro": "Vaga não encontrada."}
    vaga = dict(vaga)

    if aplicador_id is None and not data:
        conn.execute(
            """UPDATE vagas SET aplicador_id = NULL, alocacao = NULL, data = NULL
               WHERE id = ?""",
            (vaga_id,),
        )
        if repetir_par:
            _espelhar_par(conn, vaga, None, origem=None)
        return {"ok": True, "liberada": True}

    if data:
        aplicar_data_na_vaga(conn, vaga, data[:10], repetir_par)
        vaga["data"] = data[:10]
    elif aplicador_id is not None:
        garantir_data_do_periodo(conn, vaga, repetir_par)

    if aplicador_id is None:
        return {"ok": True, "avisos": [], "par_atualizado": bool(repetir_par)}

    checagem = pode_alocar(conn, vaga_id, aplicador_id)
    if not checagem["ok"] and not forcar:
        return {
            "ok": False,
            "erro": "Choque de horário: este aplicador já está em outra escola neste turno.",
            "choques": checagem["choques"],
        }

    conn.execute(
        "UPDATE vagas SET aplicador_id = ?, alocacao = ? WHERE id = ?",
        (aplicador_id, "MANUAL", vaga_id),
    )
    par_atualizado = False
    if repetir_par:
        par_atualizado = _espelhar_par(conn, vaga, aplicador_id, origem="MANUAL")
    return {
        "ok": True,
        "avisos": checagem["avisos"],
        "par_atualizado": par_atualizado,
        "forcado": bool(forcar and not checagem["ok"]),
    }


def _espelhar_par(conn, vaga, aplicador_id: int | None, origem: str | None = "AUTO") -> bool:
    par = serie_par_segundo_ano(vaga["serie"])
    if not par:
        return False
    ordem = vaga["ordem"] if vaga["ordem"] is not None else 1
    outra = conn.execute(
        """SELECT id FROM vagas
           WHERE escola_id = ? AND turno = ? AND serie = ? AND ordem = ?""",
        (vaga["escola_id"], vaga["turno"], par, ordem),
    ).fetchone()
    if not outra:
        return False
    if aplicador_id is None:
        conn.execute(
            """UPDATE vagas SET aplicador_id = NULL, alocacao = NULL, data = NULL
               WHERE id = ?""",
            (outra["id"],),
        )
        return True
    checagem = pode_alocar(conn, outra["id"], aplicador_id)
    if checagem["ok"] or origem == "MANUAL":
        conn.execute(
            "UPDATE vagas SET aplicador_id = ?, alocacao = ? WHERE id = ?",
            (aplicador_id, origem or "AUTO", outra["id"]),
        )
        return True
    return False


def _ordem_vaga(vaga) -> int:
    return vaga["ordem"] if vaga.get("ordem") is not None else 1


def _viagem_municipio(conn, municipio_id: int):
    return conn.execute(
        "SELECT data_saida, data_retorno, dias_aplicacao FROM viagens WHERE municipio_id = ?",
        (municipio_id,),
    ).fetchone()


def _dias_da_vaga(conn, vaga: dict) -> list[str]:
    mid = vaga.get("municipio_id")
    if not mid and vaga.get("id"):
        row = conn.execute(
            """SELECT e.municipio_id FROM vagas v
               JOIN escolas e ON e.id = v.escola_id WHERE v.id = ?""",
            (vaga["id"],),
        ).fetchone()
        mid = row["municipio_id"] if row else None
    if not mid:
        return []
    return dias_do_municipio(_viagem_municipio(conn, mid))


def aplicar_data_na_vaga(conn, vaga: dict, data_iso: str, repetir_par: bool = True) -> None:
    conn.execute("UPDATE vagas SET data = ? WHERE id = ?", (data_iso, vaga["id"]))
    if not repetir_par:
        return
    par = serie_par_segundo_ano(vaga["serie"])
    if not par:
        return
    ordem = _ordem_vaga(vaga)
    dias = _dias_da_vaga(conn, vaga)
    if eh_segundo_ano_dia1(vaga["serie"]):
        dia_par = dia_vizinho(dias, data_iso, 1)
    elif eh_segundo_ano_dia2(vaga["serie"]):
        dia_par = dia_vizinho(dias, data_iso, -1)
    else:
        return
    conn.execute(
        """UPDATE vagas SET data = ?
           WHERE escola_id = ? AND turno = ? AND ordem = ? AND serie = ?""",
        (dia_par, vaga["escola_id"], vaga["turno"], ordem, par),
    )


def garantir_data_do_periodo(conn, vaga: dict, repetir_par: bool = True) -> None:
    if vaga.get("data"):
        return
    periodo = _dias_da_vaga(conn, vaga)
    if not periodo:
        return
    data = periodo[0]
    if eh_segundo_ano_dia2(vaga["serie"]):
        data = periodo[1] if len(periodo) > 1 else dia_vizinho(periodo, periodo[0], 1)
    elif eh_segundo_ano_dia1(vaga["serie"]) and len(periodo) > 1:
        data = periodo[0]
    aplicar_data_na_vaga(conn, vaga, data, repetir_par)


def _carga_dia(conn, municipio_id: int, dia: str) -> int:
    return conn.execute(
        """SELECT COUNT(*) n FROM vagas v
           JOIN escolas e ON e.id = v.escola_id
           WHERE e.municipio_id = ? AND v.data = ?""",
        (municipio_id, dia),
    ).fetchone()["n"]


def _preencher_datas_faltantes(conn, municipio_id: int) -> None:
    periodo = dias_do_municipio(_viagem_municipio(conn, municipio_id))
    if not periodo:
        return
    vagas = conn.execute(
        """SELECT v.*, e.municipio_id
           FROM vagas v
           JOIN escolas e ON e.id = v.escola_id
           WHERE e.municipio_id = ? AND (v.data IS NULL OR v.data = '')
           ORDER BY CASE WHEN v.serie LIKE '%DIA 2%' THEN 1 ELSE 0 END, v.id""",
        (municipio_id,),
    ).fetchall()
    for vaga in vagas:
        item = dict(vaga)
        if item.get("data"):
            continue
        if eh_segundo_ano_dia2(item["serie"]):
            garantir_data_do_periodo(conn, item, True)
            continue
        candidatos = periodo[:-1] if eh_segundo_ano_dia1(item["serie"]) and len(periodo) > 1 else periodo
        data = min(candidatos, key=lambda d: _carga_dia(conn, municipio_id, d))
        aplicar_data_na_vaga(conn, item, data, True)


def redistribuir_datas_municipio(conn, municipio_id: int) -> int:
    row = _viagem_municipio(conn, municipio_id)
    periodo = dias_do_municipio(row)
    if not periodo:
        return 0
    antigas = [
        r["data"]
        for r in conn.execute(
            """SELECT DISTINCT v.data FROM vagas v
               JOIN escolas e ON e.id = v.escola_id
               WHERE e.municipio_id = ? AND v.data IS NOT NULL AND v.data != ''
               ORDER BY v.data""",
            (municipio_id,),
        )
    ]
    mapa = {antiga: periodo[min(i, len(periodo) - 1)] for i, antiga in enumerate(antigas)}
    vagas = conn.execute(
        """SELECT v.id, v.data FROM vagas v
           JOIN escolas e ON e.id = v.escola_id
           WHERE e.municipio_id = ?""",
        (municipio_id,),
    ).fetchall()
    if not vagas:
        return 0
    for vaga in vagas:
        if vaga["data"] and vaga["data"] in periodo:
            nova = vaga["data"]
        elif vaga["data"]:
            nova = mapa.get(vaga["data"], periodo[0])
        else:
            nova = periodo[0]
        if nova and nova != vaga["data"]:
            conn.execute("UPDATE vagas SET data = ? WHERE id = ?", (nova, vaga["id"]))
    pares = conn.execute(
        """SELECT v.id, v.escola_id, v.turno, v.ordem, v.serie, v.data
           FROM vagas v
           JOIN escolas e ON e.id = v.escola_id
           WHERE e.municipio_id = ?""",
        (municipio_id,),
    ).fetchall()
    for vaga in pares:
        if not eh_segundo_ano_dia1(vaga["serie"]) or not vaga["data"]:
            continue
        par = serie_par_segundo_ano(vaga["serie"])
        if not par:
            continue
        dia2 = dia_vizinho(periodo, vaga["data"], 1)
        conn.execute(
            """UPDATE vagas SET data = ?
               WHERE escola_id = ? AND turno = ? AND ordem = ? AND serie = ?""",
            (dia2, vaga["escola_id"], vaga["turno"], vaga["ordem"], par),
        )
    return len(vagas)


def organizar(
    conn,
    municipio_id: int | None = None,
    reset: bool = False,
    aplicador_ids: list[int] | None = None,
    nova_rodada: bool = False,
) -> dict:
    params = []
    filtro = ""
    if municipio_id:
        filtro = " AND e.municipio_id = ?"
        params.append(municipio_id)

    if reset:
        if municipio_id:
            redistribuir_datas_municipio(conn, municipio_id)
        else:
            for r in conn.execute("SELECT id FROM municipios"):
                redistribuir_datas_municipio(conn, r["id"])
        conn.execute(
            f"""UPDATE vagas SET aplicador_id = NULL, alocacao = NULL
                WHERE id IN (
                    SELECT v.id FROM vagas v
                    JOIN escolas e ON e.id = v.escola_id
                    WHERE 1=1 {filtro}
                )""",
            params,
        )
    else:
        if municipio_id:
            _preencher_datas_faltantes(conn, municipio_id)
        else:
            for r in conn.execute("SELECT id FROM municipios"):
                _preencher_datas_faltantes(conn, r["id"])
        if nova_rodada:
            conn.execute(
                f"""UPDATE vagas SET aplicador_id = NULL, alocacao = NULL
                    WHERE id IN (
                        SELECT v.id FROM vagas v
                        JOIN escolas e ON e.id = v.escola_id
                        WHERE v.alocacao = 'AUTO' {filtro}
                    )""",
                params,
            )

    vagas = list(
        conn.execute(
            f"""SELECT v.*, e.municipio_id, e.nome AS escola_nome
                FROM vagas v
                JOIN escolas e ON e.id = v.escola_id
                WHERE v.aplicador_id IS NULL {filtro}
                ORDER BY e.municipio_id, v.data, v.turno, e.nome, v.serie""",
            params,
        )
    )
    random.shuffle(vagas)

    aplicadores = list(
        conn.execute("SELECT * FROM aplicadores WHERE ativo = 1 ORDER BY codigo")
    )
    if aplicador_ids:
        ids = {int(i) for i in aplicador_ids}
        aplicadores = [a for a in aplicadores if a["id"] in ids]
    random.shuffle(aplicadores)

    alocadas = 0
    sem_candidato = 0

    def carga(aid: int) -> int:
        row = conn.execute(
            "SELECT COUNT(*) n FROM vagas WHERE aplicador_id = ?", (aid,)
        ).fetchone()
        return row["n"]

    def no_municipio(aid: int, mid: int) -> bool:
        row = conn.execute(
            """SELECT 1 FROM vagas v
               JOIN escolas e ON e.id = v.escola_id
               WHERE v.aplicador_id = ? AND e.municipio_id = ?
               LIMIT 1""",
            (aid, mid),
        ).fetchone()
        return row is not None

    def na_escola_semana(aid: int, escola_id: int) -> bool:
        row = conn.execute(
            """SELECT 1 FROM vagas
               WHERE aplicador_id = ? AND escola_id = ? LIMIT 1""",
            (aid, escola_id),
        ).fetchone()
        return row is not None

    for vaga in vagas:
        atual = conn.execute("SELECT aplicador_id FROM vagas WHERE id = ?", (vaga["id"],)).fetchone()
        if atual["aplicador_id"]:
            continue

        escolhido = None

        if eh_segundo_ano_dia2(vaga["serie"]):
            par = serie_par_segundo_ano(vaga["serie"])
            dia1 = conn.execute(
                """SELECT aplicador_id FROM vagas
                   WHERE escola_id = ? AND turno = ? AND serie = ? AND ordem = ?""",
                (vaga["escola_id"], vaga["turno"], par, vaga["ordem"]),
            ).fetchone()
            if dia1 and dia1["aplicador_id"]:
                checagem = pode_alocar(conn, vaga["id"], dia1["aplicador_id"])
                if checagem["ok"] and (
                    not aplicador_ids or dia1["aplicador_id"] in {int(i) for i in aplicador_ids}
                ):
                    escolhido = dia1["aplicador_id"]

        if escolhido is None:
            melhores = []
            for a in aplicadores:
                checagem = pode_alocar(conn, vaga["id"], a["id"])
                if not checagem["ok"]:
                    continue
                score = random.randint(-8, 8)
                if no_municipio(a["id"], vaga["municipio_id"]):
                    score += 100
                if na_escola_semana(a["id"], vaga["escola_id"]):
                    score += 40
                score -= carga(a["id"]) * 4
                score -= len(checagem["avisos"]) * 8
                melhores.append((score, a["id"]))
            if melhores:
                melhores.sort(reverse=True)
                escolhido = melhores[0][1]

        if escolhido is None:
            sem_candidato += 1
            continue

        conn.execute(
            "UPDATE vagas SET aplicador_id = ?, alocacao = ? WHERE id = ?",
            (escolhido, "AUTO", vaga["id"]),
        )
        alocadas += 1
        if eh_segundo_ano_dia1(vaga["serie"]):
            _espelhar_par(conn, vaga, escolhido, origem="AUTO")

    restantes = conn.execute(
        f"""SELECT COUNT(*) n FROM vagas v
            JOIN escolas e ON e.id = v.escola_id
            WHERE v.aplicador_id IS NULL {filtro}""",
        params,
    ).fetchone()["n"]

    return {
        "alocadas": alocadas,
        "sem_candidato": sem_candidato,
        "ainda_vagas": restantes,
        "reset": reset,
        "nova_rodada": nova_rodada,
        "aplicadores": len(aplicadores),
    }


def finalizar_vaga(conn, vaga_id: int, finalizada: bool) -> dict:
    vaga = conn.execute("SELECT id FROM vagas WHERE id = ?", (vaga_id,)).fetchone()
    if not vaga:
        return {"ok": False, "erro": "Vaga não encontrada."}
    if finalizada:
        agora = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE vagas SET status = 'FINALIZADA', finalizado_em = ? WHERE id = ?",
            (agora, vaga_id),
        )
        return {"ok": True, "status": "FINALIZADA", "finalizado_em": agora}
    conn.execute(
        "UPDATE vagas SET status = 'PREVISTA', finalizado_em = NULL WHERE id = ?",
        (vaga_id,),
    )
    return {"ok": True, "status": "PREVISTA"}
