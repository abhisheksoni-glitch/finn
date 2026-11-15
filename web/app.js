"use strict";
(() => {
const API = (window.FINN_API || "").replace(/\/$/, "");
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const store = {
  get(k, d) { try { const v = localStorage.getItem("finn:" + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("finn:" + k, JSON.stringify(v)); } catch {} }
};

const S = {
  snap: null, research: {}, win: store.get("win2", "session"), custom: null,
  mutes: store.get("mutes", []), done: store.get("done", []), openRoutine: false,
  rules: null, ask: {}, speaking: false
};

/* ---------- formatting ---------- */
const nf0 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
const cr = v => v == null ? "–" : nf0.format(v);
const sgn = (v, d = 1) => v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d) + "%";
const cls = v => v == null ? "flat" : v > 0 ? "up" : v < 0 ? "down" : "flat";
const asOf = () => new Date(S.snap.meta.as_of);
const tsOf = a => new Date(a.ts);
function when(a) {
  const t = tsOf(a), now = asOf(), h = (now - t) / 36e5;
  const hm = t.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
  if (h < 20 && t.getDate() === now.getDate()) return hm;
  if (h < 24 * 6) return t.toLocaleDateString("en-IN", { weekday: "short" }) + " " + hm;
  return t.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}
const initials = n => n.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join("").toUpperCase();
const holding = sym => S.snap.portfolio.find(h => h.symbol === sym) || { name: sym };

/* ---------- toast & sheet ---------- */
let toastT;
function toast(msg, undo) {
  const t = $("#toast");
  t.innerHTML = `<span>${esc(msg)}</span>` + (undo ? `<button type="button">Undo</button>` : "");
  t.classList.add("on");
  if (undo) t.querySelector("button").onclick = () => { undo(); t.classList.remove("on"); };
  clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove("on"), 4200);
}
function sheet(html) {
  const sh = $("#sheet");
  $("#sheet-body").innerHTML = html; sh.hidden = false;
  const close = () => { sh.hidden = true; };
  $$("[data-close]", sh).forEach(x => x.onclick = close);
  document.addEventListener("keydown", function k(e) { if (e.key === "Escape") { close(); document.removeEventListener("keydown", k); } });
}

/* ---------- triage state ---------- */
const muteKey = a => a.symbol + "|" + a.category;
function effectiveTier(a) {
  if (S.mutes.includes(muteKey(a))) return "routine";
  return a.tier;
}
/* "Since last session": from the close of the session before the latest one, so a
   Monday morning or a Sunday shows Friday's filings and the weekend, not an empty day. */
function sessionStart() {
  const ds = [...new Set(S.snap.portfolio.flatMap(h => (h.series || []).map(r => r[0])))].sort();
  const now = asOf(), today = now.toISOString().slice(0, 10);
  const past = ds.filter(d => d < today || (d === today && now.getHours() >= 16));
  const prev = past.length >= 2 ? past[past.length - 2] : null;
  return prev ? new Date(prev + "T15:30:00+05:30") : new Date(now - 24 * 36e5);
}
function windowHours() {
  const now = asOf();
  if (S.win === "custom") return S.custom ? (now - new Date(S.custom + "T00:00:00+05:30")) / 36e5 : 24;
  if (S.win === "session") return (now - sessionStart()) / 36e5;
  return S.win;
}
function inWindow(a) {
  const now = asOf();
  if (S.win === "custom" && S.custom) return tsOf(a) >= new Date(S.custom + "T00:00:00+05:30") && tsOf(a) <= now;
  return (now - tsOf(a)) / 36e5 <= windowHours();
}

/* ---------- small svg charts ---------- */
function sparkline(vals, w = 130, h = 26) {
  const v = vals.filter(x => x != null);
  if (v.length < 2) return "";
  const mn = Math.min(...v), mx = Math.max(...v), r = mx - mn || 1;
  const pts = v.map((x, i) => [(i / (v.length - 1)) * (w - 4) + 2, h - 3 - ((x - mn) / r) * (h - 6)]);
  const d = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join("");
  const l = pts[pts.length - 1];
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><path d="${d}"/><circle cx="${l[0]}" cy="${l[1]}" r="2.6"/></svg>`;
}
function miniBars(labels, vals) {
  const v = vals.map(x => x || 0), mx = Math.max(...v, 1), n = v.length, W = 300, H = 44, bw = W / n;
  return `<svg class="minibars" viewBox="0 0 ${W} ${H}" aria-label="Revenue, last ${n} quarters">` + v.map((x, i) => {
    const h = (x / mx) * (H - 14);
    return `<rect class="${i === n - 1 ? "now" : ""}" x="${i * bw + 3}" y="${H - 12 - h}" width="${bw - 6}" height="${h}" rx="2"/>` +
      (i === 0 || i === n - 1 ? `<text x="${i * bw + (i ? bw - 3 : 3)}" y="${H - 2}" text-anchor="${i ? "end" : "start"}">${esc(labels[i])}</text>` : "");
  }).join("") + `</svg>`;
}

/* ---------- Brief ---------- */
function cardResults(a) {
  const c = a.card || {};
  if (!c.metrics || c.stale || c.pending) {
    return `<p class="lede">${esc(a.line)}</p><p class="note">Numbers pending. ${esc(c.reason || "The reported tables haven't caught up with this filing yet.")} The next nightly build tries again; the filing is linked below.</p>`;
  }
  const m = c.metrics.map(x => x.v == null
    ? `<div class="m"><span class="k">${esc(x.k)}</span><span class="v flat">n/a</span><span class="d"><span>${esc(x.note || "")}</span></span></div>`
    : `<div class="m"><span class="k">${esc(x.k)}</span><span class="v num">${cr(x.v)}<small>cr</small></span>
       <span class="d"><span class="${cls(x.yoy)}"><em>YoY</em>${sgn(x.yoy)}</span><span class="${cls(x.qoq)}"><em>QoQ</em>${sgn(x.qoq)}</span></span></div>`).join("");
  const bits = [];
  if (c.margin) bits.push(`EBITDA margin ${c.margin.now}%, <span class="${cls(c.margin.bps)}">${c.margin.bps > 0 ? "+" : "−"}${Math.abs(c.margin.bps)} bps</span> on a year ago.`);
  if (c.is_financial) bits.push("Lender: EBITDA swapped for pre-provision profit.");
  return `<div class="kicker"><b>${esc(c.quarter)}</b> vs ${esc(c.vs_qoq)} and ${esc(c.vs_yoy)}, ${esc(c.basis)}, ₹ crore</div>
    <div class="grid4">${m}</div>${bits.length ? `<p class="note">${bits.join(" ")}</p>` : ""}
    ${c.series && c.series.Revenue && c.series.Revenue.length > 2 ? miniBars(c.series.cols, c.series.Revenue) : ""}
    ${guidanceBlock(c.guidance)}`;
}
function guidanceBlock(g) {
  if (!g || !g.length) return "";
  const tone = { "ahead": "up", "in line": "flat", "behind": "down" };
  return `<div class="guide"><h4>Against what they guided</h4>${g.map(x => `<div class="gline">
    <span class="gv ${tone[x.verdict] || "flat"}">${esc(x.verdict)}</span>
    <span>${esc(x.actual_label)} <b class="num">${x.actual_label.includes("YoY") ? sgn(x.actual) : esc(x.actual) + "%"}</b>
    vs <b>${esc(x.target)}</b> guided on the ${esc(x.said_in)}${x.horizon ? ` (${esc(x.horizon)})` : ""}</span></div>`).join("")}
    <small>One quarter against the guided range, not a final verdict.</small></div>`;
}
function alsoBlock(a) {
  if (!a.also || !a.also.length) return "";
  return `<div class="also"><h4>Also filed with this</h4>${a.also.map(x =>
    `<a ${x.url ? `href="${esc(x.url)}" target="_blank" rel="noopener"` : ""}><b>${esc(x.label || "")}</b> ${esc(x.line || "")}</a>`).join("")}</div>`;
}
function cardPeople(a) {
  const ch = (a.card && a.card.changes) || [];
  const inc = ch.filter(c => c.change === "appointed" || c.change === "redesignated");
  const out = ch.filter(c => c.change === "resigned" || c.change === "retired");
  let h = `<p class="lede">${esc(a.line)}</p>`;
  for (const c of inc) {
    h += `<div class="who"><div class="avatar" aria-hidden="true">${esc(initials(c.person))}</div>
      <div><h3>${esc(c.person)}</h3><div class="role">Incoming ${esc(c.role)}${c.effective ? ", from " + esc(c.effective) : ""}</div></div>
      ${c.profile ? `<p class="profile">${esc(c.profile)}<small>From the company's filing</small></p>` : ""}
      ${c.prior_roles && c.prior_roles.length ? `<ul class="roles">${c.prior_roles.map(r => `<li>${esc(r)}</li>`).join("")}</ul>` : ""}
      ${c.web && c.web.bio ? `<p class="profile">${esc(c.web.bio)}<small>From the web, ${esc(c.web.confidence || "unverified")} confidence${(c.web.sources || []).length ? ": " + c.web.sources.map(u => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(new URL(u).hostname)}</a>`).join(", ") : ""}</small></p>` : ""}
      </div>`;
  }
  for (const c of out) h += `<div class="leaving"><s>${esc(c.person)}</s>, ${esc(c.role)}, leaves${c.effective ? " " + esc(c.effective) : ""}${c.reason ? ": " + esc(c.reason) : ""}.</div>`;
  const li = inc[0] || out[0];
  if (li && li.linkedin_search) h += `<div class="actions" style="margin-top:4px"><a class="act" href="${esc(li.linkedin_search)}" target="_blank" rel="noopener">Find ${esc(li.person.split(" ")[0])} on LinkedIn</a></div>`;
  return h;
}
function cardGeneric(a) {
  return `<div class="kicker"><b>${esc(a.label)}</b></div><p class="lede">${esc(a.line)}</p>`;
}
function whyPills(a) {
  const p = [];
  if (a.reaction != null && Math.abs(a.reaction) >= 2) p.push(`<span class="pill ${cls(a.reaction)}">Stock ${sgn(a.reaction)} on the news</span>`);
  for (const w of a.why || []) if (!/stock .* on the news/.test(w)) p.push(`<span class="pill">${esc(w)}</span>`);
  return p.length ? `<div class="why">${p.join("")}</div>` : "";
}
function topCard(a) {
  const h = holding(a.symbol);
  const body = a.card && a.card.type === "results" ? cardResults(a) : a.card && a.card.type === "people" ? cardPeople(a) : cardGeneric(a);
  const kick = a.card && a.card.type === "people" ? `<div class="kicker"><b>${esc(a.label)}</b></div>` : a.card && a.card.type === "results" ? "" : "";
  const hasR = S.snap.meta.research && S.snap.meta.research.includes(a.symbol);
  return `<div class="swipe" data-id="${esc(a.id)}">
    <div class="swipe-under" aria-hidden="true"><span class="l">Done</span><span class="r">Mute ${esc(a.label.toLowerCase())}</span></div>
    <article class="card" style="--w:${(0.45 + a.score / 180).toFixed(2)}">
      <div class="head"><span class="tk">${esc(a.symbol)}</span><span class="co">${esc(h.name)}</span><span class="time">${when(a)}</span></div>
      ${a.card && a.card.type === "results" ? `<div class="kicker" style="margin-bottom:6px"><b>Results</b></div>` : kick}
      ${body}${alsoBlock(a)}${whyPills(a)}
      <div class="actions">
        ${a.url ? `<a class="act" href="${esc(a.url)}" target="_blank" rel="noopener">Filing</a>` : ""}
        <a class="act" href="#research-${esc(a.symbol)}">${hasR ? "Research" : "Research " + esc(a.symbol)}</a>
        <button class="act" type="button" data-act="done">Done</button>
        <button class="act mute" type="button" data-act="mute">Mute</button>
      </div>
    </article></div>`;
}
function glanceRow(a) {
  return `<div class="row" role="button" tabindex="0" data-open="${esc(a.id)}">
    <span class="tk">${esc(a.symbol)}</span><p>${esc(a.line)}</p>
    <span class="lab">${esc(a.label)}</span><span class="rt">${when(a)}${a.reaction != null && Math.abs(a.reaction) >= 3 ? `, <span class="${cls(a.reaction)}">${sgn(a.reaction)}</span>` : ""}</span></div>`;
}
function movesNoNews(items) {
  const R = S.rules, now = asOf();
  const hrs = windowHours();
  const withNews = new Set(items.filter(a => effectiveTier(a) !== "routine").map(a => a.symbol));
  const out = [];
  for (const h of S.snap.portfolio) {
    if (withNews.has(h.symbol)) continue;
    const st = dayStats(h.series || [], R.lookback);
    const recent = st.filter(s => (now - new Date(s.d + "T15:30:00+05:30")) / 36e5 <= Math.max(hrs, 6));
    const hit = recent.reverse().find(s => (s.ret != null && Math.abs(s.ret) >= R.price) || (s.vmult != null && s.vmult >= R.vol));
    if (hit) out.push({ symbol: h.symbol, ret: hit.ret, vmult: hit.vmult, d: hit.d });
  }
  return out;
}
function moveTile(x) {
  const h = holding(x.symbol);
  const ser = (h.series || []).slice(-30).map(r => r[1]);
  return `<button class="mv" type="button" data-sym="${esc(x.symbol)}"><span class="tk">${esc(x.symbol)}</span>
    <span class="big ${cls(x.ret)}">${sgn(x.ret)}</span><small>${x.vmult ? "vol " + x.vmult.toFixed(1) + "× avg" : ""}</small>${sparkline(ser)}</button>`;
}
function windowChips() {
  const opts = [["session", "Since last session"], [24, "24 hours"], [72, "3 days"], [168, "7 days"]];
  return `<div class="chips" role="group" aria-label="Time window">${opts.map(([v, l]) =>
    `<button class="chip" type="button" data-win="${v}" aria-pressed="${S.win === v}">${l}</button>`).join("")}
    <label class="chip" aria-pressed="${S.win === "custom"}">Since <input type="date" id="since" value="${esc(S.custom || "")}" max="${S.snap.meta.as_of.slice(0, 10)}" aria-label="Show filings since"></label></div>`;
}
function heroLine(top, glance, routine) {
  const word = n => ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"][n] || String(n);
  const t = top.length;
  const lead = t === 0 ? "Nothing needs you." : `${word(t)} ${t === 1 ? "filing needs" : "filings need"} you.`;
  const rest = [];
  if (glance.length) rest.push(`<b>${glance.length}</b> worth a glance`);
  rest.push(`<b>${routine.length}</b> routine, folded away`);
  return `<section class="hero"><h1>${lead}</h1><p>${rest.join(", ")}.</p></section>`;
}
function renderBrief() {
  const all = S.snap.announcements.filter(a => !a.merged_into).filter(inWindow).filter(a => !S.done.includes(a.id));
  const top = all.filter(a => effectiveTier(a) === "top");
  const glance = all.filter(a => effectiveTier(a) === "glance");
  const routine = all.filter(a => effectiveTier(a) === "routine");
  const doneN = S.snap.announcements.filter(a => !a.merged_into).filter(inWindow).filter(a => S.done.includes(a.id)).length;
  const moves = movesNoNews(all);
  const m = S.snap.meta;
  let h = topBar();
  if (m.source === "sample") h += `<p class="banner">Sample data: filings, prices and financials here are illustrative. Run <code>python -m finn build</code> to load the live feed.</p>`;
  h += windowChips() + heroLine(top, glance, routine);
  if (top.length) h += `<div class="stack">${top.map(topCard).join("")}</div>`;
  if (moves.length) h += `<h2 class="sect">Moved on no news <span>price or volume past your rules, no filing to explain it</span></h2><div class="moves">${moves.map(moveTile).join("")}</div>`;
  if (glance.length) h += `<h2 class="sect">Worth a glance</h2><div class="rows">${glance.map(glanceRow).join("")}</div>`;
  if (routine.length) {
    const groups = {};
    routine.forEach(a => (groups[a.label] = groups[a.label] || []).push(a));
    const keys = Object.keys(groups).sort((x, y) => groups[y].length - groups[x].length);
    h += `<h2 class="sect">Routine</h2><button class="sediment" type="button" id="sed" aria-expanded="${S.openRoutine}">
      <div class="strata" aria-hidden="true">${keys.map(k => `<span style="flex:${groups[k].length}"></span>`).join("")}</div>
      <div class="sed-text"><span><b>${routine.length}</b> ${routine.length === 1 ? "filing" : "filings"}: ${keys.slice(0, 3).map(k => esc(k.toLowerCase())).join(", ")}${keys.length > 3 ? " and more" : ""}</span><span>${S.openRoutine ? "Fold" : "Unfold"}</span></div></button>`;
    if (S.openRoutine) h += `<div class="routine-list">${keys.map(k => `<div class="rgroup"><h4>${esc(k)} <span>${groups[k].length}</span></h4>${groups[k].map(a =>
      `<a href="${esc(a.url || "#")}" ${a.url ? 'target="_blank" rel="noopener"' : ""}><b>${esc(a.symbol)}</b>${esc(a.line)}</a>`).join("")}</div>`).join("")}</div>`;
  }
  if (!all.length) h += `<p class="empty">No filings in this window. Widen it above.</p>`;
  const foot = [];
  if (S.mutes.length) foot.push(`${S.mutes.length} muted ${S.mutes.length === 1 ? "rule" : "rules"} <button class="linkbtn" type="button" id="unmute">Show all again</button>`);
  if (doneN) foot.push(`${doneN} marked done <button class="linkbtn" type="button" id="undone">Bring back</button>`);
  if (foot.length) h += `<p class="quiet">${foot.join(". ")}</p>`;
  h += `<p class="quiet">${esc(healthLine())}</p>`;
  $("#app").innerHTML = h;
  bindBrief(all);
}
function healthLine() {
  const m = S.snap.meta, u = m.usage || {}, c = u.calls || {};
  if (m.source === "sample") return `Built from the sample set. Live builds use ${m.models.fast} for bulk extraction and ${m.models.smart} for analysis.`;
  return `Built ${new Date(m.as_of).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })} in ${m.build_seconds}s. Model calls: ${c.fast || 0} fast, ${c.smart || 0} smart, ${u.cache_hits || 0} served from cache.`;
}
function topBar() {
  const t = asOf();
  return `<header class="bar"><span class="mark"><i aria-hidden="true"></i>FINN</span>
    <button class="iconbtn" type="button" id="listen" aria-pressed="${S.speaking}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9H4z"/><path d="M16 9a4 4 0 010 6"/></svg>${S.speaking ? "Stop" : "Listen"}</button>
    <span class="asof">As of ${t.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" })}<br>${t.getHours() >= 15 ? "after close" : t.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}</span></header>`;
}
function bindBrief(all) {
  $$("[data-win]").forEach(b => b.onclick = () => { S.win = b.dataset.win === "session" ? "session" : +b.dataset.win; store.set("win2", S.win); renderBrief(); });
  const since = $("#since");
  if (since) since.onchange = () => { S.custom = since.value; S.win = "custom"; renderBrief(); };
  const sed = $("#sed");
  if (sed) sed.onclick = () => { S.openRoutine = !S.openRoutine; renderBrief(); };
  const um = $("#unmute"); if (um) um.onclick = () => { S.mutes = []; store.set("mutes", []); renderBrief(); };
  const ud = $("#undone"); if (ud) ud.onclick = () => { S.done = []; store.set("done", []); renderBrief(); };
  $("#listen").onclick = () => speak(all);
  $$("[data-open]").forEach(r => { const f = () => openItem(r.dataset.open); r.onclick = f; r.onkeydown = e => { if (e.key === "Enter") f(); }; });
  $$(".mv").forEach(b => b.onclick = () => openStock(b.dataset.sym));
  $$(".swipe").forEach(bindSwipe);
}
function finish(id, how) {
  const a = S.snap.announcements.find(x => x.id === id);
  if (!a) return;
  if (how === "done") {
    S.done.push(id); store.set("done", S.done);
    toast(`${a.symbol} marked done`, () => { S.done = S.done.filter(x => x !== id); store.set("done", S.done); renderBrief(); });
  } else {
    const k = muteKey(a);
    S.mutes.push(k); store.set("mutes", S.mutes);
    toast(`${a.label} filings from ${a.symbol} will be folded away`, () => { S.mutes = S.mutes.filter(x => x !== k); store.set("mutes", S.mutes); renderBrief(); });
  }
  renderBrief();
}
function bindSwipe(el) {
  const card = $(".card", el), id = el.dataset.id;
  $$("[data-act]", el).forEach(b => b.onclick = () => finish(id, b.dataset.act));
  let x0 = null, y0 = 0, dx = 0, locked = false;
  el.addEventListener("pointerdown", e => { if (e.target.closest("a,button")) return; x0 = e.clientX; y0 = e.clientY; dx = 0; locked = false; });
  el.addEventListener("pointermove", e => {
    if (x0 == null) return;
    const ddx = e.clientX - x0, ddy = e.clientY - y0;
    if (!locked && Math.abs(ddy) > 10 && Math.abs(ddy) > Math.abs(ddx)) { x0 = null; return; }
    if (Math.abs(ddx) > 8) { locked = true; card.classList.add("dragging"); el.setPointerCapture(e.pointerId); }
    if (locked) { dx = ddx; card.style.transform = `translateX(${dx}px)`; card.style.opacity = String(1 - Math.min(Math.abs(dx) / 400, .5)); }
  });
  const end = () => {
    if (x0 == null) return;
    x0 = null; card.classList.remove("dragging");
    if (dx > 110) { card.style.transform = "translateX(110%)"; setTimeout(() => finish(id, "done"), 160); }
    else if (dx < -110) { card.style.transform = "translateX(-110%)"; setTimeout(() => finish(id, "mute"), 160); }
    else { card.style.transform = ""; card.style.opacity = ""; }
  };
  el.addEventListener("pointerup", end); el.addEventListener("pointercancel", end);
}
function openItem(id) {
  const a = S.snap.announcements.find(x => x.id === id);
  if (!a) return;
  sheet(`<div class="head"><span class="tk">${esc(a.symbol)}</span><span class="co">${esc(holding(a.symbol).name)}</span><span class="time">${when(a)}</span></div>
    <h3>${esc(a.label)}</h3><p>${esc(a.line)}</p><p class="srcnote">Exchange subject: ${esc(a.subject)}</p>${whyPills(a)}
    <div class="actions">${a.url ? `<a class="act" href="${esc(a.url)}" target="_blank" rel="noopener">Open filing</a>` : ""}<a class="act" href="#research-${esc(a.symbol)}" data-close>Research ${esc(a.symbol)}</a><button class="act" type="button" data-close>Close</button></div>`);
}
function openStock(sym) {
  const h = holding(sym), st = dayStats(h.series || [], S.rules.lookback), last = st[st.length - 1] || {};
  sheet(`<div class="head"><span class="tk">${esc(sym)}</span><span class="co">${esc(h.name)}</span></div>
    <h3 class="num">₹${nf1.format(h.last)} <span class="${cls(last.ret)}">${sgn(last.ret)}</span></h3>
    <p>Volume ${last.vmult ? last.vmult.toFixed(1) + "×" : "–"} its ${S.rules.lookback}-day average. No filing from ${esc(sym)} in this window explains the move, so check sector news or block deals.</p>
    ${sparkline(st.slice(-60).map(r => r.c), 300, 60)}
    <div class="actions"><a class="act" href="#research-${esc(sym)}" data-close>Research ${esc(sym)}</a><button class="act" type="button" data-close>Close</button></div>`);
}
function speak(all) {
  const synth = window.speechSynthesis;
  if (!synth) { toast("Voice isn't available in this browser"); return; }
  if (S.speaking) { synth.cancel(); S.speaking = false; renderBrief(); return; }
  const top = all.filter(a => effectiveTier(a) === "top"), glance = all.filter(a => effectiveTier(a) === "glance");
  const say = s => s.replace(/₹/g, "rupees ").replace(/\bcr\b/g, "crore").replace(/YoY/g, "year on year").replace(/QoQ/g, "quarter on quarter").replace(/bps/g, "basis points").replace(/×/g, " times").replace(/−/g, "minus ");
  const parts = [`${top.length || "No"} ${top.length === 1 ? "filing needs" : "filings need"} you.`];
  top.forEach(a => parts.push(`${holding(a.symbol).name}. ${a.line}`));
  if (glance.length) parts.push(`Also worth a glance: ` + glance.slice(0, 4).map(a => `${holding(a.symbol).name}, ${a.label}`).join("; ") + ".");
  const moves = movesNoNews(all);
  if (moves.length) parts.push(`Moved without news: ` + moves.map(x => `${holding(x.symbol).name} ${sgn(x.ret).replace("−", "minus ")}`).join(", ") + ".");
  try {
    synth.cancel();
    const u = new SpeechSynthesisUtterance(say(parts.join(" ")));
    u.lang = "en-IN"; u.rate = 1.04;
    u.onend = () => { S.speaking = false; if (location.hash.startsWith("#brief") || !location.hash) renderBrief(); };
    synth.speak(u); S.speaking = true; renderBrief();
  } catch { toast("Voice isn't available here"); }
}

