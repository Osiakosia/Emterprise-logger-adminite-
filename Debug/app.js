/* ccTalk Logger Enterprise UI (multi-page, AdminLTE)
   Backend endpoints (Flask):
   GET  /api/status
   GET  /api/config
   POST /api/config
   POST /api/send        { dest, header, data_hex }
   POST /api/clear_log
   POST /api/connect     { port, baud }
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
    _busyConn: false,
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

  async function apiGet(url, timeoutMs = 2500) {
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), timeoutMs);

    try {
      const r = await fetch(url, { cache: "no-store", signal: ac.signal });
      if (!r.ok) throw new Error(`${url} ${r.status}`);
      return await r.json();
    } catch (e) {
      if (e?.name === "AbortError") {
        throw new Error(`timeout after ${timeoutMs}ms`);
      }
      throw e;
    } finally {
      clearTimeout(t);
    }
  }

  async function apiPost(url, payload, timeoutMs = 2000) {
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), timeoutMs);
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
        signal: ac.signal,
      });

      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.error || `${url} ${r.status}`);
      return j;
    } finally {
      clearTimeout(t);
    }
  }

  function safe(s) { return (s ?? "").toString(); }

  function stringifyDecoded(decoded) {
    if (decoded == null) return "";
    if (typeof decoded === "string") return decoded;
    try {
      return JSON.stringify(decoded, null, 0);
    } catch {
      return String(decoded);
    }
  }

    function isHexString(s) {
    const x = safe(s).trim();
    return x.length >= 2 && x.length % 2 === 0 && /^[0-9a-fA-F]+$/.test(x);
  }

  function hexToAscii(hex) {
    const x = safe(hex).trim();
    let out = "";
    for (let i = 0; i < x.length; i += 2) {
      const b = parseInt(x.slice(i, i + 2), 16);
      if (!Number.isFinite(b)) return null;
      out += String.fromCharCode(b);
    }
    return out;
  }

  function looksPrintableAscii(s) {
    const t = safe(s);
    for (let i = 0; i < t.length; i++) {
      const c = t.charCodeAt(i);
      const ok = (c === 9 || c === 10 || c === 13) || (c >= 32 && c <= 126);
      if (!ok) return false;
    }
    return true;
  }

  function prettySw(swRaw) {
    const sw = safe(swRaw).trim();
    if (!sw) return "-";

    // If it's hex, try decode to ASCII
    if (isHexString(sw)) {
      const ascii = hexToAscii(sw);
      if (ascii && looksPrintableAscii(ascii)) {
        const cleaned = ascii.replace(/\0/g, "").trim();
        if (cleaned) return cleaned;
      }
    }
    return sw;
  }
  function dedent(s) {
  const text = (s ?? "").replace(/^\n/, "");
  const lines = text.split("\n");

  // find minimum indentation of non-empty lines
  let min = null;
  for (const line of lines) {
    if (!line.trim()) continue;
    const m = line.match(/^(\s*)/);
    const n = m ? m[1].length : 0;
    if (min === null || n < min) min = n;
  }
  const cut = min ?? 0;

  return lines.map(l => l.slice(cut)).join("\n").trim();
}

  // Normalize a device list that can be either LIST or MAP
  function normDevicesList(devs) {
    const list = Array.isArray(devs)
      ? devs
      : (devs && typeof devs === "object")
        ? Object.keys(devs).map(k => {
            const d = devs[k] || {};
            return { ...d, address: parseInt(k, 10) };
          })
        : [];

    return list.map(d => ({
      address: parseInt(d.address, 10),
      name: d.name || d.kind || d.type || `Device ${d.address}`,
      type: d.type || d.kind || "",
      last_seen: d.last_seen || d.last_seen_ts || null,
      health: d.health || "",
      manufacturer: d.manufacturer || "",
      category: d.category || "",
      serial: d.serial || d.serial_raw || "",
      sw_rev: d.sw_rev || "",
      product_text: d.product_text || "",
      last_identify_ts: d.last_identify_ts ?? null,
    })).filter(d => Number.isFinite(d.address));
  }

  // ---- Normalize backend shape (supports: devices, devices_configured, devices_seen) ----
  function normStatus(raw) {
    const st = raw || {};

    // Backward compat:
    // - old backend: st.devices = configured
    // - new backend: st.devices = seen
    const devicesList = normDevicesList(st.devices);

    // New split lists (if backend provides them)
    const devicesConfigured = normDevicesList(st.devices_configured);
    const devicesSeen = normDevicesList(st.devices_seen);

    // frames: adapt FrameRecord snapshot => UI expects from/to/hex/decoded string
    const hostAddr = 1;
    const frames = Array.isArray(st.frames) ? st.frames : [];

    const uiFrames = frames.map(f => {
      const dir = safe(f.direction).toUpperCase();
      const addr = Number.isFinite(+f.addr) ? parseInt(f.addr, 10) : null;

      const from = (dir === "RX") ? addr : hostAddr;
      const to   = (dir === "TX") ? addr : hostAddr;

      return {
        ts: f.ts,
        time: f.time || "",
        direction: dir,
        from: from,
        to: to,
        hex: f.raw_hex || f.hex || "",
        decoded: stringifyDecoded(f.decoded),
        _addr: addr,
      };
    });

    let rx = 0, tx = 0;
    for (const f of uiFrames) {
      if (f.direction === "RX") rx++;
      else if (f.direction === "TX") tx++;
    }

    return {
      connected: !!st.connected,
      port: st.port || "",
      baud: st.baud || 0,
      validate_checksum: !!st.validate_checksum,
      last_error: st.last_error || "",

      // Keep old field name used in multiple pages:
      // Prefer split lists if present; otherwise fall back to st.devices
      devices_list: (devicesConfigured.length || devicesSeen.length)
        ? devicesSeen   // in new backend "devices" means seen; this keeps dashboard mini meaningful
        : devicesList,

      // New fields for Devices page
      devices_configured_list: devicesConfigured.length ? devicesConfigured : devicesList,
      devices_seen_list: devicesSeen.length ? devicesSeen : devicesList,

      frames_ui: uiFrames,
      counts: {
        rx: st.counts?.rx ?? rx,
        tx: st.counts?.tx ?? tx,
        decode_errors: st.counts?.decode_errors ?? 0,
        devices_seen: st.counts?.devices_seen ?? (devicesSeen.length || devicesList.length),
      }
    };
  }

  function renderTopBar(nst, cfg) {
    const conn = !!nst.connected;
    const connBadge = qs("connBadge");

    if (state._busyConn) {
      // keep whatever status text we set during connect/disconnect
    } else {
      badge(connBadge, conn ? "CONNECTED" : "DISCONNECTED", conn ? "badge-success" : "badge-secondary");
    }

    // Clickable connect/disconnect badge (bind once)
    if (connBadge && !state._connBadgeBound) {
      state._connBadgeBound = true;
      connBadge.style.cursor = "pointer";
      connBadge.addEventListener("click", async () => {
        if (state._busyConn) return;
        state._busyConn = true;

        try {
          const current = normStatus(state.status || await apiGet("/api/status"));
          const isConn = !!current.connected;

          const port = (state.cfg?.port || current.port || "COM4");
          const baud = Number(state.cfg?.baud || current.baud || 9600);

          badge(connBadge, isConn ? "DISCONNECTING…" : "CONNECTING…", "badge-warning");

          if (isConn) await apiPost("/api/disconnect", {});
          else await apiPost("/api/connect", { port, baud });

          state.lastFramesHash = "";
          await tick();
        } catch (e) {
          badge(connBadge, "ERROR", "badge-danger");
          console.error(e);
          setTimeout(() => { tick().catch(() => {}); }, 500);
        } finally {
          state._busyConn = false;
        }
      });
    }
    if (connBadge) connBadge.title = conn ? "Click to disconnect" : "Click to connect";

    const portLabel = qs("portLabel");
    const baudLabel = qs("baudLabel");
    if (portLabel) portLabel.textContent = safe(cfg?.port || nst.port || "-");
    if (baudLabel) baudLabel.textContent = safe(cfg?.baud || nst.baud || "-");

    const errEl = qs("lastError");
    if (errEl) {
      const le = safe(nst.last_error || "");
      errEl.textContent = le ? ("Error: " + le) : "";
      errEl.className = le ? "small text-danger" : "small text-muted";
    }
  }

  function renderCounters(nst) {
    const rx = qs("rxCount"); if (rx) rx.textContent = safe(nst.counts.rx ?? 0);
    const tx = qs("txCount"); if (tx) tx.textContent = safe(nst.counts.tx ?? 0);
    const err = qs("errCount"); if (err) err.textContent = safe(nst.counts.decode_errors ?? 0);
    const dev = qs("devCount"); if (dev) dev.textContent = safe(nst.counts.devices_seen ?? 0);
  }

  function fmtTime(tsOrStr) {
    return safe(tsOrStr);
  }

  function renderFrames(nst) {
    const tbody = qs("framesTbody");
    if (!tbody) return;

    const frames = nst.frames_ui || [];
    const hash = frames.length ? (frames[frames.length - 1].ts + "|" + frames.length) : "empty";
    if (hash === state.lastFramesHash) return;
    state.lastFramesHash = hash;

    const dirFilter = qs("dirFilter")?.value || "";
    const addrFilterRaw = qs("addrFilter")?.value || "";
    const textFilter = (qs("textFilter")?.value || "").toLowerCase();
    const addrFilter = addrFilterRaw.trim() ? parseInt(addrFilterRaw.trim(), 10) : null;

    let rows = frames;
    if (dirFilter) rows = rows.filter(f => (f.direction || "").toUpperCase() === dirFilter);
    if (Number.isFinite(addrFilter)) rows = rows.filter(f => (f.from === addrFilter) || (f.to === addrFilter) || (f._addr === addrFilter));
    if (textFilter) rows = rows.filter(f => {
      const hx = safe(f.hex).toLowerCase();
      const dc = safe(f.decoded).toLowerCase();
      return hx.includes(textFilter) || dc.includes(textFilter);
    });

    tbody.innerHTML = rows.map(f => {
      const dir = safe(f.direction).toUpperCase();
      const dirBadge = dir === "RX"
        ? '<span class="badge badge-info">RX</span>'
        : '<span class="badge badge-success">TX</span>';

      const decoded = safe(f.decoded);
      const decodedHtml = decoded ? `<span class="mono">${decoded}</span>` : '<span class="text-muted">—</span>';

      return `
        <tr>
          <td>${fmtTime(f.time || f.ts)}</td>
          <td>${dirBadge}</td>
          <td><span class="badge badge-light">${safe(f.from)}</span></td>
          <td><span class="badge badge-light">${safe(f.to)}</span></td>
          <td class="mono">${safe(f.hex)}</td>
          <td>${decodedHtml}</td>
        </tr>`;
    }).join("");

    if (window.PAGE_ID === "frames") {
      const container = tbody.closest(".table-responsive");
      if (container && !state.scrollLock) container.scrollTop = container.scrollHeight;
    }
  }

  // Renders a small list on Dashboard
  function renderDeviceMini(nst) {
    const host = qs("deviceMiniList");
    if (!host) return;

    // Prefer configured if present; otherwise fall back to whatever we have
    const devs = (nst.devices_configured_list && nst.devices_configured_list.length)
      ? nst.devices_configured_list
      : (nst.devices_list || []);

    if (!devs.length) {
      host.innerHTML = '<div class="p-3 text-muted">No devices configured.</div>';
      return;
    }

    const items = devs.slice(0, 8).map(d => {
      const addr = d.address;
      const name = safe(d.name || "Device");
      return `
        <div class="p-2 border-bottom">
          <div class="d-flex justify-content-between align-items-center">
            <div>
              <span class="badge badge-dark mr-1">${addr}</span>
              ${name}
            </div>
            <span class="badge badge-secondary">${safe(d.type || "")}</span>
          </div>
        </div>`;
    }).join("");

    host.innerHTML = items;
  }

  // Helper to create a "section" header
  function makeSectionHeader(title, badgeText, badgeCls) {
    const col = document.createElement("div");
    col.className = "col-12";
    col.innerHTML = `
      <div class="d-flex align-items-center justify-content-between mb-2 mt-2">
        <h5 class="mb-0">${title}</h5>
        <span class="badge badge-pill ${badgeCls}">${badgeText}</span>
      </div>
    `;
    return col;
  }

  function renderDevicesGrid(nst) {
  const grid = qs("devicesGrid");
  if (!grid || window.PAGE_ID !== "devices") return;

  const configured = nst.devices_configured_list || [];
  const seen = nst.devices_seen_list || [];

  const intro = grid.querySelector(".callout")?.closest(".col-12");
  grid.innerHTML = "";
  if (intro) grid.appendChild(intro);

  // If both empty -> show legacy message
  if (!configured.length && !seen.length) {
    const col = document.createElement("div");
    col.className = "col-12";
    col.innerHTML =
      '<div class="callout callout-warning"><h5><i class="fas fa-question-circle mr-1"></i>No devices</h5><p>Add devices to devices.json or scan the bus.</p></div>';
    grid.appendChild(col);
    return;
  }

  // ---- Seen on bus section ----
  if (seen.length) {
    grid.appendChild(makeSectionHeader("Seen on bus", `${seen.length}`, "badge-success"));
    seen
      .slice()
      .sort((a, b) => parseInt(a.address, 10) - parseInt(b.address, 10))
      .forEach(d => {
        const addr = d.address;
        const name = safe(d.name || `Device ${addr}`);
        const type = safe(d.type || "");
        const manufacturer = safe(d.manufacturer || "-");
        const category = safe(d.category || d.type || "-");
        const serial = safe(d.serial || "-");
        const sw = prettySw(d.sw_rev);

        const col = document.createElement("div");
        col.className = "col-lg-4 col-md-6";
        col.innerHTML = dedent(`
          <div class="card device-card border border-success">
            <div class="card-header">
              <h3 class="card-title">
                <span class="badge badge-dark mr-2">${addr}</span>${name}
              </h3>
              <div class="card-tools">
                <span class="badge badge-success">SEEN</span>
                <span class="badge badge-info ml-1">${type || "—"}</span>
              </div>
            </div>
            <div class="card-body">
              <div class="small text-muted">Discovered on the bus (RX / identify)</div>
              <div class="mt-2 small text-muted mono">
                <div><b>Manufacturer:</b> ${manufacturer}</div>
                <div><b>Type:</b> ${category}</div>
                <div><b>Serial:</b> ${serial}</div>
                <div><b>SW:</b> ${sw}</div>
              </div>
            </div>
          </div>
        `);
        grid.appendChild(col);
      });
  } else {
    grid.appendChild(makeSectionHeader("Seen on bus", "0", "badge-secondary"));
  }

  // ---- Configured section ----
  if (configured.length) {
    grid.appendChild(makeSectionHeader("Configured (devices.json)", `${configured.length}`, "badge-info"));
    configured
      .slice()
      .sort((a, b) => parseInt(a.address, 10) - parseInt(b.address, 10))
      .forEach(d => {
        const addr = d.address;
        const name = safe(d.name || `Device ${addr}`);
        const type = safe(d.type || "");
        const manufacturer = safe(d.manufacturer || "-");
        const category = safe(d.category || d.type || "-");
        const serial = safe(d.serial || "-");
        const sw = prettySw(d.sw_rev);

        const col = document.createElement("div");
        col.className = "col-lg-4 col-md-6";
        col.innerHTML = dedent(`
          <div class="card device-card">
            <div class="card-header">
              <h3 class="card-title">
                <span class="badge badge-dark mr-2">${addr}</span>${name}
              </h3>
              <div class="card-tools">
                <span class="badge badge-info">CONFIG</span>
                <span class="badge badge-secondary ml-1">${type || "—"}</span>
              </div>
            </div>
            <div class="card-body">
              <div class="small text-muted">Configured device from <span class="mono">devices.json</span></div>
              <div class="mt-2 small text-muted mono">
                <div><b>Manufacturer:</b> ${manufacturer}</div>
                <div><b>Type:</b> ${category}</div>
                <div><b>Serial:</b> ${serial}</div>
                <div><b>SW:</b> ${sw}</div>
              </div>
            </div>
          </div>
        `);
        grid.appendChild(col);
      });
  } else {
    grid.appendChild(makeSectionHeader("Configured (devices.json)", "0", "badge-secondary"));
  }
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

    // Devices page: Identify all seen
const idAllBtn = qs("btnIdentifyAllSeen");
if (idAllBtn) {
  idAllBtn.addEventListener("click", async (ev) => {
    ev.preventDefault();

    const stEl = qs("identifyAllSeenStatus");
    const progWrap = qs("identifyAllSeenProgress");
    const progBar = progWrap?.querySelector('.progress-bar');
    const setStatus = (msg, cls = "text-muted") => {
      if (!stEl) return;
      stEl.className = "small ml-2 " + cls;
      stEl.textContent = msg;
    };
    const setProgress = (done, total) => {
      if (!progBar || !progWrap) return;
      progWrap.style.display = total > 0 ? "" : "none";
      const pct = total > 0 ? Math.floor(100 * done / total) : 0;
      progBar.style.width = pct + "%";
      progBar.setAttribute("aria-valuenow", pct);
      progBar.textContent = done + " / " + total;
    };

    try {
      idAllBtn.disabled = true;
      setProgress(0, 0);

      // pull fresh status for seen list
      const raw = await apiGet("/api/status");
      state.status = raw;
      const nst = normStatus(raw);

      const seen = nst.devices_seen_list || [];
      if (!seen.length) {
        setStatus("No seen devices.", "text-muted");
        setProgress(0, 0);
        return;
      }

      setStatus(`Identifying ${seen.length} device(s)…`, "text-info");
      setProgress(0, seen.length);

      let ok = 0;
      let fail = 0;

      for (let i = 0; i < seen.length; i++) {
        const a = Number(seen[i].address);
        setStatus(`Identifying ${a} (${i + 1}/${seen.length})…`, "text-info");
        setProgress(i, seen.length);
        try {
          await apiPost("/api/identify", { dest: a }, 8000);
          ok++;
        } catch (e) {
          fail++;
          console.warn("Identify failed for", a, e);
        }
        await new Promise(res => setTimeout(res, 80));
      }

      setStatus(`Done. OK=${ok}, FAIL=${fail}`, fail ? "text-warning" : "text-success");
      setProgress(seen.length, seen.length);

      state.lastFramesHash = "";
      await tick();
    } catch (e) {
      console.error(e);
      setStatus("Identify error: " + (e?.message || e), "text-danger");
      setProgress(0, 0);
    } finally {
      idAllBtn.disabled = false;
      setTimeout(() => setProgress(0, 0), 1500); // Paslėpti po sekundėlės
    }
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
        if (state.status) {
          const nst = normStatus(state.status);
          renderFrames(nst);
        }
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
      const raw = await apiGet("/api/status");
      state.status = raw;

      const nst = normStatus(raw);
      renderTopBar(nst, state.cfg);
      renderCounters(nst);
      renderFrames(nst);
      renderDeviceMini(nst);
      renderDevicesGrid(nst);
    } catch (e) {
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