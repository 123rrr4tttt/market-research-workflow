/** Stable wire shapes shared by the MRW host transport and its consumers. */

export type MrwSkillDescriptor = {
  name: string;
  path: string;
  contentDigest?: string;
  sourceRoot?: string;
  relativePath?: string;
};

/** App-server `UserInput` skill branch, derived from a verified host-mapped skill. */
export type MrwTurnSkillInput = {
  type: 'skill';
  name: string;
  path: string;
};

export type MrwPreparedEnvironment = {
  bindingId: string;
  projectKey: string;
  packageId: string | null;
  packageVersion: string | null;
  sessionId: string | null;
  threadId: string | null;
  status: string;
  environmentStatus: string;
  environmentDigest: string;
  dynamicTools: unknown[];
  skills: MrwSkillDescriptor[];
  skillRoots: string[];
  environmentStale?: boolean;
};

export type MrwBindResult = MrwPreparedEnvironment;

export type MrwPendingAction = {
  actionId: string;
  actionDigest?: string;
  toolName: string;
  arguments: Record<string, unknown>;
  projectKey: string;
  threadId: string;
  turnId: string;
  callId: string;
};

export type MrwDispatchResult = {
  success: boolean;
  result?: unknown;
  resultProjection?: Record<string, unknown>;
  pendingAction?: {
    actionId: string;
    actionDigest?: string;
    toolName: string;
    arguments: Record<string, unknown>;
    projectKey: string;
    threadId: string;
    turnId: string;
  };
  contentItems: { type: string; text?: string }[];
};

export type MrwConfirmRequest = {
  threadId: string;
  turnId: string;
  actionId: string;
  approved: boolean;
  userText?: string;
};

export type MrwConfirmResult = {
  confirmed: boolean;
  actionId: string;
  approved: boolean;
  threadId: string;
};

export type MrwDynamicToolCallParams = {
  threadId: string;
  turnId: string;
  callId: string;
  namespace: string | null;
  tool: string;
  arguments: Record<string, unknown>;
};