/* ---------- Watch ---------- */
function dayStats(series, lb) {
  return series.map((r, i) => {
    const prev = i ? series[i - 1][1] : null;
    const win = series.slice(Math.max(0, i - lb), i).map(x => x[2]).filter(Boolean);
    const avg = win.length >= Math.max(5, lb / 2) ? win.reduce((s, x) => s + x, 0) / win.length : null;
    return { d: r[0], c: r[1], v: r[2], ret: prev ? (r[1] / prev - 1) * 100 : null, vmult: avg ? r[2] / avg : null };
  });
}
const CATS = [["results", "Results"], ["M&A", "M&A"], ["management_change", "Management"], ["fund_raise", "Fund raise"],
  ["credit_rating", "Credit rating"], ["litigation", "Legal"], ["pledging", "Pledge"], ["insider_trading", "Insider deals"],
  ["capex", "Capex"], ["dividend", "Dividend"], ["press_release", "Press releases"]];
function rulesDefault() {
  const r = S.snap.meta.rules || {};
  return { price: r.price_move_pct ?? 4, vol: r.volume_multiple ?? 2, lookback: r.volume_lookback_days ?? 20, cats: r.alert_categories || ["results", "M&A", "management_change"] };
}
function backtest(R, days = 60) {
  const rows = [];
  let hits = 0;
  for (const h of S.snap.portfolio) {
    const st = dayStats(h.series || [], R.lookback).slice(-days);
    const cells = st.map(s => {
      const p = s.ret != null && Math.abs(s.ret) >= R.price, v = s.vmult != null && s.vmult >= R.vol;
      if (p || v) hits++;
      return p ? (s.ret > 0 ? "hit-up" : "hit-down") : v ? "hit-vol" : "";
    });
    rows.push({ sym: h.symbol, cells, dates: st.map(s => s.d), st });
  }
  return { rows, hits, days };
}
function matrix(bt) {
  const lw = 74, cw = 5, gap = 1.4, rh = 11, W = lw + bt.days * cw, H = bt.rows.length * rh + 14;
  let s = `<svg class="matrix" viewBox="0 0 ${W} ${H}" role="img" aria-label="Alert backtest: one row per stock, one column per session">`;
  bt.rows.forEach((r, i) => {
    s += `<text x="0" y="${i * rh + 8}">${esc(r.sym)}</text>`;
    r.cells.forEach((c, j) => { s += `<rect class="cell ${c}" x="${lw + j * cw}" y="${i * rh}" width="${cw - gap}" height="${rh - 2.4}" rx="1"><title>${esc(r.sym)} ${r.dates[j]}</title></rect>`; });
  });
  const d0 = bt.rows[0] ? bt.rows[0].dates[0] : "", d1 = bt.rows[0] ? bt.rows[0].dates[bt.rows[0].dates.length - 1] : "";
  s += `<text x="${lw}" y="${H - 2}">${esc(d0)}</text><text x="${W}" y="${H - 2}" text-anchor="end">${esc(d1)}</text></svg>`;
  return s;
}
function renderWatch() {
  const R = S.rules;
  const bt = backtest(R);
  const perWeek = bt.hits / (bt.days / 5);
  const last = bt.rows.map(r => ({ sym: r.sym, s: r.st[r.st.length - 1] })).filter(x => x.s && ((x.s.ret != null && Math.abs(x.s.ret) >= R.price) || (x.s.vmult != null && x.s.vmult >= R.vol)));
  const lastDay = bt.rows[0] ? bt.rows[0].dates[bt.rows[0].dates.length - 1] : "";
  const filingAl = S.snap.announcements.filter(a => R.cats.includes(a.category) && a.score >= 60 && (asOf() - tsOf(a)) / 36e5 <= 72);
  let h = `<header class="bar"><span class="mark"><i aria-hidden="true"></i>Watch</span><span class="asof">You decide<br>what is unusual</span></header>
  <section class="preview"><h3 id="bt-h">These rules would have pinged you ${bt.hits} ${bt.hits === 1 ? "time" : "times"} in ${bt.days} sessions, about ${perWeek.toFixed(1)} a week.</h3>
    <p>Each row is a holding, each square a trading day. Drag a threshold to see the noise change before you commit to it.</p>
    <div id="mx">${matrix(bt)}</div>
    <div class="legend"><span><i style="background:var(--up)"></i>up move</span><span><i style="background:var(--down)"></i>down move</span><span><i style="background:var(--saffron)"></i>volume only</span></div></section>
  <div class="rule"><label for="r-price">Daily price move <output id="o-price">±${R.price.toFixed(1)}%</output></label><p>Alert when a stock closes up or down by at least this much.</p>
    <input type="range" id="r-price" min="1" max="10" step="0.5" value="${R.price}"></div>
  <div class="rule"><label for="r-vol">Volume spike <output id="o-vol">${R.vol.toFixed(1)}×</output></label><p>Alert when the day's volume is this multiple of the <span id="lbtxt">${R.lookback}</span>-day average.</p>
    <input type="range" id="r-vol" min="1.2" max="5" step="0.1" value="${R.vol}">
    <div class="chips" role="group" aria-label="Average over" style="margin:6px 0 0">${[10, 20, 50].map(n => `<button class="chip" type="button" data-lb="${n}" aria-pressed="${R.lookback === n}">${n}-day</button>`).join("")}</div></div>
  <div class="rule"><label>Filings that should ping you</label><p>Anything else still shows up in the brief, ranked, but won't interrupt you.</p>
    <div class="catgrid">${CATS.map(([k, l]) => `<button class="chip" type="button" data-cat="${esc(k)}" aria-pressed="${R.cats.includes(k)}">${esc(l)}</button>`).join("")}</div></div>
  <h2 class="sect">Fired on ${esc(lastDay)} <span>${last.length + filingAl.length} alerts</span></h2>
  <div class="rows">${last.map(x => `<div class="row" role="button" tabindex="0" data-sym="${esc(x.sym)}"><span class="tk">${esc(x.sym)}</span>
    <p>${[x.s.ret != null && Math.abs(x.s.ret) >= R.price ? `<span class="${cls(x.s.ret)}">${sgn(x.s.ret)}</span> on the day` : "", x.s.vmult >= R.vol ? `volume ${x.s.vmult.toFixed(1)}× average` : ""].filter(Boolean).join(", ")}</p>
    <span class="lab">Price and volume</span><span class="rt">close ₹${nf1.format(x.s.c)}</span></div>`).join("")}
    ${filingAl.map(a => `<div class="row" role="button" tabindex="0" data-open="${esc(a.id)}"><span class="tk">${esc(a.symbol)}</span><p>${esc(a.line)}</p><span class="lab">${esc(a.label)}</span><span class="rt">${when(a)}</span></div>`).join("")}</div>
  <p class="quiet">For real push, the nightly build can send these to Telegram: <code>python -m finn notify</code>. Rules here are saved on this device.</p>
  <h2 class="sect">The book <span>${S.snap.portfolio.length} holdings</span></h2>
  <div class="rows book">${S.snap.portfolio.map(hd => {
    const st = dayStats(hd.series || [], R.lookback), l = st[st.length - 1] || {};
    return `<div class="row"><p><span class="tk">${esc(hd.symbol)}</span><br><span class="lab">${esc(hd.sector)}, ${esc(hd.size.toLowerCase())} cap, ${hd.weight}%</span></p>
      <div>${sparkline(st.slice(-40).map(r => r.c), 70, 26)}</div>
      <div class="px num">₹${hd.last != null ? nf1.format(hd.last) : "–"}<small class="${cls(l.ret)}">${sgn(l.ret)}</small></div></div>`; }).join("")}</div>`;
  $("#app").innerHTML = h;
  const save = () => { store.set("rules", S.rules); };
  const live = () => {
    const b = backtest(S.rules);
    $("#mx").innerHTML = matrix(b);
    $("#bt-h").textContent = `These rules would have pinged you ${b.hits} ${b.hits === 1 ? "time" : "times"} in ${b.days} sessions, about ${(b.hits / (b.days / 5)).toFixed(1)} a week.`;
  };
  $("#r-price").oninput = e => { S.rules.price = +e.target.value; $("#o-price").textContent = "±" + S.rules.price.toFixed(1) + "%"; live(); };
  $("#r-vol").oninput = e => { S.rules.vol = +e.target.value; $("#o-vol").textContent = S.rules.vol.toFixed(1) + "×"; live(); };
  $("#r-price").onchange = $("#r-vol").onchange = () => { save(); renderWatch(); };
  $$("[data-lb]").forEach(b => b.onclick = () => { S.rules.lookback = +b.dataset.lb; save(); renderWatch(); });
  $$("[data-cat]").forEach(b => b.onclick = () => {
    const k = b.dataset.cat; S.rules.cats = S.rules.cats.includes(k) ? S.rules.cats.filter(x => x !== k) : [...S.rules.cats, k]; save(); renderWatch();
  });
  $$(".row[data-sym]").forEach(r => r.onclick = () => openStock(r.dataset.sym));
  $$("[data-open]").forEach(r => r.onclick = () => openItem(r.dataset.open));
}

