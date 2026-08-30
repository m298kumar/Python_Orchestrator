import type React from 'react';
import { useState, useEffect, useCallback } from 'react';
import {
  Loader2,
  AlertCircle,
  Save,
  RotateCcw,
  ChevronDown,
  ChevronRight,
  Settings,
  Cpu,
  FolderOutput,
  CheckCircle2,
  Eye,
  EyeOff,
  Wifi,
  WifiOff,
  Check,
  X,
  Globe,
  Code,
  TestTube,
  FileText,
  ShieldCheck,
  BarChart3,
  Database,
  Zap,
  Activity,
  Download,
} from 'lucide-react';
import { getConfig, updateConfig, testLlmConnection } from '../api/client';
import type { ConfigResponse, LLMTestResponse } from '../api/client';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PROVIDER_MODELS: Record<string, string[]> = {
  ollama: [
    'qwen2.5:32b-instruct-q4_K_M',
    'nemotron-cascade-2',
    'qwen3.5:35b-a3b',
    'gpt-oss:20b',
    'qwen2.5:7b-instruct',
    'phi4-mini:3.8b',
    'llama3:8b',
    'llama3.1:8b',
    'mistral:7b',
    'codellama:7b',
    'qwen2.5:7b',
  ],
  openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-3.5-turbo', 'gpt-4-turbo'],
  anthropic: ['claude-sonnet-4-20250514', 'claude-opus-4-20250514', 'claude-haiku-4-20250514'],
  azure: ['gpt-4o', 'gpt-4o-mini', 'gpt-35-turbo'],
};

interface ProviderOption {
  id: string;
  label: string;
  emoji: string;
  description: string;
}

const PROVIDERS: ProviderOption[] = [
  {
    id: 'ollama',
    label: 'Ollama (Local)',
    emoji: '\uD83E\uDD99',
    description: 'Free, runs on your machine',
  },
  {
    id: 'openai',
    label: 'OpenAI',
    emoji: '\uD83D\uDFE2',
    description: 'GPT-4o, GPT-4o-mini',
  },
  {
    id: 'anthropic',
    label: 'Anthropic',
    emoji: '\uD83D\uDFE3',
    description: 'Claude Sonnet, Claude Opus',
  },
  {
    id: 'azure',
    label: 'Azure OpenAI',
    emoji: '\uD83D\uDD37',
    description: 'Enterprise Azure deployment',
  },
];

const PLATFORM_OPTIONS = ['web', 'mobile', 'api', 'desktop'];
const BACKEND_TYPE_OPTIONS = ['rest', 'graphql', 'grpc', 'soap'];

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------

interface ToastState {
  message: string;
  type: 'success' | 'error';
}

// ---------------------------------------------------------------------------
// Connection test result
// ---------------------------------------------------------------------------

interface ConnectionResult {
  status: 'idle' | 'testing' | 'success' | 'error';
  message: string;
  models: string[];
}

// ---------------------------------------------------------------------------
// Collapsible Section
// ---------------------------------------------------------------------------

interface CollapsibleSectionProps {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
}

function CollapsibleSection({
  title,
  icon,
  children,
  defaultOpen = false,
}: CollapsibleSectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-5 py-4 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
      >
        {open ? (
          <ChevronDown className="h-4 w-4 text-gray-400 dark:text-gray-500" />
        ) : (
          <ChevronRight className="h-4 w-4 text-gray-400 dark:text-gray-500" />
        )}
        <span className="text-gray-500 dark:text-gray-400">{icon}</span>
        <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">{title}</span>
      </button>
      {open && <div className="px-5 pb-5 border-t border-gray-100 dark:border-gray-700 pt-4 space-y-4">{children}</div>}
    </div>
  );
}

function JsonConfigEditor({
  label, value, onChange,
}: {
  label: string;
  value: unknown;
  onChange: (value: Record<string, unknown>) => void;
}) {
  const [text, setText] = useState(() => JSON.stringify(value ?? {}, null, 2));
  const [error, setError] = useState('');
  useEffect(() => setText(JSON.stringify(value ?? {}, null, 2)), [value]);
  const commit = () => {
    try {
      const parsed = JSON.parse(text);
      if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
        throw new Error('Value must be a JSON object');
      }
      onChange(parsed);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid JSON');
    }
  };
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{label}</label>
      <textarea value={text} onChange={(e) => setText(e.target.value)} onBlur={commit} rows={8}
        className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-xs font-mono focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none" />
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Password Field
// ---------------------------------------------------------------------------

