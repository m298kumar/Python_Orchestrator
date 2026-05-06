import axios from 'axios';

// ---------------------------------------------------------------------------
// Interfaces matching backend schemas
// ---------------------------------------------------------------------------

export interface PipelineRunRequest {
  pipeline_path?: string;
  config?: Record<string, any>;
  resume_from?: string;
  max_workers?: number;
  profile?: string;
}

export interface PipelineRunStatus {
  run_id: string;
  pipeline_name: string;
  status: string;
  started_at: string;
  completed_at?: string;
  stages_completed: string[];
  stages_failed: string[];
  stages_skipped: string[];
  current_stage?: string;
  total_duration_seconds?: number;
  error_message?: string;
  archived: boolean;
  archived_at?: string;
}

export interface PipelineRunSummary {
  run_id: string;
  pipeline_name: string;
  status: string;
  started_at: string;
  stages_completed_count: number;
  total_duration_seconds?: number;
  archived: boolean;
  archived_at?: string;
}

export interface AgentInfo {
  agent_id: string;
  agent_version: string;
  description: string;
  input_types: string[];
  output_types: string[];
}

export interface Requirement {
  req_id: string;
  title: string;
  description: string;
  priority: string;
  category: string;
  acceptance_criteria: string[];
  tags: string[];
}

export interface TestStep {
  action: string;
  expected_result: string;
}

export interface TestCase {
  tc_id: string;
  req_id: string;
  title: string;
  description: string;
  preconditions: string;
  test_type: string;
  priority: string;
  category: string;
  component: string;
  steps: TestStep[];
  given: string;
  when: string;
  then: string;
  expected_outcome: string;
  tags: string[];
  status: string;
  test_level: string;
  quality_score: number;
  run_id?: string;
}

export interface FeatureFile {
  filename: string;
  req_id: string;
  scenario_count: number;
  tags: string[];
  content?: string;
  run_id?: string;
}

export interface HealthResponse {
  status: string;
  version: string;
  stage: number;
  agents_registered: number;
}

export interface FeedbackRequest {
  agent_id: string;
  feedback_type: string;
  message: string;
}

export interface AuthStatus {
  auth_enabled: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

// ---------------------------------------------------------------------------
// Axios instance
// ---------------------------------------------------------------------------

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Attach Bearer token to requests when available
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('stlc_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor — normalise errors into a predictable shape
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      // Server responded with a non-2xx status
      const message =
        error.response.data?.detail ??
        error.response.data?.message ??
        error.response.statusText ??
        'Request failed';
      const enhanced = new Error(message);
      (enhanced as any).status = error.response.status;
      (enhanced as any).data = error.response.data;
      return Promise.reject(enhanced);
    }
    if (error.request) {
      // Request was made but no response received
      return Promise.reject(new Error('No response from server. Check your network connection.'));
    }
    return Promise.reject(error);
  },
);

// ---------------------------------------------------------------------------
// Pipeline
// ---------------------------------------------------------------------------

export const triggerPipelineRun = (req: PipelineRunRequest) =>
  api.post<PipelineRunStatus>('/pipeline/run', req);

export const listPipelineRuns = () => api.get<PipelineRunSummary[]>('/pipeline/runs');

export const getPipelineRun = (runId: string) =>
  api.get<PipelineRunStatus>('/pipeline/runs/' + runId);

export const archiveRun = (runId: string) =>
  api.post<PipelineRunSummary>('/pipeline/runs/' + runId + '/archive');

export const restoreRun = (runId: string) =>
  api.post<PipelineRunSummary>('/pipeline/runs/' + runId + '/restore');

export const deleteRun = (runId: string) =>
  api.delete<{ deleted: string }>('/pipeline/runs/' + runId);

export const clearAllRuns = () =>
  api.delete<{ deleted: number }>('/pipeline/runs');

// ---------------------------------------------------------------------------
// Agents
// ---------------------------------------------------------------------------

export const listAgents = () => api.get<AgentInfo[]>('/agents/');

export const getAgent = (agentId: string) => api.get<AgentInfo>('/agents/' + agentId);

// ---------------------------------------------------------------------------
// Requirements
// ---------------------------------------------------------------------------

