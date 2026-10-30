import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/App";
import { ForestPlot } from "../src/components/ForestPlot";
import { Blind } from "../src/features/blind/Blind";
import { Glossary } from "../src/features/glossary/Glossary";
import type { Bet } from "../src/lib/data";
import { inline, num, pct, signed } from "../src/lib/format";

const data = (name: string) => JSON.parse(readFileSync(resolve(__dirname, "../public/data", name), "utf8"));
const ALL = ["summary.json", "bets.json", "glossary.json", "heldout.json"];
const all = () => Object.fromEntries(ALL.map((f) => [f, data(f)]));

function wrap(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function serve(files: Record<string, unknown>) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const name = String(url).split("/").pop()!;
    return name in files ? new Response(JSON.stringify(files[name]), { status: 200 }) : new Response("no", { status: 500 });
  }));
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
});

describe("format", () => {
  it("formats numbers, shares and titles", () => {
    expect(num(15170)).toBe("15,170");
    expect(pct(0.194)).toBe("19.4%");
    expect(signed(-345)).toBe("−345");
    expect(signed(12)).toBe("+12");
    expect(inline("Agent-to-agent (A2A) endpoint")).toBe("agent-to-agent (A2A) endpoint");
    expect(inline("AI answers")).toBe("AI answers");
  });
});

describe("ForestPlot", () => {
  it("describes every bet, measured or stated", () => {
    const bets = data("bets.json").scored.filter((b: Bet) => b.bucket !== "efficiency");
    render(<ForestPlot bets={bets} now={new Set(["facets"])} />);
    const label = screen.getByRole("img").getAttribute("aria-label")!;
    for (const b of bets) expect(label).toContain(b.title);
    expect(label).toContain("stated");
  });
});

describe("the review", () => {
  it("opens on the evidence, the roadmap and the gate", async () => {
    serve(all());
    wrap(<App />);
    expect(await screen.findByRole("heading", { name: "What to build next, and the evidence for it" })).toBeInTheDocument();
    const s = data("summary.json");
    expect(await screen.findByText(num(s.observed.north_star.estimate_per_week))).toBeInTheDocument();
    const passed = s.gate.filter((g: { passed: boolean }) => g.passed).length;
    expect(await screen.findByRole("heading", { name: `Release gate: ${passed} of ${s.gate.length} checks pass` })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Now" })).toBeInTheDocument();
  });

  it("moves between views with the keyboard", async () => {
    serve(all());
    wrap(<App />);
    screen.getByRole("tab", { name: "Overview" }).focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(await screen.findByRole("heading", { name: "The bets", level: 1 })).toBeInTheDocument();
    expect(window.location.hash).toBe("#bets");
  });

  it("shows errors with a retry, and skeletons while loading", async () => {
    serve({});
    wrap(<App />);
    const alerts = await screen.findAllByRole("alert");
    expect(alerts[0]).toHaveTextContent("dgp export-web");
    serve(all());
    await userEvent.click(within(alerts[0]!).getByRole("button", { name: "Load again" }));
    expect(await screen.findByText(num(data("summary.json").observed.north_star.estimate_per_week))).toBeInTheDocument();
  });

  it("shows skeletons while loading", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    wrap(<App />);
    expect(screen.getAllByRole("status")[0]).toHaveAccessibleName("Loading the North Star");
  });
});

describe("blind check and glossary", () => {
  it("says how to run a blind set when there is none", async () => {
    serve({ "heldout.json": [] });
    wrap(<Blind />);
    expect(await screen.findByRole("heading", { name: "No blind set has been run" })).toBeInTheDocument();
  });

  it("reviews proposals and offers the decisions for download", async () => {
    serve({ "glossary.json": { metrics: { ev_sales: ["e-car"] }, geos: { DE: ["deutschland"] } } });
    wrap(<Glossary />);
    expect(await screen.findByText("2 to review, 0 approved, 0 rejected")).toBeInTheDocument();
    const download = screen.getByRole("button", { name: "Download decisions" });
    expect(download).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Approve e-car for ev sales" }));
    await userEvent.click(screen.getByRole("button", { name: "Reject deutschland for DE" }));
    expect(await screen.findByText("0 to review, 1 approved, 1 rejected")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Every proposal has a decision" })).toBeInTheDocument();
    expect(download).toBeEnabled();
  });

  it("an empty proposal list says so", async () => {
    serve({ "glossary.json": { metrics: {}, geos: {} } });
    wrap(<Glossary />);
    expect(await screen.findByRole("heading", { name: "No proposals this week" })).toBeInTheDocument();
  });
});
