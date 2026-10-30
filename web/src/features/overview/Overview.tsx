import { ForestPlot } from "../../components/ForestPlot";
import { Loaded } from "../../components/States";
import { type Bet, type Bets, type Summary, useBets, useHeldout, useSummary } from "../../lib/data";
import { inline, num, pct } from "../../lib/format";

function NorthStar({ s }: { s: Summary }) {
  const ns = s.observed.north_star;
  const d = s.observed.drivers;
  const g = s.observed.guardrails;
  return (
    <section className="star" aria-labelledby="star-title">
      <div className="star__figure">
        <h2 id="star-title">Verified answers a week</h2>
        <p className="star__number">{num(ns.estimate_per_week)}</p>
        <p className="note">
          From analysts' audit of {num(ns.audited)} answers ({pct(ns.accuracy_estimate)} right); 90% interval{" "}
          {num(ns.interval_per_week[0])} to {num(ns.interval_per_week[1])}. The simulation's truth: {num(s.truth_north_star)}.
        </p>
      </div>
      <dl className="star__drivers">
        <div><dt>Sessions a week</dt><dd>{num(d.sessions_per_week)}</dd></div>
        <div><dt>Searches that found nothing</dt><dd>{pct(d.zero_result_share)}</dd></div>
        <div><dt>Sessions where the user rephrased</dt><dd>{pct(d.rephrased_share)}</dd></div>
        <div><dt>Fetches answered with a value</dt><dd>{pct(d.fetch_ok_share)}</dd></div>
        <div><dt>Wrong-number tickets a week</dt><dd>{num(g.wrong_number_tickets_per_week)}</dd></div>
        <div><dt>p95 latency</dt><dd>{num(g.latency_p95_ms)} ms</dd></div>
      </dl>
    </section>
  );
}

const COLUMNS: { key: keyof Bets["roadmap"]; title: string }[] = [
  { key: "now", title: "Now" }, { key: "next", title: "Next" }, { key: "discovery", title: "Discovery" }, { key: "not_now", title: "Not now" },
];

function Roadmap({ b }: { b: Bets }) {
  const today = b.variants.today?.summary;
  return (
    <section className="section" aria-labelledby="road-title">
      <h2 id="road-title">The roadmap that follows</h2>
      <div className="road">
        {COLUMNS.map((c) => {
          const items = b.roadmap[c.key] as Bet[];
          return (
            <div key={c.key} className={`road__col road__col--${c.key}`}>
              <h3>{c.title}</h3>
              {items.length === 0 ? <p className="note">Nothing.</p> : (
                <ul>
                  {items.map((x) => (
                    <li key={x.id}>
                      <strong>{x.title}</strong>
                      <span>{x.why?.join("; ") || "highest score that fits"}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
      {today && (
        <p className="note">
          Run together, the Now column adds {num(b.plan.delta.value?.per_week)} a week (90% interval{" "}
          {num(b.plan.delta.value?.low)} to {num(b.plan.delta.value?.high)}); wrong numbers fall from{" "}
          {pct(today.wrong_number_share)} to {pct(b.plan.summary.wrong_number_share)} of answers.
        </p>
      )}
    </section>
  );
}

function BlindNote() {
  const h = useHeldout();
  const first = h.data?.[0];
  const t = first?.configs.today;
  const p = first?.configs.plan;
  if (!first || !t || !p) return null;
  const val = (c: typeof t) => (c.results.correct ?? 0) - 3 * ((c.results.wrong_number ?? 0) + (c.results.stale ?? 0));
  const holds = val(p) > val(t);
  return (
    <p className={holds ? "verdict verdict--ok" : "verdict verdict--warn"}>
      Blind check ({first.cases} questions nobody tuned for): with the Now bets, {(p.results.correct ?? 0) - (t.results.correct ?? 0)} more
      right answers and {(p.results.wrong_number ?? 0) - (t.results.wrong_number ?? 0)} more wrong numbers than today.{" "}
      {holds ? "The plan holds up." : "Not yet a win: ship behind analyst review and a canary with its kill criterion."}
    </p>
  );
}

function Gate({ s }: { s: Summary }) {
  const passed = s.gate.filter((g) => g.passed).length;
  return (
    <section className="section" aria-labelledby="gate-title">
      <h2 id="gate-title">Release gate: {passed} of {s.gate.length} checks pass</h2>
      <ul className="gate">
        {s.gate.map((g) => (
          <li key={g.name} className={g.passed ? "gate__item" : "gate__item gate__item--fail"}>
            <span aria-hidden="true">{g.passed ? "✓" : "✕"}</span>
            <span>{g.name}</span>
            <span className="visually-hidden">{g.passed ? "passes" : "fails"}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function Overview() {
  const s = useSummary();
  const b = useBets();
  return (
    <>
      <header className="intro">
        <h1>What to build next, and the evidence for it</h1>
        <p className="lede">
          Every bet below was run on the same customer questions as today's platform before it was planned. Bets
          only backed by customer requests are drawn hollow: stated, not measured.
        </p>
      </header>
      <Loaded q={s} label="the North Star">{(x) => <NorthStar s={x} />}</Loaded>
      <Loaded q={b} label="the bets" empty={(x) => (x.scored.length === 0 ? <p>No bets in config/product.yaml yet.</p> : null)}>
        {(x) => {
          const now = new Set(x.roadmap.now.map((r) => r.id));
          const growth = x.scored.filter((r) => r.bucket !== "efficiency");
          const eff = x.scored.filter((r) => r.bucket === "efficiency");
          return (
            <>
              <section className="section" aria-labelledby="forest-title">
                <h2 id="forest-title" className="visually-hidden">The evidence behind each bet</h2>
                <ForestPlot bets={growth} now={now} />
                {eff.map((e) => (
                  <p key={e.id} className="note">
                    Efficiency: {inline(e.title)} saves EUR {num(e.value, 2)} a week in warehouse cost, measured the same way;
                    it does not change what customers are told.
                  </p>
                ))}
              </section>
              <Roadmap b={x} />
              <BlindNote />
            </>
          );
        }}
      </Loaded>
      <Loaded q={s} label="the release gate">{(x) => <Gate s={x} />}</Loaded>
    </>
  );
}
