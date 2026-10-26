"use client";

import { useId, useState } from "react";
import { shortPartName, type PartTile } from "@/lib/inventory";

// One equal slice per part. The slice is everything expected inside the processed devices; the lit
// shape grows out from the middle as parts are cut. Hover, focus or tap a slice for its numbers.
const SIZE = 440, C = SIZE / 2;
const R_IN = 78, R_OUT = 212;          // hole and outer edge
const ROUND = 9;                        // corner radius (drawn as a round-joined stroke)
const GAP = 3;                          // px between slices
const RIM = 7;                          // px between a slice's edge and its lit shape
const LABEL_R = R_IN + 0.62 * (R_OUT - R_IN);

const at = (r: number, a: number) => `${(C + r * Math.cos(a)).toFixed(2)} ${(C + r * Math.sin(a)).toFixed(2)}`;

/** Ring sector between radii r0..r1 and angles a0..a1, shrunk by `pad` px on every side. */
function sector(r0: number, r1: number, a0: number, a1: number, pad: number) {
  const ri = r0 + pad, ro = r1 - pad;
  if (ro - ri < 0.5) return null;
  const s0 = a0 + pad / ro, s1 = a1 - pad / ro, t0 = a0 + pad / ri, t1 = a1 - pad / ri;
  const large = s1 - s0 > Math.PI ? 1 : 0;
  return `M${at(ro, s0)} A${ro} ${ro} 0 ${large} 1 ${at(ro, s1)} L${at(ri, t1)} A${ri} ${ri} 0 ${large} 0 ${at(ri, t0)}Z`;
}

export function PartsWheel({ tiles, devices }: { tiles: PartTile[]; devices: number }) {
  const [active, setActive] = useState<number | null>(null);
  const uid = useId().replace(/:/g, "");
  const n = tiles.length;
  const step = (2 * Math.PI) / n;
  const a = active !== null ? tiles[active] : null;

  return (
    <div className="flex flex-col items-center">
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="w-full max-w-[440px] select-none" role="group"
        aria-label={`Parts to cut from ${devices} processed device${devices === 1 ? "" : "s"}`}>
        {tiles.map((t, i) => {
          const a0 = -Math.PI / 2 + i * step, a1 = a0 + (n === 1 ? 2 * Math.PI - 0.001 : step);
          const half = GAP / 2 + ROUND / 2;
          const outer = sector(R_IN, R_OUT, a0, a1, half);
          const frac = t.expected ? Math.min(t.cut / t.expected, 1) : t.cut > 0 ? 1 : 0;
          const span = R_OUT - R_IN - 2 * RIM;
          // A small share still shows as a nub, so "some cut" never looks like "none cut"
          const litOuter = frac > 0 ? R_IN + RIM + Math.max(frac * span, ROUND + 4) : 0;
          const la0 = a0 + RIM / LABEL_R, la1 = a1 - RIM / LABEL_R;
          const lit = frac > 0 ? sector(R_IN + RIM, litOuter, la0, la1, half) : null;
          // The lit shape's outline without the rounded corners: dark text is clipped to it, so a label
          // that crosses the lit edge switches colour exactly there
          const litClip = frac > 0 ? sector(R_IN + RIM, litOuter, la0, la1, GAP / 2) : null;
          const mid = (a0 + a1) / 2;
          const lx = C + LABEL_R * Math.cos(mid), ly = C + LABEL_R * Math.sin(mid);
          const label = shortPartName(t);
          const text = (dark: boolean) => (<>
            <text x={lx} y={ly - 2} textAnchor="middle" className="text-[22px] font-semibold tabular-nums"
              fill={dark ? "rgb(var(--primary-foreground))" : "rgb(var(--foreground))"}>{t.expected || t.cut}</text>
            <text x={lx} y={ly + 15} textAnchor="middle" className="text-[11.5px]"
              fill={dark ? "rgb(var(--primary-foreground))" : "rgb(var(--muted-foreground))"}>{label}</text>
          </>);
          return (
            <g key={t.componentTypeId} role="button" tabIndex={0}
              aria-label={`${t.name}: ${t.cut} of ${t.expected} cut${t.done ? ", done" : `, ${t.left} left`}`}
              className="cursor-pointer outline-none transition-opacity duration-150"
              style={{ opacity: active === null || active === i ? 1 : 0.45 }}
              onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(i)} onBlur={() => setActive(null)} onClick={() => setActive(i)}>
              {outer && <path d={outer} fill="rgb(var(--border))" stroke="rgb(var(--border))" strokeWidth={ROUND} strokeLinejoin="round" />}
              {text(false)}
              {lit && <path d={lit} fill="rgb(var(--primary))" stroke="rgb(var(--primary))" strokeWidth={ROUND} strokeLinejoin="round" />}
              {litClip && (<>
                <clipPath id={`${uid}-lit-${i}`}><path d={litClip} /></clipPath>
                <g clipPath={`url(#${uid}-lit-${i})`}>{text(true)}</g>
              </>)}
            </g>
          );
        })}
        <g aria-hidden="true" textAnchor="middle">
          {a ? (<>
            <text x={C} y={C - 12} className="text-[13px] font-semibold" fill="rgb(var(--foreground))">{shortPartName(a)}</text>
            <text x={C} y={C + 6} className="text-[12px] tabular-nums" fill="rgb(var(--muted-foreground))">{a.cut} of {a.expected} cut</text>
            <text x={C} y={C + 23} className="text-[12px] font-medium" fill={a.done ? "rgb(var(--success-ink))" : "rgb(var(--foreground))"}>
              {a.done ? "Done" : `${a.left} left`}
            </text>
          </>) : (<>
            <text x={C} y={C + 4} className="text-[26px] font-semibold tabular-nums" fill="rgb(var(--foreground))">{devices}</text>
            <text x={C} y={C + 22} className="text-[11.5px]" fill="rgb(var(--muted-foreground))">processed</text>
          </>)}
        </g>
      </svg>
      <p className="mt-1 text-xs text-muted-foreground">Each slice is a part. The lit area is how many have been cut.</p>
    </div>
  );
}
