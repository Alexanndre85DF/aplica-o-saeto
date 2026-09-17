from __future__ import annotations

import os
from pathlib import Path

from fastapi import Cookie, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .acesso import (
    aplicador_da_sessao,
    encerrar_sessao,
    entrar_por_cpf,
    garantir_token_acesso,
    minhas_aplicacoes,
    minhas_extras,
)
from .admin_auth import (
    COOKIE_ADMIN,
    admin_do_token,
    autenticar,
    criar_token,
)
from .alocacao import (
    alocar,
    alocar_extra,
    candidatos_para_extra,
    candidatos_para_vaga,
    contar_choques,
    definir_n_extras,
    enriquecer_vaga,
    enriquecer_vagas,
    finalizar_vaga,
    organizar,
    receber_prova,
    redistribuir_datas_municipio,
    remover_extra,
    substituir_aplicador,
    _preencher_datas_faltantes,
)
from .cadastro import (
    atualizar_escola,
    atualizar_municipio,
    formatar_cpf,
    vincular_pessoa,
    desvincular_pessoa,
    _eh_placeholder,
    consolidar_municipios,
    criar_escola,
    criar_municipio,
    criar_vaga,
    excluir_aplicador,
    excluir_escola,
    excluir_municipio,
    excluir_vaga,
    origem_manual,
    opcoes,
    zerar_tudo,
    criar_lote_aplicadores,
)
from .config import DATA_DIR, localizar_planilha, usando_nuvem, usando_postgres, usando_supabase
from .db import get_db, init_db, row_to_dict, rows_to_dicts
from .importar import completar_planilha, importar_planilha, salvar_planilha_atual
from .regras import dias_do_municipio, fmt_data

STATIC = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="SAETO SRE Gurupi — Sistema de Aplicação")
app.add_middleware(GZipMiddleware, minimum_size=800)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class AlocarBody(BaseModel):
    aplicador_id: int | None = None
    repetir_par: bool = True
    data: str | None = None
    forcar: bool = False


class SubstituirBody(BaseModel):
    aplicador_id: int
    data: str | None = None


class ExtraBody(BaseModel):
    aplicador_id: int
    forcar: bool = False


class NExtrasBody(BaseModel):
    n_extras: int


class OrganizarBody(BaseModel):
    municipio_id: int | None = None
    reset: bool = False
    aplicador_ids: list[int] | None = None
    nova_rodada: bool = False


class LimparBody(BaseModel):
    municipio_id: int | None = None


class AplicadorBody(BaseModel):
    nome: str | None = None
    codigo: str | None = None
    cpf: str | None = None
    numero: int | None = None
    ativo: bool | None = None


class LoteAplicadoresBody(BaseModel):
    quantidade: int


class VincularBody(BaseModel):
    nome: str
    cpf: str | None = None
    numero: int | None = None
    codigo: str | None = None


class MunicipioBody(BaseModel):
    nome: str
    data_saida: str | None = None
    data_retorno: str | None = None
    dias: list[str] | None = None


class MunicipioPatchBody(BaseModel):
    nome: str | None = None
    data_saida: str | None = None
    data_retorno: str | None = None
    dias: list[str] | None = None
    limpar_datas_vagas: bool = False
    aplicar_datas_vagas: bool = False


class EscolaBody(BaseModel):
    municipio_id: int
    nome: str
    codigo: str | None = None
    rede: str = "MUNICIPAL"
    rural: bool = False


class EscolaPatchBody(BaseModel):
    municipio_id: int | None = None
    nome: str | None = None
    codigo: str | None = None
    rede: str | None = None
    rural: bool | None = None


class VagaNovaBody(BaseModel):
    escola_id: int
    serie: str
    turno: str
    data: str
    quantidade: int = 1
    criar_par: bool = True


class EntrarBody(BaseModel):
    cpf: str
    token_link: str | None = None


class AdminEntrarBody(BaseModel):
    email: str
    senha: str


class FinalizarBody(BaseModel):
    finalizada: bool = True
    n_presentes: int | None = None


class ReceberProvaBody(BaseModel):
    recebida: bool = True


@app.on_event("startup")
def startup():
    try:
        init_db()
        with get_db() as conn:
            n = conn.execute("SELECT COUNT(*) n FROM vagas").fetchone()["n"]
            so_manual = origem_manual(conn)
        if n == 0 and not so_manual:
            planilha = localizar_planilha()
            if planilha:
                importar_planilha(planilha)
    except Exception as exc:
        print("FALHA AO INICIAR BANCO:", exc)


