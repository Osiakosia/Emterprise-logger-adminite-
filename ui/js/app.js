/* ccTalk Logger Enterprise UI (multi-page, AdminLTE)
   Backend endpoints (Flask):
   GET  /api/status
   GET  /api/config
   POST /api/config
   POST /api/send_hex  { hex: "...", add_checksum: true/false }
   POST /api/clear_log
   POST /api/connect
   POST /api/disconnect
*/
(function () {
  const state = {
    autorefresh: true,
    scrollLock: false,
    lastFramesHash: "",
    cfg: null,
    status: null,
    _connBadgeBound: false,
  };

  function qs(id) { return document.getElementById(id); }

  function setActiveNav() {
    const pid = window.PAGE_ID || "dashboard";
    const map = {
      dashboard: "nav-dashboard",
      devices: "nav-devices",
      controller: "nav-controller",
      frames: "nav-frames",
      settings: "nav-settings",
    };
    const elId = map[pid];
    if (elId) {
      const el = qs(elId);
      if (el) el.classList.add("active");
    }
  }

  function badge(el, text, cls) {
    if (!el) return;
    el.textContent = text;
    el.className = "badge badge-pill " + cls;
  }

  async function apiGet(url, timeoutMs = 900) {
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), timeoutMs);
    try {
      const r = await fetch(url, { cache: "no-store", signal: ac.signal });
      if (!r.ok) throw new Error(`${url} ${r.status}`);
      return await r.json();
    } finally {
      clearTimeout(t);
    }
  }

  async function apiPost(url, payload, timeoutMs = 1500) {
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), timeoutMs);
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
        signal: ac.signal,
      });
      // We want JSON even on 400/500 when server returns {ok:false,...}
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.error || `${url} ${r.status}`);
      return j;
    } finally {
      clearTimeout(t);
    }
  }

  function safe(s) { return (s ?? "").toString(); }

  function renderTopBar(status, cfg) {
    const conn = !!status?.serial?.connected;
    const connBadge = qs("connBadge");
    badge(connBadge, conn ? "CONNECTED" : "DISCONNECTED", conn ? "badge-success" : "badge-secondary");

    // Clickable connect/disconnect badge (bind once)
    if (connBadge && !state._connBadgeBound) {
      state._connBadgeBound = true;
      connBadge.style.cursor = "pointer";
      connBadge.addEventListener("click", async () => {
        try {
          const st = state.status || await apiGet("/api/status");
          const isConn = !!st?.serial?.connected;

          const port = (state.cfg?.port || st?.serial?.port || "COM4");
          const baud = Number(state.cfg?.baud || st?.serial?.baud || 9600);

          badge(connBadge, isConn ? "DISCONNECTING…" : "CONNECTING…", "badge-warning");

          if (isConn) await apiPost("/api/disconnect", {});
          else await apiPost("/api/connect", { port, baud });

          state.lastFramesHash = "";
          await tick();
        } catch (e) {
          // Don't freeze UI; just show error for a moment
          badge(connBadge, "ERROR", "badge-danger");
          console.error(e);
          setTimeout(() => { tick().catch(() => {}); }, 400);
        }
      });
    }
    if (connBadge) connBadge.title = conn ? "Click to disconnect" : "Click to connect";

    const portLabel = qs("portLabel");
    const baudLabel = qs("baudLabel");
    if (portLabel) portLabel.textContent = safe(cfg?.port || status?.serial?.port || "-");
    if (baudLabel) baudLabel.textContent = safe(cfg?.baud || status?.serial?.baud || "-");

    // Optional: show last_error somewhere if you have an element
    const errEl = qs("lastError");
    if (errEl) {
      const le = status?.serial?.last_error || "";
      errEl.textContent = le ? ("Error: " + le) : "";
      errEl.className = le ? "small text-danger" : "small text-muted";
    }
  }

  function renderCounters(status) {
    const rx = qs("rxCount"); if (rx) rx.textContent = safe(status?.counts?.rx ?? 0);
    const tx = qs("txCount"); if (tx) tx.textContent = safe(status?.counts?.tx ?? 0);
    const err = qs("errCount"); if (err) err.textContent = safe(status?.counts?.decode_errors ?? 0);
    const dev = qs("devCount"); if (dev) dev.textContent = safe(status?.counts?.devices_seen ?? Object.keys(status?.devices || {}).length);
  }

  function fmtTime(tsOrStr) {
    return safe(tsOrStr);
  }

  function renderFrames(status) {
    const tbody = qs("framesTbody");
    if (!tbody) return;

    const frames = status?.frames || [];
    const hash = frames.length ? (frames[frames.length - 1].ts + "|" + frames.length) : "empty";
    if (hash === state.lastFramesHash) return;
    state.lastFramesHash = hash;

    const dirFilter = qs("dirFilter")?.value || "";
    const addrFilterRaw = qs("addrFilter")?.value || "";
    const textFilter = (qs("textFilter")?.value || "").toLowerCase();
    const addrFilter = addrFilterRaw.trim() ? parseInt(addrFilterRaw.trim(), 10) : null;

    let rows = frames;
    if (dirFilter) rows = rows.filter(f => (f.direction || "").toUpperCase() === dirFilter);
    if (Number.isFinite(addrFilter)) rows = rows.filter(f => (f.from === addrFilter) || (f.to === addrFilter));
    if (textFilter) rows = rows.filter(f => (safe(f.hex).toLowerCase().includes(textFilter) || safe(f.decoded).toLowerCase().includes(textFilter)));

    tbody.innerHTML = rows.map(f => {
      const dir = safe(f.direction).toUpperCase();
      const dirBadge = dir === "RX"
        ? '<span class="badge badge-info">RX</span>'
        : '<span class="badge badge-success">TX</span>';
      const decoded = safe(f.decoded);
      const decodedHtml = decoded ? decoded : '<span class="text-muted">—</span>';
      return `
        <tr>
          <td>${fmtTime(f.time || f.ts)}</td>
          <td>${dirBadge}</td>
          <td><span class="badge badge-light">${safe(f.from)}</span></td>
          <td><span class="badge badge-light">${safe(f.to)}</span></td>
          <td class="mono">${safe(f.hex || f.raw_hex)}</td>
          <td>${decodedHtml}</td>
        </tr>`;
    }).join("");

    if (window.PAGE_ID === "frames") {
      const container = tbody.closest(".table-responsive");
      if (container && !state.scrollLock) container.scrollTop = container.scrollHeight;
    }
  }

  function renderDeviceMini(status) {
    const host = qs("deviceMiniList");
    if (!host) return;

    const devs = status?.devices || {};
    const keys = Object.keys(devs);
    if (!keys.length) {
      host.innerHTML = '<div class="p-3 text-muted">No devices yet.</div>';
      return;
    }

    const items = keys.slice(0, 8).map(addr => {
      const d = devs[addr] || {};
      const name = safe(d.name || d.kind || "Device");
      const last = safe(d.last_seen || d.last_seen_ts || "");
      const health = (d.health || "").toLowerCase();
      const dot = health === "online" ? "bg-success" : health === "slow" ? "bg-warning" : "bg-danger";

      return `
        <div class="p-2 border-bottom">
          <div class="d-flex justify-content-between align-items-center">
            <div>
              <span class="badge badge-dark mr-1">${addr}</span>
              <span class="${dot} mr-1" style="width:10px;height:10px;border-radius:50%;display:inline-block;"></span>
              ${name}
            </div>
            <span class="badge badge-secondary">${last ? "seen" : "—"}</span>
          </div>
        </div>`;
    }).join("");

    host.innerHTML = items;
  }

  function renderDevicesGrid(status) {
    const grid = qs("devicesGrid");
    if (!grid || window.PAGE_ID !== "devices") return;

    const devs = status?.devices || {};
    const keys = Object.keys(devs);

    const intro = grid.querySelector(".callout")?.closest(".col-12");
    grid.innerHTML = "";
    if (intro) grid.appendChild(intro);

    if (!keys.length) {
      const col = document.createElement("div");
      col.className = "col-12";
      col.innerHTML = '<div class="callout callout-warning"><h5><i class="fas fa-question-circle mr-1"></i>No devices discovered yet</h5><p>Send a poll or request identification to known addresses (e.g. 1, 2, 4, 5, 6, 40…)</p></div>';
      grid.appendChild(col);
      return;
    }

    keys.sort((a,b)=>parseInt(a,10)-parseInt(b,10)).forEach(addr => {
      const d = devs[addr] || {};
      const kind = safe(d.kind || "");
      const name = safe(d.name || kind || "ccTalk device");
      const last = safe(d.last_seen || "");
      const health = (d.health || "").toLowerCase();
      const healthBadge = health === "online" ? "badge-success" : health === "slow" ? "badge-warning" : "badge-danger";

      const col = document.createElement("div");
      col.className = "col-lg-4 col-md-6";
      col.innerHTML = `
        <div class="card device-card">
          <div class="card-header">
            <h3 class="card-title">
              <span class="badge badge-dark mr-2">${addr}</span>${name}
            </h3>
            <div class="card-tools">
              <span class="badge ${healthBadge}">${health ? health.toUpperCase() : "—"}</span>
            </div>
          </div>
          <div class="card-body">
            <div class="mb-2">
              ${kind ? `<span class="badge badge-info">${kind}</span>` : ""}
              ${last ? `<span class="badge badge-light">seen ${last}</span>` : `<span class="badge badge-light">—</span>`}
            </div>
            <div class="small text-muted mono">Manufacturer: ${safe(d.manufacturer || "-")} • Product: ${safe(d.product || "-")}</div>
          </div>
        </div>
      `;
      grid.appendChild(col);
    });
  }

  async function loadConfig() {
    try { state.cfg = await apiGet("/api/config"); } catch (e) { /* ignore */ }
  }

  function wireCommonUI() {
    const auto = qs("autoRefreshSwitch");
    if (auto) {
      auto.addEventListener("change", () => { state.autorefresh = !!auto.checked; });
      state.autorefresh = !!auto.checked;
    }

    const clearBtn = qs("btnClearLog");
    if (clearBtn) {
      clearBtn.addEventListener("click", async (ev) => {
        ev.preventDefault();
        try { await apiPost("/api/clear_log", {}); } catch (e) {}
      });
    }

    const scrollBtn = qs("btnScrollLock");
    if (scrollBtn) {
      scrollBtn.addEventListener("click", () => {
        state.scrollLock = !state.scrollLock;
        scrollBtn.classList.toggle("text-warning", state.scrollLock);
      });
    }

    const cfgForm = qs("configForm");
    if (cfgForm) {
      cfgForm.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const port = (qs("cfgPort")?.value || "").trim();
        const baud = parseInt(qs("cfgBaud")?.value || "0", 10);
        const validate_checksum = !!qs("cfgValidateChecksum")?.checked;
        const out = qs("cfgResult");
        try {
          await apiPost("/api/config", { port, baud, validate_checksum });
          if (out) { out.className = "ml-2 text-success small"; out.textContent = "Saved"; }
          await loadConfig();
          await tick();
        } catch (e) {
          if (out) { out.className = "ml-2 text-danger small"; out.textContent = "Error: " + e.message; }
        }
      });
    }

    // filters trigger repaint
    ["dirFilter","addrFilter","textFilter"].forEach(id => {
      const el = qs(id);
      if (el) el.addEventListener("input", ()=> {
        state.lastFramesHash = "";
        if (state.status) renderFrames(state.status);
      });
    });
  }

  function renderSettings(cfg) {
    if (window.PAGE_ID !== "settings") return;
    if (!cfg) return;
    const port = qs("cfgPort"); if (port && !port.value) port.value = cfg.port || "";
    const baud = qs("cfgBaud"); if (baud && !baud.value) baud.value = cfg.baud || "";
    const v = qs("cfgValidateChecksum");
    if (v) v.checked = !!cfg.validate_checksum;
  }

  async function tick() {
    if (!state.autorefresh) return;
    try {
      const status = await apiGet("/api/status");
      state.status = status;
      renderTopBar(status, state.cfg);
      renderCounters(status);
      renderFrames(status);
      renderDeviceMini(status);
      renderDevicesGrid(status);
    } catch (e) {
      // Never freeze UI on slow/hung backend; show disconnected but keep timer running.
      badge(qs("connBadge"), "DISCONNECTED", "badge-secondary");
      console.warn("status fetch failed", e);
    }
  }

  async function init() {
    setActiveNav();
    wireCommonUI();
    await loadConfig();
    renderSettings(state.cfg);
    await tick();
    setInterval(() => { tick().catch(() => {}); }, 1000);
  }

  document.addEventListener("DOMContentLoaded", init);
})();