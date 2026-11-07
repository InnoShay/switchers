// Live Switch network map: the room as a system diagram. Every event lights the real path it took.
// Neutral ink on paper, one accent for traffic, amber for the owner's attention, red for stops.
const NS = "http://www.w3.org/2000/svg";
const VB = { w: 1280, h: 720 };

// id -> [x, y, w, h, label, sub, kind]
const NODES = {
  you: [40, 300, 200, 110, "Owner", "Telegram · Mattermost", "human"],
  switch: [440, 235, 280, 240, "Switch", "rooms · roles · approvals", "hub"],
  concierge: [880, 30, 200, 84, "Concierge", "Console agent", "agent"],
  builder: [880, 134, 200, 84, "Builder", "Console agent", "agent"],
  scout: [880, 238, 200, 84, "Scout", "Console agent", "agent"],
  life: [880, 342, 200, 84, "Life", "runtime agent", "agent"],
  hands: [880, 446, 200, 104, "Hands", "desk-laptop", "agent"],
  backup: [880, 570, 200, 84, "Hands · backup", "desk-backup · standby", "agent"],
  n8n: [1130, 342, 120, 84, "n8n", "calendar · mail", "ext"],
  machine: [1130, 446, 120, 104, "Laptop", "macOS", "ext"],
};
// edges: [a, b, d]
const RIGHT = { concierge: 275, builder: 305, scout: 335, life: 365, hands: 395, backup: 425 };
const edge = (a, b, x1, y1, x2, y2) => {
  const dx = Math.max(40, Math.abs(x2 - x1) / 2);
  return [a, b, `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`];
};
const mid = (id) => NODES[id][1] + NODES[id][3] / 2;
const EDGES = [
  edge("you", "switch", 240, 355, 440, 355),
  ...Object.keys(RIGHT).map((k) => edge("switch", k, 720, RIGHT[k], 880, mid(k))),
  edge("life", "n8n", 1080, mid("life"), 1130, mid("n8n")),
  edge("hands", "machine", 1080, mid("hands"), 1130, mid("machine")),
];

const el = (tag, attrs = {}, parent) => {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (parent) parent.append(n);
  return n;
};
const clip = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

export class NetMap {
  constructor(svg) {
    this.svg = svg;
    svg.setAttribute("viewBox", `0 0 ${VB.w} ${VB.h}`);
    this.edges = [];
    this.nodes = {};
    this.parts = [];
    this.tags = [];
    this.holder = "hands"; // node that holds the hands role
    this.frozen = false;
    this.waiting = false; // an approval is waiting on the owner
    this.t = 0;
    this.last = performance.now();
    this.build();
    requestAnimationFrame((n) => this.frame(n));
  }

  build() {
    const svg = this.svg;
    this.gEdges = el("g", { class: "edges" }, svg);
    this.gNodes = el("g", { class: "nodes" }, svg);
    this.gParts = el("g", { class: "parts" }, svg);
    this.gTags = el("g", { class: "tags" }, svg);
    EDGES.forEach(([a, b, d], i) => {
      const g = el("g", { class: "edge" }, this.gEdges);
      g.style.setProperty("--i", i);
      const base = el("path", { d, class: "edge-base", pathLength: 1 }, g);
      const live = el("path", { d, class: "edge-live" }, g);
      this.edges.push({ a, b, d, base, live, hot: 0, g, len: base.getTotalLength() });
    });
    let n = 0;
    for (const [id, [x, y, w, h, label, sub, kind]] of Object.entries(NODES)) {
      const g = el("g", { class: `node k-${kind} s-idle`, transform: `translate(${x},${y})` }, this.gNodes);
      g.style.setProperty("--n", n++);
      el("rect", { class: "node-box", width: w, height: h, rx: 6 }, g);
      el("rect", { class: "node-ring", width: w, height: h, rx: 6 }, g);
      const t = el("text", { class: "node-label", x: 16, y: kind === "hub" ? 34 : 30 }, g);
      t.textContent = label;
      const s = el("text", { class: "node-sub", x: 16, y: kind === "hub" ? 54 : 50 }, g);
      s.textContent = sub;
      const st = el("text", { class: "node-state", x: w - 14, y: 26, "text-anchor": "end" }, g);
      st.textContent = "";
      const badge = el("g", { class: "badge", transform: `translate(${w - 78},${h - 30})` }, g);
      el("rect", { width: 64, height: 20, rx: 3 }, badge);
      const bt = el("text", { x: 32, y: 14, "text-anchor": "middle" }, badge);
      bt.textContent = "HANDS";
      this.nodes[id] = { id, g, w, h, x, y, label: t, sub: s, st, badge, state: "idle" };
    }
    this.nodes.hands.badge.classList.add("on");

    // switch hub: the rooms it is holding right now
    const hub = this.nodes.switch.g;
    const rooms = el("g", { class: "rooms", transform: "translate(16,84)" }, hub);
    this.roomHq = this.room(rooms, 0, "HQ", "RoomService HQ");
    this.roomMission = this.room(rooms, 62, "MISSION", "none");
    const bridge = el("text", { class: "node-sub", x: 16, y: 228 }, hub);
    bridge.textContent = "bridges: telegram · mattermost";

    // laptop: what the desk is doing right now
    const m = this.nodes.machine.g;
    this.act = el("text", { class: "node-act", x: 14, y: 78 }, m);
    this.actBar = el("rect", { class: "node-bar", x: 14, y: 90, width: 0, height: 3 }, m);
    this.roomHq.v.textContent = "RoomService HQ";
  }

