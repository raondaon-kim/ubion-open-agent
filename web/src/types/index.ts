export type Role = "user" | "assistant" | "system";

/** assistant 가 응답 작성 중일 때 사용자에게 보여줄 진행 상태 */
export interface ProgressState {
  /** "thinking" = LLM 호출 중, "tool" = 도구 실행 중 */
  stage: "thinking" | "tool";
  /** 도구 이름 — stage = "tool" 일 때만 */
  toolName?: string;
  /** 이 단계 시작 시각 (ms epoch) — 경과 시간 표시용 */
  startedAt: number;
  /** 최근에 끝낸 도구의 누적 카운트 (UX 용) */
  toolsCompleted?: number;
}

export interface Message {
  id: string;
  role: Role;
  content: string;
  /** ISO 타임스탬프 */
  createdAt: string;
  /** 스트리밍 중인지 표시 (assistant 메시지에만 의미) */
  streaming?: boolean;
  /** 응답 작성 중 진행 상태 (streaming=true 일 때만 의미) */
  progress?: ProgressState;
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