/* ---------- Ask FINN ---------- */
/* A conversation over the book the phone is already showing. The app sends the model a
   compact view of exactly what is on screen (ranked filings, prices, alerts, research
   it has), and every answer comes back with citations that open the card they rest on.
   With no server or no model, common questions are answered right here on the phone. */
S.chat = [];
S.listening = false;
const SUGGEST = ["What needs me today?", "Anything move without news?", "How were this week's results?", "Summarise my book in 30 seconds"];

function bookContext(q) {
  const now = asOf(), R = S.rules;
  const recent = S.snap.announcements.filter(a => !a.merged_into && (now - tsOf(a)) / 36e5 <= 24 * 7);
  const rank = { top: 0, glance: 1, routine: 2 };
  recent.sort((a, b) => rank[effectiveTier(a)] - rank[effectiveTier(b)] || b.score - a.score);
  const filings = recent.slice(0, 40).map(a => {
    const f = { id: a.id, symbol: a.symbol, type: a.label, tier: effectiveTier(a), when: a.ts.slice(0, 16), line: a.line };
    if (a.reaction != null) f.stock_move_next_session_pct = a.reaction;
    const c = a.card || {};
    if (c.metrics) f.results = { quarter: c.quarter, vs: [c.vs_qoq, c.vs_yoy], metrics_cr: c.metrics.map(m => ({ k: m.k, v: m.v, yoy_pct: m.yoy, qoq_pct: m.qoq })), margin: c.margin || null };
    if (c.pending) f.results = { pending: c.reason };
    if (c.guidance && c.guidance.length) f.vs_guidance = c.guidance.map(g => `${g.verdict}: ${g.actual_label} ${g.actual} vs ${g.target} guided on the ${g.said_in}`);
    if (c.changes) f.people = c.changes.map(p => ({ person: p.person, role: p.role, change: p.change, effective: p.effective, profile: p.profile || (p.web && p.web.bio) || null }));
    if (a.also) f.also_filed = a.also.map(x => `${x.label}: ${x.line}`);
    return f;
  });
  const holdings = S.snap.portfolio.map(h => {
    const st = dayStats(h.series || [], R.lookback), l = st[st.length - 1] || {}, w = st[st.length - 6];
    return { symbol: h.symbol, name: h.name, sector: h.sector, weight_pct: h.weight, close: h.last, day_pct: l.ret != null ? +l.ret.toFixed(2) : null,
      week_pct: w && l.c ? +((l.c / w.c - 1) * 100).toFixed(2) : null, volume_x_avg: l.vmult ? +l.vmult.toFixed(2) : null, date: l.d };
  });
  const research = [];
  const named = new Set((q.toUpperCase().match(/[A-Z&]{2,15}/g) || []).filter(w => S.snap.portfolio.some(h => h.symbol === w) || S.research[w]));
  for (const sym of named) {
    const r = S.research[sym]; if (!r || !r.analysis) continue;
    const an = r.analysis;
    research.push({ symbol: sym, verdict: an.verdict, guidance_now: (an.guidance_now || []).slice(0, 4),
      promises: (an.ledger || []).slice(0, 6).map(x => ({ said_in: x.said_in, promise: x.promise, delivered: x.delivered, verdict: x.verdict })),
      bull: (an.bull || []).map(x => x.point), bear: (an.bear || []).map(x => x.point) });
  }
  return { as_of: S.snap.meta.as_of, data_source: S.snap.meta.source, rules: { price_move_pct: R.price, volume_x: R.vol, lookback_days: R.lookback },
    holdings, filings, routine_folded: recent.filter(a => effectiveTier(a) === "routine").length,
    moved_without_news: movesNoNews(recent).map(x => ({ symbol: x.symbol, day_pct: x.ret != null ? +x.ret.toFixed(2) : null, volume_x_avg: x.vmult ? +x.vmult.toFixed(2) : null, date: x.d })),
    research_ready: S.snap.meta.research || [], research };
}

