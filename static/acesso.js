const tokenLink = decodeURIComponent(location.pathname.replace(/^\/acesso\/?/, "")) || null;

function mascaraCpf(v) {
  const d = String(v || "").replace(/\D/g, "").slice(0, 11);
  if (d.length <= 3) return d;
  if (d.length <= 6) return `${d.slice(0, 3)}.${d.slice(3)}`;
  if (d.length <= 9) return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6)}`;
  return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
}

async function req(path, options = {}) {
  const res = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data.detail || data.erro || "Não foi possível concluir.";
    const err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    err.status = res.status;
    throw err;
  }
  return data;
}

const login = document.getElementById("tela-login");
const painel = document.getElementById("tela-painel");
const erro = document.getElementById("erro-login");
const cpf = document.getElementById("cpf");

cpf.addEventListener("input", () => {
  cpf.value = mascaraCpf(cpf.value);
});

document.getElementById("form-login").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  erro.classList.add("hidden");
  try {
    await req("/api/acesso/entrar", {
      method: "POST",
      body: JSON.stringify({ cpf: cpf.value, token_link: tokenLink || null }),
    });
    await carregarPainel();
  } catch (e) {
    erro.textContent = e.message;
    erro.classList.remove("hidden");
  }
});

document.getElementById("btn-sair").addEventListener("click", async () => {
  await req("/api/acesso/sair", { method: "POST", body: "{}" });
  login.classList.remove("hidden");
  painel.classList.add("hidden");
});

function tit(s) {
  if (!s) return "";
  const mini = new Set(["do", "da", "de", "dos", "das", "e"]);
  return String(s)
    .toLowerCase()
    .split(" ")
    .map((w, i) => (i > 0 && mini.has(w) ? w : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(" ");
}

let vagaPresentes = null;

function fecharDlgPresentes() {
  vagaPresentes = null;
  document.getElementById("dlg-presentes").classList.add("hidden");
}

function abrirDlgPresentes(a) {
  vagaPresentes = a;
  document.getElementById("dlg-presentes-escola").textContent =
    `${tit(a.escola)} · ${a.serie}${a.turma ? " — " + a.turma : ""}`;
  document.getElementById("dlg-presentes-total").textContent =
    a.n_alunos != null && a.n_alunos !== "" ? String(a.n_alunos) : "não informado";
  const inp = document.getElementById("dlg-presentes-n");
  inp.value = a.n_alunos != null && a.n_alunos !== "" ? String(a.n_alunos) : "";
  inp.max = a.n_alunos != null && a.n_alunos !== "" ? String(a.n_alunos) : "";
  document.getElementById("dlg-presentes-erro").classList.add("hidden");
  document.getElementById("dlg-presentes").classList.remove("hidden");
  inp.focus();
  inp.select();
}

document.getElementById("dlg-presentes-cancelar").addEventListener("click", fecharDlgPresentes);
document.getElementById("dlg-presentes-x").addEventListener("click", fecharDlgPresentes);
document.getElementById("form-presentes").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  if (!vagaPresentes) return;
  const erro = document.getElementById("dlg-presentes-erro");
  const n = Number(document.getElementById("dlg-presentes-n").value);
  if (!Number.isInteger(n) || n < 0) {
    erro.textContent = "Informe um número inteiro de presentes.";
    erro.classList.remove("hidden");
    return;
  }
  const total = vagaPresentes.n_alunos;
  if (total != null && total !== "" && n > Number(total)) {
    erro.textContent = `Presentes não pode ser maior que o total (${total}).`;
    erro.classList.remove("hidden");
    return;
  }
  try {
    await req(`/api/acesso/vagas/${vagaPresentes.id}/finalizar`, {
      method: "POST",
      body: JSON.stringify({ finalizada: true, n_presentes: n }),
    });
    fecharDlgPresentes();
    await carregarPainel();
  } catch (e) {
    erro.textContent = e.message;
    erro.classList.remove("hidden");
  }
});

let abaAtual = "aplicar";

async function carregarPainel() {
  const dados = await req("/api/acesso/eu");
  login.classList.add("hidden");
  painel.classList.remove("hidden");
  document.getElementById("nome-apl").textContent = dados.aplicador.nome;
  document.getElementById("codigo-apl").textContent = dados.aplicador.codigo || "";
  document.getElementById("cpf-apl").textContent = dados.aplicador.cpf_fmt || "";
  const box = document.getElementById("lista-apps");
  const aplicacoes = dados.aplicacoes || [];
  const extras = dados.extras || [];
  if (aplicacoes.length && extras.length) {
    document.getElementById("codigo-apl").textContent =
      `${dados.aplicador.codigo || ""} · aplicador e extra`;
  }
  if (!aplicacoes.length && !extras.length) {
    box.innerHTML = "<p class='vazio'>Nenhuma aplicação ou extra atribuído a você ainda.</p>";
    return;
  }
  if (abaAtual === "aplicar" && !aplicacoes.length) abaAtual = "extra";
  if (abaAtual === "extra" && !extras.length && aplicacoes.length) abaAtual = "aplicar";
  const nPend = aplicacoes.filter((a) => !a.finalizada).length;
  const nFim = aplicacoes.length - nPend;
  const htmlTitular = aplicacoes.length
    ? `<p class="resumo-lista">${aplicacoes.length} aplicação(ões) · ${nPend} prevista(s) · ${nFim} finalizada(s)</p>` +
      aplicacoes
        .map((a) => {
          const viagem = a.saida_fmt && a.saida_fmt !== "—"
            ? `Saída ${a.saida_fmt} · retorno ${a.retorno_fmt}`
            : "";
          const total = a.n_alunos != null && a.n_alunos !== ""
            ? `Total de estudantes: ${a.n_alunos}`
            : "Total de estudantes: não informado";
          const presentes = a.finalizada
            ? (a.n_presentes != null
              ? `Presentes: ${a.n_presentes}${a.n_alunos != null ? " de " + a.n_alunos : ""}`
              : "Presentes: ainda não informado")
            : "";
          return `<article class="app ${a.finalizada ? "feita" : ""}">
        <span class="chip ${a.finalizada ? "ok" : ""}">${a.finalizada ? "Finalizada" : "Prevista"}</span>
        <span class="chip ${a.prova_recebida ? "ok" : ""}">${a.prova_recebida ? "Prova: recebida" : "Prova: pendente"}</span>
        <b>${tit(a.escola)}</b>
        <div class="meta">
          ${tit(a.municipio)} · ${a.data_fmt} · ${a.turno}<br />
          <b>${a.serie}${a.turma ? " — " + a.turma : ""}</b>
          ${a.rede ? "<br />" + a.rede.toLowerCase() : ""}
          ${viagem ? "<br />" + viagem : ""}
          <br /><b>${total}</b>
          ${presentes ? "<br /><b>" + presentes + "</b>" : ""}
          ${!a.prova_recebida && !a.finalizada ? "<br />Aguarde a SRE marcar o recebimento da prova." : ""}
        </div>
        <button type="button" data-id="${a.id}" data-feita="${a.finalizada ? "1" : "0"}" ${!a.prova_recebida && !a.finalizada ? "disabled" : ""}>
          ${a.finalizada ? "Reabrir" : "Marcar como aplicada"}
        </button>
      </article>`;
        })
        .join("")
    : "<p class='vazio'>Você não aplica em nenhuma turma. Extra fica na outra aba.</p>";
  const htmlExtras = extras.length
    ? `<p class="resumo-lista">${extras.length} turma(s) · acompanhar aluno especial. Sem baixa e sem recebimento de prova.</p>` +
      extras
        .map((a) => {
          const titular = a.titular
            ? `Pegue a prova específica no bloco de ${a.titular.nome}${a.titular.codigo ? " · " + a.titular.codigo : ""}.`
            : "A turma ainda não tem aplicador titular. A prova sai do bloco dele quando for alocado.";
          return `<article class="app extra">
        <span class="chip extra">Extra · ciência</span>
        <b>${tit(a.escola)}</b>
        <div class="meta">
          ${tit(a.municipio)} · ${a.data_fmt} · ${a.turno}<br />
          <b>${a.serie}${a.turma ? " — " + a.turma : ""}</b>
          ${a.rede ? "<br />" + a.rede.toLowerCase() : ""}
          <br />${titular}
          <br />Aqui você só vê a agenda. Quem aplica e dá baixa é o titular da turma.
        </div>
      </article>`;
        })
        .join("")
    : "<p class='vazio'>Nenhuma turma como extra. O que você aplica fica na outra aba.</p>";
  box.innerHTML = `
    <div class="abas" role="tablist">
      <button type="button" class="aba ${abaAtual === "aplicar" ? "ativo" : ""}" data-aba="aplicar">
        Aplicações (${aplicacoes.length})
      </button>
      <button type="button" class="aba ${abaAtual === "extra" ? "ativo" : ""}" data-aba="extra">
        Extra (${extras.length})
      </button>
    </div>
    <div id="aba-aplicar" class="aba-corpo ${abaAtual === "aplicar" ? "" : "hidden"}">${htmlTitular}</div>
    <div id="aba-extra" class="aba-corpo extra-papel ${abaAtual === "extra" ? "" : "hidden"}">${htmlExtras}</div>
  `;
  box.querySelectorAll(".aba").forEach((btn) => {
    btn.addEventListener("click", () => {
      abaAtual = btn.dataset.aba;
      box.querySelectorAll(".aba").forEach((b) => b.classList.toggle("ativo", b === btn));
      document.getElementById("aba-aplicar").classList.toggle("hidden", abaAtual !== "aplicar");
      document.getElementById("aba-extra").classList.toggle("hidden", abaAtual !== "extra");
    });
  });
  box.querySelectorAll("button[data-id]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const feita = btn.dataset.feita === "1";
      if (feita) {
        if (!confirm("Reabrir esta aplicação? Os presentes informados serão apagados.")) return;
        await req(`/api/acesso/vagas/${btn.dataset.id}/finalizar`, {
          method: "POST",
          body: JSON.stringify({ finalizada: false }),
        });
        await carregarPainel();
        return;
      }
      const app = aplicacoes.find((x) => String(x.id) === String(btn.dataset.id));
      if (app) abrirDlgPresentes(app);
    });
  });
}

function tickRelogio() {
  const el = document.getElementById("relogio");
  if (!el) return;
  el.textContent = new Date().toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}
tickRelogio();
setInterval(tickRelogio, 10000);

req("/api/acesso/eu")
  .then(() => carregarPainel())
  .catch(() => {
    login.classList.remove("hidden");
    painel.classList.add("hidden");
  });