def _cadastro_erro(exc: Exception):
    if isinstance(exc, LookupError):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(400, str(exc)) from exc
    texto = str(exc).lower()
    if "unique" in texto or "duplicate" in texto or "integrity" in texto:
        raise HTTPException(
            400,
            "Não deu para gravar: esse registro já existe no banco.",
        ) from exc
    raise HTTPException(400, str(exc) or "Não foi possível concluir.") from exc


def _cookie_https(request: Request) -> bool:
    return request.url.scheme == "https" or bool(os.getenv("RENDER"))


@app.middleware("http")
async def proteger_admin(request: Request, call_next):
    path = request.url.path
    if (
        path.startswith("/static")
        or path.startswith("/acesso")
        or path.startswith("/api/acesso")
        or path == "/api/admin/entrar"
        or path == "/api/admin/sair"
    ):
        response = await call_next(request)
        if path.startswith("/static"):
            response.headers["Cache-Control"] = "public, max-age=604800, immutable"
        return response
    if path.startswith("/api/"):
        try:
            admin_do_token(request.cookies.get(COOKIE_ADMIN))
        except LookupError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=401)
    return await call_next(request)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/acesso")
@app.get("/acesso/{token_link}")
def pagina_acesso(token_link: str | None = None):
    return FileResponse(STATIC / "acesso.html")


COOKIE_PORTAL = "saeto_portal"


@app.post("/api/admin/entrar")
def api_admin_entrar(body: AdminEntrarBody, request: Request, response: Response):
    try:
        admin = autenticar(body.email, body.senha)
    except LookupError as exc:
        raise HTTPException(401, str(exc)) from exc
    response.set_cookie(
        key=COOKIE_ADMIN,
        value=criar_token(admin),
        httponly=True,
        samesite="lax",
        secure=_cookie_https(request),
        max_age=12 * 3600,
    )
    return {"admin": admin}


@app.get("/api/admin/eu")
def api_admin_eu(request: Request):
    try:
        return {"admin": admin_do_token(request.cookies.get(COOKIE_ADMIN))}
    except LookupError as exc:
        raise HTTPException(401, str(exc)) from exc


@app.post("/api/admin/sair")
def api_admin_sair(request: Request, response: Response):
    response.delete_cookie(
        COOKIE_ADMIN, samesite="lax", secure=_cookie_https(request)
    )
    return {"ok": True}


@app.post("/api/acesso/entrar")
def api_acesso_entrar(body: EntrarBody, response: Response):
    with get_db() as conn:
        try:
            dados = entrar_por_cpf(conn, body.cpf, body.token_link)
        except Exception as exc:
            _cadastro_erro(exc)
    response.set_cookie(
        key=COOKIE_PORTAL,
        value=dados["sessao"],
        httponly=True,
        samesite="lax",
        max_age=12 * 3600,
    )
    return {"aplicador": dados["aplicador"]}


@app.get("/api/acesso/eu")
def api_acesso_eu(saeto_portal: str | None = Cookie(default=None)):
    with get_db() as conn:
        try:
            pessoa = aplicador_da_sessao(conn, saeto_portal)
        except LookupError as exc:
            raise HTTPException(401, str(exc)) from exc
        return {
            "aplicador": {
                "nome": pessoa["nome"] or pessoa["codigo"],
                "codigo": pessoa["codigo"],
                "numero": pessoa["numero"],
                "cpf_fmt": formatar_cpf(pessoa["cpf"]),
            },
            "aplicacoes": minhas_aplicacoes(conn, pessoa["id"]),
            "extras": minhas_extras(conn, pessoa["id"]),
        }


@app.post("/api/acesso/vagas/{vaga_id}/finalizar")
def api_acesso_finalizar(
    vaga_id: int,
    body: FinalizarBody,
    saeto_portal: str | None = Cookie(default=None),
):
    with get_db() as conn:
        try:
            pessoa = aplicador_da_sessao(conn, saeto_portal)
        except LookupError as exc:
            raise HTTPException(401, str(exc)) from exc
        vaga = conn.execute("SELECT * FROM vagas WHERE id = ?", (vaga_id,)).fetchone()
        if not vaga or vaga["aplicador_id"] != pessoa["id"]:
            raise HTTPException(404, "Aplicação não encontrada.")
        if body.finalizada and body.n_presentes is None:
            raise HTTPException(400, "Informe quantos estudantes estavam presentes.")
        resultado = finalizar_vaga(conn, vaga_id, body.finalizada, body.n_presentes)
        if not resultado.get("ok"):
            raise HTTPException(400, resultado.get("erro") or "Não foi possível concluir.")
        return resultado


