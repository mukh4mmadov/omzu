export type ToolEvent = {
  type: "tool";
  name: string;
  args: Record<string, unknown>;
  result: Record<string, any>;
};

export type Source = { title: string; source: string };

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  extra?: { tools: ToolEvent[]; sources: Source[] } | null;
  rating?: number | null;
  status?: string | null;
  streaming?: boolean;
};

export type Conversation = { id: string; title: string; updated: string };

export type StreamEvent =
  | { type: "meta"; conversation_id: string; message_id: string; user_message_id: string }
  | { type: "status"; text: string }
  | ToolEvent
  | { type: "sources"; items: Source[] }
  | { type: "token"; text: string }
  | { type: "done" };

export type Status = { name: string; mode: "model" | "tools"; label: string };
export type Memory = { id: number; fact: string; created: string };
export type Reminder = { id: number; text: string; due: string; done?: boolean };
export type Task = { id: number; text: string; due: string | null; done: boolean };
export type DocInfo ={ name: string; chunks: number; chars: number };
export type UploadResult = { ok: boolean; name: string; chunks?: number; chars?: number; error?: string };

export const ACCEPT = ".pdf,.docx,.md,.markdown,.txt,.html,.htm,.csv,.json,.js,.ts,.py,.java,.c,.cpp,.cs,.go,.rs,.php,.rb,.css,.sql";
