// SPDX-License-Identifier: Apache-2.0
const APP = "phong-may";
const BASE = `/apps/${APP}/`;
const API = `${BASE}api`;
const REALM = "/auth/realms/saigonos";
const PROCESS = "phong_may.dat_phong";
const ZONE = "Asia/Ho_Chi_Minh";
const OFFSET = "+07:00";
const REFRESH_MARGIN = 15000;
const POLL = 30000;
const ROLE = {
  teacher: "phong-may.giao-vien",
  manager: "phong-may.phu-trach",
  staff: "phong-may.chuyen-vien",
  student: "phong-may.hoc-sinh",
};
const ROLE_NAMES = {
  [ROLE.teacher]: "Giáo viên, giảng viên",
  [ROLE.manager]: "Phụ trách phòng",
  [ROLE.staff]: "Chuyên viên",
  [ROLE.student]: "Học sinh, sinh viên",
};
const STATUS = {
  cho_duyet: ["Chờ duyệt", "status-waiting"],
  da_duyet: ["Đã duyệt", "status-approved"],
  san_sang: ["Sẵn sàng", "status-ready"],
  tu_choi: ["Từ chối", "status-rejected"],
};
const PURPOSE = { day_hoc: "Dạy học", thi: "Thi, kiểm tra" };
const DECISIONS = { dong_y: "Đồng ý", tu_choi: "Từ chối" };
const LIVE_TABS = new Set(["tong-quan", "don-cua-toi", "cho-duyet", "chuan-bi", "tat-ca", "lich", "thong-bao"]);
const WEEKDAYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];
const SVG = "http://www.w3.org/2000/svg";
const ICONS = {
  overview:
    '<rect x="3" y="3" width="7" height="9"/><rect x="14" y="3" width="7" height="5"/><rect x="14" y="12" width="7" height="9"/><rect x="3" y="16" width="7" height="5"/>',
  add: '<rect x="3" y="5" width="18" height="16"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="8" y1="3" x2="8" y2="7"/><line x1="16" y1="3" x2="16" y2="7"/><line x1="12" y1="13" x2="12" y2="19"/><line x1="9" y1="16" x2="15" y2="16"/>',
  document:
    '<path d="M6 3h9l4 4v14H6z"/><polyline points="14 3 14 8 19 8"/><line x1="9" y1="13" x2="16" y2="13"/><line x1="9" y1="17" x2="16" y2="17"/>',
  approve: '<rect x="3" y="3" width="18" height="18"/><polyline points="8 12 11 15 16 9"/>',
  list: '<line x1="9" y1="6" x2="20" y2="6"/><line x1="9" y1="12" x2="20" y2="12"/><line x1="9" y1="18" x2="20" y2="18"/><line x1="4" y1="6" x2="5" y2="6"/><line x1="4" y1="12" x2="5" y2="12"/><line x1="4" y1="18" x2="5" y2="18"/>',
  monitor: '<rect x="3" y="4" width="18" height="12"/><line x1="8" y1="20" x2="16" y2="20"/><line x1="12" y1="16" x2="12" y2="20"/>',
  prepare:
    '<rect x="5" y="4" width="14" height="17"/><rect x="9" y="2" width="6" height="4"/><polyline points="9 13 11 15 15 11"/>',
  calendar:
    '<rect x="3" y="5" width="18" height="16"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="8" y1="3" x2="8" y2="7"/><line x1="16" y1="3" x2="16" y2="7"/><rect x="7" y="13" width="3" height="3"/>',
  bell: '<path d="M6 16v-5a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
  clock: '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/>',
};
const numberFormat = new Intl.NumberFormat("vi-VN");
const K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);
const H0 = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];

const session = { token: null, refresh: null, idToken: null, expires: 0, claims: {} };
const state = {
  config: null,
  roles: new Set(),
  rooms: [],
  tab: null,
  week: null,
  focus: null,
  flash: null,
  unread: 0,
  counts: {},
  ticket: 0,
  editing: false,
  filters: { status: "", room: "", text: "", scheduleRoom: "" },
};
let refreshing = null;

const dayFormat = new Intl.DateTimeFormat("vi-VN", {
  timeZone: ZONE,
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});
const timeFormat = new Intl.DateTimeFormat("vi-VN", {
  timeZone: ZONE,
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});
const weekdayFormat = new Intl.DateTimeFormat("vi-VN", { timeZone: ZONE, weekday: "long" });
const isoDayFormat = new Intl.DateTimeFormat("en-CA", {
  timeZone: ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const day = (value) => dayFormat.format(new Date(value));
const time = (value) => timeFormat.format(new Date(value));
const isoDay = (value) => isoDayFormat.format(new Date(value));
const today = () => isoDay(Date.now());
const instant = (dayValue, timeValue) => `${dayValue}T${timeValue}:00${OFFSET}`;
const pause = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
const hasAny = (...roles) => roles.some((role) => state.roles.has(role));
const roomOf = (id) => state.rooms.find((room) => room.id === id);

function period(start, end) {
  if (isoDay(start) === isoDay(end)) {
    return `${time(start)}–${time(end)}, ${day(start)}`;
  }
  return `${time(start)} ${day(start)} – ${time(end)} ${day(end)}`;
}

function shiftDay(value, days) {
  const [year, month, date] = value.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, date + days)).toISOString().slice(0, 10);
}

function weekStart(value) {
  const [year, month, date] = value.split("-").map(Number);
  const weekday = new Date(Date.UTC(year, month - 1, date)).getUTCDay();
  return shiftDay(value, -((weekday + 6) % 7));
}

const noon = (value) => new Date(`${value}T12:00:00${OFFSET}`);

function dayTitle(value) {
  const weekday = weekdayFormat.format(noon(value));
  return `${weekday.charAt(0).toUpperCase()}${weekday.slice(1)}, ${day(noon(value))}`;
}


function sha256(data) {
  const size = Math.ceil((data.length + 9) / 64) * 64;
  const padded = new Uint8Array(size);
  padded.set(data);
  padded[data.length] = 0x80;
  const view = new DataView(padded.buffer);
  view.setUint32(size - 8, Math.floor(data.length / 0x20000000));
  view.setUint32(size - 4, (data.length * 8) >>> 0);
  const hash = Uint32Array.from(H0);
  const words = new Uint32Array(64);
  const rotate = (value, bits) => (value >>> bits) | (value << (32 - bits));
  for (let offset = 0; offset < size; offset += 64) {
    for (let index = 0; index < 16; index += 1) {
      words[index] = view.getUint32(offset + index * 4);
    }
    for (let index = 16; index < 64; index += 1) {
      const early = words[index - 15];
      const late = words[index - 2];
      const first = rotate(early, 7) ^ rotate(early, 18) ^ (early >>> 3);
      const second = rotate(late, 17) ^ rotate(late, 19) ^ (late >>> 10);
      words[index] = words[index - 16] + first + words[index - 7] + second;
    }
    let [a, b, c, d, e, f, g, h] = hash;
    for (let index = 0; index < 64; index += 1) {
      const choice = (e & f) ^ (~e & g);
      const one = (h + (rotate(e, 6) ^ rotate(e, 11) ^ rotate(e, 25)) + choice + K[index] + words[index]) >>> 0;
      const majority = (a & b) ^ (a & c) ^ (b & c);
      const two = ((rotate(a, 2) ^ rotate(a, 13) ^ rotate(a, 22)) + majority) >>> 0;
      [h, g, f, e, d, c, b, a] = [g, f, e, (d + one) >>> 0, c, b, a, (one + two) >>> 0];
    }
    [a, b, c, d, e, f, g, h].forEach((value, index) => {
      hash[index] += value;
    });
  }
  const result = new Uint8Array(32);
  const output = new DataView(result.buffer);
  hash.forEach((value, index) => output.setUint32(index * 4, value));
  return result;
}

