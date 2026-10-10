import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AppProvider } from "@/components/AppContext";
import { AppRoutes } from "@/App";
import { DRAFT_STORAGE_KEY } from "@/features/onboarding/flow";
import { mockApi } from "./mockApi";

function renderAt(path: string) {
  mockApi();
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={[path]}>
      <AppProvider><AppRoutes /></AppProvider>
    </MemoryRouter>,
  );
}

const next = () => userEvent.click(screen.getByRole("button", { name: /^next/i }));

describe("onboarding wizard", () => {
  it("blocks Next with a validation error until a business type is chosen", async () => {
    renderAt("/onboarding");
    expect(await screen.findByText("What kind of business is this?")).toBeInTheDocument();
    await next();
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose a business type");
    expect(screen.getByRole("radio", { name: /hybrid/i })).toBeDisabled(); // reserved for a later release
    await userEvent.click(screen.getByRole("radio", { name: /online e-commerce/i }));
    await next();
    expect(await screen.findByText("Where are you today?")).toBeInTheDocument();
  });

  it("branches the market question: physical shops are asked for a city", async () => {
    renderAt("/onboarding");
    await userEvent.click(await screen.findByRole("radio", { name: /physical retail shop/i }));
    await next();
    await userEvent.click(screen.getByRole("radio", { name: /planning a new business/i }));
    await next();
    await userEvent.click(screen.getByRole("radio", { name: /^food & beverages/i }));
    await next();
    // Focus options come from the registry for the chosen category
    expect(await screen.findByRole("radio", { name: /coffee and tea/i })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /premium pantry products/i })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /coffee and tea/i }));
    await next();
    expect(await screen.findByLabelText("City")).toBeInTheDocument();
    expect(screen.queryByText(/sell worldwide/i)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /india/i }));
    await next();
    expect(await screen.findByText("City is required for a physical shop")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("City"), "Mumbai");
    await next();
    expect(await screen.findByRole("radio", { name: /shopping mall/i })).toBeInTheDocument();
  });

  it("shows a custom field for Other and a comparison picker for Undecided", async () => {
    renderAt("/onboarding?step=category");
    await userEvent.click(await screen.findByRole("radio", { name: /^other/i }));
    expect(screen.getByLabelText("Describe your category")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /^undecided/i }));
    expect(screen.getByText(/compare category-level opportunity for/i)).toBeInTheDocument();
    expect(screen.queryByLabelText("Describe your category")).not.toBeInTheDocument();
  });

  it("saves the draft locally as the user answers", async () => {
    renderAt("/onboarding");
    await userEvent.click(await screen.findByRole("radio", { name: /online e-commerce/i }));
    const stored = JSON.parse(localStorage.getItem(DRAFT_STORAGE_KEY) ?? "{}");
    expect(stored.draft.business_type).toBe("online");
  });

  it("review screen lists unknown inputs explicitly", async () => {
    const { fromProfile, storeDraft } = await import("@/features/onboarding/flow");
    const { savedAnalysis } = await import("./mockApi");
    storeDraft({ draft: fromProfile(savedAnalysis.status.profile), step: "advanced", profileId: null });
    renderAt("/onboarding/review");
    expect(await screen.findByText("Your business profile")).toBeInTheDocument();
    expect(screen.getAllByText("Unknown").length).toBeGreaterThan(3);
    expect(screen.getByText(/Yes – recorded; research scoped to the pilot/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run market analysis/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /save draft/i })).toBeEnabled();
  });
});
