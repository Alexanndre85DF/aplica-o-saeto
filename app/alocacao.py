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
    turnos_sobrepoem,
)


def _nome_aplicador(row) -> str | None:
    if row is None:
        return None
    return row["nome"] or row["codigo"]


def _vago_msg() -> dict:
    return {
        "tipo": "vago",
        "grau": "vago",
        "mensagem": "Sem aplicador nesta vaga.",
    }


def _unicos_problemas(problemas: list[dict]) -> list[dict]:
    vistos = set()
    unicos = []
    for p in problemas:
        chave = (p["tipo"], p["mensagem"])
        if chave in vistos:
            continue
        vistos.add(chave)
        unicos.append(p)
    return unicos


def _problemas_com_outros(vaga: dict, outros) -> list[dict]:
    problemas = []
    mun_atual = vaga.get("municipio_id")
    mesma_data = bool(vaga.get("data"))
    no_mesmo_dia = 0
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
        if o["data"] != vaga["data"]:
            if o["municipio_id"] != mun_atual:
                problemas.append(
                    {
                        "tipo": "municipio_outro",
                        "grau": "aviso",
                        "mensagem": f"Também alocado em {o['municipio_nome']}.",
                    }
                )
            continue
        no_mesmo_dia += 1
        if turnos_sobrepoem(o["turno"], vaga["turno"]):
            if o["escola_id"] != vaga["escola_id"]:
                msg = (
                    f"Choque: já está em {o['escola_nome']} "
                    f"({o['turno'].title()}) neste turno."
                )
            else:
                outra = o.get("serie") or "outra turma"
                if o.get("turma"):
                    outra = f"{outra} — {o['turma']}"
                msg = (
                    f"Choque: já está em {outra} nesta escola "
                    f"({o['turno'].title()}) neste turno."
                )
            problemas.append(
                {
                    "tipo": "choque",
                    "grau": "choque",
                    "mensagem": msg,
                }
            )
        elif o["municipio_id"] != mun_atual:
            problemas.append(
                {
                    "tipo": "municipio_mesmo_dia",
                    "grau": "choque",
                    "mensagem": f"Já está em {o['municipio_nome']} neste dia.",
                }
            )
        elif o["escola_id"] != vaga["escola_id"]:
            problemas.append(
                {
                    "tipo": "dois_turnos",
                    "grau": "aviso",
                    "mensagem": (
                        f"{o['turno'].title()} em outra escola no mesmo dia: {o['escola_nome']}."
                    ),
                }
            )
    if mesma_data and no_mesmo_dia >= 3:
        problemas.append(
            {
                "tipo": "limite_dia",
                "grau": "choque",
                "mensagem": "Já tem 3 aplicações neste dia (manhã, tarde e noite). Integral conta como um turno.",
            }
        )
    return problemas


def _aviso_par_2ano(vaga: dict, par_row) -> dict | None:
    if not par_row:
        return None
    aplicador_id = vaga.get("aplicador_id")
    par_apl = par_row.get("aplicador_id")
    nome = par_row.get("apl_nome") or par_row.get("nome")
    codigo = par_row.get("apl_codigo") or par_row.get("codigo")
    if par_apl and par_apl != aplicador_id:
        return {
            "tipo": "par_2ano",
            "grau": "aviso",
            "mensagem": (
                "2º ano Dia 1 e Dia 2 com aplicadores diferentes "
                f"({nome or codigo})."
            ),
        }
    if not par_apl and eh_segundo_ano_dia1(vaga["serie"]):
        return {
            "tipo": "par_2ano_vago",
            "grau": "aviso",
            "mensagem": "O Dia 2 desta turma ainda está vago.",
        }
    return None


def problemas_da_vaga(conn, vaga: dict) -> list[dict]:
    aplicador_id = vaga.get("aplicador_id")
    if not aplicador_id:
        return [_vago_msg()]

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
    problemas = _problemas_com_outros(vaga, outros)

    par = serie_par_segundo_ano(vaga["serie"])
    if par:
        par_row = conn.execute(
            """SELECT v.aplicador_id, a.codigo, a.nome
               FROM vagas v
               LEFT JOIN aplicadores a ON a.id = v.aplicador_id
               WHERE v.escola_id = ? AND v.turno = ? AND v.serie = ? AND v.ordem = ?""",
            (vaga["escola_id"], vaga["turno"], par, vaga.get("ordem") or 1),
        ).fetchone()
        aviso = _aviso_par_2ano(vaga, dict(par_row) if par_row else None)
        if aviso:
            problemas.append(aviso)

    return _unicos_problemas(problemas)


