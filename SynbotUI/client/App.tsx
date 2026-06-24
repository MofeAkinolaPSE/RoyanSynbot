import "./global.css";

import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HashRouter, Routes, Route } from "react-router-dom";
import ThemeProvider from "./components/theme-provider";
import AuthProvider from "./components/AuthProvider";
import SessionPrewarm from "./components/SessionPrewarm";
import ProtectedRoute from "./components/ProtectedRoute";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Executive from "./pages/Executive";
import ExecutiveSummaryDetails from "./pages/ExecutiveSummaryDetails";
import FinanceAnalytics from "./pages/FinanceAnalytics";
import FinanceReports from "./pages/FinanceReports";
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
import StaffDashboard from "./pages/StaffDashboard";
import StaffCollaboration from "./pages/StaffCollaboration";
import StaffTimeTracker from "./pages/StaffTimeTracker";
import Compliance from "./pages/Compliance";
import QualityControl from "./pages/QualityControl";
import FinanceAR from "./pages/FinanceAR";
import FinanceVendorPayments from "./pages/FinanceVendorPayments";
import FinanceBudget from "./pages/FinanceBudget";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import HospitalPatients      from "./pages/HospitalPatients";
import PatientProfile        from "./pages/PatientProfile";
import ClinicalQueue         from "./pages/ClinicalQueue";
import WardsAndBeds          from "./pages/WardsAndBeds";
import Laboratory            from "./pages/Laboratory";
import PharmacyDispensing    from "./pages/PharmacyDispensing";
import HospitalBilling       from "./pages/HospitalBilling";
import HospitalAppointments  from "./pages/HospitalAppointments";
import HMOAdmin              from "./pages/HMOAdmin";
import DoctorDashboard       from "./pages/DoctorDashboard";
import FeeSchedule           from "./pages/FeeSchedule";
import AuditLog              from "./pages/AuditLog";
import NursingStation        from "./pages/NursingStation";
import Radiology             from "./pages/Radiology";
import SurgicalTheatre       from "./pages/SurgicalTheatre";
import MCHObGyn              from "./pages/MCHObGyn";
import DigitalEngagement     from "./pages/DigitalEngagement";
import QualitySafety        from "./pages/QualitySafety";
import HRShifts             from "./pages/HRShifts";
import Reports               from "./pages/Reports";
import PaymentGateway        from "./pages/PaymentGateway";
import SpecialistClinics     from "./pages/SpecialistClinics";
import NurseDashboard        from "./pages/NurseDashboard";
import AdminDashboard        from "./pages/AdminDashboard";
import FrontDesk            from "./pages/FrontDesk";
import QueueDisplay         from "./pages/QueueDisplay";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 180_000,
      gcTime: 1_800_000,
      refetchOnMount: false,
      refetchOnWindowFocus: false,
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
        <Sonner />
        <AuthProvider>
          <SessionPrewarm />
          <HashRouter>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route
                element={
                  <ProtectedRoute>
                    <Layout />
                  </ProtectedRoute>
                }
              >
                <Route path="/" element={<Dashboard />} />
                <Route path="/executive" element={<Executive />} />
                <Route path="/executive/summary" element={<ExecutiveSummaryDetails />} />
                <Route path="/finance/analytics" element={<FinanceAnalytics />} />
                <Route path="/finance/reports" element={<FinanceReports />} />
                <Route path="/finance/reports/ar/:bucket" element={<ARAgingBucketDetails />} />
                <Route path="/finance/ar" element={<FinanceAR />} />
                <Route path="/finance/vendor-payments" element={<FinanceVendorPayments />} />
                <Route path="/finance/budget" element={<FinanceBudget />} />
                <Route path="/hr" element={<HR />} />
                <Route path="/operations/suppliers" element={<Suppliers />} />
                <Route path="/quality-control" element={<QualityControl />} />
                <Route path="/synbot" element={<AskSynbot />} />
                <Route path="/calendar/tasks" element={<CalendarTaskManager />} />
                <Route path="/agents" element={<AgentsDashboard />} />
                <Route path="/agents/:name" element={<AgentDetail />} />
                <Route path="/compliance" element={<Compliance />} />
                <Route path="/workflow" element={<Workflow />} />
                <Route path="/staff/dashboard" element={<StaffDashboard />} />
                <Route path="/staff/collaboration" element={<StaffCollaboration />} />
                <Route path="/staff/time-tracker" element={<StaffTimeTracker />} />
                <Route path="/admin/users" element={<AdminUsers />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="/hospital/patients"          element={<HospitalPatients />} />
                <Route path="/hospital/patients/:mrn"    element={<PatientProfile />} />
                <Route path="/hospital/queue"            element={<ClinicalQueue />} />
                <Route path="/hospital/wards"            element={<WardsAndBeds />} />
                <Route path="/hospital/lab"              element={<Laboratory />} />
                <Route path="/hospital/pharmacy"         element={<PharmacyDispensing />} />
                <Route path="/hospital/billing"          element={<HospitalBilling />} />
                <Route path="/hospital/appointments"     element={<HospitalAppointments />} />
                <Route path="/hospital/hmo"              element={<HMOAdmin />} />
                <Route path="/hospital/doctor"           element={<DoctorDashboard />} />
                <Route path="/admin/fee-schedule"        element={<FeeSchedule />} />
                <Route path="/admin/audit-log"           element={<AuditLog />} />
                <Route path="/hospital/nursing"          element={<NursingStation />} />
                <Route path="/hospital/radiology"       element={<Radiology />} />
                <Route path="/hospital/theatre"         element={<SurgicalTheatre />} />
                <Route path="/hospital/mch"             element={<MCHObGyn />} />
                <Route path="/hospital/engagement"      element={<DigitalEngagement />} />
                <Route path="/hospital/quality"        element={<QualitySafety />} />
                <Route path="/hospital/hr"             element={<HRShifts />} />
                <Route path="/hospital/reports"        element={<Reports />} />
                <Route path="/admin/payments"          element={<PaymentGateway />} />
                <Route path="/hospital/specialist"     element={<SpecialistClinics />} />
                <Route path="/hospital/nurse"          element={<NurseDashboard />} />
                <Route path="/hospital/admin-dashboard" element={<AdminDashboard />} />
                <Route path="/hospital/front-desk"     element={<FrontDesk />} />
              </Route>
              {/* Public display board — no sidebar, full-screen */}
              <Route path="/hospital/display" element={<QueueDisplay />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </HashRouter>
        </AuthProvider>
      </TooltipProvider>
    </ThemeProvider>
  </QueryClientProvider>
);

export default App;