/* answers on the phone, no model: the questions an investor asks most */
function localAnswer(q) {
  const t = q.toLowerCase(), now = asOf();
  const recent = S.snap.announcements.filter(a => !a.merged_into && (now - tsOf(a)) / 36e5 <= windowHours());
  const top = recent.filter(a => effectiveTier(a) === "top"), glance = recent.filter(a => effectiveTier(a) === "glance");
  const sym = S.snap.portfolio.map(h => h.symbol).find(s => new RegExp(`\\b${s.toLowerCase()}\\b`).test(t))
    || (S.snap.portfolio.find(h => t.includes(h.name.toLowerCase().split(" ")[0]) && h.name.length > 3) || {}).symbol;
  const line = a => `${a.symbol}: ${a.line}`;
  if (sym) {
    const h = holding(sym), st = dayStats(h.series || [], S.rules.lookback), l = st[st.length - 1] || {};
    const fs = S.snap.announcements.filter(a => a.symbol === sym && !a.merged_into && (now - tsOf(a)) / 36e5 <= 24 * 7 && effectiveTier(a) !== "routine");
    let ans = `${sym} closed at ₹${nf1.format(h.last)}, ${sgn(l.ret)} on the day${l.vmult ? ` on ${l.vmult.toFixed(1)}× its usual volume` : ""}. `;
    ans += fs.length ? `This week: ${fs.slice(0, 3).map(a => a.line).join(" ")}` : "No material filing from it this week.";
    return { answer: ans, cites: [`P:${sym}`, ...fs.slice(0, 3).map(a => `F:${a.id}`)], follow_ups: [`Research ${sym}`, "What needs me today?"] };
  }
  if (/no news|without news|unusual|volume|spike|mov(e|ed)/.test(t)) {
    const m = movesNoNews(recent);
    return { answer: m.length ? `${m.length} ${m.length === 1 ? "holding" : "holdings"} crossed your rules with no filing to explain it: ${m.map(x => `${x.symbol} ${sgn(x.ret)}${x.vmult ? ` (volume ${x.vmult.toFixed(1)}×)` : ""}`).join(", ")}.` : `Nothing crossed your ±${S.rules.price}% or ${S.rules.vol}× volume rules without news.`,
      cites: m.map(x => `P:${x.symbol}`), follow_ups: ["What needs me today?"] };
  }
  if (/result|quarter|earning|numbers/.test(t)) {
    const rs = recent.filter(a => a.card && a.card.type === "results");
    return { answer: rs.length ? rs.map(a => a.line).join(" ") : "No results filed in this window.", cites: rs.map(a => `F:${a.id}`), follow_ups: ["Anything move without news?"] };
  }
  if (/need|today|important|summar|brief|book|happen|what.?s up|catch me up/.test(t)) {
    if (!top.length && !glance.length) return { answer: "Nothing material in this window. Everything filed was routine paperwork.", cites: [], follow_ups: ["Anything move without news?"] };
    return { answer: `${top.length} ${top.length === 1 ? "filing needs" : "filings need"} you. ${top.slice(0, 3).map(line).join(" ")}${glance.length ? ` Also worth a glance: ${glance.slice(0, 3).map(a => `${a.symbol} ${a.label.toLowerCase()}`).join(", ")}.` : ""}`,
      cites: [...top, ...glance].slice(0, 5).map(a => `F:${a.id}`), follow_ups: ["Anything move without news?", "How were this week's results?"] };
  }
  return { answer: "I answer from your brief, prices and research. Try one of the questions below, or name a stock.", cites: [], follow_ups: SUGGEST.slice(0, 3) };
}