@app.post("/api/acesso/sair")
def api_acesso_sair(
    response: Response, saeto_portal: str | None = Cookie(default=None)
):
    with get_db() as conn:
        encerrar_sessao(conn, saeto_portal)
    response.delete_cookie(COOKIE_PORTAL)
    return {"ok": True}


@app.get("/api/opcoes")
def api_opcoes():
    return opcoes()


@app.get("/api/resumo")
def resumo():
    with get_db() as conn:
        consolidar_municipios(conn)
        tot = conn.execute(
            """SELECT
                 (SELECT COUNT(DISTINCT e.municipio_id)
                    FROM escolas e JOIN vagas v ON v.escola_id = e.id) AS municipios,
                 (SELECT COUNT(*) FROM escolas) AS escolas,
                 (SELECT COUNT(*) FROM aplicadores) AS aplicadores,
                 COUNT(*) AS vagas,
                 COALESCE(SUM(CASE WHEN aplicador_id IS NOT NULL THEN 1 ELSE 0 END), 0) AS ocupadas,
                 COALESCE(SUM(CASE WHEN aplicador_id IS NULL THEN 1 ELSE 0 END), 0) AS livres,
                 COALESCE(SUM(CASE WHEN status = 'FINALIZADA' THEN 1 ELSE 0 END), 0) AS finalizadas
               FROM vagas"""
        ).fetchone()
        por_rede = {
            r["rede"]: r["n"]
            for r in conn.execute(
                """SELECT e.rede, COUNT(*) n FROM vagas v
                   JOIN escolas e ON e.id = v.escola_id
                   GROUP BY e.rede"""
            )
        }
        por_mun = rows_to_dicts(
            conn.execute(
                """SELECT m.id, m.nome,
                          COUNT(v.id) AS vagas,
                          COALESCE(SUM(CASE WHEN v.id IS NOT NULL AND v.aplicador_id IS NULL THEN 1 ELSE 0 END), 0) AS livres,
                          COALESCE(SUM(CASE WHEN v.status = 'FINALIZADA' THEN 1 ELSE 0 END), 0) AS finalizadas
                   FROM municipios m
                   JOIN escolas e ON e.municipio_id = m.id
                   JOIN vagas v ON v.escola_id = e.id
                   GROUP BY m.id, m.nome
                   ORDER BY m.nome"""
            )
        )
        return {
            "municipios": tot["municipios"],
            "escolas": tot["escolas"],
            "aplicadores": tot["aplicadores"],
            "vagas": tot["vagas"],
            "ocupadas": tot["ocupadas"],
            "livres": tot["livres"],
            "finalizadas": tot["finalizadas"],
            "choques": contar_choques(conn),
            "por_rede": por_rede,
            "por_municipio": por_mun,
            "banco": "supabase" if usando_postgres() else "sqlite",
            "tem_nuvem": usando_nuvem(),
        }


@app.get("/api/acompanhamento")
def acompanhamento(municipio_id: int | None = None, data: str | None = None):
    with get_db() as conn:
        filtro = []
        params: list = []
        if municipio_id:
            filtro.append("e.municipio_id = ?")
            params.append(municipio_id)
        if data:
            filtro.append("v.data = ?")
            params.append(data)
        where = f"WHERE {' AND '.join(filtro)}" if filtro else ""
        rows = conn.execute(
            f"""SELECT v.id, v.serie, v.turno, v.data, v.ordem, v.status, v.finalizado_em,
                      v.turma, v.n_alunos, v.n_presentes,
                      e.nome AS escola, e.rede, e.codigo AS escola_codigo,
                      m.id AS municipio_id, m.nome AS municipio,
                      a.id AS aplicador_id, a.nome AS aplicador_nome, a.codigo AS aplicador_codigo
               FROM vagas v
               JOIN escolas e ON e.id = v.escola_id
               JOIN municipios m ON m.id = e.municipio_id
               LEFT JOIN aplicadores a ON a.id = v.aplicador_id
               {where}
               ORDER BY v.data, v.turno, m.nome, e.nome, v.serie""",
            params,
        ).fetchall()
        pendentes = []
        aplicadas = []
        livres = []
        for r in rows:
            item = dict(r)
            item["aplicador"] = None
            if item["aplicador_id"]:
                item["aplicador"] = {
                    "id": item["aplicador_id"],
                    "nome": item["aplicador_nome"] or item["aplicador_codigo"],
                    "codigo": item["aplicador_codigo"],
                }
            if item["status"] == "FINALIZADA":
                aplicadas.append(item)
            elif item["aplicador_id"]:
                pendentes.append(item)
            else:
                livres.append(item)
        datas = sorted({r["data"] for r in rows if r["data"]})
        return {
            "total": len(rows),
            "pendentes": pendentes,
            "aplicadas": aplicadas,
            "livres": livres,
            "datas": datas,
            "contagem": {
                "pendentes": len(pendentes),
                "aplicadas": len(aplicadas),
                "livres": len(livres),
            },
        }


