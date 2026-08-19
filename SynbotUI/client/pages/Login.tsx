import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/components/AuthProvider";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { motion } from "framer-motion";
import { Activity, Users, ShieldCheck, Loader2, Eye, EyeOff } from "lucide-react";

// ── Feature chips — icon + one word, no description copy ──────────────────────
const FEATURES = [
  { icon: Activity,     label: "Real-Time Ops" },
  { icon: Users,        label: "Workforce" },
  { icon: ShieldCheck,  label: "Audit-Ready" },
] as const;

const Login = () => {
  const { login, isLoading } = useAuth();
  const [email, setEmail]     = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw]   = useState(false);
  const [error, setError]     = useState("");
  const navigate = useNavigate();

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      await login(email, password);
      navigate("/", { replace: true });
    } catch {
      setError("Invalid email or password. Please try again.");
    }
  };

  return (
    <div className="relative flex min-h-screen overflow-hidden" style={{ background: "#0A1F45" }}>
      {/* ── Background photo — Royan Hospital's own reception, faded into the
          Royal Azure palette. Blurred + darkened rather than shown sharp: it's
          a small source photo, and this is what gives the page real depth
          instead of a flat gradient. ── */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
        <div
          className="absolute inset-0 scale-110"
          style={{
            backgroundImage: "url(/brand/royan-reception.jpg)",
            backgroundSize: "cover",
            backgroundPosition: "center 30%",
            filter: "blur(3px) saturate(0.55) brightness(0.5) contrast(1.05)",
          }}
        />
      </div>

      {/* ── Colour grade + depth layers — Royal Azure ────────────────────────── */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
        {/* Base tone-map: pulls the photo into the brand's blue */}
        <div className="absolute inset-0" style={{ background: "rgba(10,31,69,0.62)" }} />
        {/* Rich blue glow, off-centre for depth rather than a flat wash */}
        <div
          className="absolute inset-0"
          style={{
            background: "radial-gradient(ellipse 100% 80% at 78% 30%, rgba(37,105,190,0.38) 0%, rgba(10,31,69,0.05) 55%, transparent 100%)",
          }}
        />
        {/* Gold glow, lower-right — the second tone that gives the gradient real range */}
        <div
          className="absolute inset-0"
          style={{
            background: "radial-gradient(ellipse 80% 70% at 85% 95%, rgba(201,162,75,0.28) 0%, transparent 60%)",
          }}
        />
        {/* Left vignette — keeps hero text area dark and readable over the photo */}
        <div
          className="absolute inset-0"
          style={{
            background: "linear-gradient(to right, #0A1F45 0%, rgba(10,31,69,0.94) 20%, rgba(10,31,69,0.75) 42%, rgba(10,31,69,0.35) 65%, rgba(10,31,69,0.12) 100%)",
          }}
        />
        {/* Top + bottom vignette */}
        <div
          className="absolute inset-0"
          style={{
            background: "linear-gradient(to bottom, #0A1F45 0%, rgba(10,31,69,0.55) 14%, transparent 38%, transparent 62%, rgba(10,31,69,0.5) 85%, #0A1F45 100%)",
          }}
        />
        {/* Fine grain, for texture over the large flat gradient areas */}
        <div
          className="absolute inset-0 opacity-[0.4]"
          style={{
            backgroundImage: "radial-gradient(circle at 50% 50%, rgba(255,255,255,0.025) 1px, transparent 1px)",
            backgroundSize: "28px 28px",
          }}
        />
      </div>

      {/* Ambient glow orbs */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
        <div className="absolute -left-48 top-1/4 h-[500px] w-[500px] rounded-full bg-cyan-500/10 blur-[140px]" />
        <div className="absolute -right-40 bottom-0 h-[560px] w-[560px] rounded-full bg-[#C9A24B]/[0.14] blur-[150px]" />
      </div>

      {/* ── LEFT HERO PANEL ──────────────────────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, x: -28 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.75, ease: [0.22, 1, 0.36, 1] }}
        className="relative hidden flex-col justify-center gap-8 p-12 lg:flex lg:w-[58%]"
      >
        <div className="flex max-w-[420px] flex-col gap-5">
          {/* Logo — gold + blue dual-tone ring */}
          <div
            className="relative mb-2 inline-flex w-fit overflow-hidden rounded-2xl px-5 py-3"
            style={{
              background: "linear-gradient(135deg, rgba(19,167,224,0.08) 0%, rgba(201,162,75,0.07) 100%)",
              border: "1px solid rgba(201,162,75,0.28)",
              boxShadow: "0 0 32px rgba(19,167,224,0.10), 0 0 50px rgba(201,162,75,0.10), inset 0 1px 0 rgba(255,255,255,0.08)",
            }}
          >
            <div
              className="pointer-events-none absolute inset-0"
              aria-hidden
              style={{ background: "radial-gradient(ellipse 80% 50% at 50% 0%, rgba(255,255,255,0.09) 0%, transparent 70%)" }}
            />
            <img
              src="/royan-logo.png"
              alt="Royan Hospital"
              className="relative h-12 w-auto object-contain"
              style={{ filter: "drop-shadow(0 2px 12px rgba(19,167,224,0.35)) drop-shadow(0 0 4px rgba(255,255,255,0.12))" }}
            />
          </div>

          <motion.p
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.25 }}
            className="text-[13px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "#E4C583" }}
          >
            Welcome to Royan Hospital
          </motion.p>

          <motion.h1
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.3 }}
            className="text-[2.5rem] font-extrabold leading-[1.1] tracking-tight text-white lg:text-[2.9rem]"
          >
            LESS SEARCHING.<br />
            <span className="bg-gradient-to-r from-cyan-300 to-blue-400 bg-clip-text text-transparent">
              MORE CARING.
            </span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.35 }}
            className="text-sm font-semibold"
            style={{ color: "#C9A24B" }}
          >
            Everything Royan runs on, in one place.
          </motion.p>

          {/* Feature chips — icon + single word, no description copy */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.5 }}
            className="flex flex-wrap gap-2 pt-1"
          >
            {FEATURES.map((f) => {
              const Icon = f.icon;
              return (
                <span
                  key={f.label}
                  className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium text-white/70"
                  style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.10)" }}
                >
                  <Icon className="h-3.5 w-3.5" style={{ color: "#5FD4FA" }} />
                  {f.label}
                </span>
              );
            })}
          </motion.div>
        </div>

        {/* Bottom credit */}
        <p className="text-[13px] text-white/25">© 2026 Royan Hospital · All rights reserved</p>
      </motion.div>

      {/* ── RIGHT LOGIN PANEL ────────────────────────────────────────────────── */}
      <div className="relative flex flex-1 items-center justify-center p-6 lg:p-14">
        {/* Vertical divider (desktop) */}
        <div
          className="absolute left-0 top-[8%] hidden h-[84%] w-px lg:block"
          style={{ background: "linear-gradient(to bottom, transparent, rgba(201,162,75,0.16) 30%, rgba(201,162,75,0.16) 70%, transparent)" }}
          aria-hidden
        />

        <motion.div
          initial={{ opacity: 0, y: 22 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.65, delay: 0.18, ease: [0.22, 1, 0.36, 1] }}
          className="w-full max-w-[360px]"
        >
          {/* Mobile-only logo */}
          <div className="mb-8 flex justify-center lg:hidden">
            <div
              className="relative inline-flex overflow-hidden rounded-xl px-4 py-2.5"
              style={{
                background: "linear-gradient(135deg, rgba(19,167,224,0.08) 0%, rgba(201,162,75,0.07) 100%)",
                border: "1px solid rgba(201,162,75,0.28)",
                boxShadow: "0 0 24px rgba(19,167,224,0.10), 0 0 36px rgba(201,162,75,0.10), inset 0 1px 0 rgba(255,255,255,0.07)",
              }}
            >
              <div
                className="pointer-events-none absolute inset-0"
                aria-hidden
                style={{ background: "radial-gradient(ellipse 80% 50% at 50% 0%, rgba(255,255,255,0.08) 0%, transparent 70%)" }}
              />
              <img
                src="/royan-logo.png"
                alt="Royan Hospital"
                className="relative mx-auto h-11 w-auto object-contain"
                style={{ filter: "drop-shadow(0 2px 10px rgba(19,167,224,0.3)) drop-shadow(0 0 3px rgba(255,255,255,0.1))" }}
              />
            </div>
          </div>

          {/* Glassmorphism card — thin gold top rule */}
          <div
            className="relative overflow-hidden rounded-2xl border border-white/10 p-8 shadow-2xl"
            style={{
              background: "rgba(255,255,255,0.042)",
              backdropFilter: "blur(28px)",
              WebkitBackdropFilter: "blur(28px)",
            }}
          >
            <div className="absolute inset-x-0 top-0 h-[2px]" style={{ background: "linear-gradient(90deg, #C9A24B, #13A7E0)" }} />

            {/* Nav accent strip */}
            <div
              className="mb-7 flex items-center gap-2 rounded-xl px-4 py-2.5"
              style={{ background: "linear-gradient(90deg, rgba(201,162,75,0.16) 0%, rgba(25,87,163,0.14) 100%)", border: "1px solid rgba(201,162,75,0.22)" }}
            >
              <div className="h-2 w-2 rounded-full" style={{ background: "#C9A24B", boxShadow: "0 0 6px rgba(201,162,75,0.8)" }} />
              <span className="text-[13px] font-semibold uppercase tracking-widest" style={{ color: "#E4C583" }}>
                Secure Access Portal
              </span>
            </div>

            <div className="mb-6 space-y-1">
              <h2 className="text-[1.35rem] font-bold text-white">Staff Sign-In</h2>
              <p className="text-xs text-white/40">Securely access your Royan Hospital dashboard</p>
            </div>

            <form className="space-y-4" onSubmit={onSubmit}>
              <div className="space-y-1.5">
                <label className="text-[13px] font-semibold uppercase tracking-wide text-white/50">
                  Email
                </label>
                <Input
                  type="email"
                  placeholder="you@royanhospital.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="border-white/10 bg-white/5 text-white placeholder:text-white/20 focus-visible:border-cyan-400/50 focus-visible:ring-1 focus-visible:ring-cyan-400/30"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-[13px] font-semibold uppercase tracking-wide text-white/50">
                  Password
                </label>
                <div className="relative">
                  <Input
                    type={showPw ? "text" : "password"}
                    placeholder="Password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    className="border-white/10 bg-white/5 pr-10 text-white placeholder:text-white/20 focus-visible:border-cyan-400/50 focus-visible:ring-1 focus-visible:ring-cyan-400/30"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPw((p) => !p)}
                    tabIndex={-1}
                    aria-label={showPw ? "Hide password" : "Show password"}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-white/25 transition-colors hover:text-white/60"
                  >
                    {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              {error && (
                <motion.p
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-xs text-red-400"
                >
                  {error}
                </motion.p>
              )}

              <Button
                type="submit"
                disabled={isLoading}
                className="mt-1 w-full border-0 font-semibold text-white"
                style={{
                  background: "linear-gradient(90deg, #13A7E0 0%, #1957A3 100%)",
                  boxShadow: "0 0 0 1px rgba(201,162,75,0.35), 0 8px 24px rgba(19,167,224,0.18)",
                }}
              >
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Signing in…
                  </>
                ) : (
                  "Sign In"
                )}
              </Button>
            </form>

            <p className="mt-6 text-center text-[12px] leading-relaxed text-white/20">
              Authorized personnel only · This system is monitored and all access is logged
            </p>

            <p className="mt-4 text-center text-xs text-white/40">
              New staff member? <Link to="/register" className="hover:underline" style={{ color: "#E4C583" }}>Register here</Link>
            </p>
          </div>

          <p className="mt-5 text-center text-[13px] text-white/20">
            Royan Hospital © 2026
          </p>
        </motion.div>
      </div>
    </div>
  );
};

export default Login;
