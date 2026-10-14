/**
 * SOAP draft state.
 *
 * A reducer rather than a dozen useState calls: gating derives from the WHOLE
 * draft (see lib/soap-gate.ts), every section mutates a different branch, and
 * the persistence layer needs one serialisable object to write. Splitting it
 * into separate state slots would mean recomputing the gate from scattered
 * values on every render and would make draft restore fiddly.
 */
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import {
  emptySoapDraft,
  evaluateSoapGate,
  isDraftDirty,
  type DiagnosisEntry,
  type DraftOrder,
  type SoapDraft,
} from "@/lib/soap-gate";

const STORAGE_PREFIX = "synbot_soap_draft_v1";
const SAVE_DEBOUNCE_MS = 500;

export type SoapAction =
  | { type: "setChiefComplaint"; value: string }
  | { type: "setHpc"; value: string }
  | { type: "setRos"; value: string }
  | { type: "setGeneral"; value: string }
  | { type: "setSystem"; system: string; value: string }
  | { type: "removeSystem"; system: string }
  | { type: "addDiagnosis"; diagnosis: DiagnosisEntry }
  | { type: "removeDiagnosis"; icdCode: string }
  | { type: "setPrimaryDiagnosis"; icdCode: string }
  | { type: "setAssessmentText"; value: string }
  | { type: "setPlanText"; value: string }
  | { type: "addOrder"; order: DraftOrder }
  | { type: "removeOrder"; tempId: string }
  | { type: "appendTo"; field: "hpc" | "ros" | "general" | "assessmentText" | "planText"; text: string }
  | { type: "replace"; draft: SoapDraft }
  | { type: "reset" };

export function soapReducer(state: SoapDraft, action: SoapAction): SoapDraft {
  switch (action.type) {
    case "setChiefComplaint":
      return { ...state, subjective: { ...state.subjective, chief_complaint: action.value } };
    case "setHpc":
      return { ...state, subjective: { ...state.subjective, hpc: action.value } };
    case "setRos":
      return { ...state, subjective: { ...state.subjective, ros: action.value } };

    case "setGeneral":
      return { ...state, objective: { ...state.objective, general: action.value } };
    case "setSystem":
      return {
        ...state,
        objective: {
          ...state.objective,
          systems: { ...state.objective.systems, [action.system]: action.value },
        },
      };
    case "removeSystem": {
      const { [action.system]: _drop, ...rest } = state.objective.systems;
      return { ...state, objective: { ...state.objective, systems: rest } };
    }

    case "addDiagnosis": {
      // De-duplicate by code; the first diagnosis added becomes primary.
      if (state.assessment.diagnoses.some((d) => d.icd_code === action.diagnosis.icd_code)) {
        return state;
      }
      const isFirst = state.assessment.diagnoses.length === 0;
      return {
        ...state,
        assessment: {
          ...state.assessment,
          diagnoses: [
            ...state.assessment.diagnoses,
            { ...action.diagnosis, is_primary: action.diagnosis.is_primary ?? isFirst },
          ],
        },
      };
    }
    case "removeDiagnosis": {
      const remaining = state.assessment.diagnoses.filter((d) => d.icd_code !== action.icdCode);
      // Never leave a list with no primary — promote the first survivor.
      if (remaining.length && !remaining.some((d) => d.is_primary)) {
        remaining[0] = { ...remaining[0], is_primary: true };
      }
      return { ...state, assessment: { ...state.assessment, diagnoses: remaining } };
    }
    case "setPrimaryDiagnosis":
      return {
        ...state,
        assessment: {
          ...state.assessment,
          diagnoses: state.assessment.diagnoses.map((d) => ({
            ...d,
            is_primary: d.icd_code === action.icdCode,
          })),
        },
      };
    case "setAssessmentText":
      return { ...state, assessment: { ...state.assessment, text: action.value } };

    case "setPlanText":
      return { ...state, plan: { ...state.plan, text: action.value } };
    case "addOrder":
      return { ...state, plan: { ...state.plan, orders: [...state.plan.orders, action.order] } };
    case "removeOrder":
      return {
        ...state,
        plan: { ...state.plan, orders: state.plan.orders.filter((o) => o.tempId !== action.tempId) },
      };

    case "appendTo": {
      const join = (existing: string) => (existing.trim() ? `${existing.replace(/\s+$/, "")}\n${action.text}` : action.text);
      switch (action.field) {
        case "hpc":
          return { ...state, subjective: { ...state.subjective, hpc: join(state.subjective.hpc) } };
        case "ros":
          return { ...state, subjective: { ...state.subjective, ros: join(state.subjective.ros) } };
        case "general":
          return { ...state, objective: { ...state.objective, general: join(state.objective.general) } };
        case "assessmentText":
          return { ...state, assessment: { ...state.assessment, text: join(state.assessment.text) } };
        case "planText":
          return { ...state, plan: { ...state.plan, text: join(state.plan.text) } };
        default:
          return state;
      }
    }

    case "replace":
      return action.draft;
    case "reset":
      return emptySoapDraft();
    default:
      return state;
  }
}

