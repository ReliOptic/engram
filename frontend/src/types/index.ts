/** Agent roles in the Engram system */
export type AgentRole = 'analyzer' | 'finder' | 'reviewer' | 'user';

/** Agent status during orchestration */
export type AgentStatus = 'idle' | 'thinking' | 'done' | 'waiting' | 'processing';

/** A single agent's contribution in the discussion */
export interface AgentMessage {
  id: string;
  agent: AgentRole;
  contributionType: string;
  content: string;
  addressedTo?: string;
  timestamp: string;
  silo?: SiloSelection;
}

/** Cascading dropdown selection */
export interface SiloSelection {
  account: string;
  tool: string;
  component: string;
}

/** Dropdown config from backend */
export interface DropdownConfig {
  accounts: Record<string, {
    tools: Record<string, {
      components: string[];
    }>;
  }>;
}

/** Source document reference from agents */
export interface SourceRef {
  id: string;
  title: string;
  type: 'manual' | 'case' | 'weekly';
  relevance: number;
}

/** A chunk retrieved from GET /api/chunks/{id} */
export interface ChunkDetail {
  id: string;
  document: string;
  metadata: Record<string, unknown>;
  collection: string;
}

/** WebSocket message envelope */
export interface WsMessage {
  type: 'user_message' | 'agent_message' | 'status_update' | 'error';
  payload: unknown;
}

/** Agent display metadata */
export interface AgentInfo {
  role: AgentRole;
  displayName: string;
  description: string;
  color: string;
  status: AgentStatus;
}
