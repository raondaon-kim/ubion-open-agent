export type Role = "user" | "assistant" | "system";

export interface Message {
  id: string;
  role: Role;
  content: string;
  /** ISO 타임스탬프 */
  createdAt: string;
  /** 스트리밍 중인지 표시 (assistant 메시지에만 의미) */
  streaming?: boolean;
}

export interface ChatSession {
  id: string;
  title: string;
  /** ISO 타임스탬프 */
  updatedAt: string;
  messages: Message[];
  model: string;
}

export type Panel = "chat" | "skills" | "memory" | "settings";

export interface ModelInfo {
  id: string;
  /** 'anthropic' | 'deepseek' — UI 배지용 추론치 */
  provider?: string;
}

export interface SkillEntry {
  name: string;
  description: string;
  content?: string;
  /** 자동 생성된 skill 인지 (`.usage.json` 기반) */
  agentCreated?: boolean;
  useCount?: number;
}

export interface MemoryEntry {
  id: string;
  type: "user" | "feedback" | "project" | "reference" | string;
  description: string;
  body: string;
}
