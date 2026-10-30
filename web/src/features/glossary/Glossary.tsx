import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useMemo, useState } from "react";
import { EmptyState, Loaded } from "../../components/States";
import { type Glossary as GlossaryData, useGlossary } from "../../lib/data";
import { label } from "../../lib/format";
import { motionTokens } from "../../theme/motion";

type Verdict = "approved" | "rejected";
interface Candidate { key: string; kind: "metric" | "geography"; target: string; word: string }

function candidates(g: GlossaryData): Candidate[] {
  const m = Object.entries(g.metrics).flatMap(([t, ws]) => ws.map((w) => ({ key: `m:${t}:${w}`, kind: "metric" as const, target: t, word: w })));
  const geo = Object.entries(g.geos).flatMap(([t, ws]) => ws.map((w) => ({ key: `g:${t}:${w}`, kind: "geography" as const, target: t, word: w })));
  return [...geo, ...m];
}

function Queue({ g }: { g: GlossaryData }) {
  const all = useMemo(() => candidates(g), [g]);
  const [verdicts, setVerdicts] = useState<Record<string, Verdict>>({});
  const reduce = useReducedMotion();
  const open = all.filter((c) => !verdicts[c.key]);
  const decided = Object.values(verdicts);
  const download = () => {
    const blob = new Blob([JSON.stringify({ reviewed: new Date().toISOString(), decisions: all.filter((c) => verdicts[c.key]).map((c) => ({ ...c, verdict: verdicts[c.key] })) }, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "glossary-review.json";
    a.click();
    URL.revokeObjectURL(a.href);
  };
  return (
    <>
      <div className="queue__bar" role="status">
        <span>{open.length} to review, {decided.filter((v) => v === "approved").length} approved, {decided.filter((v) => v === "rejected").length} rejected</span>
        <button type="button" className="btn" onClick={download} disabled={decided.length === 0}>Download decisions</button>
      </div>
      {open.length === 0 ? (
        <EmptyState title="Every proposal has a decision">Download the decisions and commit them as the approved list; only approved words are served.</EmptyState>
      ) : (
        <ul className="queue">
          <AnimatePresence initial={false}>
            {open.map((c) => (
              <motion.li key={c.key} className="queue__item" layout={!reduce}
                exit={reduce ? undefined : { opacity: 0, x: 24 }} transition={{ duration: motionTokens.base, ease: motionTokens.ease }}>
                <span className="queue__word">{c.word}</span>
                <span className="queue__target">means the {c.kind} <strong>{label(c.target)}</strong></span>
                <span className="queue__actions">
                  <button type="button" className="btn btn--ghost" onClick={() => setVerdicts((v) => ({ ...v, [c.key]: "approved" }))}
                    aria-label={`Approve ${c.word} for ${label(c.target)}`}>Approve</button>
                  <button type="button" className="btn btn--ghost" onClick={() => setVerdicts((v) => ({ ...v, [c.key]: "rejected" }))}
                    aria-label={`Reject ${c.word} for ${label(c.target)}`}>Reject</button>
                </span>
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
      )}
    </>
  );
}

export function Glossary() {
  const q = useGlossary();
  return (
    <section className="section" aria-labelledby="g-title">
      <h1 id="g-title">Glossary review</h1>
      <p className="lede">Words customers used that the catalogue does not, mined from rephrased questions. Nothing here is served until an analyst approves it; some proposals are chance co-occurrences.</p>
      <Loaded q={q} label="the proposals" empty={(g) => (candidates(g).length === 0 ? <EmptyState title="No proposals this week">The mining job found no word with enough sessions behind it.</EmptyState> : null)}>
        {(g) => <Queue g={g} />}
      </Loaded>
    </section>
  );
}