@app.get("/api/recebimento-provas")
def recebimento_provas(municipio_id: int | None = None, data: str | None = None):
    with get_db() as conn:
        filtro = ["v.aplicador_id IS NOT NULL"]
        params: list = []
        if municipio_id:
            filtro.append("e.municipio_id = ?")
            params.append(municipio_id)
        if data:
            filtro.append("v.data = ?")
            params.append(data)
        where = f"WHERE {' AND '.join(filtro)}"
        rows = conn.execute(
            f"""SELECT v.id, v.serie, v.turno, v.data, v.ordem, v.status, v.turma, v.n_alunos,
                      v.prova_recebida_em, v.finalizado_em,
                      e.nome AS escola, e.rede, e.codigo AS escola_codigo,
                      m.id AS municipio_id, m.nome AS municipio,
                      a.id AS aplicador_id, a.nome AS aplicador_nome, a.codigo AS aplicador_codigo
               FROM vagas v
               JOIN escolas e ON e.id = v.escola_id
               JOIN municipios m ON m.id = e.municipio_id
               JOIN aplicadores a ON a.id = v.aplicador_id
               {where}
               ORDER BY v.data, v.turno, m.nome, e.nome, v.serie""",
            params,
        ).fetchall()
        pendentes = []
        recebidas = []
        for r in rows:
            item = dict(r)
            item["aplicador"] = {
                "id": item["aplicador_id"],
                "nome": item["aplicador_nome"] or item["aplicador_codigo"],
                "codigo": item["aplicador_codigo"],
            }
            item["prova_recebida"] = bool(item.get("prova_recebida_em"))
            if item["prova_recebida"]:
                recebidas.append(item)
            else:
                pendentes.append(item)
        datas = sorted({r["data"] for r in rows if r["data"]})
        return {
            "total": len(rows),
            "pendentes": pendentes,
            "recebidas": recebidas,
            "datas": datas,
            "contagem": {
                "pendentes": len(pendentes),
                "recebidas": len(recebidas),
                "alocadas": len(rows),
            },
        }


@app.get("/api/municipios")
def municipios():
    with get_db() as conn:
        consolidar_municipios(conn)
        rows = rows_to_dicts(
            conn.execute(
                """SELECT m.*,
                          v.data_saida, v.data_retorno, v.dias_aplicacao,
                          COUNT(vg.id) AS vagas,
                          COALESCE(SUM(CASE WHEN vg.id IS NOT NULL AND vg.aplicador_id IS NULL THEN 1 ELSE 0 END), 0) AS livres
                   FROM municipios m
                   LEFT JOIN viagens v ON v.municipio_id = m.id
                   LEFT JOIN escolas e ON e.municipio_id = m.id
                   LEFT JOIN vagas vg ON vg.escola_id = e.id
                   GROUP BY m.id, m.nome, v.data_saida, v.data_retorno, v.dias_aplicacao
                   ORDER BY m.nome"""
            )
        )
        for row in rows:
            row["dias"] = dias_do_municipio(row)
        return rows


@app.get("/api/escolas")
def escolas(municipio_id: int | None = None):
    with get_db() as conn:
        filtro = ""
        params: tuple = ()
        if municipio_id:
            filtro = " WHERE e.municipio_id = ?"
            params = (municipio_id,)
        return rows_to_dicts(
            conn.execute(
                f"""SELECT e.*, m.nome AS municipio,
                          COUNT(v.id) AS vagas,
                          COALESCE(SUM(CASE WHEN v.aplicador_id IS NULL THEN 1 ELSE 0 END), 0) AS livres
                   FROM escolas e
                   JOIN municipios m ON m.id = e.municipio_id
                   LEFT JOIN vagas v ON v.escola_id = e.id
                   {filtro}
                   GROUP BY e.id, e.codigo, e.nome, e.municipio_id, e.rede, e.rural, m.nome
                   ORDER BY m.nome, e.nome""",
                params,
            )
        )


