import { useQuery } from "@tanstack/react-query";

/** The files `dgp export-web` writes to public/data, from reports/results.json. */
export type Evidence = "measured_offline" | "modelled" | "demand_signal";
export type Bucket = "north_star" | "efficiency" | "discovery";

export interface Interval { per_week: number; low: number; high: number }
export interface Bet {
  id: string; title: string; bucket: Bucket; evidence: Evidence; effort_weeks: number; needs: string[];
  kill: string; problem: string; hypothesis: string; value: number; unit: string; interval: [number, number] | null;
  confidence: number; score: number; breaches: string[]; why?: string[];
  correct_per_week?: number; wrong_numbers_per_week?: number; measured_against?: string;
}
export interface VariantSummary {
  questions: number; correct_per_week: number; correct_share: number; wrong_number_share: number; stale_share: number;
  missed_share: number; latency_p95_ms: number | null; cost_eur: number; cost_per_correct_eur: number; tickets: number;
  premium_leaks: number; weeks: number;
}
export interface Variant { summary: VariantSummary; delta: Record<string, Interval>; measured_against: string }
export interface Bets {
  scored: Bet[];
  roadmap: { now: Bet[]; next: Bet[]; discovery: Bet[]; not_now: Bet[]; capacity_left: Record<string, number> };
  plan: { flags: Record<string, boolean>; summary: VariantSummary; delta: Record<string, Interval>; parts_sum: number; breaches: string[] };
  variants: Record<string, Variant>;
}
export interface GateCheck { name: string; passed: boolean; value: unknown; op: string; bound: unknown }
export interface Summary {
  represents: number; truth_north_star: number; gate: GateCheck[];
  observed: {
    weeks: number;
    north_star: { estimate_per_week: number; interval_per_week: [number, number]; audited: number; accuracy_estimate: number; accuracy_interval: [number, number] };
    drivers: { sessions_per_week: number; searches_per_week: number; zero_result_share: number; rephrased_share: number; fetch_ok_share: number; fetch_status: Record<string, number> };
    guardrails: { latency_p95_ms: number; cost_per_week_eur: number; cost_per_fetch_eur: number; wrong_number_tickets_per_week: number };
    top_ticketed_statistics: { stat_id: string; tickets: number }[];
    clients: Record<string, number>;
    producers: { deliveries: number; refused: number; days_refused_to_live_median: number | null; refusal_reasons: Record<string, number> };
  };
}
export interface Glossary { metrics: Record<string, string[]>; geos: Record<string, string[]> }
export interface HeldoutConfig { right: number; share: number; by_expect: Record<string, { cases: number; right: number }>; results: Record<string, number> }
export interface Heldout { set: string; status: string; cases: number; configs: Record<string, HeldoutConfig>; misses: { id: string; expect: string; result: string; why: string }[] }

async function load<T>(path: string): Promise<T> {
  const res = await fetch(`./data/${path}`);
  if (!res.ok) throw new Error(`Could not load ${path} (HTTP ${res.status}). Run \`dgp run && dgp export-web\`, then reload.`);
  return (await res.json()) as T;
}

export const useSummary = () => useQuery({ queryKey: ["summary"], queryFn: () => load<Summary>("summary.json") });
export const useBets = () => useQuery({ queryKey: ["bets"], queryFn: () => load<Bets>("bets.json") });
export const useGlossary = () => useQuery({ queryKey: ["glossary"], queryFn: () => load<Glossary>("glossary.json") });
export const useHeldout = () => useQuery({ queryKey: ["heldout"], queryFn: () => load<Heldout[]>("heldout.json") });
