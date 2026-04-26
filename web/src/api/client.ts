const API_BASE = "/api";

export async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function putJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function deleteJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export type WsMessage = { type: string; data: Record<string, unknown> };

// --- Engine control ---

export type SystemStatus = {
  cybos_connected: boolean;
  server_type: string;
  engine_running: boolean;
  active_workers: number;
  account_number: string;
  error: string | null;
  telegram_code_pending: boolean;
};

export function fetchStatus(): Promise<SystemStatus> {
  return fetchJson<SystemStatus>("/status");
}

export function launchCybos(): Promise<{ status: string }> {
  return postJson("/engine/launch-cybos");
}

export function startEngine(): Promise<{ status: string }> {
  return postJson("/engine/start");
}

export function stopEngine(): Promise<{ status: string }> {
  return postJson("/engine/stop");
}

export function emergencySellAll(): Promise<{ status: string; count?: number }> {
  return postJson("/emergency/sell-all");
}

export function submitTelegramCode(code: string): Promise<{ status: string }> {
  return postJson("/telegram/auth-code", { code });
}

// --- News feed ---

export type NewsFeedItem = {
  stock_code: string;
  stock_name: string;
  source: string;
  category?: string;
  text: string;
  time?: string;
  timestamp?: string;
};

export function fetchNewsFeed(): Promise<NewsFeedItem[]> {
  return fetchJson<NewsFeedItem[]>("/news-feed");
}

// --- Log streaming ---

export type LogEntry = {
  seq?: number;
  timestamp: string;
  level: string;
  logger: string;
  message: string;
};

export type LiveLogsResponse = {
  logs: LogEntry[];
  seq: number;
};

export function fetchLiveLogs(afterSeq: number): Promise<LiveLogsResponse> {
  return fetchJson<LiveLogsResponse>(`/logs/live?after=${afterSeq}`);
}

export function connectWebSocket(onMessage: (msg: WsMessage) => void): WebSocket {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${protocol}//${location.host}/ws`);

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data) as WsMessage;
      onMessage(msg);
    } catch {}
  };

  ws.onclose = () => {
    setTimeout(() => {
      const reconnected = connectWebSocket(onMessage);
      Object.assign(ws, reconnected);
    }, 3000);
  };

  return ws;
}
