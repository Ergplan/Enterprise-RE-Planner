// One week of the 15-minute profile (the busiest month's first week) as a line, in Harmony tokens.
export function ProfileChart({ kw, maxKw }: { kw: number[]; maxKw?: number }) {
  if (kw.length === 0) return null;
  const W = 840;
  const H = 220;
  const pad = { l: 48, r: 12, t: 12, b: 26 };
  const top = Math.max(maxKw ?? 0, ...kw) * 1.08 || 1;
  const x = (i: number) => pad.l + (i / (kw.length - 1)) * (W - pad.l - pad.r);
  const y = (v: number) => pad.t + (1 - v / top) * (H - pad.t - pad.b);
  const d = kw.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(top * f));
  const days = Math.round(kw.length / 96);
  return (
    <svg className="ep-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Load over one week, 15-minute blocks">
      {ticks.map((t) => (
        <g key={t}>
          <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} className="ep-chart__grid" />
          <text x={pad.l - 6} y={y(t) + 4} textAnchor="end" className="ep-chart__tick">{t.toLocaleString("en-IN")}</text>
        </g>
      ))}
      {Array.from({ length: days }, (_, i) => (
        <text key={i} x={x(i * 96 + 48)} y={H - 8} textAnchor="middle" className="ep-chart__tick">Day {i + 1}</text>
      ))}
      {maxKw ? <line x1={pad.l} x2={W - pad.r} y1={y(maxKw)} y2={y(maxKw)} className="ep-chart__md" /> : null}
      <path d={d} className="ep-chart__line" />
      <text x={pad.l} y={pad.t + 2} className="ep-chart__tick">kW</text>
    </svg>
  );
}
