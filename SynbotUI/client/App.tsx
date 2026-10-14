import "./global.css";
import { lazy, Suspense } from "react";

import { Toaster } from "@/components/ui/toaster";
import { AskHost } from "@/lib/ask";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HashRouter, Routes, Route, Navigate } from "react-router-dom";
import ThemeProvider from "./components/theme-provider";
import AuthProvider from "./components/AuthProvider";
import { TourProvider } from "./components/tour/TourProvider";
import { WalkthroughProvider } from "./components/tour/WalkthroughProvider";
import ProtectedRoute from "./components/ProtectedRoute";
import Layout from "./components/Layout";
import Workstation from "./pages/Workstation";
import Executive from "./pages/Executive";
import ReportComposer from "./pages/ReportComposer";
import ReportLibrary from "./pages/ReportLibrary";
import Procurement from "./pages/Procurement";
import PatientRelations from "./pages/PatientRelations";
import HospitalCalendar from "./pages/HospitalCalendar";
import ARAgingBucketDetails from "./pages/ARAgingBucketDetails";
import HR from "./pages/HR";
import Suppliers from "./pages/Suppliers";
import AskSynbot from "./pages/AskSynbot";
import CalendarTaskManager from "./pages/CalendarTaskManager";
import AgentsDashboard from "./pages/AgentsDashboard";
import AgentDetail from "./pages/AgentDetail";
import Workflow from "./pages/Workflow";
import Settings from "./pages/Settings";
import AdminUsers from "./pages/AdminUsers";
import AdminRegistrations from "./pages/AdminRegistrations";
import AdminReliability from "./pages/AdminReliability";
import AdminClinicalExplorer from "./pages/AdminClinicalExplorer";
import StaffWorkspace from "./pages/StaffWorkspace";
import Compliance from "./pages/Compliance";
import QualityControl from "./pages/QualityControl";
import FinanceAR from "./pages/FinanceAR";
import Login from "./pages/Login";
import Register from "./pages/Register";
import NotFound from "./pages/NotFound";
import HospitalPatients      from "./pages/HospitalPatients";
import PatientProfile        from "./pages/PatientProfile";
import ClinicalQueue         from "./pages/ClinicalQueue";
import WardsAndBeds          from "./pages/WardsAndBeds";
import Laboratory            from "./pages/Laboratory";
import PharmacyDispensing    from "./pages/PharmacyDispensing";
import Inventory             from "./pages/Inventory";
import HospitalBilling       from "./pages/HospitalBilling";
import HospitalInvoice       from "./pages/HospitalInvoice";
import HospitalAppointments  from "./pages/HospitalAppointments";
import HMOAdmin              from "./pages/HMOAdmin";
import DoctorDashboard       from "./pages/DoctorDashboard";
import FeeSchedule           from "./pages/FeeSchedule";
import AuditLog              from "./pages/AuditLog";
import Radiology             from "./pages/Radiology";
import SurgicalTheatre       from "./pages/SurgicalTheatre";
import MCHObGyn              from "./pages/MCHObGyn";
import Immunisation          from "./pages/Immunisation";
import DepartmentStores       from "./pages/DepartmentStores";
import BabyVaccinationRecord from "./pages/BabyVaccinationRecord";
import DigitalEngagement     from "./pages/DigitalEngagement";
import QualitySafety        from "./pages/QualitySafety";
import AuditsMaintenance    from "./pages/AuditsMaintenance";
import Reports               from "./pages/Reports";
import PaymentGateway        from "./pages/PaymentGateway";
import SpecialistClinics     from "./pages/SpecialistClinics";
import NurseDashboard        from "./pages/NurseDashboard";
import AdminDashboard        from "./pages/AdminDashboard";
import FrontDesk            from "./pages/FrontDesk";
import QueueDisplay         from "./pages/QueueDisplay";

