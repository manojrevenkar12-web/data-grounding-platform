import { Loaded } from "../../components/States";
import { type Bet, type Bets as BetsData, useBets } from "../../lib/data";
import { label, num, pct, signed } from "../../lib/format";

function Card({ b, data }: { b: Bet; data: BetsData }) {
  const v = data.variants[b.id];
  const base = v ? data.variants[v.measured_against]?.summary : undefined;
  return (
    <article className={`bet bet--${b.evidence}`} aria-labelledby={`bet-${b.id}`}>
      <header>
        <h2 id={`bet-${b.id}`}>{b.title}</h2>
        <p className="bet__tags">
          <span className={`tag tag--${b.evidence}`}>{label(b.evidence)}</span>
          <span className="tag">{label(b.bucket)}</span>
          <span className="tag">{b.effort_weeks} eng-weeks</span>
          <span className="tag">score {num(b.score, 1)}</span>
        </p>
      </header>
      <dl className="bet__body">
        <dt>Problem</dt><dd>{b.problem}</dd>
        <dt>Hypothesis</dt><dd>{b.hypothesis}</dd>
        <dt>Evidence</dt>
        <dd>
          {b.bucket === "efficiency" ? `EUR ${num(b.value, 2)} saved a week.` :
            b.interval ? `${num(b.value)} a week (${num(b.interval[0])} to ${num(b.interval[1])}), measured on top of ${label(b.measured_against ?? "today")}.` :
              `${num(b.value)} a week, stated by the customers asking for it, not measured.`}
          {v && base && b.bucket !== "efficiency" && (
            <> Wrong numbers {pct(base.wrong_number_share)} → {pct(v.summary.wrong_number_share)}; verified answers{" "}
              {signed(v.delta.correct?.per_week ?? 0)} a week.</>
          )}
        </dd>
        <dt>Kill criterion</dt><dd>{b.kill}</dd>
        {b.needs.length > 0 && (<><dt>Needs</dt><dd>{b.needs.map(label).join(", ")}</dd></>)}
      </dl>
    </article>
  );
}

function Shipped({ data }: { data: BetsData }) {
  const asof = data.variants.without_as_of;
  const ent = data.variants.without_entitlement_answers;
  if (!asof || !ent) return null;
  return (
    <section className="section" aria-labelledby="shipped-title">
      <h2 id="shipped-title">Features already live, still earning their keep</h2>
      <p className="note">Switched off for the same four weeks, against today.</p>
      <ul className="plain">
        <li>Answers as of a date: without it, {num(asof.delta.stale?.per_week)} more stale numbers a week.</li>
        <li>"Not in your plan" instead of a bare error: without it, {num(ent.delta.wrong_number?.per_week)} more wrong numbers a week, as clients guess what the error meant.</li>
      </ul>
    </section>
  );
}

export function Bets() {
  const q = useBets();
  return (
    <>
      <h1 className="page-title">The bets</h1>
      <Loaded q={q} label="the bets" empty={(d) => (d.scored.length === 0 ? <p>No bets yet.</p> : null)}>
        {(d) => (
          <>
            <div className="bets">{[...d.scored].sort((a, b) => b.score - a.score).map((b) => <Card key={b.id} b={b} data={d} />)}</div>
            <Shipped data={d} />
          </>
        )}
      </Loaded>
    </>
  );
}