@app.get("/api/aplicadores")
def aplicadores(lista: bool = False):
    with get_db() as conn:
        if lista:
            pessoas = rows_to_dicts(
                conn.execute(
                    """SELECT id, codigo, nome, ativo, numero FROM aplicadores
                       ORDER BY COALESCE(numero, 9999), codigo"""
                )
            )
            for item in pessoas:
                item["identificado"] = not _eh_placeholder(item.get("nome"), item.get("codigo"))
            return pessoas
        pessoas = rows_to_dicts(
            conn.execute(
                "SELECT * FROM aplicadores ORDER BY COALESCE(numero, 9999), codigo"
            )
        )
        por_apl: dict[int, list] = {}
        por_extra: dict[int, list] = {}
        for r in rows_to_dicts(
            conn.execute(
                """SELECT v.id, v.aplicador_id, v.serie, v.turno, v.data, v.status,
                          e.nome AS escola, e.rede, m.nome AS municipio
                   FROM vagas v
                   JOIN escolas e ON e.id = v.escola_id
                   JOIN municipios m ON m.id = e.municipio_id
                   WHERE v.aplicador_id IS NOT NULL
                   ORDER BY v.data, v.turno, e.nome"""
            )
        ):
            por_apl.setdefault(r["aplicador_id"], []).append(r)
        try:
            for r in rows_to_dicts(
                conn.execute(
                    """SELECT x.aplicador_id, v.id, v.serie, v.turno, v.data, v.turma,
                              e.nome AS escola, m.nome AS municipio
                       FROM vaga_extras x
                       JOIN vagas v ON v.id = x.vaga_id
                       JOIN escolas e ON e.id = v.escola_id
                       JOIN municipios m ON m.id = e.municipio_id
                       ORDER BY v.data, v.turno, e.nome"""
                )
            ):
                por_extra.setdefault(r["aplicador_id"], []).append(r)
        except Exception:
            pass
        lista = []
        for item in pessoas:
            vagas = por_apl.get(item["id"], [])
            extras = por_extra.get(item["id"], [])
            item["carga"] = len(vagas)
            item["carga_extra"] = len(extras)
            item["municipios"] = sorted({r["municipio"] for r in vagas + extras})
            item["vagas"] = vagas
            item["extras"] = extras
            item["cpf_fmt"] = formatar_cpf(item.get("cpf"))
            item["identificado"] = not _eh_placeholder(item.get("nome"), item.get("codigo"))
            if item.get("cpf") and not item.get("acesso_token"):
                item["acesso_token"] = garantir_token_acesso(conn, item["id"])
            item["tem_acesso"] = bool(item.get("cpf")) and item["identificado"]
            lista.append(item)
        return lista


@app.patch("/api/aplicadores/{aplicador_id}")
def editar_aplicador(aplicador_id: int, body: AplicadorBody):
    with get_db() as conn:
        atual = conn.execute(
            "SELECT * FROM aplicadores WHERE id = ?", (aplicador_id,)
        ).fetchone()
        if not atual:
            raise HTTPException(404, "Aplicador não encontrado.")
        if body.nome is not None and not str(body.nome).strip():
            try:
                return desvincular_pessoa(conn, aplicador_id)
            except Exception as exc:
                _cadastro_erro(exc)
        nome = body.nome if body.nome is not None else atual["nome"]
        ativo = atual["ativo"] if body.ativo is None else (1 if body.ativo else 0)
        try:
            if body.cpf is not None or body.numero is not None:
                cpf_envio = body.cpf
                if cpf_envio is not None and not str(cpf_envio).strip():
                    cpf_envio = atual["cpf"] if "cpf" in atual.keys() else None
                return vincular_pessoa(
                    conn,
                    nome=nome or atual["codigo"],
                    cpf=cpf_envio if cpf_envio is not None else (atual["cpf"] if "cpf" in atual.keys() else None),
                    numero=body.numero if body.numero is not None else (atual["numero"] if "numero" in atual.keys() else None),
                    codigo=atual["codigo"],
                )
        except Exception as exc:
            _cadastro_erro(exc)
        conn.execute(
            "UPDATE aplicadores SET nome = ?, ativo = ? WHERE id = ?",
            (nome, ativo, aplicador_id),
        )
        return row_to_dict(
            conn.execute(
                "SELECT * FROM aplicadores WHERE id = ?", (aplicador_id,)
            ).fetchone()
        )


@app.post("/api/municipios")
def api_criar_municipio(body: MunicipioBody):
    with get_db() as conn:
        try:
            return criar_municipio(conn, body.nome, body.data_saida, body.data_retorno, body.dias)
        except Exception as exc:
            _cadastro_erro(exc)


