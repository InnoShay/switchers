// Canvas 2D orb (SPEC §16.3): 3 rings + 120-particle halo, breathing, colour flashes,
// hands arc while an action runs, slow red pulse while an approval is open.
const TAU = Math.PI * 2;
const easeOut = (x) => 1 - Math.pow(1 - x, 3);
const easeOutBack = (x) => {
  const c1 = 1.70158;
  const c3 = c1 + 1;
  return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2);
};

export class Orb {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.flashes = [];
    this.arc = false;
    this.approval = false;
    this.igniteAt = null; // performance.now() when the orb starts scaling in
    this.handsColor = "#FF5C7A";
    this.particles = Array.from({ length: 120 }, () => ({
      a: Math.random() * TAU,
      r: 1.12 + Math.random() * 0.45,
      v: (0.04 + Math.random() * 0.1) * (Math.random() < 0.5 ? -1 : 1),
      s: 0.8 + Math.random() * 1.8,
      p: Math.random() * TAU,
    }));
    this.resize();
    window.addEventListener("resize", () => this.resize());
    requestAnimationFrame((t) => this.frame(t));
  }

  flash(color) {
    this.flashes.push({ color, t0: performance.now() });
    if (this.flashes.length > 12) this.flashes.shift();
  }

  ignite(delayMs) {
    this.igniteAt = performance.now() + delayMs;
  }

  resize() {
    const dpr = window.devicePixelRatio || 1;
    const r = this.canvas.getBoundingClientRect();
    this.w = Math.max(1, r.width);
    this.h = Math.max(1, r.height);
    this.canvas.width = Math.round(this.w * dpr);
    this.canvas.height = Math.round(this.h * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  frame(now) {
    const c = this.ctx;
    c.clearRect(0, 0, this.w, this.h);
    const cx = this.w / 2;
    const cy = this.h / 2 - this.h * 0.04;
    const base = Math.min(210, Math.min(this.w, this.h) * 0.36);

    let scale = 1;
    if (this.igniteAt !== null) {
      const k = (now - this.igniteAt) / 600;
      scale = k <= 0 ? 0 : k >= 1 ? 1 : easeOutBack(k);
      if (k >= 1) this.igniteAt = null;
    }
    if (scale <= 0.001) {
      requestAnimationFrame((t) => this.frame(t));
      return;
    }
    const breathe = 1 + 0.03 * Math.sin(TAU * 0.25 * (now / 1000));
    const R = base * breathe * scale;

    // core glow
    const g = c.createRadialGradient(cx, cy, 0, cx, cy, R);
    g.addColorStop(0, "rgba(124,156,255,0.35)");
    g.addColorStop(0.6, "rgba(124,156,255,0.08)");
    g.addColorStop(1, "rgba(124,156,255,0)");
    c.fillStyle = g;
    c.beginPath();
    c.arc(cx, cy, R, 0, TAU);
    c.fill();

    // approval: slow red pulse
    if (this.approval) {
      const a = 0.22 + 0.2 * Math.sin(TAU * (now / 2400));
      c.strokeStyle = `rgba(255,59,59,${a})`;
      c.lineWidth = 10;
      c.beginPath();
      c.arc(cx, cy, R * 1.08, 0, TAU);
      c.stroke();
    }

    // three concentric rings
    [
      [0.55, "rgba(124,156,255,0.55)", 2],
      [0.78, "rgba(124,156,255,0.35)", 2],
      [1.0, "rgba(124,156,255,0.22)", 2],
    ].forEach(([f, col, w]) => {
      c.strokeStyle = col;
      c.lineWidth = w;
      c.beginPath();
      c.arc(cx, cy, R * f, 0, TAU);
      c.stroke();
    });

    // colour flashes: ring expands and fades over 400 ms
    this.flashes = this.flashes.filter((f) => now - f.t0 < 400);
    for (const f of this.flashes) {
      const k = easeOut((now - f.t0) / 400);
      c.globalAlpha = 1 - k;
      c.strokeStyle = f.color;
      c.lineWidth = 6 * (1 - k) + 1;
      c.beginPath();
      c.arc(cx, cy, R * (0.95 + 0.25 * k), 0, TAU);
      c.stroke();
      c.globalAlpha = 1;
    }

    // hands arc while an action runs
    if (this.arc) {
      const a0 = TAU * ((now % 1200) / 1200);
      c.strokeStyle = this.handsColor;
      c.lineWidth = 5;
      c.lineCap = "round";
      c.shadowColor = this.handsColor;
      c.shadowBlur = 16;
      c.beginPath();
      c.arc(cx, cy, R * 1.0, a0, a0 + Math.PI * 0.55);
      c.stroke();
      c.shadowBlur = 0;
    }

    // particle halo
    for (const p of this.particles) {
      p.a += p.v * 0.016;
      const rr = R * (p.r + 0.03 * Math.sin(now / 900 + p.p));
      const x = cx + Math.cos(p.a) * rr;
      const y = cy + Math.sin(p.a) * rr;
      c.fillStyle = `rgba(160,185,255,${0.25 + 0.3 * Math.sin(now / 700 + p.p) ** 2})`;
      c.beginPath();
      c.arc(x, y, p.s, 0, TAU);
      c.fill();
    }
    requestAnimationFrame((t) => this.frame(t));
  }
}
