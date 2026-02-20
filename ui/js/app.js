
/* ccTalk Logger Enterprise UI (multi-page, AdminLTE)
   Backend endpoints (Flask):
   GET  /api/status
   GET  /api/config
   POST /api/config
   POST /api/send_hex  { hex: "...", add_checksum: true/false }
   POST /api/clear_log
*/
(function () {
  const $ = window.jQuery;

  const state = {
    autorefresh: true,
    scrollLock: false,
    lastFramesHash: "",
    cfg: null,
    status: null,
  };

  function qs(id) { return document.getElementById(id); }

  function setActiveNav() {
    const pid = window.PAGE_ID || "dashboard";
    const map = {
      dashboard: "nav-dashboard",
      devices: "nav-devices",
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

  async function apiGet(url) {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error(`${url} ${r.status}`);
    return await r.json();
  }

  async function apiPost(url, payload) {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
    if (!r.ok) throw new Error(`${url} ${r.status}`);
    return await r.json();
  }

  function fmtTime(ts) {
    // backend provides ISO or something? in this project it's already a string
    return ts || "";
  }

  function safe(s) {
    return (s ?? "").toString();
  }

  function renderTopBar(status, cfg) {
    const conn = !!status?.serial?.connected;
    const connBadge = qs("connBadge");
    badge(connBadge, conn ? "CONNECTED" : "DISCONNECTED", conn ? "badge-success" : "badge-secondary");

    const portLabel = qs("portLabel");
    const baudLabel = qs("baudLabel");
    if (portLabel) portLabel.textContent = safe(cfg?.port || status?.serial?.port || "-");
    if (baudLabel) baudLabel.textContent = safe(cfg?.baud || status?.serial?.baud || "-");

    const checksumSwitch = qs("checksumSwitch");
    if (checksumSwitch && cfg) checksumSwitch.checked = (cfg.checksum_mode || "on") === "on";
  }

  function renderCounters(status) {
    const rx = qs("rxCount"); if (rx) rx.textContent = safe(status?.counts?.rx ?? 0);
    const tx = qs("txCount"); if (tx) tx.textContent = safe(status?.counts?.tx ?? 0);
    const err = qs("errCount"); if (err) err.textContent = safe(status?.counts?.decode_errors ?? 0);
    const dev = qs("devCount"); if (dev) dev.textContent = safe(Object.keys(status?.devices || {}).length);
  }

  function renderFrames(status) {
    const tbody = qs("framesTbody");
    if (!tbody) return;

    const frames = status?.frames || [];
    // Hash to avoid repainting too often
    const hash = frames.length ? (frames[frames.length - 1].ts + "|" + frames.length) : "empty";
    if (hash === state.lastFramesHash) {
      // still update decoded error counters etc elsewhere
      return;
    }
    state.lastFramesHash = hash;

    // apply filters (frames page)
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
          <td>${fmtTime(f.ts)}</td>
          <td>${dirBadge}</td>
          <td><span class="badge badge-light">${safe(f.from)}</span></td>
          <td><span class="badge badge-light">${safe(f.to)}</span></td>
          <td class="mono">${safe(f.hex)}</td>
          <td>${decodedHtml}</td>
        </tr>`;
    }).join("");

    // autoscroll on frames page if not locked
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
      return `
        <div class="p-2 border-bottom">
          <div class="d-flex justify-content-between">
            <div><span class="badge badge-dark mr-1">${addr}</span> ${name}</div>
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

    // keep the intro callout (first child) then append cards
    const intro = grid.querySelector(".callout")?.closest(".col-12");
    grid.innerHTML = "";
    if (intro) grid.appendChild(intro);

    if (!keys.length) {
      const col = document.createElement("div");
      col.className = "col-12";
      col.innerHTML = '<div class="callout callout-warning"><h5><i class="fas fa-question-circle mr-1"></i>No devices discovered yet</h5><p>Send a poll or request identification to known addresses (e.g. 1, 2, 4, 5, 6, 230…)</p></div>';
      grid.appendChild(col);
      return;
    }

    keys.sort((a,b)=>parseInt(a,10)-parseInt(b,10)).forEach(addr => {
      const d = devs[addr] || {};
      const kind = safe(d.kind || "");
      const name = safe(d.name || kind || "ccTalk device");
      const last = safe(d.last_seen || "");
      const caps = (d.capabilities || []).slice(0, 4);

      const col = document.createElement("div");
      col.className = "col-lg-4 col-md-6";
      col.innerHTML = `
        <div class="card device-card">
          <div class="card-header">
            <h3 class="card-title">
              <span class="badge badge-dark mr-2">${addr}</span>${name}
            </h3>
            <div class="card-tools">
              <span class="badge badge-secondary">${last ? "seen" : "—"}</span>
            </div>
          </div>
          <div class="card-body">
            <div class="mb-2">
              ${kind ? `<span class="badge badge-info">${kind}</span>` : ""}
              ${caps.map(c => `<span class="badge badge-light">${c}</span>`).join("")}
            </div>
            <div class="btn-group btn-group-sm" role="group">
              <button class="btn btn-outline-primary" data-action="poll" data-addr="${addr}"><i class="fas fa-satellite-dish mr-1"></i>Poll</button>
              <button class="btn btn-outline-primary" data-action="id" data-addr="${addr}"><i class="fas fa-id-card mr-1"></i>ID</button>
              <button class="btn btn-outline-primary" data-action="status" data-addr="${addr}"><i class="fas fa-heartbeat mr-1"></i>Status</button>
            </div>
            <div class="small text-muted mt-2 mono">Tip: Use these as templates; devices differ by manufacturer.</div>
          </div>
        </div>
      `;
      grid.appendChild(col);
    });

    // Wire quick actions (simple, generic ccTalk request templates)
    grid.querySelectorAll("button[data-action]").forEach(btn => {
      btn.addEventListener("click", async () => {
        const addr = parseInt(btn.getAttribute("data-addr"), 10);
        const action = btn.getAttribute("data-action");
        // Generic ccTalk frame format: [dest][len][src][cmd][data...][checksum]
        // Here we send minimal requests from SRC=1 to DEST=addr; checksum optional by UI setting.
        // cmd values are placeholders for common patterns; adjust to your device's command set.
        let cmd = 254; // default: simple poll is often 254 in ccTalk
        if (action === "id") cmd = 245;        // "Request manufacturer id" often 245 (varies)
        if (action === "status") cmd = 242;    // "Request status" often 242 (varies)
        const src = 1;
        const len = 0;
        const hex = [addr, len, src, cmd].map(b => b.toString(16).padStart(2, "0")).join("");
        try {
          const addCk = !!qs("checksumSwitch")?.checked;
          const res = await apiPost("/api/send_hex", { hex, add_checksum: addCk });
          flashSendResult(res);
        } catch (e) {
          flashSendResult({ ok: false, error: e.message });
        }
      });
    });
  }

  function flashSendResult(res) {
    const el = qs("sendResult");
    if (!el) return;
    if (res?.ok) {
      el.className = "small text-success";
      el.textContent = "Sent: " + safe(res.sent_hex || res.hex || "");
    } else {
      el.className = "small text-danger";
      el.textContent = "Error: " + safe(res?.error || "unknown");
    }
  }

  async function loadConfig() {
    try {
      state.cfg = await apiGet("/api/config");
    } catch (e) {
      // ignore
    }
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
        try {
          await apiPost("/api/clear_log", {});
        } catch (e) {}
      });
    }

    const scrollBtn = qs("btnScrollLock");
    if (scrollBtn) {
      scrollBtn.addEventListener("click", () => {
        state.scrollLock = !state.scrollLock;
        scrollBtn.classList.toggle("text-warning", state.scrollLock);
      });
    }

    const sendForm = qs("sendHexForm");
    if (sendForm) {
      sendForm.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const hex = (qs("hexInput")?.value || "").trim();
        const addCk = !!qs("checksumSwitch")?.checked;
        if (!hex) return;
        try {
          const res = await apiPost("/api/send_hex", { hex, add_checksum: addCk });
          flashSendResult(res);
          qs("hexInput").value = "";
        } catch (e) {
          flashSendResult({ ok: false, error: e.message });
        }
      });
    }

    const cfgForm = qs("configForm");
    if (cfgForm) {
      cfgForm.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const port = (qs("cfgPort")?.value || "").trim();
        const baud = parseInt(qs("cfgBaud")?.value || "0", 10);
        const checksum_mode = qs("cfgChecksum")?.value || "on";
        const out = qs("cfgResult");
        try {
          const res = await apiPost("/api/config", { port, baud, checksum_mode });
          if (out) { out.className = "ml-2 text-success small"; out.textContent = "Saved"; }
          state.cfg = res?.config || state.cfg;
        } catch (e) {
          if (out) { out.className = "ml-2 text-danger small"; out.textContent = "Error: " + e.message; }
        }
      });
    }

    // filters should trigger repaint
    ["dirFilter","addrFilter","textFilter"].forEach(id => {
      const el = qs(id);
      if (el) el.addEventListener("input", ()=> {
        // force repaint next tick
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
    const cs = qs("cfgChecksum"); if (cs) cs.value = (cfg.checksum_mode || "on");
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
      // show disconnected if failing
      badge(qs("connBadge"), "DISCONNECTED", "badge-secondary");
    }
  }

  async function init() {
    setActiveNav();
    wireCommonUI();
    await loadConfig();
    renderSettings(state.cfg);
    // initial tick then interval
    await tick();
    setInterval(tick, 1000);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