@app.patch("/api/municipios/{municipio_id}")
def api_editar_municipio(municipio_id: int, body: MunicipioPatchBody):
    with get_db() as conn:
        try:
            dados = body.model_dump(exclude_unset=True)
            aplicar = dados.pop("aplicar_datas_vagas", False)
            mun = atualizar_municipio(conn, municipio_id, **dados)
            if aplicar:
                _preencher_datas_faltantes(conn, municipio_id)
                mun = atualizar_municipio(conn, municipio_id)
            return mun
        except Exception as exc:
            _cadastro_erro(exc)


@app.delete("/api/municipios/{municipio_id}")
def api_excluir_municipio(municipio_id: int):
    with get_db() as conn:
        try:
            excluir_municipio(conn, municipio_id)
        except Exception as exc:
            _cadastro_erro(exc)
    return {"ok": True}


@app.post("/api/escolas")
def api_criar_escola(body: EscolaBody):
    with get_db() as conn:
        try:
            return criar_escola(
                conn, body.municipio_id, body.nome, body.codigo, body.rede, body.rural
            )
        except Exception as exc:
            _cadastro_erro(exc)


@app.patch("/api/escolas/{escola_id}")
def api_editar_escola(escola_id: int, body: EscolaPatchBody):
    with get_db() as conn:
        try:
            return atualizar_escola(conn, escola_id, **body.model_dump(exclude_unset=True))
        except Exception as exc:
            _cadastro_erro(exc)


@app.delete("/api/escolas/{escola_id}")
def api_excluir_escola(escola_id: int):
    with get_db() as conn:
        try:
            excluir_escola(conn, escola_id)
        except Exception as exc:
            _cadastro_erro(exc)
    return {"ok": True}


@app.post("/api/aplicadores/lote")
def api_lote_aplicadores(body: LoteAplicadoresBody):
    with get_db() as conn:
        try:
            return criar_lote_aplicadores(conn, body.quantidade)
        except Exception as exc:
            _cadastro_erro(exc)


@app.post("/api/aplicadores")
def api_criar_aplicador(body: AplicadorBody):
    if not body.nome:
        raise HTTPException(400, "Informe o nome do aplicador.")
    with get_db() as conn:
        try:
            return vincular_pessoa(
                conn,
                nome=body.nome,
                cpf=body.cpf,
                numero=body.numero,
                codigo=body.codigo,
            )
        except Exception as exc:
            _cadastro_erro(exc)


@app.post("/api/aplicadores/vincular")
def api_vincular_aplicador(body: VincularBody):
    with get_db() as conn:
        try:
            return vincular_pessoa(
                conn,
                nome=body.nome,
                cpf=body.cpf,
                numero=body.numero,
                codigo=body.codigo,
            )
        except Exception as exc:
            _cadastro_erro(exc)


@app.delete("/api/aplicadores/{aplicador_id}")
def api_excluir_aplicador(aplicador_id: int):
    with get_db() as conn:
        try:
            excluir_aplicador(conn, aplicador_id)
        except Exception as exc:
            _cadastro_erro(exc)
    return {"ok": True}


@app.post("/api/vagas")
def api_criar_vaga(body: VagaNovaBody):
    with get_db() as conn:
        try:
            ids = criar_vaga(
                conn,
                body.escola_id,
                body.serie,
                body.turno,
                body.data,
                body.quantidade,
                body.criar_par,
            )
        except Exception as exc:
            _cadastro_erro(exc)
        return {"ok": True, "ids": ids, "criadas": len(ids)}


@app.delete("/api/vagas/{vaga_id}")
def api_excluir_vaga(vaga_id: int):
    with get_db() as conn:
        try:
            excluir_vaga(conn, vaga_id)
        except Exception as exc:
            _cadastro_erro(exc)
    return {"ok": True}