/** Shape written to localStorage. Versioned so a format change can be ignored. */
interface StoredDraft {
  v: 1;
  savedAt: string;
  draft: SoapDraft;
}

function storageKey(encounterId: string | number) {
  return `${STORAGE_PREFIX}:${encounterId}`;
}

function readStored(encounterId: string | number): StoredDraft | null {
  try {
    const raw = window.localStorage.getItem(storageKey(encounterId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredDraft;
    if (parsed?.v !== 1 || !parsed.draft?.subjective) return null;
    return parsed;
  } catch {
    // Corrupt or unavailable storage must never block note-writing.
    return null;
  }
}

export interface UseSoapDraftResult {
  draft: SoapDraft;
  dispatch: React.Dispatch<SoapAction>;
  gate: ReturnType<typeof evaluateSoapGate>;
  isDirty: boolean;
  /** A recovered draft awaiting an explicit Restore/Discard decision. */
  pendingRestore: { savedAt: string; draft: SoapDraft } | null;
  restorePending: () => void;
  discardPending: () => void;
  /** Clear both in-memory and persisted state (call after a successful sign). */
  clearDraft: () => void;
}

export function useSoapDraft(encounterId: string | number): UseSoapDraftResult {
  const [draft, dispatch] = useReducer(soapReducer, undefined, emptySoapDraft);
  const [pendingRestore, setPendingRestore] = useState<{ savedAt: string; draft: SoapDraft } | null>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cleared = useRef(false);

  const gate = useMemo(() => evaluateSoapGate(draft), [draft]);
  const isDirty = useMemo(() => isDraftDirty(draft), [draft]);

  // Offer any recovered draft — never restore silently. Quietly resurrecting
  // text into a medico-legal document the clinician did not knowingly reopen
  // is not acceptable; they must choose.
  useEffect(() => {
    const stored = readStored(encounterId);
    if (stored && isDraftDirty(stored.draft)) {
      setPendingRestore({ savedAt: stored.savedAt, draft: stored.draft });
    }
  }, [encounterId]);

  // Debounced persistence so an interrupted session keeps its work.
  useEffect(() => {
    if (cleared.current) return;
    if (!isDirty) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      try {
        const payload: StoredDraft = { v: 1, savedAt: new Date().toISOString(), draft };
        window.localStorage.setItem(storageKey(encounterId), JSON.stringify(payload));
      } catch {
        /* quota or private mode — losing autosave is survivable, crashing is not */
      }
    }, SAVE_DEBOUNCE_MS);
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, [draft, isDirty, encounterId]);

  const restorePending = useCallback(() => {
    if (!pendingRestore) return;
    dispatch({ type: "replace", draft: pendingRestore.draft });
    setPendingRestore(null);
  }, [pendingRestore]);

  const discardPending = useCallback(() => {
    setPendingRestore(null);
    try {
      window.localStorage.removeItem(storageKey(encounterId));
    } catch {
      /* ignore */
    }
  }, [encounterId]);

  const clearDraft = useCallback(() => {
    cleared.current = true;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    dispatch({ type: "reset" });
    setPendingRestore(null);
    try {
      window.localStorage.removeItem(storageKey(encounterId));
    } catch {
      /* ignore */
    }
    // Allow autosave again for a subsequent note on the same encounter.
    setTimeout(() => {
      cleared.current = false;
    }, SAVE_DEBOUNCE_MS + 50);
  }, [encounterId]);

  return { draft, dispatch, gate, isDirty, pendingRestore, restorePending, discardPending, clearDraft };
}
