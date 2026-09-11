const state = {
  view: "resumo",
  municipioId: null,
  filtroRede: "TODAS",
  filtroVago: false,
  filtroStatus: "TODAS",
  campoMun: "",
  campoData: "",
  buscaAplicador: "",
  cadastroTab: "municipios",
  editMunId: null,
  aplicadoresSel: null,
  diasMun: [],
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    let msg = "Falha na requisição.";
    try {
      const data = await res.json();
      msg = data.detail || data.erro || msg;
    } catch (_) {}
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  if (res.status === 204) return null;
  return res.json();
}

function titulo(h1, p) {
  $("#titulo-pagina").textContent = h1;
  $("#subtitulo-pagina").textContent = p;
}

function fmtData(iso) {
  if (!iso) return "—";
  const [a, m, d] = iso.split("-");
  return `${d}/${m}/${a}`;
}

function nomeApl(a) {
  if (!a) return "Vago";
  return a.nome || a.codigo || "Vago";
}

function tit(s) {
  if (!s) return "";
  const mini = new Set(["do", "da", "de", "dos", "das", "e"]);
  return String(s)
    .toLowerCase()
    .split(" ")
    .map((w, i) => (i > 0 && mini.has(w) ? w : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(" ");
}

function badgeRede(rede) {
  return `<span class="chip ${rede}">${rede.toLowerCase()}</span>`;
}

$$(".nav-btn").forEach((btn) => {
  btn.addEventListener("click", () => mostrarView(btn.dataset.view));
});

function mostrarView(view, extra = {}) {
  state.view = view;
  if (extra.municipioId) state.municipioId = extra.municipioId;
  if (view === "cadastro") {
    if (extra.tab) state.cadastroTab = extra.tab;
    else if (state.cadastroTab === "aplicadores") state.cadastroTab = "municipios";
  }
  $$(".nav-btn").forEach((b) => b.classList.toggle("ativo", b.dataset.view === view));
  $$(".view").forEach((v) => v.classList.add("hidden"));
  $(`#view-${view}`).classList.remove("hidden");
  if (view === "resumo") carregarResumo();
  if (view === "quadro") carregarQuadro();
  if (view === "campo") carregarCampo();
  if (view === "cadastro") carregarCadastro();
  if (view === "aplicadores") carregarAplicadores();
  if (view === "escolas") carregarEscolas();
}

$("#btn-reimportar").addEventListener("click", async () => {
  if (!confirm("Recarregar a última planilha salva? As linhas da planilha voltam a valer; o que você cadastrou na mão permanece.")) return;
  try {
    const r = await api("/api/importar", { method: "POST", body: "{}" });
    alert(`Importado: ${r.vagas_gravadas} aplicações de ${r.arquivo}.`);
    mostrarView(state.view);
  } catch (err) {
    alert(err.message);
  }
});

$("#btn-enviar-planilha").addEventListener("click", () => $("#arquivo-planilha").click());
$("#arquivo-planilha").addEventListener("change", async (ev) => {
  const file = ev.target.files && ev.target.files[0];
  ev.target.value = "";
  if (!file) return;
  if (!confirm(`Importar "${file.name}" e deixar o quadro igual a essa planilha? O que veio de planilha anterior é substituído. Cadastros manuais permanecem.`)) return;
  const fd = new FormData();
  fd.append("arquivo", file);
  try {
    const res = await fetch("/api/importar/arquivo", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Falha ao importar.");
    const avisos = (data.avisos || []).length ? `\nAvisos: ${data.avisos.length}` : "";
    alert(`Quadro atualizado: ${data.vagas_gravadas} aplicações de ${file.name}.${avisos}`);
    mostrarView(state.view);
  } catch (err) {
    alert(err.message);
  }
});

function fecharDrawer() {
  $("#drawer").classList.add("hidden");
  $("#drawer-fundo").classList.add("hidden");
  $("#drawer").setAttribute("aria-hidden", "true");
}
$("#fechar-drawer").addEventListener("click", fecharDrawer);
$("#drawer-fundo").addEventListener("click", fecharDrawer);

async function abrirVaga(vagaId) {
  const data = await api(`/api/vagas/${vagaId}/candidatos`);
  const v = data.vaga;
  $("#drawer-kicker").textContent = `${tit(v.municipio_nome)} · ${v.turno}`;
  $("#drawer-titulo").textContent = v.serie;
  const problemas = (v.problemas || [])
    .map((p) => `<li>${p.mensagem}</li>`)
    .join("");
  const cands = data.candidatos
    .map((c) => {
      const motivo = c.ok
        ? `${c.carga} aplicação(ões)${c.no_municipio ? " · já neste município" : ""}`
        : (c.choques[0] && c.choques[0].mensagem) || "Indisponível";
      const rotulo = c.nome && c.nome !== c.codigo ? `${c.nome} · ${c.codigo}` : c.nome;
      return `<button class="cand ${c.ok ? "" : "choque"} ${c.selecionado ? "selecionado" : ""}"
                data-id="${c.id}" data-ok="${c.ok ? "1" : "0"}">
                <b>${rotulo}</b>
                <small>${c.ok ? motivo : "Choque: " + motivo + " — clique para colocar mesmo assim"}</small>
              </button>`;
    })
    .join("");
  const dataPadrao = v.data || v.data_saida || "";
  const minData = v.data_saida || "";
  const maxData = v.data_retorno || v.data_saida || "";
  $("#drawer-corpo").innerHTML = `
    <p>${tit(v.escola_nome)}</p>
    <p>${badgeRede(v.rede)}</p>
    <label class="campo">Data da aplicação
      <input type="date" id="vaga-data" value="${dataPadrao}" ${minData ? `min="${minData}"` : ""} ${maxData ? `max="${maxData}"` : ""} />
    </label>
    <button type="button" class="btn sm" id="btn-salvar-data" style="margin:8px 0 12px">Salvar data</button>
    ${problemas ? `<ul>${problemas}</ul>` : ""}
    <p>${
      v.status === "FINALIZADA"
        ? '<span class="chip aplicada">Aplicador já marcou como aplicada</span>'
        : '<span class="chip vago">Ainda não aplicada no campo</span>'
    }</p>
    <button class="btn ${v.status === "FINALIZADA" ? "ghost" : "gold"}" id="btn-status-vaga">
      ${v.status === "FINALIZADA" ? "Reabrir (não aplicada)" : "Marcar como aplicada"}
    </button>
    <label class="toolbar" style="margin: 12px 0">
      <input type="checkbox" id="repetir-par" checked />
      Repetir no Dia 1/Dia 2 do 2º ano, se houver
    </label>
    <button class="btn ghost" id="btn-liberar">Tirar aplicador (volta para Sem data)</button>
    <button class="btn warn" id="btn-excluir-vaga">Apagar turma do quadro</button>
    <h3 style="font-family:Fraunces,serif">Quem pode entrar</h3>
    <div id="lista-cands">${cands}</div>
  `;
  $("#drawer").classList.remove("hidden");
  $("#drawer-fundo").classList.remove("hidden");
  $("#drawer").setAttribute("aria-hidden", "false");

  const dataEscolhida = () => $("#vaga-data")?.value || null;

  $("#btn-salvar-data").onclick = async () => {
    const dia = dataEscolhida();
    if (!dia) {
      alert("Informe a data desta aplicação.");
      return;
    }
    try {
      await api(`/api/vagas/${vagaId}/alocar`, {
        method: "POST",
        body: JSON.stringify({
          aplicador_id: v.aplicador_id || null,
          repetir_par: $("#repetir-par").checked,
          data: dia,
        }),
      });
      fecharDrawer();
      mostrarView("quadro");
    } catch (err) {
      alert(err.message);
    }
  };
  $("#btn-liberar").onclick = async () => {
    const repetir = $("#repetir-par").checked;
    await api(`/api/vagas/${vagaId}/alocar`, {
      method: "POST",
      body: JSON.stringify({ aplicador_id: null, repetir_par: repetir }),
    });
    fecharDrawer();
    mostrarView("quadro");
  };
  $("#btn-excluir-vaga").onclick = async () => {
    if (!confirm("Isso APAGA a turma do quadro, não só o aplicador. Para só tirar a pessoa e a data, cancele e use Tirar aplicador. Apagar de vez?")) return;
    await api(`/api/vagas/${vagaId}`, { method: "DELETE" });
    fecharDrawer();
    mostrarView("quadro");
  };
  $("#btn-status-vaga").onclick = async () => {
    const feita = v.status === "FINALIZADA";
    await api(`/api/vagas/${vagaId}/finalizar`, {
      method: "POST",
      body: JSON.stringify({ finalizada: !feita }),
    });
    fecharDrawer();
    mostrarView("quadro");
  };
  $$("#lista-cands .cand").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const repetir = $("#repetir-par").checked;
      const forcar = btn.dataset.ok !== "1";
      if (forcar && !confirm("Este aplicador tem choque neste horário. Colocar mesmo assim? Depois você pode mover para outro dia ou outra vaga.")) return;
      try {
        await api(`/api/vagas/${vagaId}/alocar`, {
          method: "POST",
          body: JSON.stringify({
            aplicador_id: Number(btn.dataset.id),
            repetir_par: repetir,
            data: dataEscolhida(),
            forcar,
          }),
        });
        fecharDrawer();
        mostrarView("quadro");
      } catch (err) {
        alert(err.message);
      }
    });
  });
}

