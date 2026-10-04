/** The public learning API uses an anonymous, short-lived session token. */
export type BridgeLanguage = 'en' | 'zh';
export type GroundingStatus = 'GROUNDED' | 'INSUFFICIENT EVIDENCE';

export interface BridgeModule {
  id: string;
  title: string;
  course_id?: string;
  description?: string | null;
  active?: boolean;
  assessment_locked?: boolean;
  created_at?: string;
  updated_at?: string;
  material_count?: number;
  ready_count?: number;
}

export interface BridgeMaterial {
  id: string;
  module_id: string;
  filename: string;
  size_bytes: number;
  processing_status: string;
  processing_error?: string | null;
  page_count?: number;
  chunk_count?: number;
  created_at: string;
  processed_at?: string | null;
}
export interface BridgeSolution { id: string; filename: string; size_bytes: number; }
export type BridgeChunkType = 'DEFINITION' | 'EXAMPLE' | 'HINT' | 'PARTIAL_SOLUTION' | 'WORKED_SOLUTION' | 'ANSWER' | 'UNREVIEWED';
export interface BridgeChunk {
  id: string; module_id: string; material_id: string; filename: string; page_number?: number | null;
  chunk_index: number; text: string; language: string; chunk_type: BridgeChunkType; reviewed: boolean;
}

export interface BridgeGlossaryTerm { id?: string; english: string; chinese: string; notes?: string; }
export interface BridgeConcept {
  id: string; key: string; title_en: string; title_zh: string; description: string;
  source_chunk_id?: string | null; reviewed: boolean;
}
export interface BridgeTemplate {
  id: string; concept_id: string; template_type: string; language: string; text: string;
  source_chunk_id?: string | null; reviewed: boolean;
}
export interface BridgeRegressionPrompt {
  id: string; concept_id?: string | null; question: string; language: string;
  expected_chunk_id?: string | null; expected_status: string; reviewed: boolean;
}
export interface BridgeArtefacts {
  concepts: BridgeConcept[];
  templates: BridgeTemplate[];
  regression_prompts: BridgeRegressionPrompt[];
  gaps: string[];
  created_counts?: Record<string, number>;
}
export interface BridgeTestRun {
  total: number; passed: number; failed: number; skipped: number; executed?: number; not_run?: number; scope?: string;
  results: { id: string; question: string; passed: boolean | null; reason: string; actual_sources: string[] }[];
}
export interface BridgeDashboard {
  interaction_count_band: string; suppression_threshold: number; window: string;
  misconceptions: { concept_key: string; count: number }[];
  stages: { stage: string; count: number }[];
  stall_points?: { concept_key?: string; stage?: string; count: number }[];
  most_retrieved_materials?: { source_file?: string; filename?: string; count: number }[];
  suggested_interventions?: { concept_key?: string; suggestion?: string; prompt?: string; text?: string }[];
}

export interface BridgeSession {
  session_token: string;
  module_id: string;
  language: BridgeLanguage;
  expires_at: string;
  lock_status: boolean;
  stage: string;
  avatar_state: string;
  welcome: string;
  grounding_status?: GroundingStatus;
  sources?: BridgeSource[];
}

export interface BridgeSource {
  source_id?: string;
  document?: string;
  page?: number | null;
  reference?: string;
  chunk_id?: string;
}

export interface BridgeTutorReply {
  response: string;
  stage: string;
  avatar_state: string;
  grounding_status: GroundingStatus;
  sources: BridgeSource[];
  language: BridgeLanguage;
  practice: string | null;
  lock_status: boolean;
  learning_state?: { concept_key?: string; scaffold_count?: number; mastery?: boolean };
}

export class BridgeApiError extends Error {
  constructor(public status: number, message: string) { super(message); this.name = 'BridgeApiError'; }
}

const delay = (ms: number) => new Promise<void>(resolve => window.setTimeout(resolve, ms));