function PasswordField({
  label,
  value,
  onChange,
  placeholder,
  helperText,
}: {
  label: string;
  value: string;
  onChange: (val: string) => void;
  placeholder?: string;
  helperText?: string;
}) {
  const [visible, setVisible] = useState(false);
  const isMasked = value === '***';

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{label}</label>
      <div className="relative">
        <input
          type={visible ? 'text' : 'password'}
          value={isMasked ? '' : value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={isMasked ? 'API key is set (hidden)' : placeholder}
          className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 pr-10 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
        />
        <button
          type="button"
          onClick={() => setVisible(!visible)}
          className="absolute inset-y-0 right-0 flex items-center pr-3 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
        >
          {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
      {helperText && <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">{helperText}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Model Combobox
// ---------------------------------------------------------------------------

function ModelCombobox({
  value,
  onChange,
  suggestions,
}: {
  value: string;
  onChange: (val: string) => void;
  suggestions: string[];
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const filtered = query
    ? suggestions.filter((s) => s.toLowerCase().includes(query.toLowerCase()))
    : suggestions;

  return (
    <div className="relative">
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Model</label>
       <input
         type="text"
         value={value ?? ''}
         onChange={(e) => { setQuery(e.target.value); onChange(e.target.value); }}
         onFocus={() => { setQuery(''); setOpen(true); }}
         onBlur={() => setTimeout(() => setOpen(false), 200)}
         placeholder="Select or type a model name"
         className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
       />
        {open && filtered.length > 0 && (
          <ul className="absolute z-10 mt-1 w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-md shadow-lg max-h-48 overflow-auto">
            {filtered.map((model) => (
              <li
                key={model}
                onMouseDown={() => {
                  onChange(model);
                  setQuery('');
                  setOpen(false);
                }}
                className="px-3 py-2 text-sm font-mono text-gray-900 dark:text-gray-100 cursor-pointer hover:bg-blue-50 hover:text-blue-700 dark:hover:bg-blue-900 dark:hover:text-blue-300"
              >
                {model}
              </li>
            ))}
          </ul>
        )}
      <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">Choose from the list or type a custom model name</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Config Page
// ---------------------------------------------------------------------------

export default function Config() {
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [editedConfig, setEditedConfig] = useState<ConfigResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [connectionResult, setConnectionResult] = useState<ConnectionResult>({
    status: 'idle',
    message: '',
    models: [],
  });

  // -----------------------------------------------------------------------
  // Fetch config
  // -----------------------------------------------------------------------

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getConfig();
      setConfig(res.data);
      setEditedConfig(structuredClone(res.data));
    } catch (err: any) {
      setError(err.message ?? 'Failed to load config');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  // -----------------------------------------------------------------------
  // Derived state
  // -----------------------------------------------------------------------

  const llm = editedConfig?.llm ?? {};
  const selectedProvider: string = llm.provider ?? '';

  const hasChanges =
    config && editedConfig && JSON.stringify(config) !== JSON.stringify(editedConfig);

  // -----------------------------------------------------------------------
  // Helpers
  // -----------------------------------------------------------------------

  function updateLlm(key: string, value: any) {
    if (!editedConfig) return;
    setEditedConfig({
      ...editedConfig,
      llm: { ...editedConfig.llm, [key]: value },
    });
  }

  function updateProject(key: string, value: any) {
    if (!editedConfig) return;
    setEditedConfig({
      ...editedConfig,
      project: { ...editedConfig.project, [key]: value },
    });
  }

  function updateSpecifications(key: string, value: any) {
    if (!editedConfig) return;
    setEditedConfig({
      ...editedConfig,
      specifications: { ...editedConfig.specifications, [key]: value },
    });
  }

  function updateReview(key: string, value: any) {
    if (!editedConfig) return;
    setEditedConfig({ ...editedConfig, review: { ...editedConfig.review, [key]: value } });
  }

  function updateOutput(key: string, value: any) {
    if (!editedConfig) return;
    setEditedConfig({
      ...editedConfig,
      output: { ...editedConfig.output, [key]: value },
    });
  }

  function updateCrawler(key: string, value: any) {
    if (!editedConfig) return;
    setEditedConfig({
      ...editedConfig,
      crawler: { ...editedConfig.crawler, [key]: value },
    });
  }

  function updateApiTesting(key: string, value: any) {
    if (!editedConfig) return;
    setEditedConfig({
      ...editedConfig,
      api_testing: { ...editedConfig.api_testing, [key]: value },
    });
  }

  function updateTestGeneration(key: string, value: any) {
    if (!editedConfig) return;
    setEditedConfig({
      ...editedConfig,
      test_generation: { ...editedConfig.test_generation, [key]: value },
    });
  }

  function updateBdd(key: string, value: any) {
    if (!editedConfig) return;
    setEditedConfig({
      ...editedConfig,
      bdd: { ...editedConfig.bdd, [key]: value },
    });
  }

  function updateQualityGate(key: string, value: any) {
    if (!editedConfig) return;
    setEditedConfig({
      ...editedConfig,
      quality_gate: { ...editedConfig.quality_gate, [key]: value },
    });
  }

  function updateCoverage(key: string, value: any) {
    if (!editedConfig) return;
    setEditedConfig({
      ...editedConfig,
      coverage: { ...editedConfig.coverage, [key]: value },
    });
  }

  function updateChromadb(key: string, value: any) {
    if (!editedConfig) return;
    setEditedConfig({
      ...editedConfig,
      chromadb: { ...editedConfig.chromadb, [key]: value },
    });
  }

  function updateExport(key: string, value: any) {
    if (!editedConfig) return;
    setEditedConfig({
      ...editedConfig,
      export: { ...editedConfig.export, [key]: value },
    });
  }

  function updateCircuitBreaker(key: string, value: any) {
    if (!editedConfig) return;
    setEditedConfig({
      ...editedConfig,
      circuit_breaker: { ...editedConfig.circuit_breaker, [key]: value },
    });
  }

  function updateMetrics(key: string, value: any) {
    if (!editedConfig) return;
    setEditedConfig({
      ...editedConfig,
      metrics: { ...editedConfig.metrics, [key]: value },
    });
  }

  function selectProvider(providerId: string) {
    if (!editedConfig) return;
    const newLlm: Record<string, any> = {
      ...editedConfig.llm,
      provider: providerId,
    };
    // Set sensible defaults when switching provider
    if (providerId === 'ollama') {
      newLlm.base_url = newLlm.base_url || 'http://localhost:11434';
    }
    setEditedConfig({ ...editedConfig, llm: newLlm });
    // Reset connection test when switching
    setConnectionResult({ status: 'idle', message: '', models: [] });
  }

  // -----------------------------------------------------------------------
  // Save / Reset
  // -----------------------------------------------------------------------

  async function handleSave() {
    if (!editedConfig) return;
    setSaving(true);
    try {
      // Build payload, stripping masked api_key so we never send *** back
      const payload = structuredClone(editedConfig);
      if (payload.llm?.api_key === '***' || payload.llm?.api_key === '') {
        delete payload.llm.api_key;
      }
      await updateConfig(payload);
      // Refresh from server to get the canonical state
      const res = await getConfig();
      setConfig(res.data);
      setEditedConfig(structuredClone(res.data));
      setToast({
        message: 'Configuration saved successfully.',
        type: 'success',
      });
    } catch (err: any) {
      setToast({
        message: err.message ?? 'Failed to save configuration.',
        type: 'error',
      });
    } finally {
      setSaving(false);
    }
  }

  function handleReset() {
    if (config) {
      setEditedConfig(structuredClone(config));
      setConnectionResult({ status: 'idle', message: '', models: [] });
    }
  }

  // -----------------------------------------------------------------------
  // Test connection
  // -----------------------------------------------------------------------

  async function handleTestConnection() {
    setConnectionResult({ status: 'testing', message: '', models: [] });
    try {
      const res = await testLlmConnection({
        provider: llm.provider ?? '',
        model: llm.model ?? '',
        base_url: llm.base_url ?? '',
        api_key: llm.api_key === '***' ? '' : (llm.api_key ?? ''),
      });
      const data: LLMTestResponse = res.data;
      if (data.success) {
        setConnectionResult({
          status: 'success',
          message: data.message || `Connected! ${data.models?.length ?? 0} models available`,
          models: data.models ?? [],
        });
      } else {
        setConnectionResult({
          status: 'error',
          message: data.message || 'Connection failed',
          models: [],
        });
      }
    } catch (err: any) {
      setConnectionResult({
        status: 'error',
        message: err.message ?? 'Connection test failed',
        models: [],
      });
    }
  }

  // -----------------------------------------------------------------------
  // Render: Loading / Error
  // -----------------------------------------------------------------------

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
        <span className="ml-3 text-gray-500">Loading configuration...</span>
      </div>
    );
  }

  if (error && !editedConfig) {
    return (
      <div className="flex items-center justify-center h-64 text-red-600">
        <AlertCircle className="h-6 w-6 mr-2" />
        {error}
      </div>
    );
  }

  if (!editedConfig) return null;

  // -----------------------------------------------------------------------
  // Render: Provider-specific fields
  // -----------------------------------------------------------------------

  function renderProviderFields() {
    const provider = selectedProvider;
    const models = PROVIDER_MODELS[provider] ?? [];

    return (
      <div className="space-y-4">
        {/* API Key — shown for all except ollama */}
        {provider !== 'ollama' && provider !== '' && (
          <PasswordField
            label="API Key"
            value={llm.api_key ?? ''}
            onChange={(val) => updateLlm('api_key', val)}
            placeholder={
              provider === 'openai'
                ? 'sk-...'
                : provider === 'anthropic'
                  ? 'sk-ant-...'
                  : 'Enter your API key'
            }
            helperText="Your key is stored locally and never shared."
          />
        )}

        {/* Base URL — shown for ollama and azure (required), optional for others */}
        {(provider === 'ollama' || provider === 'azure') && (
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Base URL {provider === 'azure' && <span className="text-red-500">*</span>}
            </label>
            <input
              type="text"
              value={llm.base_url ?? ''}
              onChange={(e) => updateLlm('base_url', e.target.value)}
              placeholder={
                provider === 'ollama'
                  ? 'http://localhost:11434'
                  : 'https://your-resource.openai.azure.com'
              }
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
            {provider === 'ollama' && (
              <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                Default Ollama address. Change only if you run Ollama on a different host or port.
              </p>
            )}
            {provider === 'azure' && (
              <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">Your Azure OpenAI resource endpoint URL</p>
            )}
          </div>
        )}

        {/* Model selector */}
        {provider !== '' && (
          <ModelCombobox
            value={llm.model ?? ''}
            onChange={(val) => updateLlm('model', val)}
            suggestions={models}
          />
        )}

        {/* Common fields: Temperature + Timeout */}
        {provider !== '' && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Temperature slider */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Temperature</label>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={llm.temperature ?? ''}
                  onChange={(e) => updateLlm('temperature', parseFloat(e.target.value))}
                  className="flex-1 h-2 bg-gray-200 dark:bg-gray-600 rounded-lg appearance-none cursor-pointer accent-blue-600"
                />
                <span className="text-sm font-mono text-gray-700 dark:text-gray-300 w-10 text-right">
                  {Number(llm.temperature).toFixed(2)}
                </span>
              </div>
              <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                Lower values produce more focused output; higher values are more creative.
              </p>
            </div>

            {/* Timeout */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Timeout (seconds)
              </label>
              <input
                type="number"
                min={5}
                max={600}
                value={llm.timeout ?? ''}
                onChange={(e) => updateLlm('timeout', Number(e.target.value))}
                className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
              />
              <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                Maximum time to wait for a model response.
              </p>
            </div>
          </div>
        )}

        {/* Ollama-specific: Context window + Max predict tokens */}
        {provider === 'ollama' && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Context Window (num_ctx)
              </label>
              <input
                type="number"
                min={512}
                max={131072}
                step={512}
                value={llm.num_ctx ?? ''}
                onChange={(e) => updateLlm('num_ctx', Number(e.target.value))}
                className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
              />
              <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                Number of context tokens the model can process. Larger values use more VRAM.
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Max Predict Tokens (num_predict)
              </label>
              <input
                type="number"
                min={128}
                max={32768}
                step={128}
                value={llm.num_predict ?? ''}
                onChange={(e) => updateLlm('num_predict', Number(e.target.value))}
                className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
              />
              <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                Maximum tokens in generated output. Too low = truncated test cases.
              </p>
            </div>
          </div>
        )}
      </div>
    );
  }

  // -----------------------------------------------------------------------
  // Render: Connection test UI
  // -----------------------------------------------------------------------

  function renderConnectionTest() {
    if (!selectedProvider) return null;

    return (
      <div className="pt-4 border-t border-gray-100 dark:border-gray-700">
        <div className="flex items-center gap-3 flex-wrap">
          <button
            onClick={handleTestConnection}
            disabled={connectionResult.status === 'testing'}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 transition-colors"
          >
            {connectionResult.status === 'testing' ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Wifi className="h-4 w-4" />
            )}
            Test Connection
          </button>

          {connectionResult.status === 'success' && (
            <span className="inline-flex items-center gap-1.5 text-sm text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-900/30 px-3 py-1.5 rounded-full">
              <Check className="h-4 w-4" />
              {connectionResult.message}
            </span>
          )}

          {connectionResult.status === 'error' && (
            <span className="inline-flex items-center gap-1.5 text-sm text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-900/30 px-3 py-1.5 rounded-full">
              <WifiOff className="h-4 w-4" />
              {connectionResult.message}
            </span>
          )}
        </div>

        {/* Show discovered models as clickable chips (Ollama) */}
        {connectionResult.status === 'success' &&
          selectedProvider === 'ollama' &&
          connectionResult.models.length > 0 && (
            <div className="mt-3">
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">
                Available models (click to select):
              </p>
              <div className="flex flex-wrap gap-2">
                {connectionResult.models.map((model) => (
                  <button
                    key={model}
                    onClick={() => updateLlm('model', model)}
                    className={`px-3 py-1 text-xs font-mono rounded-full border transition-colors ${
                      llm.model === model
                        ? 'bg-blue-100 dark:bg-blue-900/40 border-blue-300 dark:border-blue-600 text-blue-800 dark:text-blue-300'
                        : 'bg-gray-50 dark:bg-gray-700 border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-blue-50 dark:hover:bg-blue-900/30 hover:border-blue-200 dark:hover:border-blue-600'
                    }`}
                  >
                    {model}
                  </button>
                ))}
              </div>
            </div>
          )}
      </div>
    );
  }

  // -----------------------------------------------------------------------
  // Render: Main page
  // -----------------------------------------------------------------------

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6 pb-24">
      {/* Toast */}
      {toast && (
        <div
          className={`fixed top-4 right-4 z-50 flex items-center gap-2 px-4 py-3 rounded-lg shadow-lg text-sm font-medium transition-all ${
            toast.type === 'success'
              ? 'bg-green-50 dark:bg-green-900/40 text-green-800 dark:text-green-200 border border-green-200 dark:border-green-700'
              : 'bg-red-50 dark:bg-red-900/40 text-red-800 dark:text-red-200 border border-red-200 dark:border-red-700'
          }`}
        >
          {toast.type === 'success' ? (
            <CheckCircle2 className="h-4 w-4" />
          ) : (
            <AlertCircle className="h-4 w-4" />
          )}
          {toast.message}
          <button
            onClick={() => setToast(null)}
            className="ml-2 text-current opacity-60 hover:opacity-100"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Header + Save/Reset */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Configuration</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Set up your AI provider and project settings</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={handleReset}
            disabled={!hasChanges}
            className="flex items-center gap-2 px-4 py-2 text-sm text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <RotateCcw className="h-4 w-4" />
            Reset
          </button>
          <button
            onClick={handleSave}
            disabled={!hasChanges || saving}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save Changes
          </button>
        </div>
      </div>

      {/* ================================================================= */}
      {/* 1. LLM Provider Section                                            */}
      {/* ================================================================= */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100 dark:border-gray-700">
          <div className="flex items-center gap-3">
            <Cpu className="h-5 w-5 text-blue-600" />
            <div>
              <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">AI Provider</h2>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                Choose which LLM powers test generation and analysis
              </p>
            </div>
          </div>
        </div>

        <div className="px-5 py-5 space-y-5">
          {/* Provider cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {PROVIDERS.map((p) => {
              const isSelected = selectedProvider === p.id;
              return (
                <button
                  key={p.id}
                  onClick={() => selectProvider(p.id)}
                  className={`relative flex flex-col items-center text-center p-4 rounded-lg border-2 transition-all ${
                    isSelected
                      ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/30 shadow-sm'
                      : 'border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 hover:border-gray-300 dark:hover:border-gray-500 hover:bg-gray-50 dark:hover:bg-gray-700'
                  }`}
                >
                  {isSelected && (
                    <span className="absolute top-2 right-2">
                      <Check className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                    </span>
                  )}
                  <span className="text-2xl mb-2">{p.emoji}</span>
                  <span
                    className={`text-sm font-semibold ${
                      isSelected ? 'text-blue-900 dark:text-blue-300' : 'text-gray-900 dark:text-gray-100'
                    }`}
                  >
                    {p.label}
                  </span>
                  <span className="text-xs text-gray-500 dark:text-gray-400 mt-1">{p.description}</span>
                </button>
              );
            })}
          </div>

          {/* Provider-specific fields */}
          {selectedProvider && renderProviderFields()}

          {/* Test connection */}
          {renderConnectionTest()}
        </div>
      </div>

      {/* ================================================================= */}
      {/* 3. Project Config Section (collapsible)                            */}
      {/* ================================================================= */}
      <CollapsibleSection
        title="Project Config"
        icon={<Settings className="h-4 w-4" />}
        defaultOpen={false}
      >
        <div className="space-y-4">
          {/* Project Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Project Name</label>
            <input
              type="text"
              value={editedConfig.project?.name ?? ''}
              onChange={(e) => updateProject('name', e.target.value)}
              placeholder="My STLC Project"
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
            />
          </div>

          {/* Domain */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Domain</label>
            <input
              type="text"
              value={editedConfig.project?.domain ?? ''}
              onChange={(e) => updateProject('domain', e.target.value)}
              placeholder="e.g. e-commerce, healthcare, fintech"
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
            />
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Auto-detected from requirements if left empty.
            </p>
          </div>

          {/* Platform */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Platform</label>
            <select
              value={editedConfig.project?.platform ?? 'web'}
              onChange={(e) => updateProject('platform', e.target.value)}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            >
              {PLATFORM_OPTIONS.map((opt) => (
                <option key={opt} value={opt}>
                  {opt.charAt(0).toUpperCase() + opt.slice(1)}
                </option>
              ))}
            </select>
          </div>

          {/* Backend Type */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Backend Type</label>
            <select
              value={editedConfig.project?.backend_type ?? 'rest'}
              onChange={(e) => updateProject('backend_type', e.target.value)}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            >
              {BACKEND_TYPE_OPTIONS.map((opt) => (
                <option key={opt} value={opt}>
                  {opt.toUpperCase()}
                </option>
              ))}
            </select>
          </div>

          {/* Render remaining project fields dynamically */}
          {Object.entries(editedConfig.project ?? {})
            .filter(([key]) => !['name', 'domain', 'platform', 'backend_type'].includes(key))
            .map(([key, val]) => (
              <div key={key}>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
                </label>
                {typeof val === 'boolean' ? (
                  <button
                    onClick={() => updateProject(key, !val)}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                      val ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-600'
                    }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        val ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                ) : (
                  <input
                    type={typeof val === 'number' ? 'number' : 'text'}
                    value={typeof val === 'object' ? JSON.stringify(val) : String(val ?? '')}
                    onChange={(e) =>
                      updateProject(
                        key,
                        typeof val === 'number' ? Number(e.target.value) : e.target.value,
                      )
                    }
                    className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
                  />
                )}
              </div>
            ))}
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        title="Approved Specifications"
        icon={<ShieldCheck className="h-4 w-4" />}
        defaultOpen={false}
      >
        <div className="flex items-center justify-between">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Enforce approved specifications</label>
            <p className="text-xs text-gray-400 mt-0.5">Reject unapproved or missing generation guardrails.</p>
          </div>
          <button onClick={() => updateSpecifications('enforce', !editedConfig.specifications?.enforce)}
            className={`relative inline-flex h-6 w-11 items-center rounded-full ${editedConfig.specifications?.enforce ? 'bg-blue-600' : 'bg-gray-300'}`}>
            <span className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${editedConfig.specifications?.enforce ? 'translate-x-6' : 'translate-x-1'}`} />
          </button>
        </div>
        {(['requirements', 'test_cases', 'bdd'] as const).map((key) => (
          <div key={key}>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1 capitalize">{key.replace('_', ' ')} specification</label>
            <input type="text" value={editedConfig.specifications?.[key] ?? ''}
              onChange={(e) => updateSpecifications(key, e.target.value)}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm font-mono" />
          </div>
        ))}
      </CollapsibleSection>

      {/* ================================================================= */}
      {/* 4. Crawler / Application Under Test Section (collapsible)          */}
      {/* ================================================================= */}
      <CollapsibleSection
        title="Application Under Test"
        icon={<Globe className="h-4 w-4" />}
        defaultOpen={false}
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Base URL <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={editedConfig.crawler?.base_url ?? ''}
              onChange={(e) => updateCrawler('base_url', e.target.value)}
              placeholder="https://demo.opencart.com"
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              The URL of the web application the crawler will explore.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Max Depth</label>
            <input
              type="number"
              min={1}
              max={10}
              value={editedConfig.crawler?.max_depth ?? ''}
              onChange={(e) => updateCrawler('max_depth', Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
            />
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              How many link levels deep the crawler should navigate.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Max Pages</label>
            <input
              type="number"
              min={1}
              max={500}
              value={editedConfig.crawler?.max_pages ?? ''}
              onChange={(e) => updateCrawler('max_pages', Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
            />
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Maximum number of pages to crawl in a single run.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Rate Limit (ms)</label>
            <input
              type="number"
              min={0}
              max={10000}
              step={100}
              value={editedConfig.crawler?.rate_limit_ms ?? ''}
              onChange={(e) => updateCrawler('rate_limit_ms', Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
            />
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Delay between requests in milliseconds. Helps avoid being blocked by the target site.
            </p>
          </div>

          <div className="flex items-center justify-between">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Wait for Network Idle</label>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Wait until no network activity before parsing each page (recommended for SPAs).</p>
            </div>
            <button
              onClick={() => updateCrawler('wait_for_network_idle', !(editedConfig.crawler?.wait_for_network_idle ?? true))}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                editedConfig.crawler?.wait_for_network_idle !== false ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-600'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  editedConfig.crawler?.wait_for_network_idle !== false ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Navigation Timeout (ms)</label>
            <input type="number" min={1000} value={editedConfig.crawler?.timeout_ms ?? ''}
              onChange={(e) => updateCrawler('timeout_ms', Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm" />
          </div>

          <div className="flex items-center justify-between">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Verify TLS certificates</label>
              <p className="text-xs text-gray-400 mt-0.5">Disable only for controlled test environments.</p>
            </div>
            <button onClick={() => updateCrawler('verify_ssl', !editedConfig.crawler?.verify_ssl)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full ${editedConfig.crawler?.verify_ssl ? 'bg-blue-600' : 'bg-gray-300'}`}>
              <span className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${editedConfig.crawler?.verify_ssl ? 'translate-x-6' : 'translate-x-1'}`} />
            </button>
          </div>

          <div className="flex items-center justify-between">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Respect robots.txt</label>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Honor the site's robots.txt crawl restrictions.</p>
            </div>
            <button
              onClick={() => updateCrawler('respect_robots_txt', !(editedConfig.crawler?.respect_robots_txt ?? true))}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                editedConfig.crawler?.respect_robots_txt !== false ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-600'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  editedConfig.crawler?.respect_robots_txt !== false ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>
        </div>
      </CollapsibleSection>

      {/* ================================================================= */}
      {/* 5. API Testing Section (collapsible)                               */}
      {/* ================================================================= */}
      <CollapsibleSection
        title="API Testing"
        icon={<Code className="h-4 w-4" />}
        defaultOpen={false}
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Framework</label>
            <input
              type="text"
              value={editedConfig.api_testing?.framework ?? 'pytest_requests'}
              onChange={(e) => updateApiTesting('framework', e.target.value)}
              placeholder="pytest_requests"
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Test framework for generated API tests.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">API Base URL</label>
            <input
              type="text"
              value={editedConfig.api_testing?.base_url ?? ''}
              onChange={(e) => updateApiTesting('base_url', e.target.value)}
              placeholder="https://api.example.com"
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Base URL for API test execution. Leave empty to auto-detect from requirements.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">OpenAPI Spec Path / URL</label>
            <input
              type="text"
              value={editedConfig.api_testing?.openapi_spec ?? ''}
              onChange={(e) => updateApiTesting('openapi_spec', e.target.value)}
              placeholder="./specs/openapi.json or https://api.example.com/openapi.json"
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Local file path (./specs/openapi.json) or HTTP URL to an OpenAPI 3.x / Swagger 2.0 spec (JSON or YAML).
              Leave empty to skip API test generation — the discover_apis stage will be cleanly bypassed.
            </p>
          </div>
        </div>
      </CollapsibleSection>

      {/* ================================================================= */}
      {/* 6. Crawler Auth Section (collapsible)                              */}
      {/* ================================================================= */}
      <CollapsibleSection
        title="Crawler Authentication"
        icon={<ShieldCheck className="h-4 w-4" />}
        defaultOpen={false}
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Auth Type</label>
            <input
              type="text"
              value={editedConfig.crawler?.auth?.type ?? ''}
              onChange={(e) => updateCrawler('auth', { ...editedConfig.crawler?.auth, type: e.target.value })}
              placeholder="basic, form, cookie"
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Authentication method for crawling protected pages.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Login URL</label>
            <input
              type="text"
              value={editedConfig.crawler?.auth?.login_url ?? ''}
              onChange={(e) => updateCrawler('auth', { ...editedConfig.crawler?.auth, login_url: e.target.value })}
              placeholder="https://demo.opencart.com/admin"
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Username</label>
            <input
              type="text"
              value={editedConfig.crawler?.auth?.username ?? ''}
              onChange={(e) => updateCrawler('auth', { ...editedConfig.crawler?.auth, username: e.target.value })}
              placeholder="admin"
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
            />
          </div>

          <PasswordField
            label="Password"
            value={editedConfig.crawler?.auth?.password ?? ''}
            onChange={(val) => updateCrawler('auth', { ...editedConfig.crawler?.auth, password: val })}
            placeholder="Crawler password"
            helperText="Used to authenticate when crawling protected pages."
          />
        </div>
      </CollapsibleSection>

      {/* ================================================================= */}
      {/* 7. Test Generation Section (collapsible)                           */}
      {/* ================================================================= */}
      <CollapsibleSection
        title="Test Generation"
        icon={<TestTube className="h-4 w-4" />}
        defaultOpen={false}
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Max Tests Per Requirement</label>
            <input
              type="number"
              min={1}
              max={20}
              value={editedConfig.test_generation?.max_per_requirement ?? ''}
              onChange={(e) => updateTestGeneration('max_per_requirement', Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
            />
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Maximum number of test cases generated per requirement.
            </p>
          </div>

          <div className="flex items-center justify-between">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Include Negative Tests</label>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Generate tests for invalid inputs and error paths.</p>
            </div>
            <button
              onClick={() => updateTestGeneration('include_negative', !(editedConfig.test_generation?.include_negative ?? true))}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                editedConfig.test_generation?.include_negative !== false ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-600'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  editedConfig.test_generation?.include_negative !== false ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>

          <div className="flex items-center justify-between">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Include Edge Cases</label>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Generate boundary and corner-case tests.</p>
            </div>
            <button
              onClick={() => updateTestGeneration('include_edge_cases', !(editedConfig.test_generation?.include_edge_cases ?? true))}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                editedConfig.test_generation?.include_edge_cases !== false ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-600'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  editedConfig.test_generation?.include_edge_cases !== false ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Format</label>
            <input
              type="text"
              value={editedConfig.test_generation?.format ?? ''}
              onChange={(e) => updateTestGeneration('format', e.target.value)}
              placeholder="gherkin"
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
          </div>
          <JsonConfigEditor label="Acceptance-criterion types" value={editedConfig.test_generation?.ac_types}
            onChange={(value) => updateTestGeneration('ac_types', value)} />
          <JsonConfigEditor label="Domain keywords" value={editedConfig.test_generation?.domain_keywords}
            onChange={(value) => updateTestGeneration('domain_keywords', value)} />
          <JsonConfigEditor label="Sanitiser rules" value={editedConfig.test_generation?.sanitiser}
            onChange={(value) => updateTestGeneration('sanitiser', value)} />
          <JsonConfigEditor label="Component suffix map" value={editedConfig.test_generation?.component_suffix_map}
            onChange={(value) => updateTestGeneration('component_suffix_map', value)} />
        </div>
      </CollapsibleSection>

      {/* ================================================================= */}
      {/* 8. BDD Settings Section (collapsible)                              */}
      {/* ================================================================= */}
      <CollapsibleSection
        title="BDD Settings"
        icon={<FileText className="h-4 w-4" />}
        defaultOpen={false}
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Language</label>
            <input
              type="text"
              value={editedConfig.bdd?.language ?? ''}
              onChange={(e) => updateBdd('language', e.target.value)}
              placeholder="python"
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Framework</label>
            <input
              type="text"
              value={editedConfig.bdd?.framework ?? ''}
              onChange={(e) => updateBdd('framework', e.target.value)}
              placeholder="behave"
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Automation Library</label>
            <input
              type="text"
              value={editedConfig.bdd?.automation_lib ?? ''}
              onChange={(e) => updateBdd('automation_lib', e.target.value)}
              placeholder="playwright"
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Page Object Language</label>
            <input type="text" value={editedConfig.bdd?.pom_language ?? ''}
              onChange={(e) => updateBdd('pom_language', e.target.value)}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm font-mono" />
          </div>
        </div>
      </CollapsibleSection>

      {/* ================================================================= */}
      {/* 9. Quality Gate Section (collapsible)                              */}
      {/* ================================================================= */}
      <CollapsibleSection
        title="Quality Gate"
        icon={<ShieldCheck className="h-4 w-4" />}
        defaultOpen={false}
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Accept Threshold</label>
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={editedConfig.quality_gate?.accept_threshold ?? ''}
              onChange={(e) => updateQualityGate('accept_threshold', Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Minimum quality score to auto-approve tests (0-1).
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Regenerate Threshold</label>
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={editedConfig.quality_gate?.regenerate_threshold ?? 0.4}
              onChange={(e) => updateQualityGate('regenerate_threshold', parseFloat(e.target.value) || 0.4)}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Score below which tests are regenerated (0-1).
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Max Regeneration Attempts</label>
            <input
              type="number"
              min={1}
              max={5}
              value={editedConfig.quality_gate?.max_regeneration_attempts ?? 2}
              onChange={(e) => updateQualityGate('max_regeneration_attempts', parseInt(e.target.value, 10) || 2)}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Auto Example Threshold</label>
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={editedConfig.quality_gate?.auto_example_threshold ?? 0.8}
              onChange={(e) => updateQualityGate('auto_example_threshold', parseFloat(e.target.value) || 0.8)}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Score above which generated tests are auto-stored as good examples for future runs (0-1).
            </p>
          </div>

          {/* Quality Gate Weights */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Scoring Weights</label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {['coverage', 'clarity', 'executability', 'uniqueness', 'structural'].map((w) => (
                <div key={w}>
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                    {w.charAt(0).toUpperCase() + w.slice(1)}
                  </label>
                  <input
                    type="number"
                    min={0}
                    max={1}
                    step={0.05}
                    value={editedConfig.quality_gate?.weights?.[w] ?? 0.2}
                    onChange={(e) =>
                      updateQualityGate('weights', {
                        ...editedConfig.quality_gate?.weights,
                        [w]: parseFloat(e.target.value) || 0.2,
                      })
                    }
                    className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-1.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
                  />
                </div>
              ))}
            </div>
            <p className="mt-2 text-xs text-gray-400 dark:text-gray-500">
              Weights for quality scoring dimensions. Should sum to 1.0.
            </p>
          </div>
        </div>
      </CollapsibleSection>

      {/* ================================================================= */}
      {/* 10. Coverage Section (collapsible)                                 */}
      {/* ================================================================= */}
      <CollapsibleSection
        title="Coverage"
        icon={<BarChart3 className="h-4 w-4" />}
        defaultOpen={false}
      >
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Auto-Fill Gaps</label>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Automatically generate tests for uncovered requirements.</p>
            </div>
            <button
              onClick={() => updateCoverage('auto_fill_gaps', !editedConfig.coverage?.auto_fill_gaps)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                editedConfig.coverage?.auto_fill_gaps ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-600'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  editedConfig.coverage?.auto_fill_gaps ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Weak Quality Threshold</label>
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={editedConfig.coverage?.weak_quality_threshold ?? 0.5}
              onChange={(e) => updateCoverage('weak_quality_threshold', parseFloat(e.target.value) || 0.5)}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Score below which tests are flagged as weak (0-1).
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Min Coverage Types</label>
            <input
              type="number"
              min={1}
              max={10}
              value={editedConfig.coverage?.min_coverage_types ?? 1}
              onChange={(e) => updateCoverage('min_coverage_types', parseInt(e.target.value, 10) || 1)}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
            />
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Minimum number of test types (positive, negative, edge) required per requirement.
            </p>
          </div>
        </div>
      </CollapsibleSection>

      {/* ================================================================= */}
      {/* 11. ChromaDB / Embeddings Section (collapsible)                     */}
      {/* ================================================================= */}
      <CollapsibleSection
        title="ChromaDB / Embeddings"
        icon={<Database className="h-4 w-4" />}
        defaultOpen={false}
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Persist Directory</label>
            <input
              type="text"
              value={editedConfig.chromadb?.persist_directory ?? ''}
              onChange={(e) => updateChromadb('persist_directory', e.target.value)}
              placeholder="./chroma_db"
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Collection Name</label>
            <input
              type="text"
              value={editedConfig.chromadb?.collection_name ?? 'requirements'}
              onChange={(e) => updateChromadb('collection_name', e.target.value)}
              placeholder="requirements"
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Embedding Backend</label>
            <select
              value={editedConfig.chromadb?.embedding_backend ?? 'ollama'}
              onChange={(e) => updateChromadb('embedding_backend', e.target.value)}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            >
              <option value="ollama">Ollama</option>
              <option value="sentence_transformer">Sentence Transformer</option>
            </select>
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Backend for generating text embeddings used in semantic search.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Ollama Embedding Model</label>
            <input
              type="text"
              value={editedConfig.chromadb?.ollama_embedding_model ?? 'qwen3-embedding:0.6b'}
              onChange={(e) => updateChromadb('ollama_embedding_model', e.target.value)}
              placeholder="qwen3-embedding:0.6b"
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Ollama Embedding URL</label>
            <input
              type="text"
              value={editedConfig.chromadb?.ollama_embedding_url ?? 'http://localhost:11434/api/embeddings'}
              onChange={(e) => updateChromadb('ollama_embedding_url', e.target.value)}
              placeholder="http://localhost:11434/api/embeddings"
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Sentence Transformer Model</label>
            <input
              type="text"
              value={editedConfig.chromadb?.sentence_transformer_model ?? 'all-MiniLM-L6-v2'}
              onChange={(e) => updateChromadb('sentence_transformer_model', e.target.value)}
              placeholder="all-MiniLM-L6-v2"
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Used when embedding backend is set to sentence_transformer.
            </p>
          </div>
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        title="Human Review Storage"
        icon={<Database className="h-4 w-4" />}
        defaultOpen={false}
      >
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">SQLite audit database path</label>
          <input type="text" value={editedConfig.review?.sqlite_path ?? ''}
            onChange={(e) => updateReview('sqlite_path', e.target.value)}
            className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm font-mono" />
          <p className="mt-1 text-xs text-gray-400">Relative paths are resolved from the project root. A backend restart is required after changing this path.</p>
        </div>
      </CollapsibleSection>

      {/* ================================================================= */}
      {/* 12. Export Section (collapsible)                                    */}
      {/* ================================================================= */}
      <CollapsibleSection
        title="Export Settings"
        icon={<Download className="h-4 w-4" />}
        defaultOpen={false}
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Output Directory</label>
            <input
              type="text"
              value={editedConfig.export?.output_dir ?? './output'}
              onChange={(e) => updateExport('output_dir', e.target.value)}
              placeholder="./output"
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Export Formats</label>
            <div className="flex flex-wrap gap-3">
              {['csv', 'json', 'zephyr'].map((fmt) => {
                const formats: string[] = editedConfig.export?.formats ?? ['csv', 'zephyr', 'json'];
                const isChecked = formats.includes(fmt);
                return (
                  <label key={fmt} className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => {
                        const updated = isChecked ? formats.filter((f: string) => f !== fmt) : [...formats, fmt];
                        updateExport('formats', updated);
                      }}
                      className="rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
                    />
                    {fmt.toUpperCase()}
                  </label>
                );
              })}
            </div>
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Select which export formats to generate after a pipeline run.
            </p>
          </div>

          <div className="border-t border-gray-100 dark:border-gray-700 pt-4">
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">Zephyr Integration</h4>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Project Key</label>
                <input
                  type="text"
                  value={editedConfig.export?.zephyr?.project_key ?? 'PROJ'}
                  onChange={(e) => updateExport('zephyr', { ...editedConfig.export?.zephyr, project_key: e.target.value })}
                  placeholder="PROJ"
                  className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Folder Prefix</label>
                <input
                  type="text"
                  value={editedConfig.export?.zephyr?.folder_prefix ?? 'Generated Tests'}
                  onChange={(e) => updateExport('zephyr', { ...editedConfig.export?.zephyr, folder_prefix: e.target.value })}
                  placeholder="Generated Tests"
                  className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Default Status</label>
                <select
                  value={editedConfig.export?.zephyr?.default_status ?? 'Draft'}
                  onChange={(e) => updateExport('zephyr', { ...editedConfig.export?.zephyr, default_status: e.target.value })}
                  className="w-full rounded-md border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                >
                  <option value="Draft">Draft</option>
                  <option value="Approved">Approved</option>
                  <option value="Deprecated">Deprecated</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Default Labels</label>
                <input
                  type="text"
                  value={editedConfig.export?.zephyr?.default_labels ?? 'automated,generated'}
                  onChange={(e) => updateExport('zephyr', { ...editedConfig.export?.zephyr, default_labels: e.target.value })}
                  placeholder="automated,generated"
                  className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
                />
                <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">Comma-separated labels applied to exported tests.</p>
              </div>
            </div>
          </div>
        </div>
      </CollapsibleSection>

      {/* ================================================================= */}
      {/* 13. Circuit Breaker Section (collapsible)                           */}
      {/* ================================================================= */}
      <CollapsibleSection
        title="Circuit Breaker"
        icon={<Zap className="h-4 w-4" />}
        defaultOpen={false}
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Failure Threshold</label>
            <input
              type="number"
              min={1}
              max={20}
              value={editedConfig.circuit_breaker?.threshold ?? 3}
              onChange={(e) => updateCircuitBreaker('threshold', parseInt(e.target.value, 10) || 3)}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
            />
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Number of consecutive failures before the circuit breaker opens and stops retrying.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Reset Timeout (seconds)</label>
            <input
              type="number"
              min={5}
              max={600}
              value={editedConfig.circuit_breaker?.reset_timeout ?? 60}
              onChange={(e) => updateCircuitBreaker('reset_timeout', parseFloat(e.target.value) || 60)}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
            />
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Time in seconds before a tripped circuit breaker allows retry attempts.
            </p>
          </div>
        </div>
      </CollapsibleSection>

      {/* ================================================================= */}
      {/* 14. Metrics Section (collapsible)                                   */}
      {/* ================================================================= */}
      <CollapsibleSection
        title="Metrics"
        icon={<Activity className="h-4 w-4" />}
        defaultOpen={false}
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Metrics Directory</label>
            <input
              type="text"
              value={editedConfig.metrics?.dir ?? 'output/metrics'}
              onChange={(e) => updateMetrics('dir', e.target.value)}
              placeholder="output/metrics"
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Directory where pipeline run metrics are stored.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Degradation Threshold (%)</label>
            <input
              type="number"
              min={1}
              max={100}
              step={0.5}
              value={editedConfig.metrics?.degradation_threshold_pct ?? 15}
              onChange={(e) => updateMetrics('degradation_threshold_pct', parseFloat(e.target.value) || 15)}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
            />
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Percentage drop in quality score that triggers a degradation warning.
            </p>
          </div>
        </div>
      </CollapsibleSection>

      {/* ================================================================= */}
      {/* 15. Output Config Section (collapsible)                             */}
      {/* ================================================================= */}
      <CollapsibleSection
        title="Output Config"
        icon={<FolderOutput className="h-4 w-4" />}
        defaultOpen={false}
      >
        <div className="space-y-4">
          {Object.entries(editedConfig.output ?? {}).map(([key, val]) => (
            <div key={key}>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
              </label>
              {typeof val === 'boolean' ? (
                <button
                  onClick={() => updateOutput(key, !val)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    val ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-600'
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      val ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              ) : (
                <input
                  type={typeof val === 'number' ? 'number' : 'text'}
                  value={typeof val === 'object' ? JSON.stringify(val) : String(val ?? '')}
                  onChange={(e) =>
                    updateOutput(
                      key,
                      typeof val === 'number' ? Number(e.target.value) : e.target.value,
                    )
                  }
                  className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
                />
              )}
            </div>
          ))}
          {Object.keys(editedConfig.output ?? {}).length === 0 && (
            <p className="text-sm text-gray-400 dark:text-gray-500 italic">
              No output configuration fields available.
            </p>
          )}
        </div>
      </CollapsibleSection>

      {/* ================================================================= */}
      {/* 4. Sticky bottom save bar (visible when changes exist)             */}
      {/* ================================================================= */}
      {hasChanges && (
        <div className="fixed bottom-0 left-64 right-0 bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 px-6 py-3 flex items-center justify-between shadow-lg z-40">
          <span className="text-sm text-gray-600 dark:text-gray-300">You have unsaved changes.</span>
          <div className="flex gap-3">
            <button
              onClick={handleReset}
              className="flex items-center gap-2 px-4 py-2 text-sm text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            >
              <RotateCcw className="h-4 w-4" />
              Reset
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-2 px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              Save Changes
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
