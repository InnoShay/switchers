// Control Room HUD frontend (SPEC §16): the live Switch network map. Plain ES modules, no build step.
// Every piece of chat text is written with textContent, never innerHTML.
import { NetMap } from "./netmap.js";
import { Sfx } from "./sfx.js";

const NAMES = { you: "You", concierge: "Planner", builder: "Builder", scout: "Researcher", hands: "Computer", life: "Assistant" };
const CREW = ["you", "concierge", "builder", "scout", "hands", "life"];
const FEED_MAX = 60;
const CHIPS_MAX = 8;
const STALE_MS = 10 * 60 * 1000;
const MENTION = /@(concierge|planner|builder|scout|researcher|life|assistant|hands|computer|backup|desk-laptop|desk-backup)\b/gi;

const $ = (id) => document.getElementById(id);
const sfx = new Sfx();

const S = {
  crew: Object.fromEntries(CREW.map((k) => [k, "idle"])),
  active: {},
  mission: null,
  startedAt: 0,
  conn: { switch: false, n8n: false },
  machine: "",
  frozen: false,
  actions: new Map(),
  approvals: new Map(),
  captions: new URLSearchParams(location.search).has("captions"),
};

const map = new NetMap($("map"));

// ---------- helpers ----------
const hhmm = (ts) =>
  new Date(ts || Date.now()).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};
// receipts carry emoji (SPEC §11); the HUD shows plain markers instead
const plain = (t) =>
  t
    .replace(/✅\s*/g, "✓ ")
    .replace(/⚠️\s*/g, "! ")
    .replace(/🚫\s*/g, "✗ ")
    .replace(/⌛\s*/g, "… ")
    .replace(/🔊\s*/g, "voice · ")
    .replace(/📸\s*/g, "shot · ")
    .replace(/🫱\s*/g, "role · ")
    .replace(/[⚡🧊▶]\s*/gu, "");
const clip = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

// ---------- crew + header ----------
function setState(agent, state) {
  if (!(agent in S.crew)) return;
  S.crew[agent] = state;
  if (state === "working") S.active[agent] = Date.now();
  map.setState(agent, state);
  renderCrew();
  renderHeader();
}

function renderCrew() {
  map.setMachine(S.machine);
}

function renderHeader() {
  $("mission").textContent = S.mission ? `task-${S.mission}` : "no task";
  $("c-switch").classList.toggle("ok", S.conn.switch);
  $("c-n8n").classList.toggle("ok", S.conn.n8n);
  $("c-hands").classList.toggle("ok", S.crew.hands !== "offline");
}

function tickTimer() {
  let t = "00:00:00";
  if (S.mission && S.startedAt) {
    const s = Math.max(0, Math.floor((Date.now() - S.startedAt) / 1000));
    const p = (n) => String(n).padStart(2, "0");
    t = `${p(Math.floor(s / 3600))}:${p(Math.floor((s % 3600) / 60))}:${p(s % 60)}`;
  }
  $("timer").textContent = t;
}

// ---------- feed ----------
function feed(ts, who, text, cls) {
  const li = el("li", cls || "");
  li.append(el("span", "t", hhmm(ts)));
    const w = el("span", "who", who);
  li.append(w, document.createTextNode(clip(plain(text), 160)));
  const list = $("feed-list");
  list.prepend(li);
  while (list.children.length > FEED_MAX) list.lastChild.remove();
}

// ---------- hands ledger ----------
function addChip(text, cls) {
  const chip = el("span", `chip ${cls || ""}`, text);
  const box = $("chips");
  box.append(chip);
  while (box.children.length > CHIPS_MAX) box.firstChild.remove();
  return chip;
}

// ---------- overlays ----------
let toastTimer, transferTimer, captionTimer, speakTimer, resultTimer;

function showToast(url, caption) {
  $("toast-img").src = url;
  $("toast-cap").textContent = plain(caption);
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("toast").hidden = true), 6000);
}

function showTransfer(from, to) {
  const b = $("transfer");
  b.textContent = `COMPUTER TRANSFERRED → ${to}`;
  b.title = `from ${from}`;
  b.hidden = false;
  clearTimeout(transferTimer);
  transferTimer = setTimeout(() => (b.hidden = true), 4000);
}