  room(parent, y, tag, name) {
    const g = el("g", { class: "room", transform: `translate(0,${y})` }, parent);
    el("rect", { width: 248, height: 50, rx: 4 }, g);
    const k = el("text", { x: 12, y: 20, class: "room-k" }, g);
    k.textContent = tag;
    const v = el("text", { x: 12, y: 38, class: "room-v" }, g);
    v.textContent = name;
    return { g, v };
  }

  // ---------- state ----------
  setState(agent, state) {
    const n = this.nodes[agent === "hands" ? this.holder : agent];
    if (!n || (agent === "you")) {
      if (agent === "you") this.youState(state);
      return;
    }
    n.state = state;
    n.g.setAttribute("class", n.g.getAttribute("class").replace(/ s-\w+/, "") + ` s-${state}`);
    n.st.textContent = { offline: "OFFLINE", idle: "", working: "WORKING", needs_you: "NEEDS YOU" }[state];
  }

  youState(state) {
    const n = this.nodes.you;
    n.state = state;
    n.g.setAttribute("class", n.g.getAttribute("class").replace(/ s-\w+/, "") + ` s-${state}`);
    n.st.textContent = state === "needs_you" ? "YOUR CALL" : "";
  }

  setMission(slug) {
    this.roomMission.v.textContent = slug ? `mission-${slug}` : "none";
    this.roomMission.g.classList.toggle("live", !!slug);
  }

  setMachine(name) {
    this.nodes.hands.sub.textContent = name ? `desk-${name}` : "desk-laptop";
  }

  setFrozen(on) {
    this.frozen = on;
    this.svg.classList.toggle("frozen", on);
  }

  setWaiting(on) {
    this.waiting = on;
    this.svg.classList.toggle("waiting", on);
  }

  setHolder(to) {
    const toNode = to === "desk-backup" ? "backup" : "hands";
    this.holder = toNode;
    this.nodes.hands.badge.classList.toggle("on", toNode === "hands");
    this.nodes.backup.badge.classList.toggle("on", toNode === "backup");
    this.nodes.hands.sub.textContent = toNode === "hands" ? "desk-laptop" : "desk-laptop · released";
    this.nodes.backup.sub.textContent = toNode === "backup" ? "desk-backup · holds hands" : "desk-backup · standby";
  }

  ignite() {
    const s = this.svg;
    s.classList.remove("booting");
    void s.getBoundingClientRect();
    s.classList.add("booting");
    clearTimeout(this._boot);
    this._boot = setTimeout(() => s.classList.remove("booting"), 2200);
  }

  // ---------- flow ----------
  edgeFor(a, b) {
    for (const e of this.edges) {
      if (e.a === a && e.b === b) return [e, 1];
      if (e.a === b && e.b === a) return [e, -1];
    }
    return null;
  }

  /** Send a packet along a chain of nodes, hop by hop. kind: msg | act | ask | img | role | ok */
  flow(chain, kind = "msg", text = "", hop = 520) {
    if (this.frozen) return;
    const ids = chain.map((c) => (c === "hands" ? this.holder : c));
    let delay = 0;
    for (let i = 0; i < ids.length - 1; i++) {
      const r = this.edgeFor(ids[i], ids[i + 1]);
      if (!r) continue;
      const [e, dir] = r;
      const el_ = kind === "img" ? el("rect", { class: `pk pk-${kind}`, width: 11, height: 8, rx: 1 }, this.gParts) : el("circle", { class: `pk pk-${kind}`, r: kind === "act" ? 3.2 : 4 }, this.gParts);
      const tail = el("path", { class: `pk-tail pk-${kind}` }, this.gParts);
      this.parts.push({ e, dir, kind, el: el_, tail, t0: performance.now() + delay, dur: hop, done: false });
      if (text && i === 0) this.tag(e, text, delay);
      delay += hop * 0.82;
    }
    if (this.parts.length > 80) this.parts.splice(0, this.parts.length - 80).forEach((p) => this.drop(p));
  }