async function digest(text) {
  const bytes = new TextEncoder().encode(text);
  if (globalThis.crypto?.subtle) {
    return new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  }
  return sha256(bytes);
}

function base64url(bytes) {
  let text = "";
  for (const byte of bytes) {
    text += String.fromCharCode(byte);
  }
  return btoa(text).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

function randomText(size) {
  const bytes = new Uint8Array(size);
  crypto.getRandomValues(bytes);
  return base64url(bytes);
}

function claimsOf(token) {
  const part = token.split(".")[1].replaceAll("-", "+").replaceAll("_", "/");
  const text = atob(part.padEnd(Math.ceil(part.length / 4) * 4, "="));
  return JSON.parse(new TextDecoder().decode(Uint8Array.from(text, (char) => char.charCodeAt(0))));
}

const redirectUri = () => `${location.origin}${BASE}`;

async function login() {
  const verifier = randomText(48);
  const challenge = base64url(await digest(verifier));
  const nonce = randomText(16);
  const back = `${location.search}${location.hash}`;
  sessionStorage.setItem("pkce", JSON.stringify({ verifier, state: nonce, back }));
  const query = new URLSearchParams({
    client_id: APP,
    redirect_uri: redirectUri(),
    response_type: "code",
    scope: "openid",
    code_challenge: challenge,
    code_challenge_method: "S256",
    response_mode: "fragment",
    state: nonce,
  });
  location.assign(`${state.config.authorization_endpoint}?${query}`);
}

function keep(tokens) {
  session.token = tokens.access_token;
  session.refresh = tokens.refresh_token ?? session.refresh;
  session.idToken = tokens.id_token ?? session.idToken;
  session.expires = Date.now() + tokens.expires_in * 1000;
  session.claims = claimsOf(tokens.access_token);
  const saved = {
    token: session.token,
    refresh: session.refresh,
    idToken: session.idToken,
    expires: session.expires,
  };
  sessionStorage.setItem("tokens", JSON.stringify(saved));
}

async function exchange(form) {
  const reply = await fetch(state.config.token_endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams(form),
  });
  if (!reply.ok) {
    return false;
  }
  keep(await reply.json());
  return true;
}

async function finishLogin(params) {
  const saved = JSON.parse(sessionStorage.getItem("pkce") ?? "null");
  sessionStorage.removeItem("pkce");
  if (!saved || saved.state !== params.get("state")) {
    throw new Error("Phiên đăng nhập không khớp. Hãy mở lại trang để đăng nhập.");
  }
  const done = await exchange({
    grant_type: "authorization_code",
    client_id: APP,
    redirect_uri: redirectUri(),
    code: params.get("code"),
    code_verifier: saved.verifier,
  });
  if (!done) {
    throw new Error("Không đổi được mã đăng nhập lấy access token. Hãy mở lại trang.");
  }
  history.replaceState(null, "", `${BASE}${saved.back}`);
}

function restore() {
  const saved = JSON.parse(sessionStorage.getItem("tokens") ?? "null");
  if (!saved?.refresh) {
    return false;
  }
  Object.assign(session, saved, { claims: claimsOf(saved.token) });
  return true;
}

async function accessToken() {
  if (Date.now() < session.expires - REFRESH_MARGIN) {
    return session.token;
  }
  refreshing ??= exchange({
    grant_type: "refresh_token",
    client_id: APP,
    refresh_token: session.refresh,
  }).finally(() => {
    refreshing = null;
  });
  if (!(await refreshing)) {
    sessionStorage.removeItem("tokens");
    await login();
    throw new Error("Phiên đăng nhập đã hết hạn. Đang mở trang đăng nhập.");
  }
  return session.token;
}

function logout() {
  const query = new URLSearchParams({
    client_id: APP,
    post_logout_redirect_uri: redirectUri(),
  });
  if (session.idToken) {
    query.set("id_token_hint", session.idToken);
  }
  sessionStorage.clear();
  location.assign(`${state.config.end_session_endpoint}?${query}`);
}

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function messageOf(status, data) {
  if (typeof data?.message === "string") {
    return data.message;
  }
  if (typeof data?.detail === "string") {
    return data.detail;
  }
  if (Array.isArray(data?.detail)) {
    return data.detail.map((item) => item.msg).join(" ");
  }
  if (status === 403) {
    return "Tài khoản không có quyền làm việc này.";
  }
  return `Máy chủ trả lời lỗi ${status}.`;
}

async function call(path, { method = "GET", body, headers = {} } = {}) {
  const token = await accessToken();
  const options = { method, headers: { Authorization: `Bearer ${token}`, ...headers } };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const reply = await fetch(path, options);
  const text = await reply.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!reply.ok) {
    throw new ApiError(reply.status, messageOf(reply.status, data));
  }
  return data;
}

const api = (path, options) => call(`${API}/${path}`, options);
const core = (path, options) => call(`/core/${path}`, options);

function h(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) {
      continue;
    }
    if (key === "class") {
      node.className = value;
    } else if (key.startsWith("on")) {
      node.addEventListener(key.slice(2), value);
    } else if (value === true) {
      node.setAttribute(key, "");
    } else {
      node.setAttribute(key, value);
    }
  }
  node.append(...children.flat(Infinity).filter((child) => child !== null && child !== undefined && child !== false));
  return node;
}

function icon(name) {
  const node = document.createElementNS(SVG, "svg");
  node.setAttribute("viewBox", "0 0 24 24");
  node.setAttribute("aria-hidden", "true");
  node.innerHTML = ICONS[name];
  return node;
}

function s(tag, attributes = {}, text = null) {
  const node = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attributes)) {
    node.setAttribute(key, String(value));
  }
  if (text !== null) {
    node.textContent = text;
  }
  return node;
}

function tile(name, label, value, note, warn = false) {
  return h(
    "div",
    { class: "tile" },
    h(
      "div",
      {},
      h("p", { class: "tile-label" }, label),
      h("p", { class: "tile-value" }, numberFormat.format(value)),
      h("p", { class: warn ? "tile-note overdue" : "tile-note" }, note),
    ),
    icon(name),
  );
}

function niceStep(max) {
  if (max <= 5) {
    return 1;
  }
  const rough = max / 4;
  const power = 10 ** Math.floor(Math.log10(rough));
  return [1, 2, 5, 10].map((factor) => factor * power).find((step) => step >= rough);
}

function chartBox(draw) {
  const box = h("div", { class: "chart-box" });
  let drawn = 0;
  box.redraw = () => {
    if (drawn) {
      box.replaceChildren(draw(drawn));
    }
  };
  new ResizeObserver(([entry]) => {
    const width = Math.floor(entry.contentRect.width);
    if (width > 0 && width !== drawn) {
      drawn = width;
      box.replaceChildren(draw(width));
    }
  }).observe(box);
  return box;
}

function columnChart(items, unit, label, width) {
  const [height, left, right, top, bottom] = [240, 36, 8, 20, 40];
  const max = Math.max(0, ...items.map((item) => item.value));
  const step = niceStep(max);
  const ceiling = Math.max(step, Math.ceil(max / step) * step);
  const inner = height - top - bottom;
  const slot = (width - left - right) / items.length;
  const chart = s("svg", { viewBox: `0 0 ${width} ${height}`, class: "chart", role: "img", "aria-label": label });
  for (let tick = 0; tick <= ceiling; tick += step) {
    const y = top + inner - (tick / ceiling) * inner;
    chart.append(
      s("line", { x1: left, x2: width - right, y1: y, y2: y, class: "grid" }),
      s("text", { x: left - 8, y: y + 4, class: "axis", "text-anchor": "end" }, numberFormat.format(tick)),
    );
  }
  items.forEach((item, index) => {
    const barWidth = Math.min(34, slot * 0.6);
    const center = left + index * slot + slot / 2;
    const barHeight = (item.value / ceiling) * inner;
    const y = top + inner - barHeight;
    const bar = s("rect", { x: center - barWidth / 2, y, width: barWidth, height: barHeight, class: "bar" });
    bar.append(s("title", {}, `${item.label} ${item.note}: ${numberFormat.format(item.value)} ${unit}`));
    chart.append(bar);
    if (item.value) {
      chart.append(s("text", { x: center, y: y - 6, class: "value", "text-anchor": "middle" }, numberFormat.format(item.value)));
    }
    chart.append(
      s("text", { x: center, y: height - 22, class: "axis", "text-anchor": "middle" }, item.label),
      s("text", { x: center, y: height - 8, class: "axis", "text-anchor": "middle" }, item.note),
    );
  });
  return chart;
}


