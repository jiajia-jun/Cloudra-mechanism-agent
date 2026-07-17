import { fetchEventSource } from "@microsoft/fetch-event-source";
import type { Approval, ConfigDisplay, Conversation, LogFile, Message, Session, SessionEvent, SessionRow, SkillInfo } from "./types";

const TOKEN_KEY = "cloudra_api_token";
const DESKTOP_API_ORIGIN = "http://127.0.0.1:18473";
const isDesktop = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

function endpoint(path: string) {
  return `${isDesktop ? DESKTOP_API_ORIGIN : ""}${path}`;
}

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY) ?? "",
  set: (value: string) => value ? localStorage.setItem(TOKEN_KEY, value) : localStorage.removeItem(TOKEN_KEY)
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = tokenStore.get();
  const response = await fetch(endpoint(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers
    }
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `请求失败 (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; version: string }>("/api/health"),
  conversations: () => request<Conversation[]>("/api/conversations"),
  createConversation: () => request<Conversation>("/api/conversations", { method: "POST" }),
  deleteAllConversations: () => request<{ deleted: number }>("/api/conversations", { method: "DELETE" }),
  messages: (conversationId: string) => request<Message[]>(`/api/conversations/${conversationId}/messages`),
  sessions: (conversationId: string) => request<Session[]>(`/api/conversations/${conversationId}/sessions`),
  createSession: (conversationId: string, query: string, workingDirectory: string | undefined, yolo: boolean) => request<Session>(
    `/api/conversations/${conversationId}/sessions`,
    { method: "POST", body: JSON.stringify({ query, working_directory: workingDirectory || null, yolo }) }
  ),
  session: (conversationId: string, sessionId: string) => request<Session>(
    `/api/conversations/${conversationId}/sessions/${sessionId}`
  ),
  sessionEvents: (conversationId: string, sessionId: string) => request<SessionEvent[]>(
    `/api/conversations/${conversationId}/sessions/${sessionId}/events`
  ),
  cancelSession: (conversationId: string, sessionId: string) => request<Session>(
    `/api/conversations/${conversationId}/sessions/${sessionId}/cancel`,
    { method: "POST" }
  ),
  approvals: () => request<Approval[]>("/api/approvals"),
  decideApproval: (approval: Approval, decision: "approved" | "denied") => request(
    `/api/conversations/${approval.conversation_id}/approvals/${approval.id}/decision`,
    { method: "POST", body: JSON.stringify({ decision, denial_reason: "" }) }
  ),
  getConfig: () => request<ConfigDisplay>("/api/config"),
  setConfigValue: (key: string, value: string) => request<ConfigDisplay>(
    "/api/config/set",
    { method: "POST", body: JSON.stringify({ key, value }) }
  ),
  getLogs: (conversationId: string) => request<LogFile[]>(`/api/conversations/${conversationId}/logs`),
  getAllSessions: (state?: string) => request<SessionRow[]>(
    `/api/sessions${state ? `?state=${encodeURIComponent(state)}` : ""}`
  ),
  getSkills: () => request<SkillInfo[]>("/api/skills")
};

export async function streamSession(
  conversationId: string,
  sessionId: string,
  onEvent: (event: SessionEvent) => void,
  signal: AbortSignal
) {
  const token = tokenStore.get();
  await fetchEventSource(
    endpoint(`/api/conversations/${conversationId}/sessions/${sessionId}/events/stream`),
    {
      signal,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      openWhenHidden: true,
      async onopen(response) {
        if (!response.ok) throw new Error(`事件连接失败 (${response.status})`);
      },
      onmessage(message) {
        onEvent(JSON.parse(message.data) as SessionEvent);
      },
      onerror(error) {
        throw error;
      }
    }
  );
}