// Roy Books - the hospital's finance hub (backend /fin). Lazy-loaded: finance
// staff use it, most roles never do, so it stays out of the main bundle.
const BooksOverview   = lazy(() => import("./pages/books/BooksOverview"));
const BooksSales      = lazy(() => import("./pages/books/BooksSales"));
const BooksPurchases  = lazy(() => import("./pages/books/BooksPurchases"));
const BooksStock      = lazy(() => import("./pages/books/BooksStock"));
const BooksBanking    = lazy(() => import("./pages/books/BooksBanking"));
const BooksLedger     = lazy(() => import("./pages/books/BooksLedger"));
const BooksStatements = lazy(() => import("./pages/books/BooksStatements"));
const BooksReports    = lazy(() => import("./pages/books/BooksReports"));
const BooksAssets     = lazy(() => import("./pages/books/BooksAssets"));
const BooksClose      = lazy(() => import("./pages/books/BooksClose"));
const BooksSetup      = lazy(() => import("./pages/books/BooksSetup"));
const books = (el: JSX.Element) => <Suspense fallback={<div className="p-8 text-sm text-muted-foreground">Loading Roy Books…</div>}>{el}</Suspense>;

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Every page shows what the hospital looks like now: a page re-opens with fresh data, and coming
      // back to the window refreshes it. (refetchOnMount:false kept the first answer a browser got for
      // up to 30 minutes, so two logins with the same rights could show different figures.)
      staleTime: 30_000,
      gcTime: 600_000,
      refetchOnMount: true,
      refetchOnWindowFocus: true,
      refetchOnReconnect: true,
      refetchIntervalInBackground: false,
      retry: 1,
    },
  },
});