function notice(kind, content) {
  const lines = Array.isArray(content) ? content : [content];
  const text = lines.length > 1 ? h("ul", {}, lines.map((line) => h("li", {}, line))) : h("p", {}, lines[0]);
  return h("div", { class: `notice notice-${kind}`, role: kind === "error" ? "alert" : "status" }, text);
}

function statusLabel(value) {
  const [label, kind] = STATUS[value] ?? [value, "status-waiting"];
  return h("span", { class: `status ${kind}` }, label);
}

function panel(title, body, tools = null) {
  return h(
    "section",
    { class: "panel" },
    h("div", { class: "panel-head" }, h("h2", {}, title), tools),
    h("div", { class: "panel-body" }, body),
  );
}

function table(headers, rows) {
  return h(
    "div",
    { class: "table-wrap" },
    h(
      "table",
      {},
      h("thead", {}, h("tr", {}, headers.map((name) => h("th", { scope: "col" }, name)))),
      h("tbody", {}, rows),
    ),
  );
}

function field(label, control, { hint, wide } = {}) {
  const error = h("p", { class: "field-error", id: `${control.id}-loi`, hidden: true });
  control.setAttribute("aria-describedby", error.id);
  control.errorBox = error;
  return h(
    "div",
    { class: wide ? "field field-wide" : "field" },
    h("label", { for: control.id }, label),
    control,
    hint ? h("p", { class: "hint" }, hint) : null,
    error,
  );
}

function choiceField(label, name, options, chosen) {
  const id = `${name}-nhan`;
  return h(
    "div",
    { class: "field" },
    h("span", { class: "label", id }, label),
    h(
      "div",
      { class: "choices", role: "radiogroup", "aria-labelledby": id },
      Object.entries(options).map(([value, text]) =>
        h("label", {}, h("input", { type: "radio", name, value, checked: value === chosen }), text),
      ),
    ),
  );
}

function setError(control, message) {
  control.setAttribute("aria-invalid", message ? "true" : "false");
  control.errorBox.textContent = message ?? "";
  control.errorBox.hidden = !message;
}

function chosen(container, name) {
  return container.querySelector(`input[name="${name}"]:checked`)?.value;
}

function facts(pairs) {
  return h(
    "dl",
    { class: "facts" },
    pairs.filter(([, value]) => value !== null && value !== undefined && value !== "").map(([name, value]) => [h("dt", {}, name), h("dd", {}, value)]),
  );
}

function reveal() {
  requestAnimationFrame(() => document.querySelector("tr.highlight")?.scrollIntoView({ block: "center" }));
}

function bookingOf(task) {
  const found = /(\d+)\s*$/.exec(task.description ?? "");
  return found ? Number(found[1]) : null;
}

function dueText(task) {
  if (!task.due) {
    return "";
  }
  const late = new Date(task.due) < new Date();
  return h(
    "span",
    { class: late ? "overdue nowrap" : "nowrap" },
    `${time(task.due)} ${day(task.due)}`,
    late ? " (quá hạn)" : "",
  );
}

function outcome(row) {
  if (row.trang_thai === "cho_duyet") {
    return `Hạn duyệt ${time(row.han_duyet)} ${day(row.han_duyet)}`;
  }
  if (row.trang_thai === "san_sang") {
    return [`${row.so_may_san_sang}/${row.so_may} máy sẵn sàng.`, row.ghi_chu_chuan_bi].filter(Boolean).join(" ");
  }
  if (row.trang_thai === "da_duyet") {
    return row.y_kien ?? "Chờ chuyên viên chuẩn bị phòng.";
  }
  return row.y_kien ?? "";
}

async function loadRooms() {
  state.rooms = await api("phong?order=ma");
  return state.rooms;
}

async function schedule({ room, from, to }) {
  const query = new URLSearchParams({ order: "bat_dau" });
  query.append("bat_dau", `gte.${from}T00:00:00${OFFSET}`);
  query.append("bat_dau", `lt.${to}T00:00:00${OFFSET}`);
  if (room) {
    query.set("ma_phong", `eq.${room}`);
  }
  return api(`lich?${query}`);
}

async function checkProblems(value) {
  const query = new URLSearchParams({
    ma_phong: value.ma_phong,
    bat_dau: value.bat_dau,
    ket_thuc: value.ket_thuc,
    so_may: String(value.so_may),
  });
  return api(`rpc/kiem_tra_don?${query}`);
}

const QUARTERS = Array.from({ length: 65 }, (_, index) => {
  const minutes = 360 + index * 15;
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
});

function hourOf(clock) {
  const [hours, minutes] = clock.split(":").map(Number);
  return hours + minutes / 60;
}

function later(clock, hours) {
  return QUARTERS.find((item) => hourOf(item) >= Math.min(hourOf(clock) + hours, 22)) ?? "22:00";
}

function timeSelect(id, chosen) {
  return h(
    "select",
    { id, required: true },
    QUARTERS.map((item) => h("option", { value: item, selected: item === chosen }, item)),
  );
}

function dayLine(rows, picked, good, width) {
  const [first, last, height] = [6, 22, 60];
  const scale = (width - 4) / (last - first);
  const x = (hours) => 2 + (Math.min(Math.max(hours, first), last) - first) * scale;
  const chart = s("svg", {
    viewBox: `0 0 ${width} ${height}`,
    class: "chart",
    role: "img",
    "aria-label": "Lịch của phòng trong ngày, từ 6 giờ đến 22 giờ",
  });
  chart.append(s("rect", { x: x(first), y: 8, width: x(last) - x(first), height: 26, class: "base" }));
  for (const row of rows) {
    const from = hourOf(time(row.bat_dau));
    const to = hourOf(time(row.ket_thuc)) || 24;
    const block = s("rect", { x: x(from), y: 8, width: Math.max(x(to) - x(from), 2), height: 26, class: `booked-${row.trang_thai}` });
    block.append(s("title", {}, `${time(row.bat_dau)}–${time(row.ket_thuc)}: ${row.lop}`));
    chart.append(block);
  }
  for (let hour = first; hour <= last; hour += 1) {
    chart.append(s("line", { x1: x(hour), x2: x(hour), y1: 8, y2: 34, class: "tick" }));
    if (hour % 2 === 0) {
      const anchor = hour === first ? "start" : hour === last ? "end" : "middle";
      chart.append(s("text", { x: x(hour), y: 52, class: "axis", "text-anchor": anchor }, `${hour}h`));
    }
  }
  if (picked && picked.to > picked.from) {
    const box = { x: x(picked.from), y: 5, width: x(picked.to) - x(picked.from), height: 32 };
    chart.append(s("rect", { ...box, class: good ? "picked" : "picked picked-bad" }));
  }
  return chart;
}