async function request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/bridge${path}`, init);
  } catch (error) {
    if ((error as Error)?.name === 'AbortError') throw error;
    throw new BridgeApiError(0, 'Connection unavailable');
  }
  if (retry && (response.status === 429 || response.status === 503)) {
    await delay(response.status === 429 ? 2000 : 1000);
    return request<T>(path, init, false);
  }
  if (!response.ok) {
    // Deliberately avoid surfacing backend exception text in student-facing UI.
    throw new BridgeApiError(response.status, `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function json(body: unknown, headers: Record<string, string> = {}, signal?: AbortSignal): RequestInit {
  return { method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body), signal };
}

function staffHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const token = localStorage.getItem('access_token');
  return { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...extra };
}
function staffJson(body: unknown, method = 'POST'): RequestInit {
  return { method, headers: staffHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify(body) };
}
function staffForm(file: File): RequestInit {
  const form = new FormData(); form.append('file', file);
  return { method: 'POST', headers: staffHeaders(), body: form };
}

export const bridgeApi = {
  async listPublicModules(): Promise<BridgeModule[]> {
    const result = await request<{ modules: BridgeModule[] } | BridgeModule[]>('/modules/active');
    return Array.isArray(result) ? result : result.modules || [];
  },
  createSession(moduleId: string, language: BridgeLanguage, signal?: AbortSignal) {
    return request<BridgeSession>('/sessions', json({ module_id: moduleId, language }, {}, signal));
  },
  tutor(sessionToken: string, message: string, language: BridgeLanguage, signal?: AbortSignal) {
    return request<BridgeTutorReply>('/tutor', json({ message, language }, { 'X-Bridge-Session': sessionToken }, signal));
  },
  deleteSession(sessionToken: string) {
    return request<void>('/sessions/current', { method: 'DELETE', headers: { 'X-Bridge-Session': sessionToken } }, false);
  },

  async listStaffModules(): Promise<BridgeModule[]> {
    const result = await request<{ modules: BridgeModule[] }>('/modules', { headers: staffHeaders() });
    return result.modules || [];
  },
  createModule(courseId: string, title: string) {
    return request<BridgeModule>('/modules', staffJson({ course_id: courseId, title }));
  },
  updateModule(moduleId: string, data: { title?: string; active?: boolean; assessment_locked?: boolean }) {
    return request<BridgeModule>(`/modules/${encodeURIComponent(moduleId)}`, staffJson(data, 'PATCH'));
  },
  async listMaterials(moduleId: string): Promise<BridgeMaterial[]> {
    const result = await request<{ materials: BridgeMaterial[] }>(`/modules/${encodeURIComponent(moduleId)}/materials`, { headers: staffHeaders() });
    return result.materials || [];
  },
  uploadMaterial(moduleId: string, file: File) {
    return request<BridgeMaterial>(`/modules/${encodeURIComponent(moduleId)}/materials`, staffForm(file), false);
  },
  reindexMaterial(moduleId: string, materialId: string) {
    return request<BridgeMaterial>(`/modules/${encodeURIComponent(moduleId)}/materials/${encodeURIComponent(materialId)}/reindex`, staffJson({}), false);
  },
  deleteMaterial(moduleId: string, materialId: string) {
    return request<{ deleted: boolean }>(`/modules/${encodeURIComponent(moduleId)}/materials/${encodeURIComponent(materialId)}`, { method: 'DELETE', headers: staffHeaders() }, false);
  },
  async listChunks(moduleId: string): Promise<BridgeChunk[]> {
    const result = await request<{ chunks: BridgeChunk[] }>(`/modules/${encodeURIComponent(moduleId)}/chunks`, { headers: staffHeaders() });
    return result.chunks || [];
  },
  updateChunk(moduleId: string, chunkId: string, chunkType: BridgeChunkType, reviewed: boolean) {
    return request<BridgeChunk>(`/modules/${encodeURIComponent(moduleId)}/chunks/${encodeURIComponent(chunkId)}`, staffJson({ chunk_type: chunkType, reviewed }, 'PATCH'), false);
  },
  async getGlossary(moduleId: string): Promise<BridgeGlossaryTerm[]> {
    const result = await request<{ terms: BridgeGlossaryTerm[] }>(`/modules/${encodeURIComponent(moduleId)}/glossary`, { headers: staffHeaders() });
    return result.terms || [];
  },
  async putGlossary(moduleId: string, terms: BridgeGlossaryTerm[]): Promise<BridgeGlossaryTerm[]> {
    const result = await request<{ terms: BridgeGlossaryTerm[] }>(`/modules/${encodeURIComponent(moduleId)}/glossary`, staffJson({ terms }, 'PUT'), false);
    return result.terms || [];
  },
  async listSolutions(moduleId: string): Promise<BridgeSolution[]> {
    const result = await request<{ solutions: BridgeSolution[] }>(`/modules/${encodeURIComponent(moduleId)}/solutions`, { headers: staffHeaders() });
    return result.solutions || [];
  },
  uploadSolution(moduleId: string, file: File) {
    return request<BridgeSolution>(`/modules/${encodeURIComponent(moduleId)}/solutions`, staffForm(file), false);
  },
  deleteSolution(moduleId: string, solutionId: string) {
    return request<{ deleted: boolean }>(`/modules/${encodeURIComponent(moduleId)}/solutions/${encodeURIComponent(solutionId)}`, { method: 'DELETE', headers: staffHeaders() }, false);
  },
  getArtefacts(moduleId: string) {
    return request<BridgeArtefacts>(`/staff/modules/${encodeURIComponent(moduleId)}/artefacts`, { headers: staffHeaders() });
  },
  compile(moduleId: string) {
    return request<BridgeArtefacts>(`/staff/modules/${encodeURIComponent(moduleId)}/compile`, staffJson({}), false);
  },
  addConcept(moduleId: string, data: { key: string; title_en: string; title_zh: string; description: string; source_chunk_id: string | null }) {
    return request<BridgeConcept>(`/staff/modules/${encodeURIComponent(moduleId)}/concepts`, staffJson(data), false);
  },
  addTemplate(moduleId: string, data: { concept_id: string | null; template_type: string; language: string; text: string; source_chunk_id: string | null }) {
    return request<BridgeTemplate>(`/staff/modules/${encodeURIComponent(moduleId)}/templates`, staffJson(data), false);
  },
  addRegressionPrompt(moduleId: string, data: { concept_id: string | null; question: string; language: string; expected_chunk_id: string | null; expected_status: string }) {
    return request<BridgeRegressionPrompt>(`/staff/modules/${encodeURIComponent(moduleId)}/regression-prompts`, staffJson(data), false);
  },
  editConcept(moduleId: string, conceptId: string, data: Partial<BridgeConcept>) {
    return request<BridgeConcept>(`/staff/modules/${encodeURIComponent(moduleId)}/concepts/${encodeURIComponent(conceptId)}`, staffJson(data, 'PATCH'), false);
  },
  editTemplate(moduleId: string, templateId: string, data: Partial<BridgeTemplate>) {
    return request<BridgeTemplate>(`/staff/modules/${encodeURIComponent(moduleId)}/templates/${encodeURIComponent(templateId)}`, staffJson(data, 'PATCH'), false);
  },
  editRegressionPrompt(moduleId: string, promptId: string, data: Partial<BridgeRegressionPrompt>) {
    return request<BridgeRegressionPrompt>(`/staff/modules/${encodeURIComponent(moduleId)}/regression-prompts/${encodeURIComponent(promptId)}`, staffJson(data, 'PATCH'), false);
  },
  runTests(moduleId: string) {
    return request<BridgeTestRun>(`/staff/modules/${encodeURIComponent(moduleId)}/test`, staffJson({}), false);
  },
  getDashboard(moduleId: string) {
    return request<BridgeDashboard>(`/staff/modules/${encodeURIComponent(moduleId)}/dashboard`, { headers: staffHeaders() });
  },
};
