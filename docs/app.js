(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : "#");
  const fmt = (n) => Number(n || 0).toLocaleString("en-US");
  const SOURCE_LABELS = { youtube: "YouTube", bluesky: "Bluesky", stackexchange: "Stack Exchange", sheet: "Sheet", reddit: "Reddit" };

  // Repo owner/name from the Pages URL (owner.github.io/repo), with fallbacks.
  const host = location.hostname;
  const OWNER = host.endsWith(".github.io") ? host.split(".")[0] : "rich-shrestha";
  const REPO = (host.endsWith(".github.io") && location.pathname.split("/")[1]) || "nyc-insights";
  const GH = `https://github.com/${OWNER}/${REPO}`;

  // Locally remembered "used" taps (until the bot rebuilds the site). Best-effort only.
  const store = {
    get() { try { return JSON.parse(localStorage.getItem("nyci-used") || "[]"); } catch { return []; } },
    add(id) { try { const s = new Set(this.get()); s.add(id); localStorage.setItem("nyci-used", JSON.stringify([...s])); } catch {} },
  };

  let DATA = null, BY_ID = {}, shown = 30;

  const datasetUrl = (d) => {
    if (!d.socrata_id) return "https://citibikenyc.com/system-data";
    return `https://${d.domain}/d/${d.socrata_id}`;
  };

  const meter = (label, v) => `
    <div class="meter"><span>${label}</span>
      <div class="track" title="${label}: ${v.toFixed(1)} / 10"><div class="fill" style="width:${Math.max(2, v * 10)}%"></div></div>
      <b>${v.toFixed(1)}</b></div>`;

  const usedIssueUrl = (c) => {
    const title = `used: ${c.id}`;
    const body = `Mark this cluster as used (video made).\n\nQuestion: ${c.question}\n\n_The bot adds it to config/used.yml and rebuilds the site._`;
    return `${GH}/issues/new?title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`;
  };

  const isUsed = (c) => c.used || store.get().includes(c.id);

  function card(c, { rank = null, compact = false } = {}) {
    const s = c.scores;
    const used = isUsed(c);
    const sources = c.sources.map((x) => SOURCE_LABELS[x] || x).join(", ");
    const ds = (c.datasets || []).map((d) => `
      <p class="ds-item"><a href="${datasetUrl(d)}" target="_blank" rel="noopener">${esc(d.name)}</a>
      ${d.socrata_id ? `<code>${esc(d.socrata_id)}</code>` : ""}
      <small>${esc(d.answers)}</small></p>`).join("");
    const examples = c.members.slice(0, compact ? 8 : 5).map((m) => `
      <li><a href="${esc(safeUrl(m.link))}" target="_blank" rel="noopener nofollow">${esc(m.question)}</a>
      <div class="meta">${esc(SOURCE_LABELS[m.source] || m.source)}${m.origin ? " · " + esc(m.origin) : ""} · ${esc(m.date)} · ${fmt(m.engagement)} engagement</div></li>`).join("");
    return `
    <li class="card" id="c-${esc(c.id)}">
      <div class="card-head">
        ${rank ? `<div class="rank">${rank}</div>` : ""}
        <div style="min-width:0;flex:1">
          <p class="q">${esc(c.question)}</p>
          <div class="chips">
            <span class="chip">${esc(c.theme)}</span>
            <span class="chip">${c.count}× asked</span>
            <span class="chip">${esc(sources)}</span>
            <span class="chip">latest ${esc(c.latest_date)}</span>
            ${used ? `<span class="chip used">used</span>` : ""}
          </div>
        </div>
        <div class="score"><b>${s.content.toFixed(1)}</b><span>score</span></div>
      </div>
      <p class="why">${esc(c.why)}</p>
      ${compact ? "" : `<div class="meters">${meter("Demand", s.demand)}${meter("Answerability", s.answerability)}${meter("Freshness", s.freshness)}</div>`}
      ${!compact && ds ? `<div class="ds">${ds}</div>` : ""}
      <details ${compact ? "" : ""}><summary>${compact ? "Details & " : ""}${c.members.length} example question${c.members.length === 1 ? "" : "s"}</summary>
        ${compact ? `<div class="meters">${meter("Demand", s.demand)}${meter("Answerability", s.answerability)}${meter("Freshness", s.freshness)}</div>${ds ? `<div class="ds">${ds}</div>` : ""}` : ""}
        <ul class="examples">${examples}</ul></details>
      <div class="actions">
        ${used ? `<span class="btn done">✓ Used</span>` : `<a class="btn mark-used" data-id="${esc(c.id)}" href="${usedIssueUrl(c)}" target="_blank" rel="noopener">Mark used</a>`}
        <span class="chip" style="align-self:center">id ${esc(c.id)}</span>
      </div>
    </li>`;
  }

  function renderTop() {
    const local = store.get();
    let top = DATA.top.map((id) => BY_ID[id]).filter((c) => c && !local.includes(c.id));
    if (top.length < DATA.top.length) { // backfill locally-hidden slots
      const extra = DATA.clusters.filter((c) => !isUsed(c) && !top.includes(c));
      top = top.concat(extra.slice(0, DATA.top.length - top.length));
    }
    $("#top-list").innerHTML = top.length ? top.map((c, i) => card(c, { rank: i + 1 })).join("")
      : `<li class="empty">No questions yet. Run the workflow to collect some.</li>`;
  }

  function renderAll() {
    const q = $("#q").value.trim().toLowerCase();
    const theme = $("#f-theme").value, source = $("#f-source").value, sort = $("#sort").value;
    const showUsed = $("#f-used").checked;
    let list = DATA.clusters.filter((c) =>
      (showUsed || !isUsed(c)) && (!theme || c.theme === theme) && (!source || c.sources.includes(source)) &&
      (!q || c.question.toLowerCase().includes(q) || c.members.some((m) => m.question.toLowerCase().includes(q))));
    const key = { content: (c) => c.scores.content, demand: (c) => c.scores.demand, recent: (c) => c.latest_date }[sort];
    list.sort((a, b) => (key(b) > key(a) ? 1 : key(b) < key(a) ? -1 : 0));
    $("#all-count").textContent = `${fmt(list.length)} question cluster${list.length === 1 ? "" : "s"}`;
    $("#all-list").innerHTML = list.slice(0, shown).map((c) => card(c, { compact: true })).join("") || `<li class="empty">No matches.</li>`;
    $("#more").hidden = list.length <= shown;
  }

  function render311(S) {
    const sel = $("#hood");
    const opts = [`<option value="__city">Citywide</option>`].concat(
      S.neighborhoods.map((h) => `<option value="${esc(h.id)}">${esc(h.borough)} · ${esc(h.name)}</option>`));
    sel.innerHTML = opts.join("");
    $("#c311-lede").textContent = `${fmt(S.total_requests)} 311 requests from ${S.period.start} to ${S.period.end}. Pick a neighborhood (community district) to see what people there call about most.`;
    const draw = () => {
      const id = sel.value;
      const h = S.neighborhoods.find((x) => x.id === id);
      const rows = h ? h.top : S.citywide_top.slice(0, 10);
      const total = h ? h.total : S.total_requests;
      const max = Math.max(...rows.map((r) => r.count), 1);
      $("#c311-title").textContent = h ? `Top complaints · ${h.name} (${fmt(total)} requests)` : "Top complaints · citywide";
      const chart = $("#c311-chart");
      chart.setAttribute("aria-label", rows.map((r) => `${r.type}: ${r.count}`).join("; "));
      chart.innerHTML = rows.map((r) => `
        <div class="bar-row" tabindex="0">
          <div class="bar-label"><span>${esc(r.type)}</span><b>${fmt(r.count)}</b></div>
          <div class="bar-track"><div class="bar-fill" style="width:${(r.count / max) * 100}%"></div></div>
          <div class="tip">${esc(r.type)}: ${fmt(r.count)} · ${(r.share * 100).toFixed(1)}% of requests</div>
        </div>`).join("");
      $("#c311-distinct").innerHTML = h && h.distinctive.length
        ? `<strong>Unusually common here</strong> (vs. citywide share)<ul>${h.distinctive.map((d) =>
            `<li>${esc(d.type)}: ${d.x_citywide}× the city rate (${fmt(d.count)})</li>`).join("")}</ul>` : "";
      $("#c311-note").innerHTML = `Source: 311 Service Requests (<a href="https://data.cityofnewyork.us/d/erm2-nwe9" target="_blank" rel="noopener">erm2-nwe9</a>). Generated ${esc(S.generated_at.slice(0, 10))}.`;
    };
    sel.onchange = draw;
    draw();
  }

  function renderAbout() {
    $("#repo-link").href = GH;
    $("#run-link").href = `${GH}/actions/workflows/weekly.yml`;
    const r = DATA.run_report || {};
    const parts = Object.entries(r).map(([k, v]) => {
      if (v.skipped) return `${esc(k)}: off (${esc(v.skipped)})`;
      if (v.error) return `${esc(k)}: error`;
      return `${esc(k)}: ${fmt(v.kept ?? v.total_requests ?? 0)}`;
    });
    $("#run-report").innerHTML = parts.length ? `<strong>Last run:</strong> ${parts.join(" · ")}` : "";
  }

  function setTab(name) {
    document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
    document.querySelectorAll(".tab").forEach((t) => (t.hidden = t.id !== `tab-${name}`));
    try { history.replaceState(null, "", `#${name}`); } catch {}
    window.scrollTo(0, 0);
  }

  async function init() {
    document.querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => setTab(b.dataset.tab)));
    const initial = location.hash.slice(1);
    if (["top", "all", "311", "about"].includes(initial)) setTab(initial);

    try {
      DATA = await (await fetch("data/site.json", { cache: "no-cache" })).json();
    } catch (e) {
      $("#updated").textContent = "No data yet. Run the workflow once.";
      return;
    }
    DATA.clusters.forEach((c) => (BY_ID[c.id] = c));
    const d = new Date(DATA.generated_at);
    $("#updated").textContent = `Updated ${d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })} · ${fmt(DATA.stats.questions)} questions · ${fmt(DATA.stats.clusters)} clusters`;
    document.querySelectorAll("[data-w]").forEach((el) => (el.textContent = DATA.weights[el.dataset.w]));

    $("#f-theme").innerHTML += DATA.themes.map((t) => `<option value="${esc(t)}">${esc(t)}</option>`).join("");
    $("#f-source").innerHTML += Object.keys(DATA.stats.by_source).map((s) => `<option value="${esc(s)}">${esc(SOURCE_LABELS[s] || s)}</option>`).join("");
    ["#q", "#f-theme", "#f-source", "#sort", "#f-used"].forEach((s) => $(s).addEventListener("input", () => { shown = 30; renderAll(); }));
    $("#more").onclick = () => { shown += 30; renderAll(); };

    document.addEventListener("click", (e) => {
      const a = e.target.closest(".mark-used");
      if (!a) return;
      store.add(a.dataset.id); // hide right away on this device; the issue makes it permanent
      setTimeout(() => { renderTop(); renderAll(); }, 300);
    });

    renderTop();
    renderAll();
    renderAbout();
    try {
      const S = await (await fetch("data/311.json", { cache: "no-cache" })).json();
      render311(S);
    } catch {
      $("#c311-lede").textContent = "311 summary not generated yet.";
    }
  }
  init();
})();