export const uploadRequirements = (file: File) => {
  const fd = new FormData();
  fd.append('file', file);
  return api.post('/requirements/upload', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};

export const listRequirements = () => api.get<Requirement[]>('/requirements/');

export const getRequirement = (reqId: string) => api.get<Requirement>('/requirements/' + reqId);

export const updateRequirement = (reqId: string, data: Partial<Requirement>) =>
  api.put('/requirements/' + reqId, data);

// ---------------------------------------------------------------------------
// Test Cases
// ---------------------------------------------------------------------------

export const listTestCases = (params?: Record<string, string>) =>
  api.get<TestCase[]>('/test-cases/', { params: { limit: 500, ...params } });

/** List test cases for a specific pipeline run. */
export const listTestCasesByRun = (runId: string) =>
  api.get<TestCase[]>('/test-cases/', { params: { run_id: runId } });

export const getTestCase = (tcId: string) => api.get<TestCase>('/test-cases/' + tcId);

export const updateTestCase = (tcId: string, data: Partial<TestCase>) =>
  api.put('/test-cases/' + tcId, data);

export const approveTestCase = (tcId: string) => api.post('/test-cases/' + tcId + '/approve');

export const rejectTestCase = (tcId: string) => api.post('/test-cases/' + tcId + '/reject');

export const bulkApproveTestCases = (tcIds: string[], reason?: string) =>
  api.post<{ updated: string[]; not_found: string[] }>('/test-cases/bulk/approve', {
    tc_ids: tcIds,
    reason,
  });

export const bulkRejectTestCases = (tcIds: string[], reason?: string) =>
  api.post<{ updated: string[]; not_found: string[] }>('/test-cases/bulk/reject', {
    tc_ids: tcIds,
    reason,
  });

// ---------------------------------------------------------------------------
// BDD
// ---------------------------------------------------------------------------

export const listFeatures = (runId?: string) =>
  api.get<FeatureFile[]>('/bdd/features', {
    params: { limit: 500, ...(runId ? { run_id: runId } : {}) },
  });

export const getFeature = (filename: string) => api.get<FeatureFile>('/bdd/features/' + filename);

export const downloadBddProject = () => api.get('/bdd/project/download', { responseType: 'blob' });

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export const getHealth = () => api.get<HealthResponse>('/health');

// ---------------------------------------------------------------------------
// Feedback
// ---------------------------------------------------------------------------

export const submitFeedback = (data: FeedbackRequest) => api.post('/feedback/', data);

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export const getAuthStatus = () => api.get<AuthStatus>('/auth/status');

export const login = (username: string, password: string) =>
  api.post<LoginResponse>('/auth/login', { username, password });

export const listFeedback = (agentId?: string) =>
  api.get('/feedback/', { params: agentId ? { agent_id: agentId } : {} });

// ---------------------------------------------------------------------------
// Crawler / Site Model
// ---------------------------------------------------------------------------

export interface SiteModelResponse {
  base_url: string;
  total_pages: number;
  total_elements: number;
  total_forms: number;
  navigation_graph: Record<string, string[]>;
  crawl_timestamp: string;
  run_id?: string;
}

export interface PageSummary {
  url: string;
  title: string;
  element_count: number;
  form_count: number;
  link_count: number;
}

export const listCrawlerRuns = () => api.get<string[]>('/crawler/runs');

export const getSiteModel = (runId?: string) =>
  api.get<SiteModelResponse>('/crawler/site-model', { params: runId ? { run_id: runId } : {} });

export const listCrawlerPages = (runId?: string) =>
  api.get<PageSummary[]>('/crawler/pages', { params: runId ? { run_id: runId } : {} });

// ---------------------------------------------------------------------------
// API Tests
// ---------------------------------------------------------------------------

export interface ApiTestFile {
  filename: string;
  framework: string;
  language: string;
  endpoint_path: string;
  test_count: number;
  test_level: string;
  content?: string;
  run_id?: string;
}

export const listApiTests = (runId?: string) =>
  api.get<ApiTestFile[]>('/api-tests/', {
    params: { limit: 500, ...(runId ? { run_id: runId } : {}) },
  });

export const getApiTest = (filename: string) =>
  api.get<ApiTestFile>('/api-tests/' + encodeURIComponent(filename));

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

export interface ConfigResponse {
  project: Record<string, any>;
  llm: Record<string, any>;
  crawler: Record<string, any>;
  api_testing: Record<string, any>;
  test_generation: Record<string, any>;
  bdd: Record<string, any>;
  quality_gate: Record<string, any>;
  coverage: Record<string, any>;
  output: Record<string, any>;
  chromadb: Record<string, any>;
  export: Record<string, any>;
  circuit_breaker: Record<string, any>;
  metrics: Record<string, any>;
}

export interface LLMTestRequest {
  provider: string;
  model: string;
  base_url: string;
  api_key: string;
}

export interface LLMTestResponse {
  success: boolean;
  message: string;
  models: string[];
}

export const getConfig = () => api.get<ConfigResponse>('/config/');

export const updateConfig = (data: Partial<ConfigResponse>) =>
  api.put<ConfigResponse>('/config/', data);

export const testLlmConnection = (data: LLMTestRequest) =>
  api.post<LLMTestResponse>('/config/test-llm', data);

// ---------------------------------------------------------------------------
// Metrics
// ---------------------------------------------------------------------------

export interface MetricsRun {
  run_id: string;
  timestamp: string;
  pipeline_name: string;
  total_test_cases: number;
  avg_quality_score: number;
  quality_distribution: Record<string, number>;
  tokens_used: number;
  estimated_cost_usd: number;
  cache_hit_rate: number;
  generation_time_seconds: number;
  per_stage_durations: Record<string, number>;
  per_ac_type_scores: Record<string, number>;
  coverage_pct: number;
  stages_completed: number;
  stages_failed: number;
  stages_skipped: number;
}

export interface MetricsTrend {
  run_count: number;
  avg_quality_score: number;
  avg_generation_time: number;
  total_tokens: number;
  total_cost_usd: number;
  quality_trend: { run_id: string; score: number }[];
  degradation_warning?: string;
}

export const listMetrics = (lastN?: number) =>
  api.get<MetricsRun[]>('/metrics', { params: lastN ? { last_n: lastN } : {} });

export const getMetricsTrends = (lastN?: number) =>
  api.get<MetricsTrend>('/metrics/trends', { params: lastN ? { last_n: lastN } : {} });

export const getRunMetrics = (runId: string) =>
  api.get<MetricsRun>('/metrics/' + runId);

export default api;