async function askFinn(q) {
  q = (q || "").trim(); if (!q) return;
  const rm = q.match(/^research\s+([A-Za-z&]+)$/i);
  if (rm) { location.hash = "#research-" + rm[1].toUpperCase(); return; }
  S.chat.push({ role: "user", text: q }, { role: "finn", pending: true });
  renderAsk();
  const ctx = bookContext(q);
  let out = null, local = false;
  if (API) {
    try {
      const r = await fetch(`${API}/api/chat`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ q, context: ctx, history: S.chat.filter(m => !m.pending).slice(-7, -1).map(m => ({ role: m.role, text: m.text })) }) });
      if (r.ok) out = await r.json();
    } catch {}
  }
  if (!out) { out = localAnswer(q); local = true; }
  S.chat[S.chat.length - 1] = { role: "finn", text: out.answer, cites: out.cites || [], follow: out.follow_ups || [], local };
  renderAsk();
}

function citeChip(c) {
  const [k, ...rest] = c.split(":"), v = rest.join(":");
  if (k === "F") { const a = S.snap.announcements.find(x => x.id === v); return a ? `<button class="chip cite" type="button" data-cf="${esc(v)}">${esc(a.symbol)} · ${esc(a.label)}</button>` : ""; }
  if (k === "P") return `<button class="chip cite" type="button" data-cp="${esc(v)}">${esc(v)} · price</button>`;
  if (k === "R") return `<a class="chip cite" href="#research-${esc(v)}">${esc(v)} · research</a>`;
  return "";
}
function renderAsk() {
  const msgs = S.chat.map((m, i) => m.role === "user"
    ? `<div class="msg me">${esc(m.text)}</div>`
    : m.pending ? `<div class="msg finn pending" aria-live="polite"><span></span><span></span><span></span></div>`
    : `<div class="msg finn"><p>${esc(m.text)}</p>
        ${m.cites && m.cites.length ? `<div class="cites">${m.cites.map(citeChip).join("")}</div>` : ""}
        <div class="msg-foot"><button class="linkbtn" type="button" data-say="${i}">Read aloud</button><span>${m.local ? "Answered on the phone, no model" : "From your book only"}</span></div>
        ${i === S.chat.length - 1 && m.follow && m.follow.length ? `<div class="chips follow">${m.follow.map(f => `<button class="chip" type="button" data-q="${esc(f)}">${esc(f)}</button>`).join("")}</div>` : ""}
      </div>`).join("");
  const mic = ("webkitSpeechRecognition" in window || "SpeechRecognition" in window);
  $("#app").innerHTML = `<header class="bar"><span class="mark"><i aria-hidden="true"></i>Ask FINN</span><span class="asof">Answers from your book,<br>with the cards to prove it</span></header>
    ${S.chat.length ? "" : `<section class="hero"><h1>Ask about your book.</h1><p>Type, or tap the mic and talk. Every answer links back to the filing, price or research it came from.</p></section>
      <div class="chips suggest">${SUGGEST.map(s => `<button class="chip" type="button" data-q="${esc(s)}">${esc(s)}</button>`).join("")}</div>`}
    <div class="thread" id="thread">${msgs}</div>
    <form class="search askbar" id="askf"><input id="askq" placeholder="${S.listening ? "Listening…" : "e.g. What did KAYNES report?"}" autocomplete="off" aria-label="Ask FINN">
      ${mic ? `<button class="btn ghost mic" type="button" id="mic" aria-pressed="${S.listening}" aria-label="Speak your question"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0014 0M12 18v3"/></svg></button>` : ""}
      <button class="btn" type="submit">Ask</button></form>
    ${S.chat.length ? `<p class="quiet"><button class="linkbtn" type="button" id="clearchat">Start over</button></p>` : ""}`;
  $("#askf").onsubmit = e => { e.preventDefault(); const v = $("#askq").value; askFinn(v); };
  $$("[data-q]").forEach(b => b.onclick = () => askFinn(b.dataset.q));
  $$("[data-cf]").forEach(b => b.onclick = () => openItem(b.dataset.cf));
  $$("[data-cp]").forEach(b => b.onclick = () => openPrice(b.dataset.cp));
  $$("[data-say]").forEach(b => b.onclick = () => sayText(S.chat[+b.dataset.say].text));
  const cl = $("#clearchat"); if (cl) cl.onclick = () => { S.chat = []; renderAsk(); };
  const mb = $("#mic"); if (mb) mb.onclick = listen;
  const th = $("#thread"); if (th && th.lastElementChild) th.lastElementChild.scrollIntoView({ block: "nearest" });
}
function openPrice(sym) {
  const h = holding(sym), st = dayStats(h.series || [], S.rules.lookback), last = st[st.length - 1] || {};
  sheet(`<div class="head"><span class="tk">${esc(sym)}</span><span class="co">${esc(h.name)}</span><span class="time">${esc(last.d || "")}</span></div>
    <h3 class="num">₹${h.last != null ? nf1.format(h.last) : "–"} <span class="${cls(last.ret)}">${sgn(last.ret)}</span></h3>
    <p>Volume ${last.vmult ? last.vmult.toFixed(1) + "×" : "–"} its ${S.rules.lookback}-day average. Last 60 sessions:</p>
    ${sparkline(st.slice(-60).map(r => r.c), 300, 60)}
    <div class="actions"><a class="act" href="#research-${esc(sym)}" data-close>Research ${esc(sym)}</a><button class="act" type="button" data-close>Close</button></div>`);
}
function sayText(text) {
  try {
    const synth = window.speechSynthesis; synth.cancel();
    const u = new SpeechSynthesisUtterance(text.replace(/₹/g, "rupees ").replace(/\bcr\b/g, "crore").replace(/YoY/g, "year on year").replace(/QoQ/g, "quarter on quarter").replace(/×/g, " times").replace(/−/g, "minus "));
    u.lang = "en-IN"; synth.speak(u);
  } catch { toast("Voice isn't available here"); }
}
function listen() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return;
  if (S.listening && S.rec) { S.rec.stop(); return; }
  const rec = new SR(); S.rec = rec;
  rec.lang = "en-IN"; rec.interimResults = true; rec.maxAlternatives = 1;
  rec.onresult = e => { const t = [...e.results].map(r => r[0].transcript).join(""); const i = $("#askq"); if (i) i.value = t;
    if (e.results[e.results.length - 1].isFinal) { S.listening = false; askFinn(t); } };
  rec.onerror = () => { S.listening = false; renderAsk(); toast("Couldn't hear that. Check the mic permission."); };
  rec.onend = () => { if (S.listening) { S.listening = false; renderAsk(); } };
  S.listening = true; renderAsk(); rec.start();
}

/* ---------- Research ---------- */
async function loadResearch(sym) {
  if (S.research[sym]) return S.research[sym];
  const local = (S.snap.meta.research || []).includes(sym);
  if (local) {
    try { const r = await fetch(`data/research/${sym}.json`); if (r.ok) return (S.research[sym] = await r.json()); } catch {}
  }
  if (API) {
    // The server builds in the background (202) and we poll, so a slow first build
    // never hangs on one long request. A free server may also need ~1 min to wake up.
    const url = `${API}/api/research/${encodeURIComponent(sym)}`, t0 = Date.now();
    let fails = 0;
    while (Date.now() - t0 < 12 * 60e3) {
      if (location.hash.toUpperCase() !== ("#research-" + sym).toUpperCase()) throw new Error("cancelled");
      let r;
      try { r = await fetch(url); fails = 0; }
      catch { if (++fails > 6) throw new Error("Couldn't reach the research server. It may be waking up; try again in a minute."); r = null; }
      if (r && r.status === 200) return (S.research[sym] = await r.json());
      if (r && r.status !== 202) throw new Error((await r.json().catch(() => ({}))).detail || `No data for ${sym}`);
      const st = r ? await r.json().catch(() => ({})) : {};
      onProgress(sym, st, Math.round((Date.now() - t0) / 1000));
      await new Promise(res => setTimeout(res, 4000));
    }
    throw new Error(`${sym} is taking unusually long. Try again in a few minutes; the build keeps going on the server.`);
  }
  throw new Error("offline");
}
function onProgress(sym, st, secs) {
  const el = $("#rprog");
  if (!el) return;
  const step = (st.step || "").replace(/^\s*[!-]*\s*/, "");
  el.innerHTML = `Building ${esc(sym)} from its own transcripts and annual report: ${secs}s${step ? `<br><small>${esc(step)}</small>` : ""}<br><small>First build takes 2 to 5 minutes, then it's cached.</small>`;
}
function researchHome(msg) {
  const avail = S.snap.meta.research || [];
  return `<header class="bar"><span class="mark"><i aria-hidden="true"></i>Research</span><span class="asof">From annual reports<br>and earnings calls only</span></header>
    <form class="search" id="rs"><input id="rq" placeholder="Any NSE symbol, e.g. TITAN" autocomplete="off" autocapitalize="characters" aria-label="NSE symbol"><button class="btn" type="submit">Open</button></form>
    ${msg || ""}
    <h2 class="sect">Ready to read <span>built in the last run</span></h2>
    <div class="rlist">${avail.map(s => `<a class="rcard" href="#research-${esc(s)}"><b>${esc(s)}</b><span>${holding(s).name !== s ? esc(holding(s).name) + ", in your book" : "outside your book"}</span></a>`).join("")}</div>
    <p class="quiet">${API ? "Live engine connected: any NSE symbol with filings on Screener works, built in about a minute and cached after that." : "Other symbols need the live engine: run <code>python -m finn serve</code> and set FINN_API in config.js, or prebuild with <code>python -m finn research SYMBOL</code>."}</p>`;
}
const VERD = { delivered: ["Delivered", "M5 12l5 5 9-10"], partly: ["Partly", "M5 12h14"], missed: ["Missed", "M7 7l10 10M17 7L7 17"], too_early: ["Too early", "M12 7v5l3 2"], walked_back: ["Walked back", "M9 7L5 11l4 4M5 11h9a5 5 0 010 10h-2"] };
function glyph(v) {
  const g = VERD[v] || VERD.too_early;
  return `<svg class="glyph v-${esc(v)}" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="11" fill="none" stroke="currentColor" stroke-width="1.5" opacity=".35"/><path d="${g[1]}" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" transform="scale(.75) translate(4 4)"/></svg>`;
}
const srcChips = arr => (arr && arr.length) ? `<span class="srcs">${arr.map(s => `<button class="src" type="button" data-src="${esc(s)}">${esc(s)}</button>`).join("")}</span>` : "";
function barChart(labels, vals, line, opts = {}) {
  const W = 320, H = 130, pl = 4, pb = 16, n = vals.length;
  const v = vals.map(x => x ?? 0), mx = Math.max(...v.map(Math.abs), 1), hasNeg = v.some(x => x < 0);
  const base = hasNeg ? (H - pb) / 2 : H - pb, scale = hasNeg ? (H - pb) / 2 - 4 : H - pb - 8, bw = (W - pl) / n;
  let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.label || "")}">`;
  v.forEach((x, i) => {
    const h = Math.abs(x) / mx * scale;
    s += `<rect class="${x < 0 ? "neg" : "bar"} ${i === n - 1 && opts.hiLast ? "hi" : ""}" x="${pl + i * bw + 4}" y="${x < 0 ? base : base - h}" width="${bw - 8}" height="${Math.max(h, .5)}" rx="2"><title>${esc(labels[i])}: ${x}</title></rect>`;
    s += `<text x="${pl + i * bw + bw / 2}" y="${H - 3}" text-anchor="middle">${esc(labels[i])}</text>`;
  });
  if (opts.ref != null) { const y = base - opts.ref / mx * scale; s += `<line class="ref" x1="0" x2="${W}" y1="${y}" y2="${y}"/><text x="${W}" y="${y - 3}" text-anchor="end">${esc(opts.refLabel || "")}</text>`; }
  if (line) {
    const lv = line.filter(x => x != null), lmn = Math.min(...lv), lmx = Math.max(...lv), lr = lmx - lmn || 1;
    const pts = line.map((x, i) => x == null ? null : [pl + i * bw + bw / 2, 20 + (1 - (x - lmn) / lr) * (H - pb - 46)]);
    s += `<path class="ln" d="${pts.filter(Boolean).map((p, i) => (i ? "L" : "M") + p[0] + " " + p[1]).join("")}"/>`;
    pts.forEach((p, i) => { if (p && (i === 0 || i === pts.length - 1)) s += `<text x="${p[0]}" y="${p[1] - 5}" text-anchor="middle" style="fill:var(--saffron);font-weight:700">${line[i]}%</text>`; });
  }
  return s + `</svg>`;
}
function renderTear(r) {
  const n = r.numbers, a = r.analysis || {}, sn = n.snapshot, tr = n.trajectory, ba = n.balance, ca = n.cash;
  const last = arr => (arr || []).filter(x => x != null).slice(-1)[0];
  const led = a.ledger || [];
  const cnt = k => led.filter(x => x.verdict === k).length;
  const total = led.length || 1;
  let h = `<header class="bar"><a class="iconbtn" href="#research" aria-label="Back to research">Back</a><span class="asof">${r.mode === "sample" ? "Sample analysis" : r.mode === "numbers_only" ? "Numbers only" : "Grounded analysis"}<br>${esc(r.basis || "")} figures</span></header>
  ${S.snap.meta.source === "sample" ? `<p class="banner">Sample: financials and call excerpts are illustrative so the layout can be judged offline. <code>python -m finn research ${esc(r.symbol)}</code> builds the real one.</p>` : ""}
  <div class="co-h"><h1>${esc(r.name)}</h1><p>${esc(r.symbol)}, ${esc(r.about)}</p></div>
  <div class="facts">
    <div><span>Market cap</span><b class="num">₹${sn.market_cap ? nf0.format(sn.market_cap) : "–"}<small> cr</small></b></div>
    <div><span>P/E</span><b class="num">${sn.pe ?? "–"}</b></div><div><span>ROCE</span><b class="num">${sn.roce ?? "–"}%</b></div>
    <div><span>Revenue, ${sn.ttm ? "TTM" : "latest FY"}</span><b class="num">₹${cr(sn.rev_ttm)}<small> cr</small></b></div><div><span>Op. margin</span><b class="num">${sn.opm_ttm ?? "–"}%</b></div><div><span>Debt / equity</span><b class="num">${sn.de ?? "–"}</b></div></div>
  ${a.verdict ? (r.mode === "numbers_only" ? `<p class="sub" style="margin-top:12px">${esc(a.verdict)}</p>` : `<p class="verdict">${esc(a.verdict)}</p>`) : ""}
  <nav class="toc" aria-label="Sections">${[led.length && ["ledger", "Promises"], (a.narrative || []).length && ["narrative", "Story vs numbers"], ["numbers", "Trajectory"], ["cash", "Cash"], ["balance", "Balance sheet"], ["bullbear", "Bull and bear"], ["ask", "Ask"]].filter(Boolean).map(([id, l]) => `<a href="#research-${esc(r.symbol)}" data-jump="${id}">${l}</a>`).join("")}</nav>`;
  if (led.length) {
    h += `<section class="rsec" id="s-ledger"><h2>Said versus done</h2><p class="sub">Headline guidance from the last four earnings calls, checked against what was reported.</p>
      <div class="score" aria-label="Scorecard">${["delivered", "partly", "too_early", "walked_back", "missed"].map(k => cnt(k) ? `<span style="flex:${cnt(k)};background:${k === "delivered" ? "var(--up)" : k === "partly" ? "var(--saffron)" : k === "too_early" ? "var(--rule)" : "var(--down)"}"></span>` : "").join("")}</div>
      <p class="sub">${cnt("delivered")} delivered, ${cnt("partly")} partly, ${cnt("missed") + cnt("walked_back")} missed or walked back, ${cnt("too_early")} too early to call.</p>
      <div class="ledger">${led.map(x => `<div class="lrow">${glyph(x.verdict)}<div>
        <div class="said">${esc(x.said_in)} call <span class="vlabel v-${esc(x.verdict)}">${esc((VERD[x.verdict] || ["?"])[0])}</span></div>
        <div class="prom">${esc(x.promise)}</div>${x.target || x.horizon ? `<div class="tgt">${esc([x.target, x.horizon].filter(Boolean).join(", "))}</div>` : ""}
        <div class="got"><b>Reported:</b> ${esc(x.delivered)}</div>${srcChips(x.src)}</div></div>`).join("")}</div>
      ${a.guidance_drift ? `<p class="drift"><b>How the story moved.</b> ${esc(a.guidance_drift)}</p>` : ""}</section>`;
  } else if (a.guidance_raw && a.guidance_raw.length) {
    h += `<section class="rsec" id="s-ledger"><h2>What management said</h2><p class="sub">Guidance sentences pulled from the transcripts. Add a model key to have them checked against the numbers.</p>
      <div class="ledger">${a.guidance_raw.map(g => `<div class="lrow">${glyph("too_early")}<div><div class="prom" style="font-weight:500">${esc(g.statement)}</div>${srcChips([g.src])}</div></div>`).join("")}</div></section>`;
  }
  if ((a.narrative || []).length) {
    h += `<section class="rsec" id="s-narrative"><h2>Story versus numbers</h2><p class="sub">Where management's explanation holds up, and where the reported figures disagree.</p>
      <div class="nvn">${a.narrative.map(x => `<div class="nv"><span class="tag ${x.agree ? "up" : "down"}">${x.agree ? "Holds up" : "Diverges"}</span><div class="c">${esc(x.claim)}</div><div class="n">${esc(x.numbers)}</div>${srcChips(x.src)}</div>`).join("")}</div></section>`;
  }
  if (a.business || (a.guidance_now || []).length) {
    h += `<section class="rsec"><h2>The business</h2>${a.business ? `<p>${esc(a.business.what)} ${srcChips(a.business.src)}</p>
      <div class="segs">${(a.business.segments || []).map(sg => { const pct = parseFloat(String(sg.share || "").replace(/[^\d.]/g, "")) || 0; return `<div class="seg"><span>${esc(sg.name)}</span><span class="num" style="text-align:right">${esc(sg.share || "")}</span><span class="b" style="width:${Math.max(pct, 2)}%"></span></div>`; }).join("")}</div>` : ""}
      ${(a.guidance_now || []).length ? `<h3 style="font-size:var(--s3);margin:18px 0 4px">Guidance on the table now</h3><dl class="gnow">${a.guidance_now.map(g => `<div><dt>${esc(g.metric)}</dt><dd><b>${esc(g.target)}</b> ${esc(g.horizon)} ${srcChips(g.src)}</dd></div>`).join("")}</dl>` : ""}</section>`;
  }
  const q = n.quarters || [];
  h += `<section class="rsec" id="s-numbers"><h2>Trajectory</h2><p class="sub">Annual revenue (₹ cr) with operating margin.</p>
    ${barChart(tr.years.map(y => y === "TTM" ? "TTM" : "FY" + y.slice(2)), tr.revenue || [], tr.opm, { label: "Revenue by year", hiLast: true })}
    <div class="kv"><div><span>Revenue growth, 3 yr</span><b class="${cls(tr.rev_cagr_3y)}">${sgn(tr.rev_cagr_3y)}</b> a year</div><div><span>Profit growth, 3 yr</span><b class="${cls(tr.pat_cagr_3y)}">${sgn(tr.pat_cagr_3y)}</b> a year</div>
      <div><span>Margin change, 3 yr</span><b class="${cls(tr.opm_change_3y_bps)}">${tr.opm_change_3y_bps != null ? (tr.opm_change_3y_bps > 0 ? "+" : "−") + Math.abs(tr.opm_change_3y_bps) + " bps" : "–"}</b></div><div><span>Revenue growth, 5 yr</span><b class="${cls(tr.rev_cagr_5y)}">${sgn(tr.rev_cagr_5y)}</b></div></div>
    ${q.length ? `<table class="qtable"><thead><tr><th>Quarter</th><th>Revenue</th><th>YoY</th><th>Op. margin</th><th>PAT YoY</th></tr></thead><tbody>${q.slice(-6).reverse().map(x => `<tr><td>${esc(x.q)}</td><td class="num">${cr(x.rev)}</td><td class="${cls(x.rev_yoy)}">${sgn(x.rev_yoy)}</td><td>${x.opm ?? "–"}%</td><td class="${cls(x.pat_yoy)}">${sgn(x.pat_yoy)}</td></tr>`).join("")}</tbody></table>` : ""}</section>`;
  h += `<section class="rsec" id="s-cash"><h2>Do profits turn into cash?</h2><p class="sub">Operating cash flow divided by net profit, each year. Above the line means more cash than reported profit.</p>
    ${barChart(ca.years.map(y => "FY" + y.slice(2)), ca.conversion || [], null, { label: "Cash conversion", ref: 1, refLabel: "1.0×", hiLast: true })}
    <div class="kv"><div><span>5-year cash / profit</span><b>${ca.conversion_5y != null ? ca.conversion_5y.toFixed(2) + "×" : "–"}</b></div><div><span>Free cash flow, latest</span><b>₹${cr(last(ca.fcf))} cr</b><span>${esc(ca.fcf_kind || "")}</span></div></div></section>`;
  h += `<section class="rsec" id="s-balance"><h2>Balance sheet</h2><p class="sub">Leverage and the working-capital cycle: days of sales tied up in receivables and inventory, less payables.</p>
    <div class="kv"><div><span>Borrowings</span><b>₹${cr(last(ba.borrowings))} cr</b></div><div><span>Debt / equity</span><b>${last(ba.de) ?? "–"}</b></div>
      <div><span>Working-capital days</span><b>${last(ba.wc_days) ?? "–"}</b><span>${(ba.wc_days || []).filter(x => x != null).slice(-4).join(" → ")}</span></div>
      <div><span>Cash conversion cycle</span><b>${last(ba.ccc) ?? "–"} days</b><span>${(ba.ccc || []).filter(x => x != null).slice(-4).join(" → ")}</span></div>
      <div><span>Receivable days</span><b>${last(ba.debtor_days) ?? "–"}</b></div><div><span>Inventory days</span><b>${last(ba.inventory_days) ?? "–"}</b></div></div></section>`;
  h += `<section class="rsec" id="s-bullbear"><h2>Bull and bear</h2><div class="bb"><div class="bull"><h3 class="up">Bull</h3><ul>${(a.bull || []).map(x => `<li>${esc(x.point)} ${srcChips(x.src)}</li>`).join("") || "<li>Not enough material.</li>"}</ul></div>
    <div class="bear"><h3 class="down">Bear</h3><ul>${(a.bear || []).map(x => `<li>${esc(x.point)} ${srcChips(x.src)}</li>`).join("") || "<li>Not enough material.</li>"}</ul></div></div>
    ${(a.watch || []).length ? `<h3 style="font-size:var(--s3);margin:18px 0 6px">Check next quarter</h3><ol class="watchlist">${a.watch.map(w => `<li>${esc(w)}</li>`).join("")}</ol>` : ""}</section>`;
  const sugg = ["What is the margin guidance?", "Why did working capital go up?", "What did they say about capex?"];
  h += `<section class="rsec" id="s-ask"><h2>Ask the documents</h2><p class="sub">Answers come only from this company's transcripts and annual report${(r.chunks || []).length ? `, ${r.chunks.length} passages indexed` : ""}.</p>
    <form class="ask" id="askf"><input id="askq" placeholder="Ask about guidance, capex, demand" aria-label="Question"><button class="btn" type="submit">Ask</button></form>
    <div class="suggest">${sugg.map(s => `<button class="chip" type="button" data-q="${esc(s)}">${esc(s)}</button>`).join("")}</div>
    <div class="answer" id="ans">${S.ask[r.symbol] || ""}</div></section>`;
  h += `<section class="rsec"><h2>Sources</h2><ul class="sources">${Object.entries(r.sources || {}).map(([k, v]) => `<li><b>${esc(k)}</b> <a href="${esc(v.url)}" target="_blank" rel="noopener">${esc(v.title)}</a></li>`).join("")}</ul>
    <p class="quiet">Primary documents only: reported financials, earnings-call transcripts, annual report. No news, broker notes or model memory.</p></section>`;
  $("#app").innerHTML = h;
  $$("[data-jump]").forEach(x => x.onclick = e => { e.preventDefault(); const t = $("#s-" + x.dataset.jump); if (t) t.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }); });
  $$("[data-src]").forEach(b => b.onclick = () => showSource(r, b.dataset.src));
  const f = $("#askf");
  f.onsubmit = e => { e.preventDefault(); ask(r, $("#askq").value); };
  $$("[data-q]").forEach(b => b.onclick = () => { $("#askq").value = b.dataset.q; ask(r, b.dataset.q); });
}
function showSource(r, id) {
  const key = id.split(":")[0], src = (r.sources || {})[key] || {};
  const ch = (r.chunks || []).filter(c => c.id === id || (c.id.split(":")[0] === key && !id.includes(":")));
  sheet(`<h3>${esc(src.title || id)}</h3><p class="srcnote">${esc(id)}${src.date ? ", " + esc(src.date) : ""}</p>
    ${ch.slice(0, 2).map(c => `<p class="passage">${esc(c.text)}</p>`).join("") || `<p>${key === "QR" || key === "PL" || key === "BS" || key === "CF" ? "Reported figures from the company's own results and annual accounts." : "Open the document for this page."}</p>`}
    <div class="actions">${src.url ? `<a class="act" href="${esc(src.url)}" target="_blank" rel="noopener">Open document</a>` : ""}<button class="act" type="button" data-close>Close</button></div>`);
}
/* client-side BM25, mirrors finn/engine/retrieval.py */
const STOP = new Set("the a an of to and in for on is are was were be by with that this it as at from we our you your have has had will would can could should also which there their them they its not but or if so than then into over about what how why when who did does do said say".split(" "));
const toks = s => (String(s || "").toLowerCase().match(/[a-z0-9%]+/g) || []).filter(w => !STOP.has(w) && w.length > 1);
function bm25(chunks, q, k = 3) {
  const qs = toks(q); if (!qs.length) return [];
  const docs = chunks.map(c => toks(c.text)), N = docs.length, avg = docs.reduce((s, d) => s + d.length, 0) / N, df = {};
  docs.forEach(d => new Set(d).forEach(w => df[w] = (df[w] || 0) + 1));
  return chunks.map((c, i) => {
    const tf = {}; docs[i].forEach(w => tf[w] = (tf[w] || 0) + 1);
    let s = 0;
    for (const w of qs) if (tf[w]) { const idf = Math.log(1 + (N - df[w] + .5) / (df[w] + .5)); s += idf * tf[w] * 2.2 / (tf[w] + 1.2 * (.25 + .75 * docs[i].length / avg)); }
    return [s, c];
  }).filter(x => x[0] > 0).sort((a, b) => b[0] - a[0]).slice(0, k).map(x => x[1]);
}
function highlight(text, q) {
  const ws = toks(q).filter(w => w.length > 2);
  let t = esc(text);
  if (ws.length) t = t.replace(new RegExp(`\\b(${ws.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})\\w*`, "gi"), "<mark>$&</mark>");
  return t;
}
async function ask(r, q) {
  q = (q || "").trim(); if (!q) return;
  const box = $("#ans");
  const hits = bm25(r.chunks || [], q);
  let html = "";
  if (API) {
    box.innerHTML = `<p class="quiet">Reading the transcripts</p>`;
    try {
      const res = await fetch(`${API}/api/ask`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ symbol: r.symbol, q }) });
      const j = await res.json();
      if (j.answer) html += `<p class="a">${esc(j.answer)}</p>`;
    } catch {}
  }
  if (!hits.length) html += `<p class="a">Nothing in the indexed transcripts or annual report matches that. Try the words management would use, like "guidance", "margin" or "capex".</p>`;
  else html += (html ? "" : `<p class="sub">Closest passages from the company's own documents:</p>`) + hits.map(c => `<div class="passage">${highlight(c.text, q)}<div>${srcChips([c.id])} <span class="srcnote" style="display:inline">${esc(c.title)}</span></div></div>`).join("");
  S.ask[r.symbol] = html;
  box.innerHTML = html;
  $$("[data-src]", box).forEach(b => b.onclick = () => showSource(r, b.dataset.src));
}
async function renderResearch(sym) {
  if (!sym) { $("#app").innerHTML = researchHome(); bindResearchHome(); return; }
  $("#app").innerHTML = researchHome(`<p class="quiet" id="rprog">Opening ${esc(sym)}</p>`);
  bindResearchHome();
  try { renderTear(await loadResearch(sym)); window.scrollTo(0, 0); }
  catch (e) {
    if (e.message === "cancelled") return;
    const msg = e.message === "offline"
      ? `<p class="banner">${esc(sym)} hasn't been built yet. Run <code>python -m finn research ${esc(sym)}</code>, or start <code>python -m finn serve</code> to research any symbol on demand.</p>`
      : `<p class="banner">${esc(e.message)}</p>`;
    $("#app").innerHTML = researchHome(msg); bindResearchHome();
  }
}
function bindResearchHome() {
  const f = $("#rs"); if (!f) return;
  f.onsubmit = e => { e.preventDefault(); const v = $("#rq").value.trim().toUpperCase().replace(/\.NS$/, ""); if (v) location.hash = "research-" + v; };
}