  drop(p) {
    p.el.remove();
    p.tail.remove();
    p.done = true;
  }

  tag(e, text, delay) {
    const t = el("g", { class: "tag" }, this.gTags);
    const bg = el("rect", { height: 20, rx: 3 }, t);
    const tx = el("text", { y: 14, x: 8 }, t);
    tx.textContent = clip(text, 28);
    const w = tx.getComputedTextLength() + 16;
    bg.setAttribute("width", w);
    const pt = e.base.getPointAtLength(e.len * 0.5);
    t.setAttribute("transform", `translate(${pt.x - w / 2},${pt.y - 30 - (this.tags.length % 3) * 24})`);
    t.style.animationDelay = `${delay}ms`;
    this.tags.push(t);
    setTimeout(() => {
      t.remove();
      this.tags = this.tags.filter((x) => x !== t);
    }, delay + 2300);
    while (this.tags.length > 7) this.tags.shift().remove();
  }

  message(from, targets, text) {
    const who = from === "other" ? "you" : from;
    if (who === "you") {
      this.flow(["you", "switch", ...(targets.length ? [targets[0]] : ["concierge"])], "msg", text);
      (targets.length ? targets.slice(1) : ["hands"]).forEach((t) => this.flow(["switch", t], "msg", "", 520));
    } else {
      this.flow([who, "switch", ...(targets.length ? [targets[0]] : ["you"])], "msg", text);
      targets.slice(1).forEach((t) => this.flow(["switch", t], "msg", "", 520));
    }
  }

  actionStart(verb, args) {
    const label = `${verb} ${args.join(" ")}`.trim();
    this.flow(["switch", "hands", "machine"], "act", label);
    this.act.textContent = clip(label, 14);
    this.actRunning = true;
  }

  actionEnd(ok) {
    this.flow(["machine", "hands", "switch", "you"], ok ? "ok" : "err", "", 420);
    this.actRunning = false;
    setTimeout(() => {
      if (!this.actRunning) this.act.textContent = "";
    }, 1800);
  }

  // ---------- frame ----------
  pointOn(p, k) {
    const e = p.e;
    const l = e.len * (p.dir > 0 ? k : 1 - k);
    return e.base.getPointAtLength(l);
  }

  frame(now) {
    const dt = Math.min(0.05, (now - this.last) / 1000);
    this.last = now;
    if (!this.frozen) this.t += dt;
    for (const e of this.edges) {
      e.hot = Math.max(0, e.hot - dt * 0.9);
      e.live.style.opacity = String(Math.min(1, e.hot));
    }
    if (this.actRunning) {
      const w = 92 * (0.5 + 0.5 * Math.sin(now / 260));
      this.actBar.setAttribute("width", String(w));
    } else this.actBar.setAttribute("width", "0");

    for (const p of this.parts) {
      if (p.done) continue;
      if (this.frozen) {
        p.t0 += now - (this._lastNow || now);
        continue;
      }
      const k = (now - p.t0) / p.dur;
      if (k < 0) {
        p.el.style.opacity = "0";
        p.tail.style.opacity = "0";
        continue;
      }
      if (k >= 1) {
        this.drop(p);
        continue;
      }
      const e = p.e;
      e.hot = 1;
      const ease = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      const pt = this.pointOn(p, ease);
      const tl = this.pointOn(p, Math.max(0, ease - 0.12));
      if (p.kind === "img") p.el.setAttribute("transform", `translate(${pt.x - 5.5},${pt.y - 4})`);
      else {
        p.el.setAttribute("cx", pt.x);
        p.el.setAttribute("cy", pt.y);
      }
      p.tail.setAttribute("d", `M${tl.x},${tl.y} L${pt.x},${pt.y}`);
      p.el.style.opacity = "1";
      p.tail.style.opacity = "1";
    }
    this.parts = this.parts.filter((p) => !p.done);
    this._lastNow = now;
    requestAnimationFrame((n) => this.frame(n));
  }
}