async function carregarResumo() {
  titulo("Visão geral", "Demanda da SRE Gurupi e ocupação da escala.");
  const r = await api("/api/resumo");
  const pct = r.vagas ? Math.round((r.ocupadas / r.vagas) * 100) : 0;
  const pendentes = Math.max(0, (r.ocupadas || 0) - (r.finalizadas || 0));
  $("#view-resumo").innerHTML = `
    <div class="cards">
      <article class="card"><div class="label">Vagas</div><div class="value">${r.vagas}</div></article>
      <article class="card ok"><div class="label">Ocupadas</div><div class="value">${r.ocupadas}<small style="font-size:16px"> ${pct}%</small></div></article>
      <article class="card warn"><div class="label">Ainda no campo</div><div class="value">${pendentes}</div></article>
      <article class="card ok"><div class="label">Já aplicadas</div><div class="value">${r.finalizadas}</div></article>
    </div>
    <div class="cards">
      <article class="card"><div class="label">Municípios</div><div class="value">${r.municipios}</div></article>
      <article class="card"><div class="label">Escolas</div><div class="value">${r.escolas}</div></article>
      <article class="card"><div class="label">Aplicadores</div><div class="value">${r.aplicadores}</div></article>
      <article class="card ${r.choques ? "bad" : "ok"}"><div class="label">Choques</div><div class="value">${r.choques}</div></article>
    </div>
    <p style="margin:8px 0 12px;color:var(--ink-soft);font-size:14px">Banco deste computador: ${
      r.banco === "supabase" ? "Supabase (nuvem, compartilhado)" : "arquivo local (SQLite)"
    }</p>
    ${r.tem_nuvem && r.banco !== "supabase" ? `
    <p style="margin:0 0 8px">
      <button class="btn gold" id="btn-publicar-nuvem">Mandar tudo para o Supabase</button>
    </p>
    <p id="status-nuvem" class="escola-meta" style="margin:0 0 16px">Primeiro rode o SQL da pasta supabase no painel. Depois disto o Render usa o mesmo banco.</p>` : ""}
    <section class="panel">
      <h2>Por município</h2>
      <div class="mun-grid">
        ${r.por_municipio
          .map(
            (m) => `<button class="mun-card" data-id="${m.id}">
              <b>${tit(m.nome)}</b>
              <span>${m.vagas} aplicações · ${m.livres} vagas · ${m.finalizadas || 0} aplicadas</span>
            </button>`
          )
          .join("")}
      </div>
    </section>
  `;
  $$(".mun-card").forEach((btn) => {
    btn.addEventListener("click", () => mostrarView("quadro", { municipioId: Number(btn.dataset.id) }));
  });
  $("#btn-publicar-nuvem")?.addEventListener("click", async () => {
    const btn = $("#btn-publicar-nuvem");
    const status = $("#status-nuvem");
    if (!confirm("Enviar municípios, escolas, turmas e aplicadores deste computador para o Supabase? O que já estiver lá com o mesmo id será atualizado.")) return;
    btn.disabled = true;
    btn.textContent = "Enviando…";
    if (status) status.textContent = "Enviando para o Supabase. Espere o recado aqui.";
    try {
      const pub = await api("/api/nuvem/publicar", { method: "POST", body: "{}" });
      const n = (pub.enviadas && pub.enviadas.vagas) || 0;
      const msg = `Enviado. Turmas na nuvem: ${n}. Agora o Render pode usar esse banco.`;
      if (status) status.textContent = msg;
      alert(msg);
    } catch (err) {
      const msg = err.message || "Não enviou. Veja o recado abaixo.";
      if (status) status.textContent = "Não enviou: " + msg;
      alert(msg);
    } finally {
      btn.disabled = false;
      btn.textContent = "Mandar tudo para o Supabase";
    }
  });
}