function bookingView() {
  const controls = {
    room: h(
      "select",
      { id: "f-phong", required: true },
      state.rooms.map((room) => h("option", { value: room.ma }, `${room.ten} (${room.so_may} máy)`)),
    ),
    day: h("input", { id: "f-ngay", type: "date", required: true, min: today(), value: shiftDay(today(), 1) }),
    count: h("input", {
      id: "f-so-may",
      type: "number",
      required: true,
      min: "1",
      max: "500",
      step: "1",
      value: "30",
      inputmode: "numeric",
    }),
    from: timeSelect("f-tu-gio", "07:00"),
    to: timeSelect("f-den-gio", "09:00"),
    course: h("input", {
      id: "f-lop",
      type: "text",
      required: true,
      maxlength: "100",
      placeholder: "Ví dụ: Lập trình cơ bản, lớp K50A",
    }),
    software: h("textarea", {
      id: "f-phan-mem",
      rows: "3",
      maxlength: "1000",
      placeholder: "Ví dụ: Visual Studio Code, Python 3.12",
    }),
    note: h("textarea", { id: "f-ghi-chu", rows: "2", maxlength: "1000" }),
  };
  const message = h("div", { "aria-live": "polite" });
  const submit = h("button", { type: "submit", class: "button" }, "Gửi đơn");
  const form = h(
    "form",
    { novalidate: true },
    h(
      "div",
      { class: "form-grid form-three" },
      field("Phòng", controls.room),
      field("Ngày", controls.day),
      field("Số máy cần", controls.count),
      field("Từ giờ", controls.from),
      field("Đến giờ", controls.to),
      choiceField("Mục đích", "muc_dich", PURPOSE, "day_hoc"),
      field("Lớp hoặc học phần", controls.course, { wide: true }),
      field("Phần mềm cần cài", controls.software, {
        wide: true,
        hint: "Chuyên viên cài các phần mềm này trước buổi học.",
      }),
      field("Ghi chú", controls.note, { wide: true }),
    ),
    message,
    h("div", { class: "actions" }, submit),
  );
  const heading = h("p", { class: "side-heading" });
  const capacity = h("p", { class: "muted side-note" });
  const check = h("div", { "aria-live": "polite" });
  const list = h("div");
  let drawing = { rows: [], picked: null, good: true };
  const line = chartBox((width) => dayLine(drawing.rows, drawing.picked, drawing.good, width));
  const slot = () => ({
    ma_phong: controls.room.value,
    bat_dau: instant(controls.day.value, controls.from.value),
    ket_thuc: instant(controls.day.value, controls.to.value),
    so_may: Number(controls.count.value),
  });
  let checking = 0;
  let timer = null;
  const recheck = async () => {
    const ticket = ++checking;
    if (!controls.day.value || !Number(controls.count.value)) {
      check.replaceChildren();
      return [];
    }
    const value = slot();
    const room = state.rooms.find((item) => item.ma === value.ma_phong);
    const [problems, rows] = await Promise.all([
      checkProblems(value),
      schedule({ room: value.ma_phong, from: controls.day.value, to: shiftDay(controls.day.value, 1) }),
    ]);
    if (ticket !== checking) {
      return problems;
    }
    heading.textContent = `${room.ten}, ${dayTitle(controls.day.value)}`;
    capacity.textContent = `Phòng có ${room.so_may} máy dùng được.`;
    check.replaceChildren(
      problems.length ? notice("error", problems) : notice("success", "Phòng còn trống và đủ máy cho giờ bạn chọn."),
    );
    drawing = {
      rows,
      picked: { from: hourOf(controls.from.value), to: hourOf(controls.to.value) },
      good: !problems.length,
    };
    line.redraw();
    list.replaceChildren(
      rows.length
        ? h(
            "ul",
            { class: "plain-list" },
            rows.map((row) =>
              h(
                "li",
                {},
                h("span", { class: "nowrap" }, `${time(row.bat_dau)}–${time(row.ket_thuc)}`),
                ` ${row.lop}, ${row.ten_nguoi_gui} `,
                statusLabel(row.trang_thai),
              ),
            ),
          )
        : h("p", { class: "muted" }, "Chưa có buổi nào được duyệt trong ngày này."),
    );
    return problems;
  };
  const soon = () => {
    clearTimeout(timer);
    timer = setTimeout(() => recheck().catch((error) => check.replaceChildren(notice("error", error.message))), 300);
  };
  controls.from.addEventListener("input", () => {
    if (controls.to.value <= controls.from.value) {
      controls.to.value = later(controls.from.value, 2);
    }
  });
  for (const control of [controls.room, controls.day, controls.from, controls.to, controls.count]) {
    control.addEventListener("input", soon);
  }
  form.addEventListener("input", () => {
    state.editing = true;
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const course = controls.course.value.trim();
    const count = Number(controls.count.value);
    setError(controls.course, course ? null : "Hãy nhập lớp hoặc học phần.");
    setError(controls.day, controls.day.value ? null : "Hãy chọn ngày.");
    setError(controls.to, controls.to.value <= controls.from.value ? "Giờ kết thúc phải sau giờ bắt đầu." : null);
    setError(controls.count, Number.isInteger(count) && count >= 1 && count <= 500 ? null : "Số máy cần từ 1 đến 500.");
    if (form.querySelector('[aria-invalid="true"]')) {
      form.querySelector('[aria-invalid="true"]').focus();
      return;
    }
    submit.disabled = true;
    message.replaceChildren();
    try {
      const problems = await recheck();
      if (problems.length) {
        message.replaceChildren(notice("error", problems));
        return;
      }
      const variables = {
        ...slot(),
        lop: course,
        muc_dich: chosen(form, "muc_dich"),
        phan_mem: controls.software.value.trim() || null,
        ghi_chu: controls.note.value.trim() || null,
      };
      await core(`processes/${PROCESS}/start`, { method: "POST", body: { variables } });
      state.flash = {
        kind: "success",
        text: "Đã gửi đơn. Phụ trách phòng sẽ duyệt đơn, kết quả được báo ở mục Thông báo.",
      };
      await pause(1500);
      open("don-cua-toi");
    } catch (error) {
      message.replaceChildren(notice("error", error.message));
    } finally {
      submit.disabled = false;
    }
  });
  soon();
  const steps = h(
    "ol",
    { class: "steps" },
    h("li", {}, h("strong", {}, "Gửi đơn. "), "Chọn phòng, giờ và số máy cần."),
    h(
      "li",
      {},
      h("strong", {}, "Phụ trách phòng duyệt. "),
      "Hạn duyệt là 24 giờ sau khi gửi và chậm nhất 2 giờ trước buổi học.",
    ),
    h("li", {}, h("strong", {}, "Chuyên viên chuẩn bị phòng. "), "Phần mềm được cài trước buổi học."),
  );
  return h(
    "div",
    { class: "split" },
    panel("Thông tin đơn", form),
    h(
      "div",
      {},
      panel("Lịch của phòng trong ngày", [
        heading,
        capacity,
        check,
        line,
        h("p", { class: "hint" }, "Phần tô màu là buổi đã duyệt. Khung viền là giờ bạn chọn."),
        list,
      ]),
      panel("Các bước xử lý đơn", [steps, h("p", { class: "muted" }, "Kết quả của từng bước được báo ở mục Thông báo.")]),
    ),
  );
}

async function mineView() {
  const query = new URLSearchParams({
    nguoi_gui: `eq.${session.claims.sub}`,
    order: "gui_luc.desc",
    limit: "100",
  });
  const rows = await api(`don?${query}`);
  if (!rows.length) {
    return panel("Đơn đã gửi", [
      h("p", { class: "empty" }, "Bạn chưa gửi đơn nào."),
      h("button", { type: "button", class: "button", onclick: () => open("dat-phong") }, "Đặt phòng"),
    ]);
  }
  return panel(
    "Đơn đã gửi",
    table(
      ["Số đơn", "Phòng", "Thời gian", "Lớp hoặc học phần", "Mục đích", "Số máy", "Trạng thái", "Kết quả"],
      rows.map((row) =>
        h(
          "tr",
          { class: row.id === state.focus ? "highlight" : null },
          h("td", {}, String(row.id)),
          h("td", { class: "nowrap" }, roomOf(row.phong_id)?.ten ?? ""),
          h("td", { class: "nowrap" }, period(row.bat_dau, row.ket_thuc)),
          h("td", {}, row.lop),
          h("td", {}, PURPOSE[row.muc_dich]),
          h("td", {}, String(row.so_may)),
          h("td", {}, statusLabel(row.trang_thai)),
          h("td", {}, outcome(row)),
        ),
      ),
    ),
  );
}

