import { Route, Routes } from "react-router-dom";
import { AppProvider } from "@/components/AppContext";
import { EmptyState, Layout, PageShell } from "@/components/Layout";
import { OnboardingWizard } from "@/features/onboarding/OnboardingWizard";
import { ReviewPage } from "@/features/onboarding/ReviewPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { LandingPage } from "@/pages/LandingPage";
import { RunPage } from "@/pages/RunPage";

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<LandingPage />} />
        <Route path="onboarding" element={<OnboardingWizard />} />
        <Route path="onboarding/review" element={<ReviewPage />} />
        <Route path="analysis/:id/run" element={<RunPage />} />
        <Route path="analysis/:id" element={<DashboardPage />} />
        <Route path="*" element={<PageShell><EmptyState title="Page not found" message="That page does not exist." /></PageShell>} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <AppProvider>
      <AppRoutes />
    </AppProvider>
  );
}
