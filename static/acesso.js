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

async function carregarPainel() {
  const dados = await req("/api/acesso/eu");
  login.classList.add("hidden");
  painel.classList.remove("hidden");
  document.getElementById("nome-apl").textContent = dados.aplicador.nome;
  document.getElementById("codigo-apl").textContent = dados.aplicador.codigo || "";
  document.getElementById("cpf-apl").textContent = dados.aplicador.cpf_fmt || "";
  const box = document.getElementById("lista-apps");
  if (!dados.aplicacoes.length) {
    box.innerHTML = "<p class='vazio'>Nenhuma aplicação atribuída a você ainda.</p>";
    return;
  }
  box.innerHTML = dados.aplicacoes
    .map((a) => {
      const viagem = a.saida_fmt && a.saida_fmt !== "—"
        ? `Saída ${a.saida_fmt} · retorno ${a.retorno_fmt}`
        : "";
      return `<article class="app ${a.finalizada ? "feita" : ""}">
        <span class="chip ${a.finalizada ? "ok" : ""}">${a.finalizada ? "Finalizada" : "Prevista"}</span>
        <b>${tit(a.escola)}</b>
        <div class="meta">
          ${tit(a.municipio)} · ${a.data_fmt} · ${a.turno}<br />
          <b>${a.serie}${a.turma ? " — " + a.turma : ""}${a.n_alunos ? " · " + a.n_alunos + " alunos" : ""}</b>
          ${a.rede ? "<br />" + a.rede.toLowerCase() : ""}
          ${viagem ? "<br />" + viagem : ""}
        </div>
        <button type="button" data-id="${a.id}" data-feita="${a.finalizada ? "1" : "0"}">
          ${a.finalizada ? "Reabrir" : "Marcar como aplicada"}
        </button>
      </article>`;
    })
    .join("");
  box.querySelectorAll("button[data-id]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const feita = btn.dataset.feita === "1";
      await req(`/api/acesso/vagas/${btn.dataset.id}/finalizar`, {
        method: "POST",
        body: JSON.stringify({ finalizada: !feita }),
      });
      await carregarPainel();
    });
  });
}

req("/api/acesso/eu")
  .then(() => carregarPainel())
  .catch(() => {
    login.classList.remove("hidden");
    painel.classList.add("hidden");
  });