def enriquecer_vaga(conn, vaga: dict) -> dict:
    return enriquecer_vagas(conn, [vaga])[0]


def enriquecer_vagas(conn, vagas: list[dict]) -> list[dict]:
    ids = {v.get("aplicador_id") for v in vagas if v.get("aplicador_id")}
    outros_por: dict[int, list[dict]] = defaultdict(list)
    if ids:
        ph = ",".join("?" * len(ids))
        rows = conn.execute(
            f"""
            SELECT v.*, e.nome AS escola_nome, e.codigo AS escola_codigo,
                   m.nome AS municipio_nome, m.id AS municipio_id
            FROM vagas v
            JOIN escolas e ON e.id = v.escola_id
            JOIN municipios m ON m.id = e.municipio_id
            WHERE v.aplicador_id IN ({ph})
            """,
            tuple(ids),
        ).fetchall()
        for r in rows:
            d = dict(r)
            outros_por[d["aplicador_id"]].append(d)

    indice_local = {
        (v["escola_id"], v["turno"], v["serie"], v.get("ordem") or 1): v for v in vagas
    }

    for vaga in vagas:
        aplicador_id = vaga.get("aplicador_id")
        if not aplicador_id:
            problemas = [_vago_msg()]
        else:
            outros = [o for o in outros_por.get(aplicador_id, []) if o["id"] != vaga["id"]]
            problemas = _problemas_com_outros(vaga, outros)
            par = serie_par_segundo_ano(vaga["serie"])
            if par:
                aviso = _aviso_par_2ano(
                    vaga,
                    indice_local.get(
                        (vaga["escola_id"], vaga["turno"], par, vaga.get("ordem") or 1)
                    ),
                )
                if aviso:
                    problemas.append(aviso)
            problemas = _unicos_problemas(problemas)
        vaga["problemas"] = problemas
        vaga["tem_choque"] = any(p["grau"] == "choque" for p in problemas)
        vaga["tem_aviso"] = any(p["grau"] == "aviso" for p in problemas)
        vaga["vago"] = aplicador_id is None
    return vagas


