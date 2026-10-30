import { motion, useReducedMotion } from "motion/react";
import type { Bet } from "../lib/data";
import { label, num } from "../lib/format";
import { motionTokens } from "../theme/motion";

/** Each bet's measured value with its 90% interval, on one axis: the evidence behind the roadmap.
 *  The axis is asinh-scaled so a bet worth 30 a week and one worth 14,000 are both readable; the
 *  tick labels are the real values. Bets only backed by demand are drawn hollow: stated, not measured. */
const W = 720;
const LEFT = 300;
const RIGHT = 40;
const ROW = 44;
const TOP = 28;

const s = (v: number) => Math.asinh(v / 50);

export function ForestPlot({ bets, now }: { bets: Bet[]; now: Set<string> }) {
  const reduce = useReducedMotion();
  const rows = [...bets].sort((a, b) => b.value - a.value);
  const max = Math.max(...rows.map((b) => b.interval?.[1] ?? b.value), 1);
  const min = Math.min(0, ...rows.map((b) => b.interval?.[0] ?? b.value));
  const x = (v: number) => LEFT + ((s(v) - s(min)) / (s(max) - s(min))) * (W - LEFT - RIGHT);
  const ticks = [0, 100, 1000, 10000].filter((t) => t <= max * 1.05 && t >= min);
  const H = TOP + rows.length * ROW + 8;
  return (
    <figure className="forest">
      <figcaption>
        Value of each bet, verified answers a week less three for every wrong number, with its 90% interval
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={rows.map((b) => `${b.title}: ${num(b.value)}${b.interval ? ` (${num(b.interval[0])} to ${num(b.interval[1])})` : " stated"}`).join("; ")}>
        {ticks.map((t) => (
          <g key={t} className={t === 0 ? "forest__zero" : "forest__tick"}>
            <line x1={x(t)} x2={x(t)} y1={TOP - 10} y2={H} />
            <text x={x(t)} y={TOP - 14} textAnchor="middle">{num(t)}</text>
          </g>
        ))}
        {rows.map((b, i) => {
          const y = TOP + i * ROW + ROW / 2;
          const [lo, hi] = b.interval ?? [b.value, b.value];
          return (
            <g key={b.id} className={`forest__row forest__row--${b.evidence}`}>
              <text className="forest__name" x={0} y={y} dy="-0.15em">{b.title}</text>
              <text className="forest__meta" x={0} y={y} dy="1.1em">
                {label(b.evidence)}, {b.effort_weeks} eng-weeks{now.has(b.id) ? ", planned now" : ""}
              </text>
              {b.interval && (
                <motion.line className="forest__ci" y1={y} y2={y}
                  initial={reduce ? false : { x1: x(0), x2: x(0) }} animate={{ x1: x(lo), x2: x(hi) }}
                  transition={{ duration: motionTokens.slow, delay: i * motionTokens.stagger * 3, ease: motionTokens.ease }} />
              )}
              <motion.circle className={b.evidence === "demand_signal" ? "forest__dot forest__dot--stated" : "forest__dot"}
                cy={y} r={b.evidence === "demand_signal" ? 6 : 7}
                initial={reduce ? false : { cx: x(0), opacity: 0 }} animate={{ cx: x(b.value), opacity: 1 }}
                transition={{ duration: motionTokens.slow, delay: i * motionTokens.stagger * 3, ease: motionTokens.ease }} />
            </g>
          );
        })}
      </svg>
    </figure>
  );
}