function fmtHora(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function cardCampo(item, feita) {
  const quem = item.aplicador ? nomeApl(item.aplicador) : "Sem aplicador";
  const hora = feita && item.finalizado_em ? ` · baixa ${fmtHora(item.finalizado_em)}` : "";
  return `<article class="item-campo ${feita ? "feita" : ""}">
    <b>${tit(item.escola)}</b>
    <div class="meta">
      ${tit(item.municipio)} · ${fmtData(item.data)} · ${item.turno}<br />
      ${item.serie}${item.ordem > 1 ? " · " + item.ordem : ""} · ${quem}${hora}
    </div>
    <button class="btn sm ${feita ? "ghost" : "gold"}" data-baixa="${item.id}" data-feita="${feita ? "1" : "0"}">
      ${feita ? "Reabrir" : "Dar baixa"}
    </button>
  </article>`;
}

async function carregarCampo() {
  titulo("Acompanhamento no campo", "No período de aplicação: de um lado o que ainda falta, do outro o que já deu baixa.");
  const municipios = await api("/api/municipios");
  const qs = new URLSearchParams();
  if (state.campoMun) qs.set("municipio_id", state.campoMun);
  if (state.campoData) qs.set("data", state.campoData);
  const d = await api(`/api/acompanhamento?${qs.toString()}`);
  const munOpts = [`<option value="">Todos os municípios</option>`]
    .concat(municipios.map((m) => `<option value="${m.id}" ${String(m.id) === String(state.campoMun) ? "selected" : ""}>${tit(m.nome)}</option>`))
    .join("");
  const dataOpts = [`<option value="">Todos os dias</option>`]
    .concat((d.datas || []).map((dt) => `<option value="${dt}" ${dt === state.campoData ? "selected" : ""}>${fmtData(dt)}</option>`))
    .join("");
  $("#view-campo").innerHTML = `
    <div class="cards">
      <article class="card warn"><div class="label">Pendentes</div><div class="value">${d.contagem.pendentes}</div></article>
      <article class="card ok"><div class="label">Deram baixa</div><div class="value">${d.contagem.aplicadas}</div></article>
      <article class="card"><div class="label">Sem aplicador</div><div class="value">${d.contagem.livres}</div></article>
      <article class="card"><div class="label">No filtro</div><div class="value">${d.total}</div></article>
    </div>
    <div class="toolbar">
      <select id="campo-mun">${munOpts}</select>
      <select id="campo-data">${dataOpts}</select>
      <button class="btn ghost" id="btn-atualizar-campo">Atualizar</button>
    </div>
    ${d.contagem.livres ? `<p class="escola-meta" style="margin-bottom:12px">${d.contagem.livres} aplicação(ões) ainda sem aplicador neste filtro.</p>` : ""}
    <div class="colunas-campo">
      <section class="panel col-campo pendente">
        <h2>Pendentes <span class="chip vago">${d.contagem.pendentes}</span></h2>
        <p class="escola-meta">Já têm aplicador, mas ainda não marcaram como aplicada.</p>
        ${d.pendentes.length ? d.pendentes.map((i) => cardCampo(i, false)).join("") : "<p class='escola-meta'>Nada pendente neste filtro.</p>"}
      </section>
      <section class="panel col-campo baixa">
        <h2>Deram baixa <span class="chip aplicada">${d.contagem.aplicadas}</span></h2>
        <p class="escola-meta">O aplicador (ou a coordenação) já confirmou no sistema.</p>
        ${d.aplicadas.length ? d.aplicadas.map((i) => cardCampo(i, true)).join("") : "<p class='escola-meta'>Nenhuma baixa neste filtro.</p>"}
      </section>
    </div>
  `;
  $("#campo-mun").addEventListener("change", (e) => {
    state.campoMun = e.target.value;
    carregarCampo();
  });
  $("#campo-data").addEventListener("change", (e) => {
    state.campoData = e.target.value;
    carregarCampo();
  });
  $("#btn-atualizar-campo").onclick = () => carregarCampo();
  $$("[data-baixa]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const feita = btn.dataset.feita === "1";
      await api(`/api/vagas/${btn.dataset.baixa}/finalizar`, {
        method: "POST",
        body: JSON.stringify({ finalizada: !feita }),
      });
      carregarCampo();
    });
  });
}

async function carregarQuadro() {
  titulo("Quadro de aplicação", "Grade por escola, turno e dia — como um horário, com vago e choque visíveis.");
  const municipios = await api("/api/municipios");
  if (!state.municipioId && municipios.length) state.municipioId = municipios[0].id;
  const munOpts = municipios
    .map((m) => `<option value="${m.id}" ${m.id === state.municipioId ? "selected" : ""}>${tit(m.nome)}</option>`)
    .join("");

  $("#view-quadro").innerHTML = `
    <div class="toolbar">
      <select id="sel-mun">${munOpts}</select>
      <select id="sel-rede">
        <option value="TODAS">Todas as redes</option>
        <option value="MUNICIPAL">Municipal</option>
        <option value="ESTADUAL">Estadual</option>
        <option value="CONVENIADA">Conveniada</option>
      </select>
      <label><input type="checkbox" id="so-vagos" /> Só vagos</label>
      <select id="sel-status">
        <option value="TODAS">Todas as situações</option>
        <option value="PENDENTES">Ainda no campo</option>
        <option value="APLICADAS">Já aplicadas</option>
      </select>
      <button class="btn gold" id="btn-organizar">Alocar com o que tem</button>
      <button class="btn" id="btn-reorganizar">Recomeçar escala</button>
      <button class="btn ghost" id="btn-restaurar-turmas">Restaurar turmas apagadas</button>
      <button class="btn ghost" id="btn-nova-vaga">Nova aplicação</button>
      <button class="btn warn" id="btn-limpar">Limpar alocações</button>
      <div class="legend">
        <span class="chip vago">vago</span>
        <span class="chip choque">choque</span>
        <span class="chip ok">alocado</span>
        <span class="chip aplicada">aplicada</span>
      </div>
    </div>
    <div id="painel-alocar"></div>
    <div id="quadro-corpo"></div>
  `;
  $("#sel-rede").value = state.filtroRede;
  $("#so-vagos").checked = state.filtroVago;
  $("#sel-status").value = state.filtroStatus;
  $("#sel-mun").addEventListener("change", (e) => {
    state.municipioId = Number(e.target.value);
    pintarQuadro();
  });
  $("#sel-rede").addEventListener("change", (e) => {
    state.filtroRede = e.target.value;
    pintarQuadro();
  });
  $("#so-vagos").addEventListener("change", (e) => {
    state.filtroVago = e.target.checked;
    pintarQuadro();
  });
  $("#sel-status").addEventListener("change", (e) => {
    state.filtroStatus = e.target.value;
    pintarQuadro();
  });
  $("#btn-organizar").onclick = () => abrirPainelAlocar();
  $("#btn-reorganizar").onclick = async () => {
    if (!confirm("Apagar as alocações deste município e montar a escala de novo nestes dias?")) return;
    try {
      if ((state.diasMun || []).length) {
        await api(`/api/municipios/${state.municipioId}`, {
          method: "PATCH",
          body: JSON.stringify({ dias: state.diasMun }),
        });
      }
      await rodarOrganizar(true);
    } catch (err) {
      alert(err.message);
    }
  };
  if ($("#btn-nova-vaga")) $("#btn-nova-vaga").onclick = () => abrirNovaAplicacao(state.municipioId);
  if ($("#btn-restaurar-turmas")) $("#btn-restaurar-turmas").onclick = async () => {
    if (!confirm("Trazer de volta só as turmas da planilha que foram apagadas? O que já está no quadro permanece.")) return;
    try {
      const r = await api("/api/restaurar-turmas", { method: "POST", body: "{}" });
      alert(`Turmas recolocadas: ${r.vagas_gravadas}. Elas voltam em Sem data.`);
      await pintarQuadro();
    } catch (err) {
      alert(err.message);
    }
  };
  $("#btn-limpar").onclick = async () => {
    if (!confirm("Deixar todas as vagas deste município livres?")) return;
    await api("/api/quadro/limpar", {
      method: "POST",
      body: JSON.stringify({ municipio_id: state.municipioId }),
    });
    pintarQuadro();
  };
  try {
    await pintarQuadro();
  } catch (err) {
    $("#quadro-corpo").innerHTML = `<section class="panel"><p>Não deu para montar o quadro: ${escHtml(err.message)}</p></section>`;
  }
}

function munNomeAtual() {
  const sel = $("#sel-mun");
  const opt = sel?.selectedOptions?.[0];
  return opt ? opt.textContent.trim() : "este município";
}

function atualizarContagemAlocar() {
  const n = $$("#painel-alocar input[type=checkbox][value]:checked").length;
  const mun = munNomeAtual();
  const el = $("#alocar-contagem");
  const btn = $("#confirmar-alocar");
  if (el) {
    el.textContent = n
      ? `${n} selecionado${n === 1 ? "" : "s"} — só estes entram no sorteio de ${mun}. O que não couber sem choque fica laranja para você colocar na mão.`
      : `Ninguém marcado. Selecione quem vai para ${mun} (ex.: 7).`;
  }
  if (btn) btn.textContent = n ? `Sortear com estes ${n}` : "Sortear com os selecionados";
  $$("#painel-alocar .check-alocar").forEach((lab) => {
    lab.classList.toggle("marcado", !!lab.querySelector("input")?.checked);
  });
}