/* ---------- routing ---------- */
function route() {
  const h = (location.hash || "#brief").slice(1);
  const [view, sym] = h.startsWith("research-") ? ["research", h.slice(9).toUpperCase()] : [h || "brief", null];
  $$("#tabs a").forEach(a => a.setAttribute("aria-current", a.dataset.tab === view ? "page" : "false"));
  if (S.speaking && view !== "brief") { try { speechSynthesis.cancel(); } catch {} S.speaking = false; }
  if (view === "watch") renderWatch();
  else if (view === "ask") renderAsk();
  else if (view === "research") renderResearch(sym);
  else renderBrief();
  if (!sym) window.scrollTo(0, 0);
}

async function boot() {
  try {
    const r = await fetch("data/snapshot.json", { cache: "no-cache" });
    S.snap = await r.json();
  } catch {
    $("#app").innerHTML = `<p class="empty">No snapshot found. Run <code>python -m finn sample</code> or <code>python -m finn build</code>, then reload.</p>`;
    return;
  }
  S.rules = Object.assign(rulesDefault(), store.get("rules", {}));
  window.addEventListener("hashchange", route);
  route();
  if ("serviceWorker" in navigator && location.protocol.startsWith("http") && !/claude|claudeusercontent/.test(location.hostname)) {
    try { navigator.serviceWorker.register("sw.js").catch(() => {}); } catch {}
  }
}
boot();
})();