const App = () => (
  <QueryClientProvider client={queryClient}>
    <ThemeProvider attribute="class" defaultTheme="light" disableTransitionOnChange>
      <TooltipProvider>
        <Toaster />
        <AskHost />
        <Sonner />
        <AuthProvider>
          <HashRouter>
            <TourProvider>
            <WalkthroughProvider>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route
                element={
                  <ProtectedRoute>
                    <Layout />
                  </ProtectedRoute>
                }
              >
                <Route path="/" element={<Workstation />} />
                <Route path="/executive" element={<Executive />} />
                {/* the old AI "health summary" drill-down; the Executive overview replaced it */}
                <Route path="/executive/summary" element={<Navigate to="/executive" replace />} />
                {/* reportGUide.md: reports about one record, procurement, patient relations, the calendar over records */}
                <Route path="/reports/new" element={<ReportComposer />} />
                <Route path="/reports/library" element={<ReportLibrary />} />
                <Route path="/procurement" element={<Procurement />} />
                <Route path="/relations" element={<PatientRelations />} />
                <Route path="/calendar" element={<HospitalCalendar />} />
                {/* The old Finance pages each duplicated a Roy Books screen (analytics, reports, vendor
                    payments into a table that never existed here, budgets): one place per fact, so they redirect. */}
                <Route path="/finance/analytics" element={<Navigate to="/finance/books" replace />} />
                <Route path="/finance/reports" element={<Navigate to="/finance/books/reports" replace />} />
                <Route path="/finance/reports/ar/:bucket" element={<ARAgingBucketDetails />} />
                <Route path="/finance/ar" element={<FinanceAR />} />
                <Route path="/finance/vendor-payments" element={<Navigate to="/finance/books/purchases?tab=payments" replace />} />
                <Route path="/finance/budget" element={<Navigate to="/finance/books/setup?tab=budgets" replace />} />
                <Route path="/finance/books"            element={books(<BooksOverview />)} />
                <Route path="/finance/books/sales"      element={books(<BooksSales />)} />
                <Route path="/finance/books/purchases"  element={books(<BooksPurchases />)} />
                <Route path="/finance/books/stock"      element={books(<BooksStock />)} />
                <Route path="/finance/books/banking"    element={books(<BooksBanking />)} />
                <Route path="/finance/books/ledger"     element={books(<BooksLedger />)} />
                <Route path="/finance/books/statements" element={books(<BooksStatements />)} />
                <Route path="/finance/books/reports"    element={books(<BooksReports />)} />
                <Route path="/finance/books/assets"     element={books(<BooksAssets />)} />
                <Route path="/finance/books/close"      element={books(<BooksClose />)} />
                <Route path="/finance/books/setup"      element={books(<BooksSetup />)} />
                <Route path="/hr" element={<HR />} />
                <Route path="/operations/suppliers" element={<Suppliers />} />
                <Route path="/quality-control" element={<QualityControl />} />
                <Route path="/synbot" element={<AskSynbot />} />
                <Route path="/calendar/tasks" element={<CalendarTaskManager />} />
                <Route path="/agents" element={<AgentsDashboard />} />
                <Route path="/agents/:name" element={<AgentDetail />} />
                <Route path="/compliance" element={<Compliance />} />
                <Route path="/workflow" element={<Workflow />} />
                {/* Staff Workspace - every member of staff's home. It replaced the Staff Dashboard,
                    Time Tracker and Collaboration pages; their links open the matching tab. */}
                <Route path="/workspace" element={<StaffWorkspace />} />
                <Route path="/staff/dashboard" element={<Navigate to="/workspace" replace />} />
                <Route path="/staff/collaboration" element={<Navigate to="/workspace?tab=messages" replace />} />
                <Route path="/staff/time-tracker" element={<Navigate to="/workspace?tab=progress" replace />} />
                <Route path="/admin/users" element={<AdminUsers />} />
                <Route path="/admin/registrations" element={<AdminRegistrations />} />
                <Route path="/admin/reliability" element={<AdminReliability />} />
                <Route path="/admin/clinical-explorer" element={<AdminClinicalExplorer />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="/hospital/patients"          element={<HospitalPatients />} />
                <Route path="/hospital/patients/:mrn"    element={<PatientProfile />} />
                <Route path="/hospital/queue"            element={<ClinicalQueue />} />
                <Route path="/hospital/wards"            element={<WardsAndBeds />} />
                <Route path="/hospital/lab"              element={<Laboratory />} />
                <Route path="/hospital/pharmacy"         element={<PharmacyDispensing />} />
                <Route path="/hospital/pharmacy/inventory" element={<Inventory />} />
                <Route path="/hospital/billing"          element={<HospitalBilling />} />
                <Route path="/hospital/appointments"     element={<HospitalAppointments />} />
                <Route path="/hospital/hmo"              element={<HMOAdmin />} />
                <Route path="/hospital/hmo/desk"         element={<Navigate to="/hospital/hmo?tab=desk" replace />} />
                <Route path="/hospital/doctor"           element={<DoctorDashboard />} />
                <Route path="/admin/fee-schedule"        element={<FeeSchedule />} />
                <Route path="/admin/audit-log"           element={<AuditLog />} />
                {/* Merged into the Nursing Station at /hospital/nurse. Kept as a
                    redirect so existing bookmarks and shared links still land. */}
                <Route path="/hospital/nursing"          element={<Navigate to="/hospital/nurse" replace />} />
                <Route path="/hospital/radiology"       element={<Radiology />} />
                <Route path="/hospital/theatre"         element={<SurgicalTheatre />} />
                <Route path="/hospital/mch"             element={<MCHObGyn />} />
                <Route path="/hospital/immunisation"    element={<Immunisation />} />
                <Route path="/hospital/stores"          element={<DepartmentStores />} />
                <Route path="/hospital/immunisation/:patientId" element={<BabyVaccinationRecord />} />
                <Route path="/hospital/engagement"      element={<DigitalEngagement />} />
                <Route path="/hospital/quality"        element={<QualitySafety />} />
                <Route path="/hospital/audits-maintenance" element={<AuditsMaintenance />} />
                {/* Merged into /hr — one HR page, six tabs. */}
                <Route path="/hospital/hr" element={<Navigate to="/hr" replace />} />
                <Route path="/hospital/reports"        element={<Reports />} />
                <Route path="/admin/payments"          element={<PaymentGateway />} />
                <Route path="/hospital/specialist"     element={<SpecialistClinics />} />
                <Route path="/hospital/nurse"          element={<NurseDashboard />} />
                <Route path="/hospital/admin-dashboard" element={<AdminDashboard />} />
                <Route path="/hospital/front-desk"     element={<FrontDesk />} />
              </Route>
              {/* Public display board — no sidebar, full-screen */}
              <Route path="/hospital/display" element={<QueueDisplay />} />
              {/* Printable invoice — dedicated full page, no sidebar chrome, so
                  browser print isn't fighting a scroll-clipped Sheet layout. */}
              <Route path="/hospital/billing/:billId/invoice" element={<ProtectedRoute><HospitalInvoice /></ProtectedRoute>} />
              <Route path="*" element={<NotFound />} />
            </Routes>
            </WalkthroughProvider>
            </TourProvider>
          </HashRouter>
        </AuthProvider>
      </TooltipProvider>
    </ThemeProvider>
  </QueryClientProvider>
);

export default App;