const fmtLeft = (ms) => {
  const s = Math.ceil(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

function renderApproval() {
  const box = $("approval");
  if (box.classList.contains("result")) return;
  const open = [...S.approvals.entries()].sort((a, b) => b[1].openedAt - a[1].openedAt)[0];
  if (!open) {
    box.hidden = true;
    return;
  }
  const [code, a] = open;
  $("ap-code").textContent = code;
  $("ap-cmd").textContent = clip(a.cmd, 120);
  const left = Math.max(0, a.expiresAt - Date.now());
  const total = Math.max(1, a.expiresAt - a.openedAt);
  $("ap-left").textContent = `expires in ${fmtLeft(left)}`;
  $("ap-bar").style.transform = `scaleX(${left / total})`;
  box.hidden = false;
}

function tickApprovals() {
  for (const [code, a] of S.approvals) {
    if (a.chip) a.chip.textContent = `${clip(a.cmd, 22)} ⚠ ${code} ${fmtLeft(Math.max(0, a.expiresAt - Date.now()))}`;
  }
  renderApproval();
}

function approvalResult(ev, a) {
  const box = $("approval");
  $("ap-code").textContent = ev.code;
  $("ap-cmd").textContent = a ? clip(a.cmd, 120) : "";
  $("ap-title").textContent =
    ev.result === "ok" ? `APPROVED${ev.by ? " BY " + ev.by.toUpperCase() : ""}` : ev.result === "no" ? "DECLINED" : "EXPIRED";
  $("ap-left").textContent = "";
  box.classList.add("result");
  box.hidden = false;
  clearTimeout(resultTimer);
  resultTimer = setTimeout(() => {
    box.classList.remove("result");
    $("ap-title").textContent = "APPROVAL NEEDED";
    renderApproval();
  }, 1500);
}

function showFreeze(on) {
  S.frozen = on;
  map.setFrozen(on);
  $("freeze").hidden = !on;
}

function demoCaption(text) {
  if (!S.captions) return;
  const c = $("demo-caption");
  c.textContent = text;
  c.hidden = false;
  clearTimeout(captionTimer);
  captionTimer = setTimeout(() => (c.hidden = true), 3800);
}

function say(text) {
  const c = $("caption");
  c.textContent = text;
  c.style.opacity = "1";
  clearTimeout(speakTimer);
  speakTimer = setTimeout(() => (c.style.opacity = "0.18"), 9000);
}

function ignition(flash) {
  const reflow = (n, cls) => {
    n.classList.remove("go", "out");
    void n.offsetWidth;
    n.classList.add(cls || "go");
  };
  if (flash) reflow($("flash"));
  map.ignite();
  const t = $("ignite-text");
  t.classList.remove("out");
  reflow(t);
  sfx.ignition();
  setTimeout(() => t.classList.add("out"), 2800);
}

// ---------- event handling ----------
function mentionedAgents(body) {
  const out = new Set();
  for (const m of body.matchAll(MENTION)) {
    const n = m[1].toLowerCase();
    const alias = { planner: "concierge", researcher: "scout", assistant: "life", computer: "hands", backup: "desk-backup" };
    const k = alias[n] || n;
    out.add(k.startsWith("desk-") ? "hands" : k);
  }
  return out;
}

const runningActions = () => S.actions.size > 0;

function handle(ev) {
  switch (ev.type) {
    case "hello": {
      // Spec §16.3: all crew start idle after hello, so "offline" from the snapshot reads as idle.
      for (const m of ev.crew) {
        S.crew[m.name] = m.state === "offline" ? "idle" : m.state;
        map.setState(m.name, S.crew[m.name]);
      }
      S.mission = ev.mission;
      S.conn = ev.connections;
      map.setMission(ev.mission);
      map.setHolder(ev.machine === "backup" ? "desk-backup" : "desk-laptop");
      S.machine = ev.machine;
      if (!ev.mission) S.startedAt = 0;
      renderCrew();
      renderHeader();
      break;
    }
    case "ignition":
      ignition(ev.lights === "flash");
      feed(ev.ts, "system", `⚡ wake-up · booting ${ev.project}`);
      demoCaption("Wake-up: one sentence wakes the room before any model answers");
      break;
    case "mission":
      S.mission = ev.slug;
      S.startedAt = ev.started_at;
      map.setMission(ev.slug);
      renderHeader();
      feed(ev.ts, "system", `task ${ev.slug}${ev.title ? " · " + ev.title : ""}`);
      demoCaption("A task room is spawned from a Switch template");
      break;
    case "message": {
      const who = ev.agent in S.crew ? ev.agent : null;
      const targets = [...mentionedAgents(ev.body)].filter((a) => a !== ev.agent);
      map.message(who || "other", targets, ev.body);
      sfx.message();
      feed(ev.ts, who ? NAMES[who] : ev.sender_name, ev.body);
      if (who && !(who === "hands" && runningActions())) setState(who, "idle");
      for (const a of targets) setState(a, "working");
      break;
    }
    case "agent_state":
      setState(ev.agent, ev.state);
      break;
    case "action_start": {
      const chip = addChip(`${ev.verb} ${ev.args.join(" ")}`.trim() + " …", "run");
      S.actions.set(ev.id, { verb: ev.verb, args: ev.args, chip });
      setState("hands", "working");
      map.actionStart(ev.verb, ev.args);
      break;
    }
    case "action_end": {
      const a = S.actions.get(ev.id);
      S.actions.delete(ev.id);
      const label = a ? `${a.verb} ${a.args.join(" ")}`.trim() : "action";
      const secs = (ev.ms / 1000).toFixed(1);
      if (a) {
        a.chip.className = `chip ${ev.ok ? "" : "fail"}`;
        a.chip.textContent = `${label} · ${secs}s`;
      } else {
        addChip(`${label} · ${secs}s`, ev.ok ? "" : "fail");
      }
      feed(ev.ts, "hands", `${ev.ok ? "✅" : "⚠️"} ${label} · ${ev.summary} · ${secs}s`, ev.ok ? "" : "warn");
      if (!runningActions()) {
        setState("hands", "idle");
        map.actionEnd(ev.ok);
      }
      break;
    }
    case "approval_open": {
      const chip = addChip(`${clip(ev.cmd, 22)} ⚠ ${ev.code}`, "appr");
      S.approvals.set(ev.code, { cmd: ev.cmd, openedAt: ev.ts, expiresAt: ev.expires_at, chip });
      setState("you", "needs_you");
      map.setWaiting(true);
      map.flow(["hands", "switch", "you"], "ask", `approval ${ev.code}`);
      sfx.approval();
      feed(ev.ts, "system", `⚠️ approval needed · ${ev.cmd} · ${ev.code}`, "warn");
      renderApproval();
      demoCaption("A risky step waits for the owner. Autonomy with a leash.");
      break;
    }
    case "approval_closed": {
      const a = S.approvals.get(ev.code);
      S.approvals.delete(ev.code);
      if (a && a.chip) {
        a.chip.className = "chip";
        a.chip.textContent = `${clip(a.cmd, 22)} ${ev.result === "ok" ? "✓" : ev.result === "no" ? "✗" : "⌛"} ${ev.code}`;
      }
      if (S.approvals.size === 0) {
        setState("you", "idle");
        map.setWaiting(false);
      }
      feed(
        ev.ts,
        "system",
        `${ev.result === "ok" ? "✅ approved" : ev.result === "no" ? "🚫 declined" : "⌛ expired"} · ${ev.code}${ev.by ? " · " + ev.by : ""}`,
      );
      map.flow(["you", "switch", "hands"], ev.result === "ok" ? "ok" : "err", `${ev.result} ${ev.code}`);
      approvalResult(ev, a);
      break;
    }
    case "screenshot":
      map.flow(["hands", "switch", "you"], "img", "screenshot");
      showToast(ev.url, ev.caption);
      sfx.shutter();
      feed(ev.ts, "hands", ev.caption);
      demoCaption("Proof on your phone: a screenshot of the running page");
      break;
    case "speak":
      say(ev.text);
      feed(ev.ts, "hands", `🔊 ${ev.text}`);
      break;
    case "transfer":
      showTransfer(ev.from_agent, ev.to_agent);
      map.flow(["hands", "switch", "backup"], "role", "role: hands", 600);
      setTimeout(() => map.setHolder(ev.to_agent), 1000);
      sfx.whoosh();
      feed(ev.ts, "hands", `🫱 computer transferred ${ev.from_agent} → ${ev.to_agent}`);
      demoCaption("The Computer is a role. It moves to another machine.");
      break;
    case "freeze":
      showFreeze(ev.on);
      feed(ev.ts, "system", ev.on ? "🧊 frozen" : "▶ unfrozen", ev.on ? "warn" : "");
      break;
    case "system":
      feed(ev.ts, "system", ev.text, ev.level === "info" ? "" : ev.level);
      break;
  }
}

// ---------- websocket ----------
let ws;
function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onopen = () => ($("pill").hidden = true);
  ws.onmessage = (m) => {
    try {
      handle(JSON.parse(m.data));
    } catch (e) {
      console.error("bad event", e, m.data);
    }
  };
  ws.onclose = () => {
    $("pill").hidden = false;
    setTimeout(connect, 1000);
  };
  ws.onerror = () => ws.close();
}

// ---------- keys ----------
async function toggleFreeze() {
  try {
    const r = await fetch("/api/freeze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ on: !S.frozen }),
    });
    if (!r.ok) feed(Date.now(), "system", `pause failed (${r.status})`, "warn");
  } catch {
    feed(Date.now(), "system", "pause failed (network)", "warn");
  }
}

addEventListener("pointerdown", () => sfx.unlock());
addEventListener("keydown", (e) => {
  sfx.unlock();
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const k = e.key.toLowerCase();
  if (k === "f") {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen().catch(() => {});
  } else if (k === "m") {
    feed(Date.now(), "system", sfx.toggleMute() ? "muted" : "sound on");
  } else if (k === "s") {
    toggleFreeze();
  } else if (k === "c") {
    S.captions = !S.captions;
    if (!S.captions) $("demo-caption").hidden = true;
  }
});

// ---------- boot ----------
renderCrew();
renderHeader();
tickTimer();
setInterval(tickTimer, 1000);
setInterval(tickApprovals, 250);
setInterval(() => {
  const now = Date.now();
  for (const k of CREW) {
    if (S.crew[k] === "working" && now - (S.active[k] || 0) > STALE_MS) setState(k, "idle");
  }
}, 30000);
connect();
