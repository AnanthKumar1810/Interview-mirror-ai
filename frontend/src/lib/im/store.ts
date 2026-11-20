import { useSyncExternalStore } from "react";
import { SEEDED_SESSIONS } from "./data";
import type { LiveInterview, Profile, Session, SetupDraft } from "./types";

export interface AppState {
  hydrated: boolean;
  sessions: Session[];
  profile: Profile;
  setup: SetupDraft;
  live: LiveInterview | null;
}

const STORAGE_KEY = "interviewmirror:v1";

export const DEFAULT_SETUP: SetupDraft = {
  domainId: "software_eng",
  languageCode: "en-IN",
  difficulty: "Intermediate",
  questionTarget: 3,
  targetRole: "Backend Engineer",
  github: "",
  highlights: "",
  useGemini: false,
  compareNoiseEnhancement: false,
  voiceTransport: "websocket",
};

const initialState: AppState = {
  hydrated: false,
  sessions: [],
  profile: {
    name: "Candidate",
    targetRole: "Backend Engineer",
    language: "en-IN",
    speakQuestions: true,
  },
  setup: DEFAULT_SETUP,
  live: null,
};

let state: AppState = initialState;
const listeners = new Set<() => void>();

function persist() {
  if (typeof window === "undefined") return;
  try {
    const { hydrated: _h, ...rest } = state;
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        ...rest,
        setup: { ...rest.setup, highlights: "" },
      }),
    );
  } catch {
    /* storage full or blocked — keep in memory */
  }
}

export function setState(update: Partial<AppState> | ((s: AppState) => Partial<AppState>)) {
  const patch = typeof update === "function" ? update(state) : update;
  state = { ...state, ...patch };
  persist();
  listeners.forEach((l) => l());
}

export function getState() {
  return state;
}

/** Load saved data from the browser once, after the first render. */
export function hydrateStore() {
  if (state.hydrated || typeof window === "undefined") return;
  let saved: Partial<AppState> = {};
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) saved = JSON.parse(raw);
  } catch {
    saved = {};
  }
  state = {
    ...state,
    ...saved,
    // A WebSocket and microphone cannot survive a page reload.
    live: null,
    profile: { ...state.profile, ...saved.profile },
    setup: { ...state.setup, ...saved.setup, highlights: "" },
    hydrated: true,
  };
  listeners.forEach((l) => l());
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useAppStore<T>(selector: (s: AppState) => T): T {
  return useSyncExternalStore(
    subscribe,
    () => selector(state),
    () => selector(initialState),
  );
}

/* ---------- actions ---------- */

export const actions = {
  updateSetup(patch: Partial<SetupDraft>) {
    setState((s) => ({ setup: { ...s.setup, ...patch } }));
  },
  updateProfile(patch: Partial<Profile>) {
    setState((s) => ({ profile: { ...s.profile, ...patch } }));
  },
  saveSession(session: Session) {
    setState((s) => ({ sessions: [session, ...s.sessions.filter((x) => x.id !== session.id)] }));
  },
  replaceSession(session: Session) {
    setState((s) => ({ sessions: s.sessions.map((x) => (x.id === session.id ? session : x)) }));
  },
  deleteSession(id: string) {
    setState((s) => ({ sessions: s.sessions.filter((x) => x.id !== id) }));
  },
  importSessions(list: Session[]) {
    setState((s) => {
      const ids = new Set(list.map((x) => x.id));
      return { sessions: [...list, ...s.sessions.filter((x) => !ids.has(x.id))] };
    });
  },
  restoreSamples() {
    setState((s) => {
      const ids = new Set(SEEDED_SESSIONS.map((x) => x.id));
      return { sessions: [...s.sessions.filter((x) => !ids.has(x.id)), ...SEEDED_SESSIONS] };
    });
  },
  clearSessions() {
    setState({ sessions: [] });
  },
  setLive(live: LiveInterview | null) {
    setState({ live });
  },
};