def contar_choques(conn) -> int:
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT v1.id) AS n
        FROM vagas v1
        JOIN escolas e1 ON e1.id = v1.escola_id
        WHERE v1.aplicador_id IS NOT NULL
          AND v1.data IS NOT NULL
          AND (
            EXISTS (
                SELECT 1 FROM vagas v2
                JOIN escolas e2 ON e2.id = v2.escola_id
                WHERE v2.aplicador_id = v1.aplicador_id
                  AND v2.id != v1.id
                  AND v2.data = v1.data
                  AND (v1.turno = v2.turno OR e1.municipio_id != e2.municipio_id)
            )
            OR (
                SELECT COUNT(*) FROM vagas v3
                WHERE v3.aplicador_id = v1.aplicador_id AND v3.data = v1.data
            ) >= 4
          )
        """
    ).fetchone()
    return int((row["n"] if row else 0) or 0)


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


def _agenda_ocupadas(conn) -> dict[int, list[dict]]:
    por: dict[int, list[dict]] = defaultdict(list)
    for r in conn.execute(
        """
        SELECT v.*, e.nome AS escola_nome, e.codigo AS escola_codigo,
               m.nome AS municipio_nome, m.id AS municipio_id
        FROM vagas v
        JOIN escolas e ON e.id = v.escola_id
        JOIN municipios m ON m.id = e.municipio_id
        WHERE v.aplicador_id IS NOT NULL
        """
    ):
        d = dict(r)
        por[d["aplicador_id"]].append(d)
    return por


def _par_da_vaga(conn, vaga: dict) -> dict | None:
    par = serie_par_segundo_ano(vaga["serie"])
    if not par:
        return None
    row = conn.execute(
        """SELECT v.aplicador_id, a.codigo, a.nome
           FROM vagas v
           LEFT JOIN aplicadores a ON a.id = v.aplicador_id
           WHERE v.escola_id = ? AND v.turno = ? AND v.serie = ? AND v.ordem = ?""",
        (vaga["escola_id"], vaga["turno"], par, vaga.get("ordem") or 1),
    ).fetchone()
    return dict(row) if row else None


def checar_alocacao(vaga: dict, aplicador_id: int, agenda: dict, par_row=None) -> dict:
    simulada = dict(vaga)
    simulada["aplicador_id"] = aplicador_id
    outros = [o for o in agenda.get(aplicador_id, []) if o["id"] != vaga["id"]]
    problemas = _problemas_com_outros(simulada, outros)
    aviso = _aviso_par_2ano(simulada, par_row)
    if aviso:
        problemas.append(aviso)
    problemas = _unicos_problemas(problemas)
    choques = [p for p in problemas if p["grau"] == "choque"]
    return {
        "ok": len(choques) == 0,
        "choques": choques,
        "avisos": [p for p in problemas if p["grau"] == "aviso"],
        "problemas": problemas,
    }


def candidatos_para_vaga(conn, vaga_id: int, data: str | None = None) -> list[dict]:
    vaga = conn.execute(
        """SELECT v.*, e.municipio_id, e.nome AS escola_nome, m.nome AS municipio_nome
           FROM vagas v
           JOIN escolas e ON e.id = v.escola_id
           JOIN municipios m ON m.id = e.municipio_id
           WHERE v.id = ?""",
        (vaga_id,),
    ).fetchone()
    if not vaga:
        return []
    vaga = dict(vaga)
    if data:
        vaga["data"] = data[:10]
    dia = vaga.get("data")

    aplicadores = conn.execute(
        "SELECT * FROM aplicadores WHERE ativo = 1 ORDER BY codigo"
    ).fetchall()
    agenda = _agenda_ocupadas(conn)
    par_row = _par_da_vaga(conn, vaga)

    lista = []
    for a in aplicadores:
        checagem = checar_alocacao(vaga, a["id"], agenda, par_row)
        slots = agenda.get(a["id"], [])
        outros_no_dia = [
            o for o in slots if o["id"] != vaga["id"] and dia and o.get("data") == dia
        ]
        selecionado = a["id"] == vaga.get("aplicador_id")
        lista.append(
            {
                "id": a["id"],
                "codigo": a["codigo"],
                "nome": a["nome"] or a["codigo"],
                "carga": len(slots),
                "no_municipio": any(o["municipio_id"] == vaga["municipio_id"] for o in slots),
                "ok": checagem["ok"],
                "choques": checagem["choques"],
                "avisos": checagem["avisos"],
                "selecionado": selecionado,
                "aplicacoes_no_dia": len(outros_no_dia),
                "livre_no_dia": bool(dia) and not selecionado and not outros_no_dia,
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
            """UPDATE vagas SET aplicador_id = NULL, alocacao = NULL, data = NULL, prova_recebida_em = NULL
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
            "erro": "Choque de horário: este aplicador já está em outra turma neste turno ou já tem 3 aplicações no dia.",
            "choques": checagem["choques"],
        }

    conn.execute(
        "UPDATE vagas SET aplicador_id = ?, alocacao = ?, prova_recebida_em = CASE WHEN aplicador_id = ? THEN prova_recebida_em ELSE NULL END WHERE id = ?",
        (aplicador_id, "MANUAL", aplicador_id, vaga_id),
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


def substituir_aplicador(
    conn, vaga_id: int, novo_aplicador_id: int, data: str | None = None
) -> dict:
    vaga = conn.execute(
        """SELECT v.*, e.municipio_id
           FROM vagas v JOIN escolas e ON e.id = v.escola_id WHERE v.id = ?""",
        (vaga_id,),
    ).fetchone()
    if not vaga:
        return {"ok": False, "erro": "Vaga não encontrada."}
    vaga = dict(vaga)
    atual_id = vaga.get("aplicador_id")
    if not atual_id:
        return {"ok": False, "erro": "Esta aplicação ainda não tem aplicador para substituir."}
    dia = (data or vaga.get("data") or "")[:10] if (data or vaga.get("data")) else None
    if not dia:
        return {"ok": False, "erro": "Salve a data desta aplicação antes de substituir o aplicador."}
    if novo_aplicador_id == atual_id:
        return {"ok": False, "erro": "Escolha outro aplicador."}

    novo = conn.execute(
        "SELECT id, ativo FROM aplicadores WHERE id = ?",
        (novo_aplicador_id,),
    ).fetchone()
    if not novo or not novo["ativo"]:
        return {"ok": False, "erro": "Aplicador não encontrado ou inativo."}

    ocupado = conn.execute(
        """SELECT COUNT(*) AS n FROM vagas
           WHERE aplicador_id = ? AND data = ? AND id != ?""",
        (novo_aplicador_id, dia, vaga_id),
    ).fetchone()
    if int((ocupado["n"] if ocupado else 0) or 0) > 0:
        return {"ok": False, "erro": "Este aplicador já tem aplicação neste dia."}

    resultado = alocar(
        conn,
        vaga_id,
        novo_aplicador_id,
        repetir_par=False,
        data=dia,
        forcar=False,
    )
    if not resultado.get("ok"):
        return resultado

    conn.execute(
        """UPDATE vagas
           SET status = 'PREVISTA', finalizado_em = NULL, n_presentes = NULL
           WHERE id = ? AND status = 'FINALIZADA'""",
        (vaga_id,),
    )
    return {
        "ok": True,
        "substituido": True,
        "anterior_id": atual_id,
        "aplicador_id": novo_aplicador_id,
        "data": dia,
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
            """UPDATE vagas SET aplicador_id = NULL, alocacao = NULL, data = NULL, prova_recebida_em = NULL
               WHERE id = ?""",
            (outra["id"],),
        )
        return True
    checagem = pode_alocar(conn, outra["id"], aplicador_id)
    if checagem["ok"] or origem == "MANUAL":
        conn.execute(
            "UPDATE vagas SET aplicador_id = ?, alocacao = ?, prova_recebida_em = CASE WHEN aplicador_id = ? THEN prova_recebida_em ELSE NULL END WHERE id = ?",
            (aplicador_id, origem or "AUTO", aplicador_id, outra["id"]),
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
            f"""UPDATE vagas SET aplicador_id = NULL, alocacao = NULL, prova_recebida_em = NULL
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
                f"""UPDATE vagas SET aplicador_id = NULL, alocacao = NULL, prova_recebida_em = NULL
                    WHERE id IN (
                        SELECT v.id FROM vagas v
                        JOIN escolas e ON e.id = v.escola_id
                        WHERE v.alocacao = 'AUTO' {filtro}
                    )""",
                params,
            )

    vagas = [
        dict(r)
        for r in conn.execute(
            f"""SELECT v.*, e.municipio_id, e.nome AS escola_nome, m.nome AS municipio_nome
                FROM vagas v
                JOIN escolas e ON e.id = v.escola_id
                JOIN municipios m ON m.id = e.municipio_id
                WHERE v.aplicador_id IS NULL {filtro}
                ORDER BY e.municipio_id, v.data, v.turno, e.nome, v.serie""",
            params,
        )
    ]
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
    agenda = _agenda_ocupadas(conn)
    pares_cache: dict[tuple, dict | None] = {}
    ids_filtro = {int(i) for i in aplicador_ids} if aplicador_ids else None

    def par_row_de(item: dict):
        par = serie_par_segundo_ano(item["serie"])
        if not par:
            return None
        chave = (item["escola_id"], item["turno"], par, item.get("ordem") or 1)
        if chave not in pares_cache:
            pares_cache[chave] = _par_da_vaga(conn, item)
        return pares_cache[chave]

    def registrar(aid: int, item: dict) -> None:
        slot = dict(item)
        slot["aplicador_id"] = aid
        agenda[aid].append(slot)

    for vaga in vagas:
        if any(o["id"] == vaga["id"] for slots in agenda.values() for o in slots):
            continue

        escolhido = None
        par_row = par_row_de(vaga)

        if eh_segundo_ano_dia2(vaga["serie"]):
            par = serie_par_segundo_ano(vaga["serie"])
            dia1 = conn.execute(
                """SELECT aplicador_id FROM vagas
                   WHERE escola_id = ? AND turno = ? AND serie = ? AND ordem = ?""",
                (vaga["escola_id"], vaga["turno"], par, vaga["ordem"]),
            ).fetchone()
            if dia1 and dia1["aplicador_id"]:
                checagem = checar_alocacao(vaga, dia1["aplicador_id"], agenda, par_row)
                if checagem["ok"] and (not ids_filtro or dia1["aplicador_id"] in ids_filtro):
                    escolhido = dia1["aplicador_id"]

        if escolhido is None:
            melhores = []
            for a in aplicadores:
                checagem = checar_alocacao(vaga, a["id"], agenda, par_row)
                if not checagem["ok"]:
                    continue
                slots = agenda.get(a["id"], [])
                score = random.randint(-8, 8)
                if any(o["municipio_id"] == vaga["municipio_id"] for o in slots):
                    score += 100
                if any(o["escola_id"] == vaga["escola_id"] for o in slots):
                    score += 40
                score -= len(slots) * 4
                score -= len(checagem["avisos"]) * 8
                melhores.append((score, a["id"]))
            if melhores:
                melhores.sort(reverse=True)
                escolhido = melhores[0][1]

        if escolhido is None:
            sem_candidato += 1
            continue

        conn.execute(
            "UPDATE vagas SET aplicador_id = ?, alocacao = ?, prova_recebida_em = CASE WHEN aplicador_id = ? THEN prova_recebida_em ELSE NULL END WHERE id = ?",
            (escolhido, "AUTO", escolhido, vaga["id"]),
        )
        registrar(escolhido, vaga)
        alocadas += 1
        if eh_segundo_ano_dia1(vaga["serie"]):
            par = serie_par_segundo_ano(vaga["serie"])
            if par and _espelhar_par(conn, vaga, escolhido, origem="AUTO"):
                outra = conn.execute(
                    """SELECT v.*, e.municipio_id, e.nome AS escola_nome, m.nome AS municipio_nome
                       FROM vagas v
                       JOIN escolas e ON e.id = v.escola_id
                       JOIN municipios m ON m.id = e.municipio_id
                       WHERE v.escola_id = ? AND v.turno = ? AND v.serie = ? AND v.ordem = ?""",
                    (vaga["escola_id"], vaga["turno"], par, vaga.get("ordem") or 1),
                ).fetchone()
                if outra:
                    registrar(escolhido, dict(outra))

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


def finalizar_vaga(conn, vaga_id: int, finalizada: bool, n_presentes: int | None = None) -> dict:
    vaga = conn.execute(
        "SELECT id, n_alunos FROM vagas WHERE id = ?", (vaga_id,)
    ).fetchone()
    if not vaga:
        return {"ok": False, "erro": "Vaga não encontrada."}
    if finalizada:
        presentes = None
        if n_presentes is not None:
            try:
                presentes = int(n_presentes)
            except (TypeError, ValueError):
                return {"ok": False, "erro": "Informe um número válido de estudantes presentes."}
            if presentes < 0:
                return {"ok": False, "erro": "O número de presentes não pode ser negativo."}
            total = vaga["n_alunos"]
            if total is not None and presentes > int(total):
                return {
                    "ok": False,
                    "erro": f"Presentes ({presentes}) não pode ser maior que o total de {int(total)} estudantes.",
                }
        agora = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE vagas SET status = 'FINALIZADA', finalizado_em = ?, n_presentes = ? WHERE id = ?",
            (agora, presentes, vaga_id),
        )
        return {
            "ok": True,
            "status": "FINALIZADA",
            "finalizado_em": agora,
            "n_presentes": presentes,
        }
    conn.execute(
        "UPDATE vagas SET status = 'PREVISTA', finalizado_em = NULL, n_presentes = NULL WHERE id = ?",
        (vaga_id,),
    )
    return {"ok": True, "status": "PREVISTA"}


def receber_prova(conn, vaga_id: int, recebida: bool) -> dict:
    vaga = conn.execute(
        "SELECT id, aplicador_id FROM vagas WHERE id = ?", (vaga_id,)
    ).fetchone()
    if not vaga:
        return {"ok": False, "erro": "Vaga não encontrada."}
    if not vaga["aplicador_id"]:
        return {"ok": False, "erro": "Esta aplicação ainda não tem aplicador."}
    if recebida:
        agora = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE vagas SET prova_recebida_em = ? WHERE id = ?",
            (agora, vaga_id),
        )
        return {"ok": True, "prova_recebida": True, "prova_recebida_em": agora}
    conn.execute(
        "UPDATE vagas SET prova_recebida_em = NULL WHERE id = ?", (vaga_id,)
    )
    return {"ok": True, "prova_recebida": False}