async function abrirPainelAlocar() {
  if (!state.municipioId) return;
  const lista = await api("/api/aplicadores");
  if (!lista.length) {
    alert("Crie os números de aplicador antes de alocar.");
    return;
  }
  const ja = state.aplicadoresSel && state.aplicadoresSel.length
    ? new Set(state.aplicadoresSel.map(Number))
    : null;
  const mun = munNomeAtual();
  const itens = lista
    .map((a) => {
      const id = Number(a.id);
      const marcado = ja ? ja.has(id) : false;
      const rotulo = a.identificado && a.nome ? `${a.codigo} — ${a.nome}` : a.codigo;
      return `<label class="check-alocar${marcado ? " marcado" : ""}">
        <input type="checkbox" value="${id}" ${marcado ? "checked" : ""} />
        <span>${escHtml(rotulo)}</span>
      </label>`;
    })
    .join("");
  $("#painel-alocar").innerHTML = `
    <section class="panel painel-alocar">
      <h2>Quem entra em ${escHtml(mun)}</h2>
      <p class="escola-meta" style="margin:0 0 12px">Marque na lista (ex.: 7). O sistema sorteia <b>só estes</b> para preencher as vagas deste município, sem choque. O que não der, você organiza no card.</p>
      <p id="alocar-contagem" class="escola-meta" style="margin:0 0 10px;font-weight:700"></p>
      <div class="toolbar" style="margin-bottom:10px">
        <button type="button" class="btn sm ghost" id="alocar-todos">Marcar todos</button>
        <button type="button" class="btn sm ghost" id="alocar-nenhum">Desmarcar todos</button>
      </div>
      <div class="lista-alocar">${itens}</div>
      <label class="check-inline" style="margin:12px 0">
        <input type="checkbox" id="nova-rodada" />
        Nova rodada: desfazer só o sorteio automático deste município e tentar de novo (o que você colocou na mão permanece)
      </label>
      <div class="toolbar">
        <button type="button" class="btn gold" id="confirmar-alocar">Sortear com os selecionados</button>
        <button type="button" class="btn ghost" id="cancelar-alocar">Cancelar</button>
      </div>
    </section>`;
  const marcar = (todos) => {
    $$("#painel-alocar input[type=checkbox][value]").forEach((c) => { c.checked = todos; });
    atualizarContagemAlocar();
  };
  $("#alocar-todos").onclick = () => marcar(true);
  $("#alocar-nenhum").onclick = () => marcar(false);
  $$("#painel-alocar input[type=checkbox][value]").forEach((c) => {
    c.addEventListener("change", atualizarContagemAlocar);
  });
  atualizarContagemAlocar();
  $("#cancelar-alocar").onclick = () => { $("#painel-alocar").innerHTML = ""; };
  $("#confirmar-alocar").onclick = async () => {
    const ids = $$("#painel-alocar input[type=checkbox][value]:checked").map((c) => Number(c.value));
    if (!ids.length) {
      alert("Selecione pelo menos um aplicador.");
      return;
    }
    state.aplicadoresSel = ids;
    const nova = $("#nova-rodada").checked;
    try {
      if ((state.diasMun || []).length) {
        await api(`/api/municipios/${state.municipioId}`, {
          method: "PATCH",
          body: JSON.stringify({
            dias: state.diasMun,
            aplicar_datas_vagas: true,
          }),
        });
      }
      $("#painel-alocar").innerHTML = "";
      await rodarOrganizar(false, { aplicador_ids: ids, nova_rodada: nova });
    } catch (err) {
      alert(err.message);
    }
  };
  $("#painel-alocar").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function rodarOrganizar(reset, extra = {}) {
  const r = await api("/api/quadro/organizar", {
    method: "POST",
    body: JSON.stringify({
      municipio_id: state.municipioId,
      reset,
      aplicador_ids: extra.aplicador_ids || null,
      nova_rodada: !!extra.nova_rodada,
    }),
  });
  const extraTxt = r.ainda_vagas
    ? " As que ficaram laranja (vago) não caberam sem choque: clique nelas e coloque na mão, ou rode outra rodada."
    : "";
  alert(`Alocadas: ${r.alocadas}. Ainda vagas: ${r.ainda_vagas}.${extraTxt}`);
  await pintarQuadro();
}

function isoLocal(dt) {
  const y = dt.getFullYear();
  const m = String(dt.getMonth() + 1).padStart(2, "0");
  const d = String(dt.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function enumerarDias(ini, fim) {
  const a = new Date(`${ini}T00:00:00`);
  const b = new Date(`${fim || ini}T00:00:00`);
  if (Number.isNaN(a.getTime())) return [];
  const start = a <= b ? a : b;
  const end = a <= b ? b : a;
  const out = [];
  const cur = new Date(start);
  while (cur <= end) {
    out.push(isoLocal(cur));
    cur.setDate(cur.getDate() + 1);
  }
  return out;
}

function htmlChipsDias() {
  const dias = state.diasMun || [];
  if (!dias.length) {
    return `<span class="escola-meta">Nenhum dia ainda. Inclua um (ex.: 10/09) e depois outro (ex.: 12/09). Só esses aparecem no quadro.</span>`;
  }
  return dias
    .map((d) => `<button type="button" class="chip-dia" data-dia="${d}">${fmtData(d)} ×</button>`)
    .join("");
}

function pintarChipsDias() {
  const box = $("#dias-chips");
  if (box) box.innerHTML = htmlChipsDias();
  ligarChipsDias();
}

function ligarChipsDias() {
  $$("#dias-chips .chip-dia").forEach((btn) => {
    btn.onclick = () => {
      state.diasMun = (state.diasMun || []).filter((d) => d !== btn.dataset.dia);
      pintarChipsDias();
    };
  });
}

function incluirDiasMun(novos) {
  const set = new Set(state.diasMun || []);
  novos.forEach((d) => { if (d) set.add(d); });
  state.diasMun = [...set].sort();
  pintarChipsDias();
}

function htmlPeriodo(q) {
  state.diasMun = Array.isArray(q.municipio.dias) ? q.municipio.dias.slice() : [];
  return `
    <div class="periodo-box">
      <p style="margin:0 0 8px"><b>Dias da aplicação</b> — pode ser intercalado (10 e 12, sem o 11). Inclua um dia, depois o outro, e salve. Aí você aloca nesses dias.</p>
      <div id="dias-chips" class="dias-chips">${htmlChipsDias()}</div>
      <p class="periodo-acoes">
        <input type="date" id="dia-novo" />
        <button type="button" class="btn sm" id="btn-incluir-dia">Incluir este dia</button>
        <span class="escola-meta">ou faixa seguida:</span>
        <input type="date" id="per-saida" />
        <span>até</span>
        <input type="date" id="per-retorno" />
        <button type="button" class="btn sm ghost" id="btn-incluir-faixa">Incluir faixa</button>
      </p>
      <p class="periodo-acoes">
        <button type="button" class="btn sm" id="btn-salvar-periodo">Salvar dias</button>
        <button type="button" class="btn sm ghost" id="btn-tirar-periodo">Tirar todos os dias</button>
      </p>
    </div>`;
}

async function salvarPeriodoMunicipio(limpar) {
  if (!state.municipioId) return;
  const dias = limpar ? [] : (state.diasMun || []);
  if (!limpar && !dias.length) {
    alert("Inclua pelo menos um dia, ou clique em Tirar todos os dias.");
    return;
  }
  if (limpar && !confirm("Tirar os dias deste município? As colunas saem do quadro e as aplicações voltam para Sem data.")) {
    return;
  }
  await api(`/api/municipios/${state.municipioId}`, {
    method: "PATCH",
    body: JSON.stringify({
      dias,
      limpar_datas_vagas: !!limpar,
    }),
  });
  await pintarQuadro();
}

function ligarPeriodoQuadro() {
  ligarChipsDias();
  $("#btn-incluir-dia")?.addEventListener("click", () => {
    const v = $("#dia-novo")?.value;
    if (!v) {
      alert("Escolha o dia e clique em Incluir este dia.");
      return;
    }
    incluirDiasMun([v]);
    $("#dia-novo").value = "";
  });
  $("#btn-incluir-faixa")?.addEventListener("click", () => {
    const a = $("#per-saida")?.value;
    const b = $("#per-retorno")?.value || a;
    if (!a) {
      alert("Informe o primeiro dia da faixa.");
      return;
    }
    incluirDiasMun(enumerarDias(a, b));
  });
  $("#btn-salvar-periodo")?.addEventListener("click", () => {
    salvarPeriodoMunicipio(false).catch((err) => alert(err.message));
  });
  $("#btn-tirar-periodo")?.addEventListener("click", () => {
    salvarPeriodoMunicipio(true).catch((err) => alert(err.message));
  });
}

async function pintarQuadro() {
  if (!state.municipioId) return;
  const q = await api(`/api/quadro?municipio_id=${state.municipioId}`);
  const periodoHtml = htmlPeriodo(q);
  if (!q.vagas) {
    $("#quadro-corpo").innerHTML = `
      <section class="panel">
        <h2>${tit(q.municipio.nome)}</h2>
        ${periodoHtml}
        <p>Ainda não há aplicações neste município. Cadastre uma escola e depois uma vaga.</p>
        <button class="btn gold" id="btn-vazia-vaga">Nova aplicação</button>
        <button class="btn ghost" id="btn-ir-cadastro">Ir para cadastros</button>
      </section>`;
    $("#btn-vazia-vaga").onclick = () => abrirNovaAplicacao(state.municipioId);
    $("#btn-ir-cadastro").onclick = () => mostrarView("cadastro");
    ligarPeriodoQuadro();
    return;
  }
  const linhas = q.linhas.filter((l) => {
    if (state.filtroRede !== "TODAS" && l.rede !== state.filtroRede) return false;
    if (state.filtroVago) {
      return q.datas.some((d) => (l.celulas[d] || []).some((s) => s.vago));
    }
    if (state.filtroStatus === "APLICADAS") {
      return q.datas.some((d) => (l.celulas[d] || []).some((s) => s.status === "FINALIZADA"));
    }
    if (state.filtroStatus === "PENDENTES") {
      return q.datas.some((d) => (l.celulas[d] || []).some((s) => !s.vago && s.status !== "FINALIZADA"));
    }
    return true;
  });
  const head = q.datas_fmt.map((d) => `<th>${d}</th>`).join("");
  const body = linhas
    .map((l) => {
      const cells = q.datas
        .map((d) => {
          const slots = (l.celulas[d] || [])
            .map((s) => {
              const cls = [
                "slot",
                s.vago ? "vago" : "",
                !s.vago && s.tem_choque ? "choque" : "",
                !s.vago && !s.tem_choque && s.status !== "FINALIZADA" ? "ok" : "",
                s.status === "FINALIZADA" ? "finalizada" : "",
              ].join(" ");
              const chip = s.status === "FINALIZADA"
                ? '<span class="chip aplicada">aplicada</span>'
                : s.vago
                  ? '<span class="chip vago">vago</span>'
                  : s.tem_choque
                    ? '<span class="chip choque">choque</span>'
                    : '<span class="chip ok">alocado</span>';
              return `<button class="${cls}" data-vaga="${s.id}">
                  ${chip}
                  <div class="serie">${s.serie}${s.ordem > 1 ? " · " + s.ordem : ""}</div>
                  ${s.turma ? `<div class="escola-meta">${escHtml(s.turma)}${s.n_alunos ? " · " + s.n_alunos + " alunos" : ""}</div>` : ""}
                  <div class="quem">${s.vago ? "Sem aplicador" : nomeApl(s.aplicador)}</div>
                  ${!s.vago && s.aplicador && s.aplicador.codigo && nomeApl(s.aplicador) !== s.aplicador.codigo
                    ? `<div class="escola-meta">${s.aplicador.codigo}</div>`
                    : ""}
                </button>`;
            })
            .join("");
          return `<td>${slots || "—"}</td>`;
        })
        .join("");
      return `<tr>
        <td class="sticky">
          <b>${tit(l.escola)}</b>
          <div class="escola-meta">${badgeRede(l.rede)} ${l.rural ? "· rural" : ""} · ${l.codigo}</div>
          <div class="turno-tag">${l.turno}</div>
        </td>
        ${cells}
      </tr>`;
    })
    .join("");

  $("#quadro-corpo").innerHTML = `
    <section class="panel" style="margin-bottom:14px">
      <h2>${tit(q.municipio.nome)}</h2>
      ${periodoHtml}
      <p style="margin:8px 0 0;color:var(--ink-soft)">${q.vagas} aplicações · ${q.livres} vagas · ${q.finalizadas || 0} aplicadas · ${q.choques} choques · Salvar dias só abre as colunas; depois use Alocar com o que tem</p>
    </section>
    <div class="grade-wrap">
      <table class="grade">
        <thead><tr><th class="sticky">Escola / turno</th>${head}</tr></thead>
        <tbody>${body || `<tr><td colspan="${q.datas.length + 1}">Nada neste filtro.</td></tr>`}</tbody>
      </table>
    </div>
  `;
  $$("#quadro-corpo [data-vaga]").forEach((btn) => {
    btn.addEventListener("click", () => abrirVaga(Number(btn.dataset.vaga)));
  });
  ligarPeriodoQuadro();
}

function mascaraCpf(v) {
  const d = String(v || "").replace(/\D/g, "").slice(0, 11);
  if (d.length <= 3) return d;
  if (d.length <= 6) return `${d.slice(0, 3)}.${d.slice(3)}`;
  if (d.length <= 9) return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6)}`;
  return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
}

function escHtml(s) {
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function carregarAplicadores() {
  titulo("Aplicadores", "Crie os números do cronograma, aloque no quadro e depois vincule o nome de cada pessoa.");
  const lista = await api("/api/aplicadores");
  const pendentes = lista.filter((a) => !a.identificado).length;
  const linkGeral = `${location.origin}/acesso`;
  const maxN = lista.reduce((m, a) => Math.max(m, Number(a.numero) || 0), 0);
  const opts = lista.length
    ? lista
        .map((a) => {
          const n = a.numero != null ? a.numero : "";
          const quem = a.identificado ? ` — ${a.nome}` : " — sem nome";
          return `<option value="${a.codigo}" data-numero="${n}">${escHtml(a.codigo)}${escHtml(quem)}</option>`;
        })
        .join("")
    : `<option value="" disabled selected>Crie os números primeiro</option>`;
  $("#view-aplicadores").innerHTML = `
    <section class="panel" style="margin-bottom:16px">
      <h2>Criar números de aplicador</h2>
      <p class="escola-meta" style="margin-bottom:12px">
        Informe quantos quer incluir. Se já existem ${maxN}, os próximos começam em ${String(maxN + 1).padStart(2, "0")}.
        Depois você aloca no quadro e associa o nome a cada número.
      </p>
      <form id="form-lote" class="form-grid">
        <label class="campo">Quantidade
          <input name="quantidade" type="number" min="1" max="200" required placeholder="Ex.: 15" />
        </label>
        <button class="btn" type="submit">Gerar aplicadores</button>
      </form>
    </section>
    <section class="panel" style="margin-bottom:16px">
      <h2>Vincular pessoa ao número</h2>
      <p class="escola-meta" style="margin-bottom:12px">${pendentes} número(s) ainda sem nome no cronograma. Depois de vincular, copie o link da pessoa para ela entrar só com o CPF.</p>
      <p class="escola-meta" style="margin-bottom:12px">Link geral (entra com o CPF): <a href="${linkGeral}" target="_blank">${linkGeral}</a></p>
      <form id="form-vincular" class="form-grid">
        <label class="campo">Nome
          <input name="nome" required placeholder="Nome completo" />
        </label>
        <label class="campo">CPF
          <input name="cpf" required placeholder="000.000.000-00" maxlength="14" />
        </label>
        <label class="campo">Número no cronograma
          <select name="codigo" ${lista.length ? "required" : "disabled"}>${opts}</select>
        </label>
        <button class="btn gold" type="submit">Vincular no quadro</button>
      </form>
    </section>
    <div class="toolbar">
      <input type="text" id="busca-apl" placeholder="Buscar por nome, CPF ou número" />
    </div>
    <section class="panel">
      <table class="tabela">
        <thead>
          <tr>
            <th>Nº</th>
            <th>No cronograma</th>
            <th>Nome</th>
            <th>CPF</th>
            <th>Carga</th>
            <th>Acesso</th>
            <th>Ações</th>
          </tr>
        </thead>
        <tbody id="tb-apl"></tbody>
      </table>
    </section>
  `;
  $("#form-lote").onsubmit = async (ev) => {
    ev.preventDefault();
    const qtd = Number(ev.target.quantidade.value);
    if (!qtd || qtd < 1) {
      alert("Informe a quantidade.");
      return;
    }
    try {
      let inicio;
      let fim;
      let quantidade;
      try {
        const r = await api("/api/aplicadores/lote", {
          method: "POST",
          body: JSON.stringify({ quantidade: qtd }),
        });
        inicio = r.inicio;
        fim = r.fim;
        quantidade = r.quantidade;
      } catch (err) {
        const atual = await api("/api/aplicadores");
        const maxN = atual.reduce((m, a) => Math.max(m, Number(a.numero) || 0), 0);
        inicio = maxN + 1;
        fim = maxN + qtd;
        for (let n = inicio; n <= fim; n += 1) {
          const codigo = `Aplicador ${String(n).padStart(2, "0")}`;
          await api("/api/aplicadores", {
            method: "POST",
            body: JSON.stringify({ nome: codigo, codigo, numero: n }),
          });
        }
        quantidade = qtd;
      }
      alert(`Criados Aplicador ${String(inicio).padStart(2, "0")} até Aplicador ${String(fim).padStart(2, "0")} (${quantidade}).`);
      carregarAplicadores();
    } catch (err) {
      alert(err.message);
    }
  };
  const cpfInput = $("#form-vincular [name=cpf]");
  cpfInput.addEventListener("input", () => {
    cpfInput.value = mascaraCpf(cpfInput.value);
  });
  $("#form-vincular").onsubmit = async (ev) => {
    ev.preventDefault();
    const f = ev.target;
    const sel = f.codigo.options[f.codigo.selectedIndex];
    try {
      const r = await api("/api/aplicadores/vincular", {
        method: "POST",
        body: JSON.stringify({
          nome: f.nome.value,
          cpf: f.cpf.value,
          codigo: f.codigo.value,
          numero: sel.dataset.numero ? Number(sel.dataset.numero) : null,
        }),
      });
      alert(
        r.acesso_token
          ? `${r.nome} ficou como ${r.codigo}.\n\nLink de acesso:\n${location.origin}/acesso/${r.acesso_token}`
          : `${r.nome} ficou como ${r.codigo} no quadro.`
      );
      carregarAplicadores();
    } catch (err) {
      alert(err.message);
    }
  };
  const pintar = () => {
    const q = ($("#busca-apl").value || "").toLowerCase();
    const fil = lista.filter((a) =>
      `${a.nome || ""} ${a.codigo} ${a.cpf_fmt || ""} ${a.numero || ""}`.toLowerCase().includes(q)
    );
    $("#tb-apl").innerHTML = fil
      .map((a) => {
        const nomeMostrar = a.identificado ? a.nome : "";
        return `<tr>
          <td><b>${a.numero != null ? String(a.numero).padStart(2, "0") : "—"}</b></td>
          <td>${escHtml(a.codigo)}${a.identificado ? "" : ' <span class="chip vago">sem nome</span>'}</td>
          <td><input class="nome-apl" data-id="${a.id}" value="${escHtml(nomeMostrar)}" placeholder="Nome da pessoa" /></td>
          <td><input class="cpf-apl" data-id="${a.id}" value="${escHtml(a.cpf_fmt || "")}" placeholder="000.000.000-00" maxlength="14" /></td>
          <td>${a.carga} · ${(a.municipios || []).map(tit).join(", ") || "sem escala"}</td>
          <td>${
            a.acesso_token
              ? `<button class="btn sm ghost" data-link="${escHtml(a.acesso_token)}">Copiar link</button>`
              : "<span class='escola-meta'>Cadastre o CPF</span>"
          }</td>
          <td style="white-space:nowrap">
            <button class="btn sm" data-salvar="${a.id}">Salvar</button>
            <button class="btn sm warn" data-excluir="${a.id}" data-nome="${escHtml(a.identificado ? a.nome : a.codigo)}" data-carga="${a.carga}">Excluir</button>
          </td>
        </tr>`;
      })
      .join("");
    $$(".cpf-apl").forEach((inp) => {
      inp.addEventListener("input", () => {
        inp.value = mascaraCpf(inp.value);
      });
    });
    $$("[data-link]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const url = `${location.origin}/acesso/${btn.dataset.link}`;
        try {
          await navigator.clipboard.writeText(url);
          btn.textContent = "Copiado";
          setTimeout(() => {
            btn.textContent = "Copiar link";
          }, 1500);
        } catch (_) {
          prompt("Copie o link de acesso:", url);
        }
      });
    });
    $$("[data-salvar]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.salvar;
        const nome = $(`.nome-apl[data-id="${id}"]`).value;
        const cpf = $(`.cpf-apl[data-id="${id}"]`).value;
        if (!nome) {
          alert("Informe o nome.");
          return;
        }
        try {
          await api(`/api/aplicadores/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ nome, cpf }),
          });
          carregarAplicadores();
        } catch (err) {
          alert(err.message);
        }
      });
    });
    $$("[data-excluir]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.excluir;
        const nome = btn.dataset.nome || "este aplicador";
        const carga = Number(btn.dataset.carga) || 0;
        const aviso = carga
          ? `${nome} está em ${carga} turma(s). Elas voltam sem aplicador (a data da escola permanece). Excluir mesmo?`
          : `Excluir ${nome}? Esse número some da lista.`;
        if (!confirm(aviso)) return;
        try {
          await api(`/api/aplicadores/${id}`, { method: "DELETE" });
          carregarAplicadores();
        } catch (err) {
          alert(err.message);
        }
      });
    });
  };
  $("#busca-apl").addEventListener("input", pintar);
  pintar();
}

