import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AppProvider } from "@/components/AppContext";
import { AppRoutes } from "@/App";
import { ANALYSIS_ID, mockApi, savedAnalysis } from "./mockApi";

function renderDashboard(tab?: string) {
  const api = mockApi();
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={[`/analysis/${ANALYSIS_ID}${tab ? `?tab=${tab}` : ""}`]}>
      <AppProvider><AppRoutes /></AppProvider>
    </MemoryRouter>,
  );
  return api;
}

describe("dashboard renders the saved demo analysis", () => {
  it("overview shows demo labelling, findings and three strategies", async () => {
    renderDashboard();
    expect(await screen.findByText("Major findings")).toBeInTheDocument();
    expect(screen.getByTestId("demo-banner")).toHaveTextContent("DEMO DATA");
    const strategies = savedAnalysis.strategies.strategies as { key: string; summary: string }[];
    expect(strategies).toHaveLength(3);
    for (const s of strategies) expect(screen.getByText(s.summary)).toBeInTheDocument();
    expect(screen.getAllByText("Observed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Modelled").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Exact available capital unknown/i).length).toBeGreaterThan(0);
  });

  it("competitor matrix lists every sampled listing with flags", async () => {
    renderDashboard("competitors");
    const table = await screen.findByTestId("listing-matrix");
    const rows = within(table).getAllByRole("row");
    expect(rows.length - 1).toBe(savedAnalysis.competitors.listings.length);
    expect(within(table).getByText("Currency mismatch")).toBeInTheDocument();
    expect(within(table).getByText("No currency")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Search listings"), "Kaapi Trail");
    expect(within(screen.getByTestId("listing-matrix")).getAllByRole("row").length).toBe(3);
  });

  it("market trends explain relative interest", async () => {
    renderDashboard("trends");
    expect(await screen.findByText("Relative search interest over time")).toBeInTheDocument();
    expect(screen.getByText(/Search interest is not sales demand/)).toBeInTheDocument();
    expect(screen.getAllByText("coffee beans").length).toBeGreaterThan(0);
  });

  it("war room shows real tool and critic events", async () => {
    renderDashboard("warroom");
    const feed = await screen.findByTestId("event-feed");
    expect(within(feed).getAllByText("Tool completed").length).toBeGreaterThan(5);
    expect(within(feed).getAllByText("Critic rejected").length).toBeGreaterThan(0);
    expect(within(feed).getAllByText("Revision performed").length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("tab", { name: "Warnings & failures" }));
    expect(within(screen.getByTestId("event-feed")).queryAllByText("Tool completed")).toHaveLength(0);
  });

  it("evidence tab lists citations with data-source labels", async () => {
    renderDashboard("evidence");
    const table = await screen.findByTestId("citations");
    expect(within(table).getAllByRole("row").length - 1).toBe(savedAnalysis.report.report.citations.length);
    expect(within(table).getAllByText("Demo data").length).toBe(savedAnalysis.report.report.citations.length);
    expect(screen.getByText("Known limitations")).toBeInTheDocument();
  });

  it("what-if sliders call the backend simulator, never SerpApi", async () => {
    const { calls } = renderDashboard("whatif");
    expect(await screen.findByText("Break-even indicator")).toBeInTheDocument();
    const thumb = screen.getAllByRole("slider")[0];
    thumb.focus();
    fireEvent.keyDown(thumb, { key: "ArrowRight" });
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/simulate"))).toBe(true));
    const post = calls.find((c) => c.url.endsWith("/simulate"))!;
    const body = post.body as { strategy_key: string; inputs: { selling_price: number } };
    const original = savedAnalysis.strategies.strategies.find((s: { key: string }) => s.key === body.strategy_key).sim_inputs.selling_price;
    expect(body.inputs.selling_price).toBeGreaterThan(original);
    expect(calls.filter((c) => c.method === "POST" && !c.url.endsWith("/simulate"))).toHaveLength(0);
  });
});
