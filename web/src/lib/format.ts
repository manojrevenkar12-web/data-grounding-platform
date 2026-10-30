const fmt = (d: number) => new Intl.NumberFormat("en-GB", { maximumFractionDigits: d, minimumFractionDigits: d });

export const num = (x: number | null | undefined, digits = 0): string =>
  x === null || x === undefined || Number.isNaN(x) ? "–" : fmt(digits).format(x);

export const pct = (x: number | null | undefined, digits = 1): string => (x === null || x === undefined ? "–" : `${num(x * 100, digits)}%`);

export const signed = (x: number): string => `${x > 0 ? "+" : x < 0 ? "−" : ""}${num(Math.abs(x))}`;

export const label = (s: string): string => s.replace(/_/g, " ");

/** A title inside a sentence: lower the first letter unless it starts an acronym (A2A, AI). */
export const inline = (t: string): string => (/^[A-Z0-9]{2}/.test(t) ? t : t.charAt(0).toLowerCase() + t.slice(1));
