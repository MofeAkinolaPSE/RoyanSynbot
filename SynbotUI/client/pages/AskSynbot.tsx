import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Send, Plus, Trash2, AlertCircle, ExternalLink, Stethoscope, BarChart3, User, X, ArrowUpRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { apiUrl } from "@/lib/api-base";
import { authClient } from "@/lib/auth-client";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { isReportContent, ReportRenderer, ChatText } from "@/components/chat/ChatReport";

type ChatMode = "executive" | "clinical";

const CLINICAL_SUGGESTIONS = [
  "Summarize the last 3 encounters for patient RHN-000001",
  "Which patients are overdue for follow-up this week?",
  "List all pending lab orders marked STAT",
  "Which HMO has the most outstanding claims?",
  "Show me drug interaction risks for Metformin + Warfarin",
  "Summarize today's discharge summary for the wards",
];

const EXECUTIVE_SUGGESTIONS = [
  "What are the key revenue trends this month?",
  "Show me the top 5 operational bottlenecks",
  "Which departments have the highest patient complaints?",
  "Summarize AR aging for the past 30 days",
];

const AskSynbot = () => {
  const [mode, setMode] = useState<ChatMode>("clinical");
  const [patientContext, setPatientContext] = useState("");
  const [patientContextActive, setPatientContextActive] = useState(false);

  const navigate = useNavigate();
  const [conversations, setConversations] = useState([
    {
      id: 1,
      title: "New Conversation",
      timestamp: new Date().toLocaleString(),
      active: true,
    },
  ]);

  const [activeConvId, setActiveConvId] = useState(1);
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<any[]>([]);
  const [isSending, setIsSending] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const buildPayload = (question: string) => {
    const base: Record<string, any> = { question, mode };
    if (mode === "clinical" && patientContextActive && patientContext.trim()) {
      base.patient_context = patientContext.trim();
    }
    return base;
  };

  const handleSendMessage = async (overrideMessage?: string) => {
    const trimmed = (overrideMessage ?? message).trim();
    if (!trimmed || isSending) return;

    const userMsg = {
      id: messages.length + 1,
      type: "user" as const,
      content: trimmed,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };
    setMessages((prev) => [...prev, userMsg]);
    setMessage("");
    setIsSending(true);

    try {
      let token = authClient.getAccessToken();
      if (!token) {
        const refreshed = await authClient.refresh();
        if (refreshed) token = authClient.getAccessToken();
      }

      const doFetch = (t: string | null) =>
        fetch(apiUrl("/chat"), {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(t ? { Authorization: `Bearer ${t}` } : {}),
          },
          body: JSON.stringify(buildPayload(trimmed)),
        });

      let res = await doFetch(token);

      if (res.status === 401) {
        const refreshed = await authClient.refresh();
        if (refreshed) {
          token = authClient.getAccessToken();
          res = await doFetch(token);
        }
      }

      if (!res.ok) {
        let detail = `Chat request failed (${res.status})`;
        try {
          const err = await res.json();
          detail = err?.detail || err?.error || detail;
        } catch {
          const txt = await res.text();
          if (txt) detail = txt;
        }
        throw new Error(detail);
      }

      const data = await res.json();
      if (!data || typeof data.answer !== "string" || !data.answer.trim()) {
        throw new Error("Chat response did not include a valid answer.");
      }
      const sources = (data.sources || []).map((s: any) => ({
        label: s.question || "Q&A snippet",
        url: "#",
      }));
      const links = (data.links || []).map((l: any) => ({ label: l.label, url: l.url }));

      const botMsg = {
        id: userMsg.id + 1,
        type: "bot" as const,
        content: data.answer,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        sources,
        links,
      };
      setMessages((prev) => [...prev, botMsg]);

      // Auto-title on first bot response
      if (messages.length === 0) {
        setConversations((prev) =>
          prev.map((c) =>
            c.id === activeConvId
              ? { ...c, title: trimmed.slice(0, 40) + (trimmed.length > 40 ? "…" : "") }
              : c,
          ),
        );
      }
    } catch (e: any) {
      const errorMsg = {
        id: messages.length + 2,
        type: "bot" as const,
        content: `Error: ${e?.message || "Chat request failed"}`,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsSending(false);
    }
  };

  const deleteConversation = (id: number) => {
    setConversations(conversations.filter((c) => c.id !== id));
    if (activeConvId === id && conversations.length > 0) {
      setActiveConvId(conversations[0].id);
    }
  };

  const activeConversation = conversations.find((c) => c.id === activeConvId);
  const suggestions = mode === "clinical" ? CLINICAL_SUGGESTIONS : EXECUTIVE_SUGGESTIONS;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={motionTransitions.standard}
      className="pw-page-surface flex min-h-[calc(100vh-8rem)]"
    >
      {/* Sidebar - Conversations */}
      <div className="z-10 flex w-64 flex-col border-r border-border/70 bg-card/80 backdrop-blur-md">
        <div className="p-4 border-b border-border space-y-3">
          {/* Mode toggle */}
          <div className="flex rounded-lg border border-border overflow-hidden">
            <button
              onClick={() => setMode("clinical")}
              className={cn(
                "flex flex-1 items-center justify-center gap-1.5 py-1.5 text-xs font-medium transition-colors",
                mode === "clinical" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted",
              )}
            >
              <Stethoscope className="h-3.5 w-3.5" /> Clinical
            </button>
            <button
              onClick={() => setMode("executive")}
              className={cn(
                "flex flex-1 items-center justify-center gap-1.5 py-1.5 text-xs font-medium transition-colors",
                mode === "executive" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted",
              )}
            >
              <BarChart3 className="h-3.5 w-3.5" /> Executive
            </button>
          </div>

          {/* Patient context (clinical only) */}
          {mode === "clinical" && (
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Patient MRN (optional)</label>
              <div className="flex gap-1">
                <Input
                  value={patientContext}
                  onChange={(e) => setPatientContext(e.target.value)}
                  placeholder="e.g. RHN-000001"
                  className="h-7 text-xs"
                />
                <Button
                  size="sm"
                  variant={patientContextActive ? "default" : "outline"}
                  className="h-7 px-2 text-xs shrink-0"
                  onClick={() => setPatientContextActive((v) => !v)}
                  disabled={!patientContext.trim()}
                >
                  <User className="h-3 w-3" />
                </Button>
              </div>
              {patientContextActive && patientContext.trim() && (
                <div className="flex items-center gap-1 rounded-md bg-primary/10 px-2 py-1">
                  <User className="h-3 w-3 text-primary" />
                  <span className="text-xs text-primary flex-1">{patientContext}</span>
                  <button
                    onClick={() => { setPatientContextActive(false); setPatientContext(""); }}
                    className="text-primary/60 hover:text-primary"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              )}
            </div>
          )}

          <Button
            className="w-full"
            size="sm"
            onClick={() => {
              const nextId = conversations.length + 1;
              const newConv = {
                id: nextId,
                title: "New Conversation",
                timestamp: new Date().toLocaleString(),
                active: true,
              };
              setConversations((prev) =>
                prev.map((c) => ({ ...c, active: false })).concat(newConv)
              );
              setActiveConvId(nextId);
              setMessages([]);
            }}
          >
            <Plus className="w-4 h-4 mr-2" />
            New Conversation
          </Button>
        </div>

        <ScrollArea className="flex-1">
          <div className="p-2 space-y-2">
            {conversations.map((conv) => (
              <div
                key={conv.id}
                onClick={() => setActiveConvId(conv.id)}
                className={`p-3 rounded-lg cursor-pointer transition-colors group ${
                  activeConvId === conv.id ? "bg-primary text-primary-foreground" : "hover:bg-muted"
                }`}
              >
                <p className="text-sm font-medium truncate">{conv.title}</p>
                <p className={`text-xs mt-1 ${activeConvId === conv.id ? "text-primary-foreground/70" : "text-muted-foreground"}`}>
                  {conv.timestamp}
                </p>
                <button
                  onClick={(e) => { e.stopPropagation(); deleteConversation(conv.id); }}
                  className="opacity-0 group-hover:opacity-100 transition-opacity mt-2 p-1 rounded hover:bg-black/10"
                  title="Delete conversation"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        </ScrollArea>

        <div className="border-t border-border/70 p-4 text-xs text-muted-foreground">
          <p>RoyanHealth v1.0</p>
          <p>Powered by Royan Hospital AI</p>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="z-10 flex flex-1 flex-col">
        {/* Header */}
        <div className="border-b border-border/70 bg-card/80 p-4 backdrop-blur-md flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-foreground flex items-center gap-2">
              {mode === "clinical" ? <Stethoscope className="h-5 w-5 text-primary" /> : <BarChart3 className="h-5 w-5 text-primary" />}
              {mode === "clinical" ? "Clinical Assistant" : "Executive Intelligence"}
              <Badge variant="outline" className="text-xs ml-1">
                {mode === "clinical" ? "Roy — Clinical" : "Roy — Executive"}
              </Badge>
            </h1>
            <p className="text-muted-foreground text-xs mt-0.5">
              {mode === "clinical"
                ? "Patient summaries, clinical decisions, lab analysis, and drug interaction checks"
                : "Business intelligence, revenue analytics, and operational insights"}
            </p>
          </div>
        </div>

        {/* Messages */}
        <ScrollArea className="flex-1 p-6" ref={scrollRef as any}>
          <div className="space-y-6 max-w-4xl">
            {messages.length === 0 && (
              <div className="py-8">
                <p className="text-center text-sm text-muted-foreground mb-4">
                  {mode === "clinical" ? "Ask about patients, labs, prescriptions, or drug interactions" : "Ask about revenue, operations, or performance metrics"}
                </p>
                <div className="flex flex-wrap gap-2 justify-center">
                  {suggestions.map((s) => (
                    <button
                      key={s}
                      onClick={() => handleSendMessage(s)}
                      className="rounded-full border border-border px-3 py-1.5 text-xs hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex gap-4 ${msg.type === "user" ? "justify-end" : "justify-start"}`}
              >
                {msg.type === "bot" && (
                  <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-primary-foreground font-semibold text-sm flex-shrink-0">
                    {mode === "clinical" ? <Stethoscope className="h-4 w-4" /> : "S"}
                  </div>
                )}

                <div className={`max-w-2xl ${msg.type === "user" ? "text-right" : "text-left"}`}>
                  <div
                    className={cn(
                      "inline-block rounded-lg p-4",
                      msg.type === "user" ? "bg-primary text-primary-foreground" : "bg-muted",
                      msg.type === "bot" && isReportContent(msg.content) ? "max-w-full w-full" : "",
                    )}
                  >
                    {msg.type === "bot" && isReportContent(msg.content) ? (
                      <ReportRenderer content={msg.content} />
                    ) : (
                      <ChatText content={msg.content} />
                    )}
                  </div>

                  {msg.type === "bot" && msg.links && msg.links.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {msg.links.map((link: any, idx: number) => (
                        <Button
                          key={idx}
                          size="sm"
                          variant="outline"
                          className="gap-1.5 h-7 text-xs"
                          onClick={() => navigate(link.url)}
                        >
                          {link.label} <ArrowUpRight className="w-3 h-3" />
                        </Button>
                      ))}
                    </div>
                  )}

                  {msg.type === "bot" && msg.sources && msg.sources.length > 0 && (
                    <div className="mt-3 space-y-1">
                      <p className="text-xs font-semibold text-muted-foreground uppercase">Sources</p>
                      {msg.sources.map((source: any, idx: number) => (
                        <a key={idx} href={source.url} className="flex items-center gap-1 text-xs text-primary hover:underline">
                          <ExternalLink className="w-3 h-3" />
                          {source.label}
                        </a>
                      ))}
                    </div>
                  )}

                  <p className="text-xs text-muted-foreground mt-2">{msg.timestamp}</p>
                </div>

                {msg.type === "user" && (
                  <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center text-secondary-foreground font-semibold text-sm flex-shrink-0">
                    A
                  </div>
                )}
              </div>
            ))}
          </div>
        </ScrollArea>

        {/* Disclaimer */}
        <div className="mx-6 mb-4 rounded-xl border border-warning/30 bg-warning/15 p-3">
          <div className="flex gap-3">
            <AlertCircle className="w-4 h-4 text-warning flex-shrink-0 mt-0.5" />
            <p className="text-xs text-warning">
              {mode === "clinical" ? (
                <><strong>Clinical Notice:</strong> RoyanHealth AI is a decision-support tool only. All clinical decisions must be validated by a licensed healthcare professional. Patient data is handled under NDPA 2023.</>
              ) : (
                <><strong>Notice:</strong> Roy analysis is for business intelligence only. For regulated decisions, consult subject matter experts and your compliance team.</>
              )}
            </p>
          </div>
        </div>

        {/* Input */}
        <div className="p-6 border-t border-border">
          <div className="flex gap-2 max-w-4xl">
            <Input
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void handleSendMessage();
                }
              }}
              placeholder={
                mode === "clinical"
                  ? "Ask about a patient, lab result, prescription, or clinical workflow…"
                  : "Ask Roy a question about hospital operations or business analytics…"
              }
              className="flex-1"
            />
            <Button onClick={() => void handleSendMessage()} size="icon" disabled={isSending}>
              {isSending ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" /> : <Send className="w-4 h-4" />}
            </Button>
          </div>
        </div>
      </div>
    </motion.div>
  );
};

export default AskSynbot;
