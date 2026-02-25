// ui/js/controller.js
// Device Controller page logic (full)
//
// Features:
// - /api/status devices supports LIST or MAP
// - Prevents sending to addr 0 when no device selected
// - Auto-refresh, scan, frames
// - Hopper / Recycler / Custom controls
// - Auto header buttons from /api/headers:
//   * Common headers shown in Coin/Hopper/Recycler as GRAY
//   * Specific headers shown only in their tab as BLUE
//   * Custom tab shows ALL with filter; DANGER shown as RED
// - Per-tab header filters (Coin/Hopper/Recycler/Custom)

let AUTO = null;
let BILL = null;
let STOP = false;

let AUTO_HEADERS_CACHE = [];

// -------------------------
// DOM helpers
// -------------------------
const qs = (id) => document.getElementById(id);

const setBadge = (el, cls, txt) => {
  if (!el) return;
  el.className = cls;
  el.textContent = txt;
};

// -------------------------
// API calls
// -------------------------
async function apiStatus() {
  const r = await fetch("/api/status", { cache: "no-store" });
  if (!r.ok) throw new Error("status");
  return await r.json();
}

async function apiSend(dest, header, dataHex) {
  const body = {
    dest: Number(dest),
    header: Number(header),
    data_hex: (dataHex || "").trim(),
  };

  const r = await fetch("/api/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const j = await r.json().catch(() => ({}));
  if (!r.ok || j.ok === false) throw new Error(j.error || "send");
  return j;
}

async function apiHeaders() {
  const r = await fetch("/api/headers", { cache: "no-store" });
  if (!r.ok) throw new Error("headers");
  return await r.json();
}

// -------------------------
// Selected address handling
// -------------------------
function selAddr() {
  const t = (qs("selAddr")?.textContent || "").trim();

  // initial UI shows "—"
  // Number("") === 0 -> would cause TX to dest=0 (wrong)
  if (t === "" || t === "—") return null;

  // only allow decimal integer string
  if (!/^\d+$/.test(t)) return null;

  const n = Number(t);
  if (!Number.isFinite(n) || n < 0 || n > 255) return null;
  return n;
}

function requireAddr() {
  const a = selAddr();
  if (a === null) {
    alert("Select a device on the left first (address must be a number).");
    return null;
  }
  return a;
}

// -------------------------
// Connection + health UI
// -------------------------
function health(dev) {
  const now = Date.now() / 1000;
  const last = dev?.last_seen_ts || 0;
  const d = now - last;
  return d < 2 ? "online" : d < 5 ? "slow" : "offline";
}

function updateConn(st) {
  const ok = !!(st.serial ? st.serial.connected : st.connected);

  setBadge(
    qs("connBadge"),
    ok ? "badge badge-success badge-pill" : "badge badge-secondary badge-pill",
    ok ? "CONNECTED" : "DISCONNECTED"
  );

  qs("portLabel").textContent = (st.serial ? st.serial.port : st.port) || "-";
  qs("baudLabel").textContent = (st.serial ? st.serial.baud : st.baud) || "-";
}

function updateHealth(dev) {
  const b = qs("healthBadge");
  if (!b) return;

  if (!dev) {
    setBadge(b, "badge badge-secondary badge-pill", "UNKNOWN");
    return;
  }

  const h = dev.health || health(dev);

  setBadge(
    b,
    h === "online"
      ? "badge badge-success badge-pill"
      : h === "slow"
        ? "badge badge-warning badge-pill"
        : "badge badge-danger badge-pill",
    h === "online" ? "ONLINE" : h === "slow" ? "SLOW" : "OFFLINE"
  );
}

// -------------------------
// Device display helpers
// -------------------------
function dispName(d) {
  const p = [];
  if (d.name) p.push(d.name);
  if (d.manufacturer) p.push(d.manufacturer);
  if (d.product) p.push(d.product);
  return p.filter(Boolean).join(" • ") || `Device ${d.address ?? d.addr ?? "?"}`;
}

function meta(d) {
  const b = [];
  if (d.kind) b.push(d.kind);
  if (d.equipment_category !== undefined) b.push(`cat:${d.equipment_category}`);
  if (d.last_seen) b.push(`seen:${d.last_seen}`);
  if (d.type) b.push(d.type);
  return b.join(" | ") || "—";
}

function autoTab(d) {
  if (!d) return;

  const cat = d.equipment_category;
  const kind = (d.kind || "").toLowerCase();

  if (kind === "coin" || cat === 2) $("#tab-coin").tab("show");
  else if (kind === "hopper" || cat === 6) $("#tab-hopper").tab("show");
  else if (kind === "bill" || kind === "recycler" || cat === 1) $("#tab-recycler").tab("show");
}

// -------------------------
// Devices list rendering (supports LIST or MAP)
// -------------------------
function normalizeDeviceList(devs) {
  const list = Array.isArray(devs) ? devs.slice() : Object.values(devs || {});
  list.sort((a, b) => Number(a.address) - Number(b.address));
  return list;
}

function renderDevices(devs) {
  const box = qs("deviceList");
  if (!box) return;

  const q = (qs("deviceSearch")?.value || "").toLowerCase().trim();
  const list = normalizeDeviceList(devs);

  const rows = [];
  for (const d of list) {
    const a = Number(d.address);
    if (!Number.isFinite(a)) continue;

    const label = `${a} ${dispName(d)} ${meta(d)}`.toLowerCase();
    if (q && !label.includes(q)) continue;

    const h = d.health || health(d);
    const dot = h === "online" ? "bg-success" : h === "slow" ? "bg-warning" : "bg-danger";

    rows.push(`
      <div class="d-flex align-items-center p-2 border rounded mb-1 device-row"
           data-addr="${a}" style="cursor:pointer;">
        <span class="badge badge-dark mr-2">${a}</span>
        <span class="${dot} mr-2"
              style="width:10px;height:10px;border-radius:50%;display:inline-block;"></span>
        <div>
          <div class="font-weight-bold" style="line-height:1.1">${dispName(d)}</div>
          <div class="small text-muted" style="line-height:1.1">${meta(d)}</div>
        </div>
      </div>
    `);
  }

  box.innerHTML = rows.length ? rows.join("") : `<div class="p-2 text-muted">No devices.</div>`;

  box.querySelectorAll(".device-row").forEach((el) => {
    el.addEventListener("click", () => selectDevice(el.getAttribute("data-addr"), list));
  });

  const cnt = qs("deviceCountBadge");
  if (cnt) cnt.textContent = String(list.length);
}

function selectDevice(addr, list) {
  const a = Number(addr);
  const d = Array.isArray(list) ? list.find((x) => Number(x.address) === a) : null;

  qs("selAddr").textContent = String(a);
  qs("selAddrBadge").textContent = String(a);
  qs("selName").textContent = d ? dispName(d) : `Address ${a}`;
  qs("selMeta").textContent = d ? meta(d) : "—";

  updateHealth(d);
  autoTab(d);
}

// -------------------------
// Frames table
// -------------------------
function renderFrames(frames) {
  const tb = qs("controllerFramesTbody");
  if (!tb) return;

  const last = (frames || []).slice(-12).reverse();

  tb.innerHTML = last
    .map(
      (f) => `
        <tr>
          <td>${f.time || ""}</td>
          <td>
            <span class="badge ${
              String(f.direction).toUpperCase() === "RX" ? "badge-success" : "badge-primary"
            }">${f.direction}</span>
          </td>
          <td>${f.from ?? ""}</td>
          <td>${f.to ?? ""}</td>
          <td><code>${f.hex || f.raw_hex || ""}</code></td>
          <td>${typeof f.decoded === "string" ? f.decoded : JSON.stringify(f.decoded || {})}</td>
        </tr>
      `
    )
    .join("");
}

// -------------------------
// Header classification + filtering (by NAME)
// -------------------------
function normName(s) {
  return String(s || "")
    .toLowerCase()
    .replace(/[_\-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function includesAny(name, keywords) {
  const n = normName(name);
  return keywords.some((k) => n.includes(k));
}

// Common — show in Coin/Hopper/Recycler tabs (GRAY)
const COMMON_KEYWORDS = [
  // your common set
  "request software revision",
  "request serial number",
  "request database version",
  "request product code",
  "request equipment category id",
  "request manufacturer id",
  "request variable set",
  "request polling priority",

  // basic
  "simple poll",
  "request comms revision",
  "request comms status variables",
  "clear comms status variables",

  // inhibit/credit (needed for recycler + coin)
  "request master inhibit status",
  "modify master inhibit status",
  "request inhibit status",
  "modify inhibit status",
  "read buffered credit or error codes",

  // address ops (you wanted in device tabs)
  "address random",
  "address change",
  "address clash",
  "address poll",
];

// Danger — show in Custom All only (RED)
const DANGER_KEYWORDS = [
  "emergency stop",
  "factory set-up",
  "reset device",

  // firmware/security
  "firmware upgrade",
  "upload firmware",
  "begin firmware upgrade",
  "finish firmware upgrade",
  "store encryption code",
  "switch encryption code",
];

// Specific per tab (BLUE)
const COIN_KEYWORDS = [
  "coin",
  "sorter",
  "sorter paths",
  "payout high / low status",
  "option flags",
  "credit",
];

const HOPPER_KEYWORDS = ["hopper", "dispense hopper", "test hopper", "payout"];

const RECYCLER_KEYWORDS = [
  "recycle",
  "recycler",
  "bill",
  "route bill",
  "escrow",
  "stack",
  "stack box",
  "barcode",
  "currency",
  "bank select",
];

function isCommonHeader(it) {
  return includesAny(it?.name || "", COMMON_KEYWORDS);
}

function isDangerHeader(it) {
  return includesAny(it?.name || "", DANGER_KEYWORDS);
}

function splitHeaders(headers) {
  const common = [];
  const coin = [];
  const hopper = [];
  const recycler = [];
  const other = [];

  for (const it of headers || []) {
    if (isDangerHeader(it)) {
      other.push(it);
      continue;
    }

    if (isCommonHeader(it)) {
      common.push(it);
      continue;
    }

    // Assign to exactly one tab by priority
    const name = it?.name || "";
    if (includesAny(name, RECYCLER_KEYWORDS)) recycler.push(it);
    else if (includesAny(name, HOPPER_KEYWORDS)) hopper.push(it);
    else if (includesAny(name, COIN_KEYWORDS)) coin.push(it);
    else other.push(it);
  }

  return { common, coin, hopper, recycler, other };
}

function headerLabel(it) {
  const h = Number(it.header);
  const name = String(it.name || `Header ${h}`);
  const hex = "0x" + h.toString(16).toUpperCase().padStart(2, "0");
  return `${name} (${h}, ${hex})`;
}

function matchesTextFilter(it, filterRaw) {
  const filter = String(filterRaw || "").trim().toLowerCase();
  if (!filter) return true;

  const h = Number(it.header);
  const name = String(it.name || "");
  const hex = "0x" + h.toString(16).toLowerCase().padStart(2, "0");

  return (
    String(h).includes(filter) ||
    hex.includes(filter) ||
    name.toLowerCase().includes(filter)
  );
}

function renderHeaderButtonsTo(containerId, items, { allowDanger = false, mode = "tab" } = {}) {
  // mode:
  // - "tab": common gray, others blue, danger excluded by default
  // - "custom": danger red, common gray, others blue
  const box = qs(containerId);
  if (!box) return;

  box.innerHTML = (items || [])
    .map((it) => {
      const danger = isDangerHeader(it);
      const common = isCommonHeader(it);

      if (danger && !allowDanger) return "";

      const cls =
        mode === "custom" && danger
          ? "btn btn-sm btn-outline-danger mr-2 mb-2"
          : common
            ? "btn btn-sm btn-outline-secondary mr-2 mb-2"
            : "btn btn-sm btn-outline-primary mr-2 mb-2";

      return `
        <button type="button"
                class="${cls}"
                data-header="${Number(it.header)}">
          ${headerLabel(it)}
        </button>
      `;
    })
    .join("");

  bindHeaderBtns();
}

function renderTabWithFilter(containerId, filterId, list) {
  const f = qs(filterId)?.value || "";
  const filtered = (list || []).filter((it) => matchesTextFilter(it, f));
  renderHeaderButtonsTo(containerId, filtered, { allowDanger: false, mode: "tab" });
}

function renderCustomAllWithFilter() {
  const f = qs("autoHeaderFilter")?.value || "";
  const filtered = (AUTO_HEADERS_CACHE || []).filter((it) => matchesTextFilter(it, f));
  renderHeaderButtonsTo("autoHeaderButtons", filtered, { allowDanger: true, mode: "custom" });
}

// -------------------------
// Load headers and render to all containers
// -------------------------
async function loadAutoHeaders() {
  const j = await apiHeaders();
  AUTO_HEADERS_CACHE = j.headers || [];

  const { common, coin, hopper, recycler } = splitHeaders(AUTO_HEADERS_CACHE);

  const coinList = common.concat(coin);
  const hopperList = common.concat(hopper);
  const recyclerList = common.concat(recycler);

  renderTabWithFilter("autoHeaderButtonsCoin", "autoHeaderFilterCoin", coinList);
  renderTabWithFilter("autoHeaderButtonsHopper", "autoHeaderFilterHopper", hopperList);
  renderTabWithFilter("autoHeaderButtonsRecycler", "autoHeaderFilterRecycler", recyclerList);

  renderCustomAllWithFilter();
}

// -------------------------
// Bind click handlers (static + dynamic buttons)
// -------------------------
function bindHeaderBtns() {
  document.querySelectorAll("[data-header]").forEach((btn) => {
    // prevent duplicate listeners when called multiple times
    if (btn.dataset.boundHeaderBtn === "1") return;
    btn.dataset.boundHeaderBtn = "1";

    btn.addEventListener("click", async () => {
      const addr = requireAddr();
      if (addr === null) return;

      try {
        const h = btn.getAttribute("data-header");
        const hex = btn.getAttribute("data-hex") || "";

        await apiSend(addr, h, hex);

        const r = qs("cmdResult");
        if (r) r.textContent = "Sent.";
      } catch (e) {
        const r = qs("cmdResult");
        if (r) r.textContent = "ERROR: " + e.message;
      }
    });
  });
}

// -------------------------
// Hopper tab
// -------------------------
function hopperCoins() {
  const amt = Number(qs("hopperAmount")?.value || 0);
  const el = qs("hopperCoins");
  if (!el) return 0;

  if (amt % 2 !== 0) {
    el.value = 0;
    return 0;
  }

  const c = amt / 2;
  el.value = c;
  return c;
}

function bindHopper() {
  qs("hopperAmount")?.addEventListener("input", hopperCoins);

  document.querySelectorAll("[data-quick-eur]").forEach((b) => {
    b.addEventListener("click", () => {
      qs("hopperAmount").value = b.getAttribute("data-quick-eur");
      hopperCoins();
    });
  });

  qs("btnHopperEnable")?.addEventListener("click", async () => {
    const addr = requireAddr();
    if (addr === null) return;
    await apiSend(addr, 164, "").catch(() => {});
  });

  qs("btnHopperStop")?.addEventListener("click", async () => {
    const addr = requireAddr();
    if (addr === null) return;
    await apiSend(addr, 172, "").catch(() => {});
  });

  qs("btnHopperPay")?.addEventListener("click", async () => {
    const addr = requireAddr();
    if (addr === null) return;

    const c = hopperCoins();
    if (c <= 0) {
      alert("Amount must be multiple of €2");
      return;
    }
    if (c > 255) {
      alert("Max 255 coins");
      return;
    }

    await apiSend(addr, 167, Number(c).toString(16).padStart(2, "0"));
  });

  hopperCoins();
}

// -------------------------
// Recycler tab
// -------------------------
function bindRecycler() {
  qs("btnEscrowStack")?.addEventListener("click", async () => {
    const addr = requireAddr();
    if (addr === null) return;
    await apiSend(addr, 154, "01").catch(() => {});
  });

  qs("btnEscrowReturn")?.addEventListener("click", async () => {
    const addr = requireAddr();
    if (addr === null) return;
    await apiSend(addr, 154, "00").catch(() => {});
  });

  qs("btnStartBillPoll")?.addEventListener("click", () => {
    const addr = requireAddr();
    if (addr === null) return;

    const ms = Math.max(200, Number(qs("billPollMs")?.value || 250));
    if (BILL) return;

    BILL = setInterval(() => apiSend(addr, 159, "").catch(() => {}), ms);
  });

  qs("btnStopBillPoll")?.addEventListener("click", () => {
    clearInterval(BILL);
    BILL = null;
  });
}

// -------------------------
// Custom tab
// -------------------------
function bindCustom() {
  qs("btnSendCustom")?.addEventListener("click", async () => {
    const addr = requireAddr();
    if (addr === null) return;

    try {
      const h = Number(qs("customHeader")?.value || 0);
      const data = (qs("customData")?.value || "").trim();

      await apiSend(addr, h, data);

      const r = qs("cmdResult");
      if (r) r.textContent = "Sent.";
    } catch (e) {
      const r = qs("cmdResult");
      if (r) r.textContent = "ERROR: " + e.message;
    }
  });
}

// -------------------------
// Scan
// -------------------------
async function scan() {
  STOP = false;

  const s = Number(qs("scanStart")?.value || 1);
  const e = Number(qs("scanEnd")?.value || 50);
  const d = Number(qs("scanDelay")?.value || 80);

  const st = qs("scanStatus");
  if (st) st.textContent = "Scanning…";

  for (let a = s; a <= e; a++) {
    if (STOP) break;

    try {
      await apiSend(a, 254, "");
    } catch (_) {
      // ignore
    }

    if (st) st.textContent = `Scan ${a}/${e}`;
    if (d) await new Promise((r) => setTimeout(r, d));
  }

  if (st) st.textContent = STOP ? "Stopped" : "Done";
}

function bindScan() {
  qs("btnScan")?.addEventListener("click", scan);
  qs("btnStopScan")?.addEventListener("click", () => {
    STOP = true;
  });
}

// -------------------------
// Refresh loop
// -------------------------
async function refresh() {
  const st = await apiStatus();

  updateConn(st);
  renderDevices(st.devices || []);
  renderFrames(st.frames || []);

  // update health for currently selected device
  const sel = (qs("selAddr")?.textContent || "").trim();
  const a = sel === "" || sel === "—" ? null : Number(sel);

  if (Number.isFinite(a) && Array.isArray(st.devices)) {
    const d = st.devices.find((x) => Number(x.address) === a);
    if (d) updateHealth(d);
  }
}

function startAuto() {
  if (AUTO) return;
  AUTO = setInterval(() => refresh().catch(() => {}), 1000);
}

function stopAuto() {
  clearInterval(AUTO);
  AUTO = null;
}

// -------------------------
// Init
// -------------------------
function init() {
  // bind static header buttons already in HTML
  bindHeaderBtns();

  bindHopper();
  bindRecycler();
  bindCustom();
  bindScan();

  qs("btnRefreshDevices")?.addEventListener("click", () => refresh().catch(() => {}));
  qs("deviceSearch")?.addEventListener("input", () => refresh().catch(() => {}));

  qs("autoRefreshSwitch")?.addEventListener("change", function () {
    this.checked ? startAuto() : stopAuto();
  });

  // --- Per-tab header filters ---
  qs("autoHeaderFilterCoin")?.addEventListener("input", () => {
    const { common, coin } = splitHeaders(AUTO_HEADERS_CACHE);
    renderTabWithFilter("autoHeaderButtonsCoin", "autoHeaderFilterCoin", common.concat(coin));
  });

  qs("autoHeaderFilterHopper")?.addEventListener("input", () => {
    const { common, hopper } = splitHeaders(AUTO_HEADERS_CACHE);
    renderTabWithFilter("autoHeaderButtonsHopper", "autoHeaderFilterHopper", common.concat(hopper));
  });

  qs("autoHeaderFilterRecycler")?.addEventListener("input", () => {
    const { common, recycler } = splitHeaders(AUTO_HEADERS_CACHE);
    renderTabWithFilter("autoHeaderButtonsRecycler", "autoHeaderFilterRecycler", common.concat(recycler));
  });

  // --- Custom filter + reload ---
  qs("autoHeaderFilter")?.addEventListener("input", renderCustomAllWithFilter);
  qs("btnReloadAutoHeaders")?.addEventListener("click", () => loadAutoHeaders().catch(() => {}));

  // load + render all header lists
  loadAutoHeaders().catch(() => {});

  refresh().catch(() => {});
  startAuto();
}

document.addEventListener("DOMContentLoaded", init);