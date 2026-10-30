import { EmptyState, Loaded } from "../../components/States";
import { type Heldout, useHeldout } from "../../lib/data";
import { label } from "../../lib/format";

const W = 3; // config/product.yaml: value.wrong_number_weight

function HeldoutSet({ h }: { h: Heldout }) {
  const t = h.configs.today;
  const p = h.configs.plan;
  const val = (c: Heldout["configs"][string]) => (c.results.correct ?? 0) - W * ((c.results.wrong_number ?? 0) + (c.results.stale ?? 0));
  return (
    <article className="section" aria-labelledby={`h-${h.set}`}>
      <h2 id={`h-${h.set}`}>{h.set}: {h.cases} questions written blind</h2>
      <p className="note">From the public catalogue listing only, by someone who had not seen how the platform searches. First run, recorded once. Status: {h.status}.</p>
      <table className="table">
        <thead><tr><th scope="col">Platform</th><th scope="col">Right</th><th scope="col">Right numbers</th><th scope="col">Wrong numbers</th><th scope="col">Trust-weighted</th></tr></thead>
        <tbody>
          {Object.entries(h.configs).map(([name, c]) => (
            <tr key={name}>
              <th scope="row">{name === "plan" ? "with the Now bets" : name}</th>
              <td>{c.right} of {h.cases}</td><td>{c.results.correct ?? 0}</td><td>{c.results.wrong_number ?? 0}</td><td>{val(c)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {t && p && (
        <p className={val(p) > val(t) ? "verdict verdict--ok" : "verdict verdict--warn"}>
          {val(p) > val(t)
            ? "The planned bets hold up on questions nobody tuned them for."
            : "Not yet a win on blind questions: the plan answers more, but also gives more wrong numbers. The glossary ships behind analyst review and a two-week canary with its kill criterion."}
        </p>
      )}
      <p className="note">Its failures are not studied: that would make it a regression set and need a new blind set.</p>
      {h.misses.length > 0 && <p className="note">{h.misses.length} questions the planned platform got wrong ({[...new Set(h.misses.map((m) => label(m.result)))].join(", ")}).</p>}
    </article>
  );
}

export function Blind() {
  const q = useHeldout();
  return (
    <>
      <h1 className="page-title">The blind check</h1>
      <Loaded q={q} label="held-out results" empty={(d) => (d.length === 0 ? (
        <EmptyState title="No blind set has been run">Have someone write questions from <code>heldout/WRITING_QUESTIONS.md</code>, then run <code>dgp heldout &lt;set&gt;</code> once.</EmptyState>
      ) : null)}>
        {(d) => <>{d.map((h) => <HeldoutSet key={h.set} h={h} />)}</>}
      </Loaded>
    </>
  );
}
