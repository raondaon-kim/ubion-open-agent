import type { Message, ModelInfo } from "../types";

const STORAGE_TOKEN = "ubion.bearer";
const STORAGE_BASE = "ubion.base";

export function getBearerToken(): string {
  return localStorage.getItem(STORAGE_TOKEN) ?? "";
}

export function setBearerToken(value: string): void {
  localStorage.setItem(STORAGE_TOKEN, value);
}

/**
 * Resolve the API base URL.
 *
 * Three modes, picked at runtime:
 *   1. User override (Settings → API base) — wins, lets a power user
 *      point at a remote engine if needed.
 *   2. Tauri shell — call the Rust `get_backend_port` command and use
 *      `http://127.0.0.1:<port>`. The port is allocated freshly on each
 *      spawn/respawn, so we re-resolve any time the cached value is 0.
 *   3. Browser dev — empty string, relying on Vite's proxy.
 *
 * The resolved value is cached for the lifetime of the page; on a Tauri
 * respawn the page itself doesn't reload, so we re-fetch the port lazily
 * inside `getApiBase()` whenever the cache is unset.
 */
let cachedBase: string | null = null;

function tauriInvoke<T>(cmd: string): Promise<T> | null {
  // The `@tauri-apps/api` IPC module is dynamically imported so the
  // pure-browser build still works for `pnpm dev` without erroring on
  // a missing __TAURI__ global.
  const w = window as unknown as { __TAURI_INTERNALS__?: unknown };
  if (!w.__TAURI_INTERNALS__) return null;
  return import("@tauri-apps/api/core").then((mod) => mod.invoke<T>(cmd));
}

export async function getApiBase(): Promise<string> {
  if (cachedBase !== null) return cachedBase;

  const override = localStorage.getItem(STORAGE_BASE);
  if (override) {
    cachedBase = override;
    return override;
  }

  const portPromise = tauriInvoke<number>("get_backend_port");
  if (portPromise) {
    const port = await portPromise.catch(() => 0);
    if (port > 0) {
      cachedBase = `http://127.0.0.1:${port}`;
      return cachedBase;
    }
  }

  cachedBase = ""; // Vite proxy fallback
  return cachedBase;
}

export function clearApiBaseCache(): void {
  cachedBase = null;
}

/** Settings UI helper — read the raw user override, no async, no Tauri. */
export function getApiBaseOverride(): string {
  return localStorage.getItem(STORAGE_BASE) ?? "";
}

export function setApiBase(value: string): void {
  localStorage.setItem(STORAGE_BASE, value);
  clearApiBaseCache();
}

function buildHeaders(): Headers {
  const headers = new Headers({ "Content-Type": "application/json" });
  const token = getBearerToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

export async function fetchModels(): Promise<ModelInfo[]> {
  const res = await fetch(`${await getApiBase()}/v1/models`, { headers: buildHeaders() });
  if (!res.ok) throw new Error(`/v1/models ${res.status}`);
  const json = await res.json();
  return (json.data ?? []).map((m: { id: string }) => ({
    id: m.id,
    provider: m.id.startsWith("deepseek") ? "deepseek" : "anthropic",
  }));
}

export async function fetchHealth(): Promise<{ status: string }> {
  const res = await fetch(`${await getApiBase()}/health`);
  if (!res.ok) throw new Error(`/health ${res.status}`);
  return res.json();
}

export interface FsEntry {
  name: string;
  path: string;
  is_dir: boolean;
}

export interface FsListResponse {
  path: string;
  parent: string | null;
  entries: FsEntry[];
  roots: string[];
}

export async function fsList(path?: string): Promise<FsListResponse> {
  const url = new URL(
    `${(await getApiBase()) || ""}/v1/ubion/fs/list`,
    window.location.origin,
  );
  if (path) url.searchParams.set("path", path);
  const res = await fetch(url.toString(), { headers: buildHeaders() });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`/v1/ubion/fs/list ${res.status}: ${text}`);
  }
  return res.json();
}

export interface ConversationMeta {
  id: string;
  title: string;
  created: string;
  updated: string;
  model: string;
}

export interface ConversationTurnPayload {
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
}

export interface ConversationDetail {
  meta: ConversationMeta;
  turns: ConversationTurnPayload[];
}

export async function listConversations(): Promise<ConversationMeta[]> {
  const res = await fetch(`${await getApiBase()}/v1/ubion/conversations`, {
    headers: buildHeaders(),
  });
  if (!res.ok) throw new Error(`/v1/ubion/conversations ${res.status}`);
  const json = await res.json();
  return json?.conversations ?? [];
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  const res = await fetch(
    `${await getApiBase()}/v1/ubion/conversations/${encodeURIComponent(id)}`,
    { headers: buildHeaders() },
  );
  if (!res.ok) throw new Error(`/v1/ubion/conversations/${id} ${res.status}`);
  return res.json();
}

export async function saveConversation(payload: {
  id?: string | null;
  model: string;
  created?: string | null;
  messages: Pick<Message, "role" | "content">[];
}): Promise<ConversationMeta> {
  const res = await fetch(`${await getApiBase()}/v1/ubion/conversations`, {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`POST /v1/ubion/conversations ${res.status}: ${text}`);
  }
  return res.json();
}

export async function deleteConversation(id: string): Promise<void> {
  const res = await fetch(
    `${await getApiBase()}/v1/ubion/conversations/${encodeURIComponent(id)}`,
    { method: "DELETE", headers: buildHeaders() },
  );
  if (!res.ok && res.status !== 404) {
    throw new Error(`DELETE /v1/ubion/conversations/${id} ${res.status}`);
  }
}

export async function fetchServerWorkspace(): Promise<string> {
  const res = await fetch(`${await getApiBase()}/v1/ubion/workspace`, {
    headers: buildHeaders(),
  });
  if (!res.ok) throw new Error(`/v1/ubion/workspace ${res.status}`);
  const json = await res.json();
  return json?.workspace ?? "";
}

export interface ChatRequestParams {
  model: string;
  messages: Pick<Message, "role" | "content">[];
  signal?: AbortSignal;
  onDelta?: (text: string) => void;
}

/**
 * OpenAI-호환 SSE 스트림을 파싱해 onDelta 콜백으로 청크를 흘려보낸다.
 * 호출자는 보통 useState 의 setter 에 onDelta 를 연결해 메시지에 누적.
 */
export async function streamChatCompletion(
  params: ChatRequestParams,
): Promise<string> {
  const res = await fetch(`${await getApiBase()}/v1/chat/completions`, {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify({
      model: params.model,
      messages: params.messages,
      stream: true,
    }),
    signal: params.signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`/v1/chat/completions ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let aggregate = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE 는 \n\n 으로 이벤트 구분
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const eventBlock = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      for (const line of eventBlock.split("\n")) {
        if (!line.startsWith("data:")) continue;
        const payload = line.slice(5).trim();
        if (payload === "[DONE]") return aggregate;
        try {
          const chunk = JSON.parse(payload);
          const delta = chunk?.choices?.[0]?.delta?.content;
          if (typeof delta === "string" && delta.length > 0) {
            aggregate += delta;
            params.onDelta?.(delta);
          }
        } catch {
          // 깨진 청크는 조용히 무시
        }
      }
    }
  }
  return aggregate;
}
