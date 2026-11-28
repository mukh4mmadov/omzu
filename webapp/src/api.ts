import type { Conversation, DocInfo, Memory, Message, Reminder, Status, StreamEvent, Task, UploadResult } from "./types";

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json() as Promise<T>;
}

export const api = {
  status: () => json<Status>("/api/status"),
  conversations: () => json<Conversation[]>("/api/conversations"),
  conversation: (id: string) => json<Message[]>(`/api/conversations/${id}`),
  deleteConversation: (id: string) => json(`/api/conversations/${id}`, { method: "DELETE" }),
  feedback: (message_id: string, rating: number, correction?: string | null) =>
    json("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message_id, rating, correction: correction ?? null }),
    }),
  memories: () => json<Memory[]>("/api/memories"),
  forget: (id: number) => json(`/api/memories/${id}`, { method: "DELETE" }),
  reminders: () => json<Reminder[]>("/api/reminders"),
  tasks: () => json<Task[]>("/api/tasks"),
  addTask: (text: string, due?: string | null) => json<Task>("/api/tasks", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, due: due ?? null }),
  }),
  toggleTask: (id: number, done: boolean) => json(`/api/tasks/${id}/toggle?done=${done}`, { method: "POST" }),
  deleteTask: (id: number) => json(`/api/tasks/${id}`, { method: "DELETE" }),
  documents: () => json<DocInfo[]>("/api/documents"),
  deleteDocument: (name: string) => json(`/api/documents/${encodeURIComponent(name)}`, { method: "DELETE" }),
  uploadDocuments: (files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return json<UploadResult[]>("/api/documents", { method: "POST", body: fd });
  },
  dueReminders: () => json<Reminder[]>("/api/reminders/due"),
};

export async function streamChat(
  message: string,
  conversationId: string | null,
  onEvent: (ev: StreamEvent) => void,
  signal: AbortSignal,
) {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, conversation_id: conversationId }),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`Server xatosi: ${res.status}`);
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, i);
      buf = buf.slice(i + 2);
      if (chunk.startsWith("data: ")) onEvent(JSON.parse(chunk.slice(6)) as StreamEvent);
    }
  }
}
