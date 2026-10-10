import { vi } from "vitest";
import saved from "./fixtures/demo-analysis.json";

export const savedAnalysis = saved as unknown as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
export const ANALYSIS_ID: string = savedAnalysis.status.id;

type Handler = (url: URL, init?: RequestInit) => unknown;

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

/** Routes fetch() calls to the saved analysis produced by the real backend workflow. */
export function mockApi(overrides: Record<string, Handler> = {}) {
  const calls: { url: string; method: string; body?: unknown }[] = [];
  const spy = vi.spyOn(globalThis, "fetch").mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input.toString(), "http://localhost");
    const method = init?.method ?? "GET";
    calls.push({ url: url.pathname + url.search, method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    for (const [pattern, handler] of Object.entries(overrides)) {
      if (url.pathname.endsWith(pattern)) return json(handler(url, init));
    }
    const p = url.pathname;
    if (p === "/api/config") return json(savedAnalysis.config);
    if (p === "/api/analyses") return json([]);
    if (p.endsWith("/events")) {
      const after = Number(url.searchParams.get("after") ?? 0);
      const events = savedAnalysis.events.events.filter((e: { seq: number }) => e.seq > after);
      return json({ ...savedAnalysis.events, events, last_seq: events.at(-1)?.seq ?? after });
    }
    for (const key of ["competitors", "trends", "strategies", "report", "evidence"]) {
      if (p.endsWith(`/${key}`)) return json(savedAnalysis[key]);
    }
    if (p.endsWith("/simulate")) {
      const body = JSON.parse(String(init?.body));
      const sim = savedAnalysis.strategies.simulations[body.strategy_key];
      return json({ simulation: { ...sim, inputs: body.inputs }, serpapi_requests_made: 0, note: "mock" });
    }
    if (/\/api\/analyses\/[a-f0-9]+$/.test(p)) return json(savedAnalysis.status);
    return json({ error: { code: "not_found", message: `No mock for ${p}` } }, 404);
  });
  return { spy, calls };
}