function taskPanel({ title, empty, headers, items, cells, form }) {
  if (!items.length) {
    return panel(title, h("p", { class: "empty" }, empty));
  }
  const rows = items.map((item) => {
    const row = h("tr", { class: item.row.id === state.focus ? "highlight" : null });
    const action = h("button", { type: "button", class: "button button-small" }, "Xử lý");
    action.addEventListener("click", () => {
      row.parentElement.querySelector("tr.detail-row")?.remove();
      const detail = h("tr", { class: "detail-row" }, h("td", { colspan: String(headers.length + 1) }));
      const close = () => {
        detail.remove();
        state.editing = false;
      };
      detail.firstChild.append(form(item, close));
      row.after(detail);
      state.editing = true;
    });
    row.append(...cells(item).map((cell) => h("td", {}, cell)), h("td", {}, action));
    return row;
  });
  return panel(title, table([...headers, ""], rows));
}

async function tasksWith(key, status) {
  const [tasks, rows] = await Promise.all([
    core("tasks?limit=200"),
    api(`don?${new URLSearchParams({ trang_thai: `eq.${status}`, order: "bat_dau" })}`),
  ]);
  const byId = new Map(rows.map((row) => [row.id, row]));
  return tasks
    .filter((task) => task.task_key === key)
    .map((task) => ({ task, row: byId.get(bookingOf(task)) }))
    .filter((item) => item.row);
}

async function complete(item, variables) {
  if (!item.task.assignee) {
    await core(`tasks/${item.task.id}/claim`, { method: "POST" });
  }
  await core(`tasks/${item.task.id}/complete`, { method: "POST", body: { variables } });
}

function decisionForm(item, close) {
  const name = `ket_qua_${item.task.id}`;
  const comment = h("textarea", { id: `y-kien-${item.task.id}`, rows: "2", maxlength: "1000" });
  const message = h("div", { "aria-live": "polite" });
  const save = h("button", { type: "submit", class: "button" }, "Lưu kết quả");
  const form = h(
    "form",
    { novalidate: true },
    facts([
      ["Phần mềm cần cài", item.row.phan_mem],
      ["Ghi chú", item.row.ghi_chu],
      ["Gửi lúc", `${time(item.row.gui_luc)} ${day(item.row.gui_luc)}`],
    ]),
    message,
    choiceField("Kết quả", name, DECISIONS, "dong_y"),
    field("Ý kiến", comment, { hint: "Bắt buộc khi từ chối. Giáo viên đọc được ý kiến này." }),
    h(
      "div",
      { class: "actions" },
      save,
      h("button", { type: "button", class: "button button-secondary", onclick: close }, "Đóng"),
    ),
  );
  checkProblems({
    ma_phong: roomOf(item.row.phong_id)?.ma,
    bat_dau: item.row.bat_dau,
    ket_thuc: item.row.ket_thuc,
    so_may: item.row.so_may,
  })
    .then((problems) => {
      if (problems.length) {
        message.replaceChildren(notice("warning", problems));
      }
    })
    .catch(() => {});
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const decision = chosen(form, name);
    const text = comment.value.trim();
    setError(comment, decision === "tu_choi" && !text ? "Hãy ghi lý do từ chối." : null);
    if (decision === "tu_choi" && !text) {
      comment.focus();
      return;
    }
    save.disabled = true;
    try {
      await complete(item, { ket_qua: decision, y_kien: text || null });
      state.flash = { kind: "success", text: `Đã lưu kết quả cho đơn số ${item.row.id}.` };
      state.editing = false;
      await pause(1200);
      show();
    } catch (error) {
      message.replaceChildren(notice("error", error.message));
      save.disabled = false;
    }
  });
  return form;
}

async function approvalView() {
  const items = await tasksWith("duyet", "cho_duyet");
  return taskPanel({
    title: "Đơn cần duyệt",
    empty: "Không có đơn nào chờ duyệt.",
    headers: ["Số đơn", "Người gửi", "Phòng", "Thời gian", "Số máy", "Mục đích", "Lớp hoặc học phần", "Hạn duyệt"],
    items,
    cells: ({ task, row }) => [
      String(row.id),
      row.ten_nguoi_gui,
      h("span", { class: "nowrap" }, roomOf(row.phong_id)?.ten ?? ""),
      h("span", { class: "nowrap" }, period(row.bat_dau, row.ket_thuc)),
      String(row.so_may),
      PURPOSE[row.muc_dich],
      row.lop,
      dueText(task),
    ],
    form: decisionForm,
  });
}

function preparationForm(item, close) {
  const count = h("input", {
    id: `san-sang-${item.task.id}`,
    class: "number-input",
    type: "number",
    min: "0",
    max: "500",
    step: "1",
    value: String(item.row.so_may),
    inputmode: "numeric",
  });
  const note = h("textarea", { id: `ghi-chu-${item.task.id}`, rows: "2", maxlength: "1000" });
  const message = h("div", { "aria-live": "polite" });
  const save = h("button", { type: "submit", class: "button" }, "Xác nhận phòng sẵn sàng");
  const form = h(
    "form",
    { novalidate: true },
    facts([
      ["Phần mềm cần cài", item.row.phan_mem ?? "Không có"],
      ["Ghi chú của giáo viên", item.row.ghi_chu],
      ["Ý kiến khi duyệt", item.row.y_kien],
    ]),
    message,
    field("Số máy sẵn sàng", count, { hint: `Đơn cần ${item.row.so_may} máy.` }),
    field("Ghi chú chuẩn bị", note),
    h(
      "div",
      { class: "actions" },
      save,
      h("button", { type: "button", class: "button button-secondary", onclick: close }, "Đóng"),
    ),
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const ready = Number(count.value);
    const valid = count.value !== "" && Number.isInteger(ready) && ready >= 0 && ready <= 500;
    setError(count, valid ? null : "Số máy sẵn sàng từ 0 đến 500.");
    if (!valid) {
      count.focus();
      return;
    }
    save.disabled = true;
    try {
      await complete(item, { so_may_san_sang: ready, ghi_chu_chuan_bi: note.value.trim() || null });
      state.flash = { kind: "success", text: `Đã báo phòng sẵn sàng cho đơn số ${item.row.id}.` };
      state.editing = false;
      await pause(1200);
      show();
    } catch (error) {
      message.replaceChildren(notice("error", error.message));
      save.disabled = false;
    }
  });
  return form;
}

async function preparationView() {
  const items = await tasksWith("chuan_bi", "da_duyet");
  return taskPanel({
    title: "Phòng cần chuẩn bị",
    empty: "Không có phòng nào cần chuẩn bị.",
    headers: ["Số đơn", "Phòng", "Thời gian", "Số máy", "Mục đích", "Lớp hoặc học phần", "Giáo viên", "Hạn chuẩn bị"],
    items,
    cells: ({ task, row }) => [
      String(row.id),
      h("span", { class: "nowrap" }, roomOf(row.phong_id)?.ten ?? ""),
      h("span", { class: "nowrap" }, period(row.bat_dau, row.ket_thuc)),
      String(row.so_may),
      PURPOSE[row.muc_dich],
      row.lop,
      row.ten_nguoi_gui,
      dueText(task),
    ],
    form: preparationForm,
  });
}