@app.get("/api/quadro")
def quadro(municipio_id: int):
    with get_db() as conn:
        mun = conn.execute(
            """SELECT m.*, v.data_saida, v.data_retorno, v.dias_aplicacao
               FROM municipios m
               LEFT JOIN viagens v ON v.municipio_id = m.id
               WHERE m.id = ?""",
            (municipio_id,),
        ).fetchone()
        if not mun:
            raise HTTPException(404, "Município não encontrado.")

        vagas = conn.execute(
            """SELECT v.*, e.nome AS escola_nome, e.codigo AS escola_codigo,
                      e.rede, e.rural, e.municipio_id,
                      a.id AS apl_id, a.codigo AS apl_codigo, a.nome AS apl_nome
               FROM vagas v
               JOIN escolas e ON e.id = v.escola_id
               LEFT JOIN aplicadores a ON a.id = v.aplicador_id
               WHERE e.municipio_id = ?
               ORDER BY e.nome, v.turno, v.data, v.serie""",
            (municipio_id,),
        ).fetchall()

        mun_d = row_to_dict(mun)
        mun_d["dias"] = dias_do_municipio(mun_d)
        datas = sorted(
            set(mun_d["dias"]) | {r["data"] for r in vagas if r["data"]}
        )
        if any(not r["data"] for r in vagas):
            datas.append("")
        linhas_map: dict[tuple, dict] = {}
        livres = 0
        choques = 0
        avisos = 0
        finalizadas = 0

        for d in enriquecer_vagas(conn, [dict(raw) for raw in vagas]):
            if d["vago"]:
                livres += 1
            if d["tem_choque"]:
                choques += 1
            if d["tem_aviso"]:
                avisos += 1
            if d["status"] == "FINALIZADA":
                finalizadas += 1
            chave = (d["escola_id"], d["turno"])
            if chave not in linhas_map:
                linhas_map[chave] = {
                    "escola_id": d["escola_id"],
                    "escola": d["escola_nome"],
                    "codigo": d["escola_codigo"],
                    "rede": d["rede"],
                    "rural": bool(d["rural"]),
                    "turno": d["turno"],
                    "celulas": {dt: [] for dt in datas},
                }
            chave_data = d["data"] or ""
            linhas_map[chave]["celulas"].setdefault(chave_data, [])
            linhas_map[chave]["celulas"][chave_data].append(
                {
                    "id": d["id"],
                    "serie": d["serie"],
                    "ordem": d["ordem"],
                    "turno": d["turno"],
                    "data": d["data"],
                    "turma": d.get("turma"),
                    "n_alunos": d.get("n_alunos"),
                    "status": d["status"],
                    "vago": d["vago"],
                    "tem_choque": d["tem_choque"],
                    "tem_aviso": d["tem_aviso"],
                    "problemas": d["problemas"],
                    "aplicador": None
                    if d["vago"]
                    else {
                        "id": d["apl_id"],
                        "codigo": d["apl_codigo"],
                        "nome": d["apl_nome"] or d["apl_codigo"],
                    },
                    "n_extras": d.get("n_extras") or 0,
                    "extras": d.get("extras") or [],
                    "extras_preenchidos": d.get("extras_preenchidos") or 0,
                    "extras_faltam": d.get("extras_faltam") or 0,
                    "extras_tem_choque": bool(d.get("extras_tem_choque")),
                }
            )

        return {
            "municipio": mun_d,
            "datas": datas,
            "datas_fmt": ["Sem data" if not d else fmt_data(d) for d in datas],
            "linhas": list(linhas_map.values()),
            "vagas": len(vagas),
            "livres": livres,
            "choques": choques,
            "avisos": avisos,
            "finalizadas": finalizadas,
        }


@app.get("/api/vagas/{vaga_id}/candidatos")
def candidatos(vaga_id: int, data: str | None = None):
    with get_db() as conn:
        vaga = conn.execute(
            """SELECT v.*, e.nome AS escola_nome, e.rede, e.municipio_id,
                      m.nome AS municipio_nome, vi.data_saida, vi.data_retorno,
                      a.codigo AS apl_codigo, a.nome AS apl_nome
               FROM vagas v
               JOIN escolas e ON e.id = v.escola_id
               JOIN municipios m ON m.id = e.municipio_id
               LEFT JOIN viagens vi ON vi.municipio_id = m.id
               LEFT JOIN aplicadores a ON a.id = v.aplicador_id
               WHERE v.id = ?""",
            (vaga_id,),
        ).fetchone()
        if not vaga:
            raise HTTPException(404, "Vaga não encontrada.")
        d = enriquecer_vaga(conn, dict(vaga))
        if data:
            d["data"] = data[:10]
        return {
            "vaga": d,
            "candidatos": candidatos_para_vaga(conn, vaga_id, data),
            "candidatos_extra": candidatos_para_extra(conn, vaga_id, data),
        }


@app.post("/api/vagas/{vaga_id}/substituir")
def api_substituir(vaga_id: int, body: SubstituirBody):
    with get_db() as conn:
        resultado = substituir_aplicador(conn, vaga_id, body.aplicador_id, body.data)
        if not resultado.get("ok"):
            raise HTTPException(409, resultado.get("erro") or "Não foi possível substituir.")
        return resultado


