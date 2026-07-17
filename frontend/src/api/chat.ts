import client from "./client";
import { useAuthStore } from "@/stores/auth";

export interface ChatImage {
  path: string;
  filename: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  images: ChatImage[];
  status: string;
  error_msg: string | null;
  usage: Record<string, number>;
  created_at: string;
}

export interface ChatSessionListItem {
  id: string;
  title: string;
  last_message_at: string | null;
  created_at: string;
}

export interface ChatSessionList {
  sessions: ChatSessionListItem[];
}

export interface ChatSessionDetail {
  id: string;
  title: string;
  created_at: string;
  last_message_at: string | null;
  messages: ChatMessage[];
}

export async function listSessions(): Promise<ChatSessionList> {
  const { data } = await client.get<ChatSessionList>("/chat/sessions");
  return data;
}

export async function createSession(): Promise<{ session_id: string }> {
  const { data } = await client.post<{ session_id: string }>("/chat/sessions");
  return data;
}

export async function getSession(id: string): Promise<ChatSessionDetail> {
  const { data } = await client.get<ChatSessionDetail>(`/chat/sessions/${id}`);
  return data;
}

export async function deleteSession(id: string): Promise<void> {
  await client.delete(`/chat/sessions/${id}`);
}

export interface StreamCallbacks {
  onDelta: (text: string) => void;
  onDone: (text: string, usage: Record<string, number>) => void;
  onError: (detail: string) => void;
}

/**
 * 流式发送消息。使用原生 fetch + ReadableStream 解析 SSE，
 * 绕过 axios（axios 拦截器不支持流式读取）。
 * 返回 Response 以便调用方读取非 200 错误。
 */
export async function sendMessageStream(
  sessionId: string,
  text: string,
  files: File[],
  cb: StreamCallbacks,
): Promise<void> {
  const form = new FormData();
  form.append("text", text);
  files.forEach((f) => form.append("images", f));

  const auth = useAuthStore();
  const resp = await fetch(`/api/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: auth.token ? { Authorization: `Bearer ${auth.token}` } : {},
    body: form,
  });

  if (!resp.ok || !resp.body) {
    // 非流式错误：尝试读取 detail
    let detail = "发送失败，请稍后重试";
    try {
      const obj = await resp.json();
      detail = obj.detail || detail;
    } catch {
      /* ignore */
    }
    // 401 / 402 交由全局处理：这里复用 axios 拦截器逻辑的简化版
    if (resp.status === 401) {
      const { ElMessage } = await import("element-plus");
      const router = (await import("@/router")).default;
      auth.logout();
      ElMessage.warning(detail || "登录已失效，请重新登录");
      router.push("/login");
    } else if (resp.status === 402) {
      const { ElMessage } = await import("element-plus");
      const router = (await import("@/router")).default;
      ElMessage.warning(detail || "积分已用完，请充值后继续使用");
      router.push("/recharge");
    } else {
      const { ElMessage } = await import("element-plus");
      ElMessage.error(detail);
    }
    cb.onError(detail);
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE 事件以空行分隔
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      parseSseEvent(rawEvent, cb);
    }
  }
  // 处理残留
  if (buffer.trim()) {
    parseSseEvent(buffer, cb);
  }
}

function parseSseEvent(raw: string, cb: StreamCallbacks): void {
  const lines = raw.split("\n");
  let event = "";
  let dataLine = "";
  for (const line of lines) {
    if (line.startsWith("event: ")) {
      event = line.slice(7).trim();
    } else if (line.startsWith("data: ")) {
      dataLine = line.slice(6);
    }
  }
  if (!dataLine) return;
  let payload: any = {};
  try {
    payload = JSON.parse(dataLine);
  } catch {
    return;
  }
  if (event === "delta") {
    cb.onDelta(payload.text || "");
  } else if (event === "done") {
    cb.onDone(payload.text || "", payload.usage || {});
  } else if (event === "error") {
    cb.onError(payload.detail || "生成失败");
  }
}