async function allView() {
  const query = new URLSearchParams({ order: "bat_dau.desc", limit: "200" });
  if (state.filters.status) {
    query.set("trang_thai", `eq.${state.filters.status}`);
  }
  if (state.filters.room) {
    query.set("phong_id", `eq.${state.filters.room}`);
  }
  const rows = await api(`don?${query}`);
  const status = h(
    "select",
    { id: "loc-trang-thai", onchange: (event) => {
      state.filters.status = event.target.value;
      show();
    } },
    h("option", { value: "" }, "Mọi trạng thái"),
    Object.entries(STATUS).map(([value, [label]]) => h("option", { value, selected: value === state.filters.status }, label)),
  );
  const room = h(
    "select",
    { id: "loc-phong", onchange: (event) => {
      state.filters.room = event.target.value;
      show();
    } },
    h("option", { value: "" }, "Mọi phòng"),
    state.rooms.map((item) => h("option", { value: String(item.id), selected: String(item.id) === state.filters.room }, item.ten)),
  );
  const search = h("input", {
    id: "loc-tu-khoa",
    type: "search",
    value: state.filters.text,
    placeholder: "Lớp, người gửi, phần mềm",
  });
  const body = h("tbody");
  const draw = () => {
    const words = state.filters.text.trim().toLowerCase();
    const shown = rows.filter((row) =>
      !words || [row.lop, row.ten_nguoi_gui, row.phan_mem ?? ""].join(" ").toLowerCase().includes(words),
    );
    body.replaceChildren(
      ...(shown.length
        ? shown.map((row) =>
            h(
              "tr",
              { class: row.id === state.focus ? "highlight" : null },
              h("td", {}, String(row.id)),
              h("td", {}, row.ten_nguoi_gui),
              h("td", { class: "nowrap" }, roomOf(row.phong_id)?.ten ?? ""),
              h("td", { class: "nowrap" }, period(row.bat_dau, row.ket_thuc)),
              h("td", {}, row.lop),
              h("td", {}, PURPOSE[row.muc_dich]),
              h("td", {}, String(row.so_may)),
              h("td", {}, statusLabel(row.trang_thai)),
              h("td", {}, outcome(row)),
            ),
          )
        : [h("tr", {}, h("td", { colspan: "9", class: "muted" }, "Không có đơn nào khớp bộ lọc."))]),
    );
  };
  search.addEventListener("input", () => {
    state.filters.text = search.value;
    draw();
  });
  draw();
  const headers = ["Số đơn", "Người gửi", "Phòng", "Thời gian", "Lớp hoặc học phần", "Mục đích", "Số máy", "Trạng thái", "Kết quả"];
  return panel("Danh sách đơn", [
    h(
      "div",
      { class: "toolbar" },
      field("Trạng thái", status),
      field("Phòng", room),
      field("Tìm", search),
    ),
    h(
      "div",
      { class: "table-wrap" },
      h("table", {}, h("thead", {}, h("tr", {}, headers.map((name) => h("th", { scope: "col" }, name)))), body),
    ),
  ]);
}

async function scheduleView() {
  state.week ??= weekStart(today());
  const end = shiftDay(state.week, 7);
  const rows = await schedule({ room: state.filters.scheduleRoom, from: state.week, to: end });
  const move = (days) => () => {
    state.week = days === 0 ? weekStart(today()) : shiftDay(state.week, days);
    show();
  };
  const room = h(
    "select",
    { id: "lich-phong", onchange: (event) => {
      state.filters.scheduleRoom = event.target.value;
      show();
    } },
    h("option", { value: "" }, "Mọi phòng"),
    state.rooms.map((item) => h("option", { value: item.ma, selected: item.ma === state.filters.scheduleRoom }, item.ten)),
  );
  const tools = h(
    "div",
    { class: "actions" },
    h("button", { type: "button", class: "button button-secondary", onclick: move(-7) }, "Tuần trước"),
    h("button", { type: "button", class: "button button-secondary", onclick: move(0) }, "Tuần này"),
    h("button", { type: "button", class: "button button-secondary", onclick: move(7) }, "Tuần sau"),
  );
  const groups = new Map();
  for (const row of rows) {
    const key = isoDay(row.bat_dau);
    groups.set(key, [...(groups.get(key) ?? []), row]);
  }
  const body = [];
  for (const [key, items] of groups) {
    body.push(h("tr", { class: "day-row" }, h("td", { colspan: "6" }, dayTitle(key))));
    for (const row of items) {
      body.push(
        h(
          "tr",
          {},
          h("td", { class: "nowrap" }, `${time(row.bat_dau)}–${time(row.ket_thuc)}`),
          h("td", { class: "nowrap" }, row.ten_phong),
          h("td", {}, row.lop),
          h("td", {}, PURPOSE[row.muc_dich]),
          h("td", {}, row.ten_nguoi_gui),
          h("td", {}, statusLabel(row.trang_thai)),
        ),
      );
    }
  }
  return panel(
    `Tuần từ ${day(noon(state.week))} đến ${day(noon(shiftDay(end, -1)))}`,
    [
      h("div", { class: "toolbar" }, field("Phòng", room)),
      body.length
        ? table(["Giờ", "Phòng", "Lớp hoặc học phần", "Mục đích", "Giáo viên", "Trạng thái"], body)
        : h("p", { class: "empty" }, "Tuần này chưa có lịch nào đã duyệt."),
    ],
    tools,
  );
}

async function roomsView() {
  const rooms = await loadRooms();
  const rows = rooms.map((room) => {
    const count = h("td", {}, String(room.so_may));
    const action = h("td", {});
    const view = () => {
      count.replaceChildren(String(room.so_may));
      action.replaceChildren(
        h("button", { type: "button", class: "button button-small button-secondary", onclick: edit }, "Sửa"),
      );
    };
    function edit() {
      state.editing = true;
      const input = h("input", {
        id: `so-may-${room.id}`,
        class: "number-input",
        type: "number",
        min: "0",
        max: "500",
        step: "1",
        value: String(room.so_may),
        "aria-label": `Số máy dùng được của ${room.ten}`,
      });
      const problem = h("p", { class: "field-error", hidden: true });
      const save = h("button", { type: "button", class: "button button-small" }, "Lưu");
      save.addEventListener("click", async () => {
        const value = Number(input.value);
        if (input.value === "" || !Number.isInteger(value) || value < 0 || value > 500) {
          problem.textContent = "Số máy từ 0 đến 500.";
          problem.hidden = false;
          return;
        }
        save.disabled = true;
        try {
          const [saved] = await api(`phong?id=eq.${room.id}`, {
            method: "PATCH",
            body: { so_may: value },
            headers: { Prefer: "return=representation" },
          });
          Object.assign(room, saved);
          state.editing = false;
          view();
        } catch (error) {
          problem.textContent = error.message;
          problem.hidden = false;
          save.disabled = false;
        }
      });
      count.replaceChildren(input, problem);
      action.replaceChildren(
        h("div", { class: "actions" }, save, h("button", {
          type: "button",
          class: "button button-small button-secondary",
          onclick: () => {
            state.editing = false;
            view();
          },
        }, "Hủy")),
      );
      input.focus();
    }
    view();
    return h("tr", {}, h("td", {}, room.ma), h("td", {}, room.ten), count, action);
  });
  return panel("Danh sách phòng", [
    h("p", { class: "muted" }, "Số máy dùng được được dùng để kiểm tra đơn mới. Khi máy hỏng hoặc sửa xong, hãy cập nhật số này."),
    table(["Mã", "Tên phòng", "Số máy dùng được", ""], rows),
  ]);
}

function focusTab() {
  if (hasAny(ROLE.manager)) {
    return "tat-ca";
  }
  if (hasAny(ROLE.staff)) {
    return "chuan-bi";
  }
  return "don-cua-toi";
}