@app.post("/api/vagas/{vaga_id}/alocar")
def api_alocar(vaga_id: int, body: AlocarBody):
    with get_db() as conn:
        resultado = alocar(
            conn,
            vaga_id,
            body.aplicador_id,
            body.repetir_par,
            body.data,
            body.forcar,
        )
        if not resultado.get("ok"):
            raise HTTPException(409, resultado.get("erro") or "Não foi possível alocar.")
        return resultado


@app.post("/api/vagas/{vaga_id}/n-extras")
def api_n_extras(vaga_id: int, body: NExtrasBody):
    with get_db() as conn:
        resultado = definir_n_extras(conn, vaga_id, body.n_extras)
        if not resultado.get("ok"):
            raise HTTPException(400, resultado.get("erro") or "Não foi possível gravar os extras.")
        return resultado


@app.post("/api/vagas/{vaga_id}/extras")
def api_alocar_extra(vaga_id: int, body: ExtraBody):
    with get_db() as conn:
        resultado = alocar_extra(conn, vaga_id, body.aplicador_id, body.forcar)
        if not resultado.get("ok"):
            raise HTTPException(409, resultado.get("erro") or "Não foi possível encaixar o extra.")
        return resultado


@app.delete("/api/vagas/{vaga_id}/extras/{aplicador_id}")
def api_remover_extra(vaga_id: int, aplicador_id: int):
    with get_db() as conn:
        resultado = remover_extra(conn, vaga_id, aplicador_id)
        if not resultado.get("ok"):
            raise HTTPException(404, resultado.get("erro") or "Extra não encontrado.")
        return resultado


@app.post("/api/vagas/{vaga_id}/finalizar")
def api_finalizar(vaga_id: int, body: FinalizarBody):
    with get_db() as conn:
        resultado = finalizar_vaga(conn, vaga_id, body.finalizada, body.n_presentes)
        if not resultado.get("ok"):
            raise HTTPException(404, resultado.get("erro"))
        return resultado


@app.post("/api/vagas/{vaga_id}/receber-prova")
def api_receber_prova(vaga_id: int, body: ReceberProvaBody):
    with get_db() as conn:
        resultado = receber_prova(conn, vaga_id, body.recebida)
        if not resultado.get("ok"):
            raise HTTPException(400, resultado.get("erro") or "Não foi possível marcar o recebimento.")
        return resultado


@app.post("/api/quadro/organizar")
def api_organizar(body: OrganizarBody):
    with get_db() as conn:
        return organizar(
            conn,
            body.municipio_id,
            body.reset,
            body.aplicador_ids,
            body.nova_rodada,
        )


@app.post("/api/quadro/limpar")
def api_limpar(body: LimparBody):
    with get_db() as conn:
        if body.municipio_id:
            conn.execute(
                """UPDATE vagas SET aplicador_id = NULL, alocacao = NULL, prova_recebida_em = NULL
                   WHERE escola_id IN (
                     SELECT id FROM escolas WHERE municipio_id = ?
                   )""",
                (body.municipio_id,),
            )
        else:
            conn.execute("UPDATE vagas SET aplicador_id = NULL, alocacao = NULL, prova_recebida_em = NULL")
        livres = conn.execute(
            "SELECT COUNT(*) n FROM vagas WHERE aplicador_id IS NULL"
        ).fetchone()["n"]
        return {"ok": True, "livres": livres}


@app.post("/api/zerar")
def api_zerar():
    with get_db() as conn:
        zerar_tudo(conn)
    return {"ok": True}


@app.post("/api/nuvem/publicar")
def api_publicar_nuvem():
    if not usando_nuvem():
        raise HTTPException(400, "Falta a chave do Supabase no arquivo .env.")
    from .nuvem import enviar_do_sqlite

    with get_db() as conn:
        try:
            enviadas = enviar_do_sqlite(conn)
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "enviadas": enviadas}


@app.post("/api/importar")
def api_importar():
    planilha = localizar_planilha()
    if not planilha:
        raise HTTPException(400, "Nenhuma planilha .xlsx encontrada na pasta do sistema.")
    return importar_planilha(planilha)


@app.post("/api/importar/arquivo")
async def api_importar_arquivo(arquivo: UploadFile = File(...)):
    if not arquivo.filename or not arquivo.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "Envie um arquivo Excel (.xlsx).")
    bruto = DATA_DIR / "envio.xlsx"
    bruto.write_bytes(await arquivo.read())
    destino = salvar_planilha_atual(bruto)
    return importar_planilha(destino)


@app.post("/api/restaurar-turmas")
def api_restaurar_turmas():
    planilha = localizar_planilha()
    if not planilha:
        raise HTTPException(400, "Não achei a planilha de turmas na pasta do sistema.")
    try:
        return completar_planilha(planilha)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
