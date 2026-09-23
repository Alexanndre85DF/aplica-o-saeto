from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta

REDE_MUNICIPAL = "MUNICIPAL"
REDE_ESTADUAL = "ESTADUAL"
REDE_CONVENIADA = "CONVENIADA"
REDES = (REDE_MUNICIPAL, REDE_ESTADUAL, REDE_CONVENIADA)

TURNOS = ("MATUTINO", "VESPERTINO", "INTEGRAL", "NOTURNO")
ANO_CAMPANHA = 2026
MES_CAMPANHA = 11


def normalizar_texto(valor) -> str:
    if valor is None:
        return ""
    texto = str(valor).replace("\xa0", " ")
    return re.sub(r"\s+", " ", texto).strip()


def normalizar_serie(valor) -> str:
    texto = normalizar_texto(valor).upper()
    texto = texto.replace("SERIE", "SÉRIE").replace("SERÍE", "SÉRIE")
    return texto


def normalizar_turno(valor) -> str:
    texto = normalizar_texto(valor).upper()
    mapa = {
        "MANHA": "MATUTINO",
        "MANHÃ": "MATUTINO",
        "TARDE": "VESPERTINO",
        "NOITE": "NOTURNO",
        "INTEGRAL": "INTEGRAL",
        "MATUTINO": "MATUTINO",
        "VESPERTINO": "VESPERTINO",
        "NOTURNO": "NOTURNO",
    }
    return mapa.get(texto, texto or "MATUTINO")


def inferir_rede(nome_escola: str) -> str:
    nome = normalizar_texto(nome_escola).upper()
    if "MUNICIPAL" in nome or re.search(r"\bMUN\b", nome):
        return REDE_MUNICIPAL
    if "ESTADUAL" in nome or "MILITAR" in nome:
        return REDE_ESTADUAL
    return REDE_CONVENIADA


def eh_rural(nome_escola: str) -> bool:
    return "RURAL" in normalizar_texto(nome_escola).upper()


def parse_data(valor) -> date | None:
    """Datas da campanha SAETO 2026 desta planilha caem em novembro."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        dia = valor.day
        return date(ANO_CAMPANHA, MES_CAMPANHA, dia)
    if isinstance(valor, date):
        return date(ANO_CAMPANHA, MES_CAMPANHA, valor.day)

    nums = [int(n) for n in re.findall(r"\d+", str(valor))]
    if not nums:
        return None

    nums = [n for n in nums if n != ANO_CAMPANHA]
    if not nums:
        return None
    if len(nums) == 1:
        dia = nums[0]
    elif MES_CAMPANHA in nums:
        outros = [n for n in nums if n != MES_CAMPANHA]
        dia = outros[0] if outros else MES_CAMPANHA
    else:
        dia = nums[0]

    if not 1 <= dia <= 31:
        return None
    return date(ANO_CAMPANHA, MES_CAMPANHA, dia)


def iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def periodo_dias(saida: str | None, retorno: str | None) -> list[str]:
    if not saida:
        return []
    ini = date.fromisoformat(str(saida)[:10])
    fim = date.fromisoformat(str(retorno or saida)[:10])
    if fim < ini:
        ini, fim = fim, ini
    dias = []
    atual = ini
    while atual <= fim:
        dias.append(atual.isoformat())
        atual += timedelta(days=1)
    return dias


def normalizar_dias(valores) -> list[str]:
    if not valores:
        return []
    if isinstance(valores, str):
        texto = valores.strip()
        if not texto:
            return []
        try:
            valores = json.loads(texto)
        except (TypeError, ValueError):
            return []
    if not isinstance(valores, (list, tuple, set)):
        return []
    dias = []
    for item in valores:
        if not item:
            continue
        try:
            dias.append(date.fromisoformat(str(item)[:10]).isoformat())
        except ValueError:
            continue
    return sorted(set(dias))


def dias_do_municipio(row) -> list[str]:
    if not row:
        return []
    try:
        extras = row["dias_aplicacao"]
    except (KeyError, TypeError):
        extras = None
    if extras is None and isinstance(row, dict):
        extras = row.get("dias") or row.get("dias_aplicacao")
    lista = normalizar_dias(extras)
    if lista:
        return lista
    try:
        saida = row["data_saida"]
        retorno = row["data_retorno"]
    except (KeyError, TypeError):
        saida = row.get("data_saida") if isinstance(row, dict) else None
        retorno = row.get("data_retorno") if isinstance(row, dict) else None
    return periodo_dias(saida, retorno)


def dia_vizinho(dias: list[str], data_iso: str, passo: int) -> str:
    if data_iso in dias:
        indice = dias.index(data_iso) + passo
        if 0 <= indice < len(dias):
            return dias[indice]
    return (date.fromisoformat(data_iso) + timedelta(days=passo)).isoformat()


def fmt_data(iso_str: str | None) -> str:
    if not iso_str:
        return "—"
    ano, mes, dia = iso_str.split("-")
    return f"{dia}/{mes}/{ano}"


def serie_base(serie: str | None) -> str:
    texto = normalizar_serie(serie)
    return re.sub(r"\s*-\s*DIA\s*[12]\s*$", "", texto, flags=re.I).strip()


def serie_par_segundo_ano(serie: str) -> str | None:
    if "DIA 1" in serie:
        return serie.replace("DIA 1", "DIA 2")
    if "DIA 2" in serie:
        return serie.replace("DIA 2", "DIA 1")
    return None


def eh_segundo_ano_dia1(serie: str) -> bool:
    return "2" in serie and "DIA 1" in serie


def eh_segundo_ano_dia2(serie: str) -> bool:
    return "2" in serie and "DIA 2" in serie


def turnos_sobrepoem(a: str, b: str) -> bool:
    """Só o mesmo turno se sobrepõe. Integral conta como um turno e não fecha manhã, tarde nem noite."""
    return (a or "") == (b or "")
