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
}

export interface PipelineRunSummary {
  run_id: string;
  pipeline_name: string;
  status: string;
  started_at: string;
  stages_completed_count: number;
  total_duration_seconds?: number;
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

export interface TestCase {
  tc_id: string;
  req_id: string;
  title: string;
  description: string;
  test_type: string;
  priority: string;
  category: string;
  component: string;
  given: string;
  when: string;
  then: string;
  expected_outcome: string;
  tags: string[];
  status: string;
}

export interface FeatureFile {
  filename: string;
  req_id: string;
  scenario_count: number;
  tags: string[];
  content?: string;
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

// ---------------------------------------------------------------------------
// Axios instance
// ---------------------------------------------------------------------------

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
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

export const listPipelineRuns = () =>
  api.get<PipelineRunSummary[]>('/pipeline/runs');

export const getPipelineRun = (runId: string) =>
  api.get<PipelineRunStatus>('/pipeline/runs/' + runId);

// ---------------------------------------------------------------------------
// Agents
// ---------------------------------------------------------------------------

export const listAgents = () =>
  api.get<AgentInfo[]>('/agents/');

export const getAgent = (agentId: string) =>
  api.get<AgentInfo>('/agents/' + agentId);

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

export const listRequirements = () =>
  api.get<Requirement[]>('/requirements/');

export const getRequirement = (reqId: string) =>
  api.get<Requirement>('/requirements/' + reqId);

export const updateRequirement = (reqId: string, data: Partial<Requirement>) =>
  api.put('/requirements/' + reqId, data);

// ---------------------------------------------------------------------------
// Test Cases
// ---------------------------------------------------------------------------

export const listTestCases = (params?: Record<string, string>) =>
  api.get<TestCase[]>('/test-cases/', { params });

export const getTestCase = (tcId: string) =>
  api.get<TestCase>('/test-cases/' + tcId);

export const updateTestCase = (tcId: string, data: Partial<TestCase>) =>
  api.put('/test-cases/' + tcId, data);

export const approveTestCase = (tcId: string) =>
  api.post('/test-cases/' + tcId + '/approve');

export const rejectTestCase = (tcId: string) =>
  api.post('/test-cases/' + tcId + '/reject');

// ---------------------------------------------------------------------------
// BDD
// ---------------------------------------------------------------------------

export const listFeatures = () =>
  api.get<FeatureFile[]>('/bdd/features');

export const getFeature = (filename: string) =>
  api.get<FeatureFile>('/bdd/features/' + filename);

export const downloadBddProject = () =>
  api.get('/bdd/project/download', { responseType: 'blob' });

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export const getHealth = () =>
  api.get<HealthResponse>('/health');

// ---------------------------------------------------------------------------
// Feedback
// ---------------------------------------------------------------------------

export const submitFeedback = (data: FeedbackRequest) =>
  api.post('/feedback/', data);

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
}

export interface PageSummary {
  url: string;
  title: string;
  element_count: number;
  form_count: number;
  link_count: number;
}

export const getSiteModel = () =>
  api.get<SiteModelResponse>('/crawler/site-model');

export const listCrawlerPages = () =>
  api.get<PageSummary[]>('/crawler/pages');

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
}

export const listApiTests = () =>
  api.get<ApiTestFile[]>('/api-tests/');

export const getApiTest = (filename: string) =>
  api.get<ApiTestFile>('/api-tests/' + encodeURIComponent(filename));

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

export interface ConfigResponse {
  project: Record<string, any>;
  ollama: Record<string, any>;
  output: Record<string, any>;
}

export const getConfig = () =>
  api.get<ConfigResponse>('/config/');

export const updateConfig = (data: Partial<ConfigResponse>) =>
  api.put('/config/', data);

export default api;