async function notificationsView() {
  const items = await core("notifications?limit=50");
  state.unread = items.filter((item) => !item.read_at).length;
  drawMenu();
  if (!items.length) {
    return panel("Thông báo gần đây", h("p", { class: "empty" }, "Chưa có thông báo nào."));
  }
  const markRead = async (item) => {
    if (!item.read_at) {
      await core(`notifications/${item.id}/read`, { method: "POST" });
    }
  };
  const list = h(
    "ul",
    { class: "notifications" },
    items.map((item) => {
      const target = item.link ? new URL(item.link, location.origin).searchParams.get("don") : null;
      const buttons = h("div", { class: "actions" });
      if (target) {
        buttons.append(
          h("button", {
            type: "button",
            class: "button button-small button-secondary",
            onclick: async () => {
              await markRead(item).catch(() => {});
              state.focus = Number(target);
              open(focusTab());
            },
          }, "Xem đơn"),
        );
      }
      if (!item.read_at) {
        buttons.append(
          h("button", {
            type: "button",
            class: "link-button",
            onclick: async () => {
              await markRead(item);
              show();
            },
          }, "Đánh dấu đã đọc"),
        );
      }
      return h(
        "li",
        { class: item.read_at ? null : "unread" },
        h(
          "div",
          {},
          h("p", { class: "notification-title" }, item.title),
          item.body ? h("p", { class: "notification-body" }, item.body) : null,
          h("p", { class: "notification-time" }, `${time(item.created_at)} ${day(item.created_at)}`),
        ),
        buttons,
      );
    }),
  );
  return panel("Thông báo gần đây", list);
}

async function focusTile() {
  if (hasAny(ROLE.manager)) {
    const tasks = (await core("tasks?limit=200")).filter((task) => task.task_key === "duyet");
    const late = tasks.filter((task) => task.due && new Date(task.due) < new Date()).length;
    const note = late ? `${late} đơn đã quá hạn duyệt` : "Không có đơn quá hạn";
    return tile("approve", "Đơn chờ duyệt", tasks.length, note, late > 0);
  }
  if (hasAny(ROLE.staff)) {
    const tasks = (await core("tasks?limit=200")).filter((task) => task.task_key === "chuan_bi");
    return tile("prepare", "Phòng cần chuẩn bị", tasks.length, "Theo các đơn đã được duyệt");
  }
  const query = new URLSearchParams({ nguoi_gui: `eq.${session.claims.sub}`, trang_thai: "eq.cho_duyet", select: "id" });
  const rows = await api(`don?${query}`);
  return tile("document", "Đơn của tôi chờ duyệt", rows.length, "Kết quả được báo ở mục Thông báo");
}

function moreTab() {
  if (hasAny(ROLE.manager)) {
    return "tat-ca";
  }
  return hasAny(ROLE.teacher) ? "don-cua-toi" : "chuan-bi";
}

function weekGrid(rows, week) {
  const days = WEEKDAYS.map((label, index) => ({ label, key: shiftDay(week, index) }));
  const now = today();
  const mark = (key) => (key === now ? "today" : null);
  const head = h(
    "tr",
    {},
    h("th", { scope: "col" }, "Phòng"),
    days.map((item) =>
      h("th", { scope: "col", class: mark(item.key) }, item.label, h("span", { class: "th-note" }, day(noon(item.key)).slice(0, 5))),
    ),
  );
  const body = state.rooms.map((room) =>
    h(
      "tr",
      {},
      h("th", { scope: "row", class: "nowrap" }, room.ten),
      days.map((item) =>
        h(
          "td",
          { class: mark(item.key) },
          rows
            .filter((row) => row.ma_phong === room.ma && isoDay(row.bat_dau) === item.key)
            .map((row) =>
              h(
                "div",
                { class: `slot slot-${row.trang_thai}`, title: `${row.lop}, ${row.ten_nguoi_gui}` },
                h("span", { class: "slot-time" }, `${time(row.bat_dau)}–${time(row.ket_thuc)}`),
                h("span", { class: "slot-class" }, row.lop),
              ),
            ),
        ),
      ),
    ),
  );
  const legend = h(
    "div",
    { class: "legend" },
    h("span", {}, statusLabel("da_duyet"), " Chờ chuẩn bị phòng"),
    h("span", {}, statusLabel("san_sang"), " Đã chuẩn bị xong"),
    h("span", {}, "Ô trống là phòng còn trống"),
  );
  return [
    h("div", { class: "table-wrap" }, h("table", { class: "week-grid" }, h("thead", {}, head), h("tbody", {}, body))),
    legend,
  ];
}

async function overviewView() {
  const week = weekStart(today());
  const [rows, focus, recent] = await Promise.all([
    schedule({ from: week, to: shiftDay(week, 7) }),
    focusTile(),
    api("don?order=gui_luc.desc&limit=6"),
  ]);
  const todayRows = rows.filter((row) => isoDay(row.bat_dau) === today());
  const machines = state.rooms.reduce((sum, room) => sum + room.so_may, 0);
  const perDay = WEEKDAYS.map((label, index) => {
    const key = shiftDay(week, index);
    const value = rows.filter((row) => isoDay(row.bat_dau) === key).length;
    return { label, note: day(noon(key)).slice(0, 5), value };
  });
  const todayTable = todayRows.length
    ? table(
        ["Giờ", "Phòng", "Lớp hoặc học phần", "Giáo viên", "Trạng thái"],
        todayRows.map((row) =>
          h(
            "tr",
            {},
            h("td", { class: "nowrap" }, `${time(row.bat_dau)}–${time(row.ket_thuc)}`),
            h("td", { class: "nowrap" }, row.ten_phong),
            h("td", {}, row.lop),
            h("td", {}, row.ten_nguoi_gui),
            h("td", {}, statusLabel(row.trang_thai)),
          ),
        ),
      )
    : h("p", { class: "empty" }, "Hôm nay chưa có buổi học nào đã duyệt.");
  const recentTable = recent.length
    ? table(
        ["Số đơn", "Phòng", "Thời gian", "Lớp hoặc học phần", "Người gửi", "Trạng thái"],
        recent.map((row) =>
          h(
            "tr",
            {},
            h("td", {}, String(row.id)),
            h("td", { class: "nowrap" }, roomOf(row.phong_id)?.ten ?? ""),
            h("td", { class: "nowrap" }, period(row.bat_dau, row.ket_thuc)),
            h("td", {}, row.lop),
            h("td", {}, row.ten_nguoi_gui),
            h("td", {}, statusLabel(row.trang_thai)),
          ),
        ),
      )
    : h("p", { class: "empty" }, "Chưa có đơn nào.");
  const more = h("button", { type: "button", class: "link-button panel-link", onclick: () => open(moreTab()) }, "Xem tất cả");
  const first = todayRows.length ? `Buổi đầu tiên lúc ${time(todayRows[0].bat_dau)}` : "Chưa có buổi nào";
  return [
    h(
      "div",
      { class: "tiles" },
      tile("clock", "Buổi học hôm nay", todayRows.length, first),
      tile("calendar", "Buổi học tuần này", rows.length, `Từ ${day(noon(week))} đến ${day(noon(shiftDay(week, 6)))}`),
      focus,
      tile("monitor", "Máy dùng được", machines, `Ở ${state.rooms.length} phòng máy`),
    ),
    panel("Lịch tuần theo phòng", weekGrid(rows, week)),
    h(
      "div",
      { class: "columns" },
      panel(
        "Buổi học trong tuần",
        chartBox((width) => columnChart(perDay, "buổi", "Số buổi học đã duyệt theo ngày trong tuần", width)),
      ),
      panel("Lịch hôm nay", todayTable),
    ),
    panel("Đơn gần đây", recentTable, more),
  ];
}