async function carregarEscolas() {
  titulo("Escolas", "Rede municipal, estadual e conveniada na SRE Gurupi.");
  const lista = await api("/api/escolas");
  $("#view-escolas").innerHTML = `
    <div class="toolbar">
      <button class="btn" id="btn-nova-escola">Nova escola</button>
    </div>
    <section class="panel">
      <table class="tabela">
        <thead><tr><th>Escola</th><th>Município</th><th>Rede</th><th>Vagas</th><th>Livres</th><th></th></tr></thead>
        <tbody>
          ${lista
            .map(
              (e) => `<tr>
                <td><b>${tit(e.nome)}</b><div class="escola-meta">${e.codigo}${e.rural ? " · rural" : ""}</div></td>
                <td>${tit(e.municipio)}</td>
                <td>${badgeRede(e.rede)}</td>
                <td>${e.vagas}</td>
                <td>${e.livres}</td>
                <td><button class="btn warn sm" data-del-esc="${e.id}">Excluir</button></td>
              </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </section>
  `;
  $("#btn-nova-escola").onclick = () => {
    mostrarView("cadastro", { tab: "escolas" });
  };
  $$("[data-del-esc]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("Excluir esta escola?")) return;
      try {
        await api(`/api/escolas/${btn.dataset.delEsc}`, { method: "DELETE" });
        carregarEscolas();
      } catch (err) {
        alert(err.message);
      }
    });
  });
}

async function abrirNovaAplicacao(municipioId) {
  const [opcoes, escolas] = await Promise.all([
    api("/api/opcoes"),
    api(municipioId ? `/api/escolas?municipio_id=${municipioId}` : "/api/escolas"),
  ]);
  if (!escolas.length) {
    alert("Cadastre uma escola neste município antes de criar a aplicação.");
    mostrarView("cadastro", { tab: "escolas" });
    return;
  }
  $("#drawer-kicker").textContent = "Demanda";
  $("#drawer-titulo").textContent = "Nova aplicação";
  $("#drawer-corpo").innerHTML = `
    <form id="form-nova-vaga" class="form-grid" style="grid-template-columns:1fr">
      <label class="campo">Escola
        <select name="escola_id">${escolas.map((e) => `<option value="${e.id}">${tit(e.nome)}</option>`).join("")}</select>
      </label>
      <label class="campo">Série
        <select name="serie">${opcoes.series.map((s) => `<option>${s}</option>`).join("")}</select>
      </label>
      <label class="campo">Turno
        <select name="turno">${opcoes.turnos.map((t) => `<option>${t}</option>`).join("")}</select>
      </label>
      <label class="campo">Data
        <input type="date" name="data" required />
      </label>
      <label class="campo">Quantas turmas / salas
        <input type="number" name="quantidade" min="1" value="1" />
      </label>
      <label class="check-inline"><input type="checkbox" name="criar_par" checked /> Se for 2º ano Dia 1, criar também o Dia 2 no dia seguinte</label>
      <button class="btn gold" type="submit">Criar vaga</button>
    </form>
  `;
  $("#drawer").classList.remove("hidden");
  $("#drawer-fundo").classList.remove("hidden");
  $("#form-nova-vaga").onsubmit = async (ev) => {
    ev.preventDefault();
    const f = ev.target;
    try {
      await api("/api/vagas", {
        method: "POST",
        body: JSON.stringify({
          escola_id: Number(f.escola_id.value),
          serie: f.serie.value,
          turno: f.turno.value,
          data: f.data.value,
          quantidade: Number(f.quantidade.value || 1),
          criar_par: f.criar_par.checked,
        }),
      });
      fecharDrawer();
      mostrarView("quadro");
    } catch (err) {
      alert(err.message);
    }
  };
}

async function carregarCadastro() {
  titulo("Cadastros", "Inclua município, escola, aplicador e vaga de aplicação. Pode começar do zero, sem planilha.");
  const [opcoes, municipios, escolas] = await Promise.all([
    api("/api/opcoes"),
    api("/api/municipios"),
    api("/api/escolas"),
  ]);
  const tabs = [
    ["municipios", "Municípios"],
    ["escolas", "Escolas"],
    ["vagas", "Aplicações"],
  ];
  $("#view-cadastro").innerHTML = `
    <section class="panel" style="margin-bottom:16px">
      <h2>Começar do zero</h2>
      <p style="margin:0 0 12px;color:var(--ink-soft)">Apaga municípios, escolas, aplicadores e vagas. Depois você cadastra tudo na mão. A planilha só volta se você clicar em Enviar planilha.</p>
      <button type="button" class="btn warn" id="btn-zerar">Zerar e cadastrar na mão</button>
    </section>
    <div class="tabs">
      ${tabs.map(([id, nome]) => `<button class="tab ${state.cadastroTab === id ? "ativo" : ""}" data-tab="${id}">${nome}</button>`).join("")}
    </div>
    <div id="cadastro-corpo"></div>
  `;
  $("#btn-zerar").onclick = async () => {
    if (!confirm("Apagar TODO o cadastro (municípios, escolas, aplicadores e vagas)?")) return;
    if (!confirm("Isso não tem volta neste sistema. Quer mesmo começar do zero?")) return;
    try {
      await api("/api/zerar", { method: "POST", body: "{}" });
      alert("Cadastro zerado. Agora use esta tela para incluir município, escola, aplicador e vagas.");
      carregarCadastro();
    } catch (err) {
      alert(err.message);
    }
  };
  $$("#view-cadastro .tab").forEach((btn) => {
    btn.onclick = () => {
      state.cadastroTab = btn.dataset.tab;
      carregarCadastro();
    };
  });
  const corpo = $("#cadastro-corpo");
  if (state.cadastroTab === "municipios") {
    corpo.innerHTML = `
      <section class="panel">
        <h2>Novo município</h2>
        <form id="form-mun" class="form-grid">
          <label class="campo">Nome <input name="nome" required placeholder="Ex.: Gurupi" /></label>
          <label class="campo">Saída da equipe <input type="date" name="data_saida" /></label>
          <label class="campo">Retorno <input type="date" name="data_retorno" /></label>
          <button class="btn" type="submit">Cadastrar</button>
        </form>
      </section>
      <section class="panel" style="margin-top:16px">
        <h2>Municípios cadastrados</h2>
        <table class="tabela">
          <thead><tr><th>Município</th><th>Viagem</th><th>Aplicações</th><th>Livres</th><th></th></tr></thead>
          <tbody>
            ${municipios.map((m) => {
              const editando = String(state.editMunId) === String(m.id);
              if (editando) {
                return `<tr>
              <td colspan="5">
                <form class="form-grid" data-save-mun="${m.id}">
                  <label class="campo">Nome <input name="nome" required value="${escHtml(tit(m.nome))}" /></label>
                  <label class="campo">Início <input type="date" name="data_saida" value="${m.data_saida || ""}" /></label>
                  <label class="campo">Fim <input type="date" name="data_retorno" value="${m.data_retorno || ""}" /></label>
                  <button class="btn" type="submit">Salvar</button>
                  <button class="btn ghost" type="button" data-limpar-per="${m.id}">Tirar período</button>
                  <button class="btn ghost" type="button" data-cancel-edit>Cancelar</button>
                </form>
              </td>
            </tr>`;
              }
              return `<tr>
              <td><b>${tit(m.nome)}</b></td>
              <td>${(m.dias && m.dias.length) ? m.dias.map(fmtData).join(", ") : (m.data_saida ? fmtData(m.data_saida) + " → " + fmtData(m.data_retorno) : "—")}</td>
              <td>${m.vagas}</td>
              <td>${m.livres}</td>
              <td>
                <button class="btn sm ghost" data-edit-mun="${m.id}">Editar</button>
                <button class="btn sm warn" data-del-mun="${m.id}">Excluir</button>
              </td>
            </tr>`;
            }).join("")}
          </tbody>
        </table>
      </section>`;
    $("#form-mun").onsubmit = async (ev) => {
      ev.preventDefault();
      const f = ev.target;
      try {
        await api("/api/municipios", {
          method: "POST",
          body: JSON.stringify({
            nome: f.nome.value,
            data_saida: f.data_saida.value || null,
            data_retorno: f.data_retorno.value || null,
          }),
        });
        carregarCadastro();
      } catch (err) { alert(err.message); }
    };
    $$("[data-del-mun]").forEach((btn) => {
      btn.onclick = async () => {
        if (!confirm("Excluir este município?")) return;
        try {
          await api(`/api/municipios/${btn.dataset.delMun}`, { method: "DELETE" });
          carregarCadastro();
        } catch (err) { alert(err.message); }
      };
    });
    $$("[data-edit-mun]").forEach((btn) => {
      btn.onclick = () => {
        state.editMunId = Number(btn.dataset.editMun);
        carregarCadastro();
      };
    });
    $$("[data-cancel-edit]").forEach((btn) => {
      btn.onclick = () => {
        state.editMunId = null;
        carregarCadastro();
      };
    });
    $$("[data-limpar-per]").forEach((btn) => {
      btn.onclick = async () => {
        if (!confirm("Tirar o período deste município? No quadro as aplicações voltam para Sem data.")) return;
        try {
          await api(`/api/municipios/${btn.dataset.limparPer}`, {
            method: "PATCH",
            body: JSON.stringify({
              data_saida: null,
              data_retorno: null,
              limpar_datas_vagas: true,
            }),
          });
          state.editMunId = null;
          carregarCadastro();
        } catch (err) { alert(err.message); }
      };
    });
    $$("[data-save-mun]").forEach((form) => {
      form.onsubmit = async (ev) => {
        ev.preventDefault();
        const f = ev.target;
        try {
          await api(`/api/municipios/${form.dataset.saveMun}`, {
            method: "PATCH",
            body: JSON.stringify({
              nome: f.nome.value,
              data_saida: f.data_saida.value || null,
              data_retorno: f.data_retorno.value || f.data_saida.value || null,
            }),
          });
          state.editMunId = null;
          carregarCadastro();
        } catch (err) { alert(err.message); }
      };
    });
  }
  if (state.cadastroTab === "escolas") {
    corpo.innerHTML = `
      <section class="panel">
        <h2>Nova escola</h2>
        <form id="form-esc" class="form-grid">
          <label class="campo">Município
            <select name="municipio_id">${municipios.map((m) => `<option value="${m.id}">${tit(m.nome)}</option>`).join("")}</select>
          </label>
          <label class="campo">Nome <input name="nome" required placeholder="Nome da escola" /></label>
          <label class="campo">Código INEP <input name="codigo" placeholder="Opcional" /></label>
          <label class="campo">Rede
            <select name="rede">${opcoes.redes.map((r) => `<option>${r}</option>`).join("")}</select>
          </label>
          <label class="check-inline"><input type="checkbox" name="rural" /> Escola rural</label>
          <button class="btn" type="submit">Cadastrar</button>
        </form>
      </section>
      <section class="panel" style="margin-top:16px">
        <h2>Escolas</h2>
        <table class="tabela">
          <thead><tr><th>Escola</th><th>Município</th><th>Rede</th><th>Vagas</th><th></th></tr></thead>
          <tbody>
            ${escolas.map((e) => `<tr>
              <td><b>${tit(e.nome)}</b><div class="escola-meta">${e.codigo}${e.rural ? " · rural" : ""}</div></td>
              <td>${tit(e.municipio)}</td>
              <td>${badgeRede(e.rede)}</td>
              <td>${e.vagas}</td>
              <td><button class="btn sm warn" data-del-esc="${e.id}">Excluir</button></td>
            </tr>`).join("")}
          </tbody>
        </table>
      </section>`;
    $("#form-esc").onsubmit = async (ev) => {
      ev.preventDefault();
      const f = ev.target;
      try {
        await api("/api/escolas", {
          method: "POST",
          body: JSON.stringify({
            municipio_id: Number(f.municipio_id.value),
            nome: f.nome.value,
            codigo: f.codigo.value || null,
            rede: f.rede.value,
            rural: f.rural.checked,
          }),
        });
        carregarCadastro();
      } catch (err) { alert(err.message); }
    };
    $$("#cadastro-corpo [data-del-esc]").forEach((btn) => {
      btn.onclick = async () => {
        if (!confirm("Excluir esta escola?")) return;
        try {
          await api(`/api/escolas/${btn.dataset.delEsc}`, { method: "DELETE" });
          carregarCadastro();
        } catch (err) { alert(err.message); }
      };
    });
  }
  if (state.cadastroTab === "vagas") {
    corpo.innerHTML = `
      <section class="panel">
        <h2>Nova vaga de aplicação</h2>
        <p>Cria a demanda no quadro (fica vaga até você alocar alguém).</p>
        <form id="form-vaga" class="form-grid">
          <label class="campo">Município
            <select id="vaga-mun">${municipios.map((m) => `<option value="${m.id}">${tit(m.nome)}</option>`).join("")}</select>
          </label>
          <label class="campo">Escola <select name="escola_id" id="vaga-esc"></select></label>
          <label class="campo">Série
            <select name="serie">${opcoes.series.map((s) => `<option>${s}</option>`).join("")}</select>
          </label>
          <label class="campo">Turno
            <select name="turno">${opcoes.turnos.map((t) => `<option>${t}</option>`).join("")}</select>
          </label>
          <label class="campo">Data <input type="date" name="data" required /></label>
          <label class="campo">Turmas / salas <input type="number" name="quantidade" min="1" value="1" /></label>
          <label class="check-inline"><input type="checkbox" name="criar_par" checked /> Criar Dia 2 do 2º ano no dia seguinte</label>
          <button class="btn gold" type="submit">Criar vaga</button>
        </form>
      </section>`;
    const selMun = $("#vaga-mun");
    const selEsc = $("#vaga-esc");
    const preencherEscolas = () => {
      const mid = Number(selMun.value);
      const lista = escolas.filter((e) => e.municipio_id === mid);
      selEsc.innerHTML = lista.length
        ? lista.map((e) => `<option value="${e.id}">${tit(e.nome)}</option>`).join("")
        : `<option value="">Nenhuma escola neste município</option>`;
    };
    selMun.onchange = preencherEscolas;
    preencherEscolas();
    $("#form-vaga").onsubmit = async (ev) => {
      ev.preventDefault();
      const f = ev.target;
      if (!f.escola_id.value) {
        alert("Cadastre uma escola neste município primeiro.");
        return;
      }
      try {
        await api("/api/vagas", {
          method: "POST",
          body: JSON.stringify({
            escola_id: Number(f.escola_id.value),
            serie: f.serie.value,
            turno: f.turno.value,
            data: f.data.value,
            quantidade: Number(f.quantidade.value || 1),
            criar_par: f.criar_par.checked,
          }),
        });
        alert("Vaga criada. Ela aparece no quadro como vaga livre.");
        state.municipioId = Number(selMun.value);
        mostrarView("quadro");
      } catch (err) { alert(err.message); }
    };
  }
}

mostrarView("resumo");
