"use client";

import type { DispatchOut } from "@/lib/runs";

const COLORS: Record<string, string> = {
  grid: "var(--eg-neutral-400, #9aa3ae)",
  withdrawn: "var(--eg-warning, #d9a400)",
  battery: "var(--eg-info, #3b82f6)",
};
const SUPPLY = ["var(--eg-success, #2f9e6b)", "var(--eg-accent, #0ea5a4)", "#7c9a2d", "#2b8a8a"];

// The re-settled 15-minute (or hourly) dispatch for a week: stacked supply under the load line.
export function DispatchWeek({ d }: { d: DispatchOut }) {
  const n = d.times.length;
  if (!n) return null;
  const num = (k: string, i: number) => Number(d.series[k]?.[i]?.value ?? 0);
  const perHour = 60 / d.minutes;
  const supply = Object.keys(d.series).filter((k) => k.startsWith("supply:"));
  const discharge = Object.keys(d.series).filter((k) => k.startsWith("discharge:"));
  const layers: { key: string; label: string; color: string; v: (i: number) => number }[] = [
    ...supply.map((k, j) => ({ key: k, label: k.slice(7).replaceAll("_", " "), color: SUPPLY[j % SUPPLY.length], v: (i: number) => num(k, i) })),
    ...(discharge.length ? [{ key: "battery", label: "battery discharge", color: COLORS.battery, v: (i: number) => discharge.reduce((a, k) => a + num(k, i), 0) }] : []),
    { key: "withdrawn", label: "from the bank", color: COLORS.withdrawn, v: (i: number) => num("withdrawn", i) },
    { key: "grid", label: "from the DISCOM", color: COLORS.grid, v: (i: number) => num("grid", i) },
  ];
  // kW = kWh per block × blocks per hour
  const stack = Array.from({ length: n }, (_, i) => layers.map((l) => l.v(i) * perHour));
  const load = Array.from({ length: n }, (_, i) => num("load", i) * perHour);
  const top = Math.max(1, ...load, ...stack.map((s) => s.reduce((a, b) => a + b, 0)));
  const W = 960, H = 260, pad = 36;
  const x = (i: number) => pad + (i / Math.max(1, n - 1)) * (W - pad - 8);
  const y = (v: number) => H - 24 - (v / top) * (H - 40);
  const areas = layers.map((l, li) => {
    const lo = (i: number) => stack[i].slice(0, li).reduce((a, b) => a + b, 0);
    const hi = (i: number) => lo(i) + stack[i][li];
    const up = Array.from({ length: n }, (_, i) => `${x(i).toFixed(1)},${y(hi(i)).toFixed(1)}`);
    const down = Array.from({ length: n }, (_, i) => `${x(n - 1 - i).toFixed(1)},${y(lo(n - 1 - i)).toFixed(1)}`);
    return { ...l, points: [...up, ...down].join(" ") };
  });
  const loadLine = load.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const days = Array.from({ length: Math.ceil(n / (24 * perHour)) }, (_, k) => k * 24 * perHour).filter((i) => i < n);
  return (
    <figure className="ep-dispatch" style={{ margin: 0 }}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Dispatch for the week" style={{ width: "100%", height: "auto" }}>
        {[0.25, 0.5, 0.75, 1].map((f) => (
          <g key={f}>
            <line x1={pad} x2={W - 8} y1={y(top * f)} y2={y(top * f)} stroke="currentColor" strokeOpacity={0.08} />
            <text x={pad - 4} y={y(top * f) + 4} textAnchor="end" fontSize={10} fill="currentColor" opacity={0.6}>{Math.round((top * f) / 1000).toLocaleString("en-IN")} MW</text>
          </g>
        ))}
        {areas.map((a) => <polygon key={a.key} points={a.points} fill={a.color} fillOpacity={0.75} />)}
        <polyline points={loadLine} fill="none" stroke="currentColor" strokeWidth={1.4} />
        {days.map((i) => (
          <text key={i} x={x(i) + 4} y={H - 6} fontSize={10} fill="currentColor" opacity={0.7}>{d.times[i].slice(5, 10)}</text>
        ))}
      </svg>
      <figcaption className="ep-row ep-small" style={{ marginTop: 6 }}>
        <span><span style={{ display: "inline-block", width: 14, borderTop: "2px solid currentColor", verticalAlign: "middle" }} /> load</span>
        {layers.map((l) => (
          <span key={l.key}><span style={{ display: "inline-block", width: 10, height: 10, background: l.color, borderRadius: 2, verticalAlign: "middle", marginRight: 4 }} />{l.label}</span>
        ))}
      </figcaption>
    </figure>
  );
}