const MENU = [
  {
    group: null,
    items: [
      { id: "tong-quan", label: "Tổng quan", icon: "overview", roles: [ROLE.teacher, ROLE.manager, ROLE.staff], view: overviewView },
    ],
  },
  {
    group: "Giáo viên",
    items: [
      { id: "dat-phong", label: "Đặt phòng", icon: "add", roles: [ROLE.teacher], view: bookingView },
      { id: "don-cua-toi", label: "Đơn của tôi", icon: "document", roles: [ROLE.teacher], view: mineView },
    ],
  },
  {
    group: "Phụ trách phòng",
    items: [
      { id: "cho-duyet", label: "Đơn chờ duyệt", icon: "approve", roles: [ROLE.manager], view: approvalView },
      { id: "tat-ca", label: "Tất cả đơn", icon: "list", roles: [ROLE.manager], view: allView },
      { id: "phong", label: "Phòng máy", icon: "monitor", roles: [ROLE.manager], view: roomsView },
    ],
  },
  {
    group: "Chuyên viên",
    items: [{ id: "chuan-bi", label: "Chuẩn bị phòng", icon: "prepare", roles: [ROLE.staff], view: preparationView }],
  },
  {
    group: "Chung",
    items: [
      { id: "lich", label: "Lịch phòng", icon: "calendar", roles: Object.values(ROLE), view: scheduleView },
      { id: "thong-bao", label: "Thông báo", icon: "bell", roles: [ROLE.teacher, ROLE.manager, ROLE.staff], view: notificationsView },
    ],
  },
];
const ITEMS = MENU.flatMap((section) => section.items);
const allowed = (item) => item.roles.some((role) => state.roles.has(role));

function drawMenu() {
  const counts = { ...state.counts, "thong-bao": state.unread };
  document.getElementById("menu").replaceChildren(
    ...MENU.flatMap((section) => {
      const items = section.items.filter(allowed);
      if (!items.length) {
        return [];
      }
      const buttons = items.map((item) =>
        h(
          "button",
          {
            type: "button",
            class: "menu-item",
            "aria-current": item.id === state.tab ? "page" : null,
            onclick: () => open(item.id),
          },
          icon(item.icon),
          h("span", {}, item.label),
          counts[item.id] ? h("span", { class: "count" }, String(counts[item.id])) : null,
        ),
      );
      return section.group ? [h("p", { class: "menu-group" }, section.group), ...buttons] : buttons;
    }),
  );
  const badge = document.getElementById("bell-count");
  badge.textContent = String(state.unread);
  badge.hidden = !state.unread;
}

function toggleMenu(opened) {
  document.getElementById("sidebar").classList.toggle("open", opened);
  document.getElementById("backdrop").hidden = !opened;
  document.getElementById("menu-toggle").setAttribute("aria-expanded", String(opened));
}

function open(id) {
  state.tab = id;
  history.replaceState(null, "", `${location.pathname}${location.search}#${id}`);
  toggleMenu(false);
  drawMenu();
  show();
}

async function show({ quiet = false } = {}) {
  const ticket = ++state.ticket;
  const main = document.getElementById("main");
  const item = ITEMS.find((entry) => entry.id === state.tab);
  const flash = state.flash;
  state.flash = null;
  state.editing = false;
  document.title = `${item.label} - Đặt phòng máy`;
  const head = h("div", { class: "page-head" }, h("h1", {}, item.label));
  const top = flash ? [head, notice(flash.kind, flash.text)] : [head];
  if (!quiet) {
    main.replaceChildren(...top, h("p", { class: "muted" }, "Đang tải…"));
  }
  try {
    const content = await item.view();
    if (ticket === state.ticket) {
      main.replaceChildren(...top, ...[content].flat());
      if (state.focus) {
        reveal();
        state.focus = null;
      }
    }
  } catch (error) {
    if (ticket === state.ticket) {
      main.replaceChildren(
        head,
        notice("error", error.message),
        h("button", { type: "button", class: "button button-secondary", onclick: () => show() }, "Thử lại"),
      );
    }
  }
}

async function refreshCounts() {
  const jobs = [];
  if (hasAny(ROLE.teacher, ROLE.manager, ROLE.staff)) {
    jobs.push(
      core("notifications?limit=200").then((items) => {
        state.unread = items.filter((item) => !item.read_at).length;
      }),
    );
  }
  if (hasAny(ROLE.manager, ROLE.staff)) {
    jobs.push(
      core("tasks?limit=200").then((tasks) => {
        state.counts = {
          "cho-duyet": tasks.filter((task) => task.task_key === "duyet").length,
          "chuan-bi": tasks.filter((task) => task.task_key === "chuan_bi").length,
        };
      }),
    );
  }
  await Promise.all(jobs);
  drawMenu();
}

async function background() {
  if (document.visibilityState !== "visible") {
    return;
  }
  await refreshCounts().catch(() => {});
  if (!state.editing && LIVE_TABS.has(state.tab)) {
    show({ quiet: true });
  }
}

function fatal(error) {
  document.getElementById("main").replaceChildren(
    notice("error", error.message),
    h("button", { type: "button", class: "button button-secondary", onclick: () => location.assign(BASE) }, "Mở lại trang"),
  );
}

function showAccount() {
  document.getElementById("account-name").textContent =
    session.claims.name || session.claims.preferred_username || "";
  document.getElementById("account-roles").textContent = [...state.roles].map((role) => ROLE_NAMES[role]).join(", ");
  document.getElementById("bell").hidden = !hasAny(ROLE.teacher, ROLE.manager, ROLE.staff);
  document.getElementById("account").hidden = false;
}

async function begin() {
  const roles = session.claims.realm_access?.roles ?? [];
  state.roles = new Set(roles.filter((role) => Object.values(ROLE).includes(role)));
  showAccount();
  if (!state.roles.size) {
    document.getElementById("main").replaceChildren(
      notice(
        "warning",
        "Tài khoản này chưa có role nào của ứng dụng Đặt phòng máy. Hãy nhờ quản trị viên gán role giáo viên, phụ trách phòng, chuyên viên hoặc học sinh.",
      ),
    );
    return;
  }
  if (hasAny(ROLE.teacher, ROLE.manager, ROLE.staff)) {
    await api("rpc/cap_nhat_nguoi_dung", { method: "POST", body: {} });
  }
  await loadRooms();
  state.focus = Number(new URLSearchParams(location.search).get("don")) || null;
  const items = ITEMS.filter(allowed);
  const wanted = location.hash.slice(1);
  if (items.some((item) => item.id === wanted)) {
    state.tab = wanted;
  } else {
    state.tab = state.focus ? focusTab() : items[0].id;
  }
  await refreshCounts().catch(() => {});
  show();
  setInterval(background, POLL);
  document.addEventListener("visibilitychange", background);
}

async function start() {
  document.getElementById("today").textContent = dayTitle(today());
  document.getElementById("logout").addEventListener("click", logout);
  document.getElementById("bell").addEventListener("click", () => open("thong-bao"));
  document.getElementById("menu-toggle").addEventListener("click", () => {
    toggleMenu(!document.getElementById("sidebar").classList.contains("open"));
  });
  document.getElementById("backdrop").addEventListener("click", () => toggleMenu(false));
  try {
    const reply = await fetch(`${REALM}/.well-known/openid-configuration`);
    if (!reply.ok) {
      throw new Error("Không đọc được cấu hình đăng nhập của hệ thống.");
    }
    state.config = await reply.json();
    const params = new URLSearchParams(location.hash.slice(1));
    if (params.has("error")) {
      throw new Error(params.get("error_description") ?? "Đăng nhập không thành công.");
    }
    if (params.has("code")) {
      await finishLogin(params);
    } else if (!restore()) {
      await login();
      return;
    }
    await begin();
  } catch (error) {
    fatal(error);
  }
}

start();
