import { useState, useEffect, useCallback } from "react";
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
} from "lucide-react";
import {
  getConfig,
  updateConfig,
  testLlmConnection,
} from "../api/client";
import type { ConfigResponse, LLMTestResponse } from "../api/client";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PROVIDER_MODELS: Record<string, string[]> = {
  ollama: [
    "qwen2.5:32b-instruct-q4_K_M",
    "nemotron-cascade-2",
    "qwen3.5:35b-a3b",
    "gpt-oss:20b",
    "qwen2.5:7b-instruct",
    "phi4-mini:3.8b",
    "llama3:8b",
    "llama3.1:8b",
    "mistral:7b",
    "codellama:7b",
    "qwen2.5:7b",
  ],
  openai: ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo", "gpt-4-turbo"],
  anthropic: [
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
    "claude-haiku-4-20250514",
  ],
  azure: ["gpt-4o", "gpt-4o-mini", "gpt-35-turbo"],
};

interface ProviderOption {
  id: string;
  label: string;
  emoji: string;
  description: string;
}

const PROVIDERS: ProviderOption[] = [
  {
    id: "ollama",
    label: "Ollama (Local)",
    emoji: "\uD83E\uDD99",
    description: "Free, runs on your machine",
  },
  {
    id: "openai",
    label: "OpenAI",
    emoji: "\uD83D\uDFE2",
    description: "GPT-4o, GPT-4o-mini",
  },
  {
    id: "anthropic",
    label: "Anthropic",
    emoji: "\uD83D\uDFE3",
    description: "Claude Sonnet, Claude Opus",
  },
  {
    id: "azure",
    label: "Azure OpenAI",
    emoji: "\uD83D\uDD37",
    description: "Enterprise Azure deployment",
  },
];

const PLATFORM_OPTIONS = ["web", "mobile", "api", "desktop"];
const BACKEND_TYPE_OPTIONS = ["rest", "graphql", "grpc", "soap"];

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------

interface ToastState {
  message: string;
  type: "success" | "error";
}

// ---------------------------------------------------------------------------
// Connection test result
// ---------------------------------------------------------------------------

interface ConnectionResult {
  status: "idle" | "testing" | "success" | "error";
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
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-5 py-4 hover:bg-gray-50 transition-colors"
      >
        {open ? (
          <ChevronDown className="h-4 w-4 text-gray-400" />
        ) : (
          <ChevronRight className="h-4 w-4 text-gray-400" />
        )}
        <span className="text-gray-500">{icon}</span>
        <span className="text-sm font-semibold text-gray-900">{title}</span>
      </button>
      {open && (
        <div className="px-5 pb-5 border-t border-gray-100 pt-4 space-y-4">
          {children}
        </div>
      )}
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
  const isMasked = value === "***";

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {label}
      </label>
      <div className="relative">
        <input
          type={visible ? "text" : "password"}
          value={isMasked ? "" : value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={isMasked ? "API key is set (hidden)" : placeholder}
          className="w-full rounded-md border border-gray-300 px-3 py-2 pr-10 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
        />
        <button
          type="button"
          onClick={() => setVisible(!visible)}
          className="absolute inset-y-0 right-0 flex items-center pr-3 text-gray-400 hover:text-gray-600"
        >
          {visible ? (
            <EyeOff className="h-4 w-4" />
          ) : (
            <Eye className="h-4 w-4" />
          )}
        </button>
      </div>
      {helperText && (
        <p className="mt-1 text-xs text-gray-400">{helperText}</p>
      )}
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
  const filtered = suggestions.filter((s) =>
    s.toLowerCase().includes((value ?? "").toLowerCase())
  );

  return (
    <div className="relative">
      <label className="block text-sm font-medium text-gray-700 mb-1">
        Model
      </label>
      <input
        type="text"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 200)}
        placeholder="Select or type a model name"
        className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
      />
      {open && filtered.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg max-h-48 overflow-auto">
          {filtered.map((model) => (
            <li
              key={model}
              onMouseDown={() => {
                onChange(model);
                setOpen(false);
              }}
              className="px-3 py-2 text-sm font-mono cursor-pointer hover:bg-blue-50 hover:text-blue-700"
            >
              {model}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-1 text-xs text-gray-400">
        Choose from the list or type a custom model name
      </p>
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
    status: "idle",
    message: "",
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
      setError(err.message ?? "Failed to load config");
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
  const selectedProvider: string = llm.provider ?? "";

  const hasChanges =
    config &&
    editedConfig &&
    JSON.stringify(config) !== JSON.stringify(editedConfig);

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

  function updateOutput(key: string, value: any) {
    if (!editedConfig) return;
    setEditedConfig({
      ...editedConfig,
      output: { ...editedConfig.output, [key]: value },
    });
  }

  function selectProvider(providerId: string) {
    if (!editedConfig) return;
    const newLlm: Record<string, any> = {
      ...editedConfig.llm,
      provider: providerId,
    };
    // Set sensible defaults when switching provider
    if (providerId === "ollama") {
      newLlm.base_url = newLlm.base_url || "http://localhost:11434";
    }
    setEditedConfig({ ...editedConfig, llm: newLlm });
    // Reset connection test when switching
    setConnectionResult({ status: "idle", message: "", models: [] });
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
      if (payload.llm?.api_key === "***" || payload.llm?.api_key === "") {
        delete payload.llm.api_key;
      }
      await updateConfig(payload);
      // Refresh from server to get the canonical state
      const res = await getConfig();
      setConfig(res.data);
      setEditedConfig(structuredClone(res.data));
      setToast({
        message: "Configuration saved successfully.",
        type: "success",
      });
    } catch (err: any) {
      setToast({
        message: err.message ?? "Failed to save configuration.",
        type: "error",
      });
    } finally {
      setSaving(false);
    }
  }

  function handleReset() {
    if (config) {
      setEditedConfig(structuredClone(config));
      setConnectionResult({ status: "idle", message: "", models: [] });
    }
  }

  // -----------------------------------------------------------------------
  // Test connection
  // -----------------------------------------------------------------------

  async function handleTestConnection() {
    setConnectionResult({ status: "testing", message: "", models: [] });
    try {
      const res = await testLlmConnection({
        provider: llm.provider ?? "",
        model: llm.model ?? "",
        base_url: llm.base_url ?? "",
        api_key: llm.api_key === "***" ? "" : llm.api_key ?? "",
      });
      const data: LLMTestResponse = res.data;
      if (data.success) {
        setConnectionResult({
          status: "success",
          message: data.message || `Connected! ${data.models?.length ?? 0} models available`,
          models: data.models ?? [],
        });
      } else {
        setConnectionResult({
          status: "error",
          message: data.message || "Connection failed",
          models: [],
        });
      }
    } catch (err: any) {
      setConnectionResult({
        status: "error",
        message: err.message ?? "Connection test failed",
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
        {provider !== "ollama" && provider !== "" && (
          <PasswordField
            label="API Key"
            value={llm.api_key ?? ""}
            onChange={(val) => updateLlm("api_key", val)}
            placeholder={
              provider === "openai"
                ? "sk-..."
                : provider === "anthropic"
                ? "sk-ant-..."
                : "Enter your API key"
            }
            helperText="Your key is stored locally and never shared."
          />
        )}

        {/* Base URL — shown for ollama and azure (required), optional for others */}
        {(provider === "ollama" || provider === "azure") && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Base URL {provider === "azure" && <span className="text-red-500">*</span>}
            </label>
            <input
              type="text"
              value={llm.base_url ?? ""}
              onChange={(e) => updateLlm("base_url", e.target.value)}
              placeholder={
                provider === "ollama"
                  ? "http://localhost:11434"
                  : "https://your-resource.openai.azure.com"
              }
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
            {provider === "ollama" && (
              <p className="mt-1 text-xs text-gray-400">
                Default Ollama address. Change only if you run Ollama on a
                different host or port.
              </p>
            )}
            {provider === "azure" && (
              <p className="mt-1 text-xs text-gray-400">
                Your Azure OpenAI resource endpoint URL
              </p>
            )}
          </div>
        )}

        {/* Model selector */}
        {provider !== "" && (
          <ModelCombobox
            value={llm.model ?? ""}
            onChange={(val) => updateLlm("model", val)}
            suggestions={models}
          />
        )}

        {/* Common fields: Temperature + Timeout */}
        {provider !== "" && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Temperature slider */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Temperature
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={llm.temperature ?? 0.7}
                  onChange={(e) =>
                    updateLlm("temperature", parseFloat(e.target.value))
                  }
                  className="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
                />
                <span className="text-sm font-mono text-gray-700 w-10 text-right">
                  {(llm.temperature ?? 0.7).toFixed(2)}
                </span>
              </div>
              <p className="mt-1 text-xs text-gray-400">
                Lower values produce more focused output; higher values are more
                creative.
              </p>
            </div>

            {/* Timeout */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Timeout (seconds)
              </label>
              <input
                type="number"
                min={5}
                max={600}
                value={llm.timeout ?? 120}
                onChange={(e) =>
                  updateLlm("timeout", parseInt(e.target.value, 10) || 120)
                }
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
              />
              <p className="mt-1 text-xs text-gray-400">
                Maximum time to wait for a model response.
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
      <div className="pt-4 border-t border-gray-100">
        <div className="flex items-center gap-3 flex-wrap">
          <button
            onClick={handleTestConnection}
            disabled={connectionResult.status === "testing"}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            {connectionResult.status === "testing" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Wifi className="h-4 w-4" />
            )}
            Test Connection
          </button>

          {connectionResult.status === "success" && (
            <span className="inline-flex items-center gap-1.5 text-sm text-green-700 bg-green-50 px-3 py-1.5 rounded-full">
              <Check className="h-4 w-4" />
              {connectionResult.message}
            </span>
          )}

          {connectionResult.status === "error" && (
            <span className="inline-flex items-center gap-1.5 text-sm text-red-700 bg-red-50 px-3 py-1.5 rounded-full">
              <WifiOff className="h-4 w-4" />
              {connectionResult.message}
            </span>
          )}
        </div>

        {/* Show discovered models as clickable chips (Ollama) */}
        {connectionResult.status === "success" &&
          selectedProvider === "ollama" &&
          connectionResult.models.length > 0 && (
            <div className="mt-3">
              <p className="text-xs font-medium text-gray-500 mb-2">
                Available models (click to select):
              </p>
              <div className="flex flex-wrap gap-2">
                {connectionResult.models.map((model) => (
                  <button
                    key={model}
                    onClick={() => updateLlm("model", model)}
                    className={`px-3 py-1 text-xs font-mono rounded-full border transition-colors ${
                      llm.model === model
                        ? "bg-blue-100 border-blue-300 text-blue-800"
                        : "bg-gray-50 border-gray-200 text-gray-600 hover:bg-blue-50 hover:border-blue-200"
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
            toast.type === "success"
              ? "bg-green-50 text-green-800 border border-green-200"
              : "bg-red-50 text-red-800 border border-red-200"
          }`}
        >
          {toast.type === "success" ? (
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
          <h1 className="text-2xl font-bold text-gray-900">Configuration</h1>
          <p className="text-sm text-gray-500 mt-1">
            Set up your AI provider and project settings
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={handleReset}
            disabled={!hasChanges}
            className="flex items-center gap-2 px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <RotateCcw className="h-4 w-4" />
            Reset
          </button>
          <button
            onClick={handleSave}
            disabled={!hasChanges || saving}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            Save Changes
          </button>
        </div>
      </div>

      {/* ================================================================= */}
      {/* 1. LLM Provider Section                                            */}
      {/* ================================================================= */}
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <Cpu className="h-5 w-5 text-blue-600" />
            <div>
              <h2 className="text-base font-semibold text-gray-900">
                AI Provider
              </h2>
              <p className="text-xs text-gray-500 mt-0.5">
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
                      ? "border-blue-500 bg-blue-50 shadow-sm"
                      : "border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50"
                  }`}
                >
                  {isSelected && (
                    <span className="absolute top-2 right-2">
                      <Check className="h-4 w-4 text-blue-600" />
                    </span>
                  )}
                  <span className="text-2xl mb-2">{p.emoji}</span>
                  <span
                    className={`text-sm font-semibold ${
                      isSelected ? "text-blue-900" : "text-gray-900"
                    }`}
                  >
                    {p.label}
                  </span>
                  <span className="text-xs text-gray-500 mt-1">
                    {p.description}
                  </span>
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
      {/* 2. Project Config Section (collapsible)                            */}
      {/* ================================================================= */}
      <CollapsibleSection
        title="Project Config"
        icon={<Settings className="h-4 w-4" />}
        defaultOpen={false}
      >
        <div className="space-y-4">
          {/* Project Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Project Name
            </label>
            <input
              type="text"
              value={editedConfig.project?.name ?? ""}
              onChange={(e) => updateProject("name", e.target.value)}
              placeholder="My STLC Project"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
            />
          </div>

          {/* Domain */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Domain
            </label>
            <input
              type="text"
              value={editedConfig.project?.domain ?? ""}
              onChange={(e) => updateProject("domain", e.target.value)}
              placeholder="e.g. e-commerce, healthcare, fintech"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
            />
            <p className="mt-1 text-xs text-gray-400">
              Auto-detected from requirements if left empty.
            </p>
          </div>

          {/* Platform */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Platform
            </label>
            <select
              value={editedConfig.project?.platform ?? "web"}
              onChange={(e) => updateProject("platform", e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none bg-white"
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
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Backend Type
            </label>
            <select
              value={editedConfig.project?.backend_type ?? "rest"}
              onChange={(e) => updateProject("backend_type", e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none bg-white"
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
            .filter(
              ([key]) =>
                !["name", "domain", "platform", "backend_type"].includes(key)
            )
            .map(([key, val]) => (
              <div key={key}>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {key
                    .replace(/_/g, " ")
                    .replace(/\b\w/g, (c) => c.toUpperCase())}
                </label>
                {typeof val === "boolean" ? (
                  <button
                    onClick={() => updateProject(key, !val)}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                      val ? "bg-blue-600" : "bg-gray-300"
                    }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        val ? "translate-x-6" : "translate-x-1"
                      }`}
                    />
                  </button>
                ) : (
                  <input
                    type={typeof val === "number" ? "number" : "text"}
                    value={
                      typeof val === "object"
                        ? JSON.stringify(val)
                        : String(val ?? "")
                    }
                    onChange={(e) =>
                      updateProject(
                        key,
                        typeof val === "number"
                          ? Number(e.target.value)
                          : e.target.value
                      )
                    }
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
                  />
                )}
              </div>
            ))}
        </div>
      </CollapsibleSection>

      {/* ================================================================= */}
      {/* 3. Output Config Section (collapsible)                             */}
      {/* ================================================================= */}
      <CollapsibleSection
        title="Output Config"
        icon={<FolderOutput className="h-4 w-4" />}
        defaultOpen={false}
      >
        <div className="space-y-4">
          {Object.entries(editedConfig.output ?? {}).map(([key, val]) => (
            <div key={key}>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {key
                  .replace(/_/g, " ")
                  .replace(/\b\w/g, (c) => c.toUpperCase())}
              </label>
              {typeof val === "boolean" ? (
                <button
                  onClick={() => updateOutput(key, !val)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    val ? "bg-blue-600" : "bg-gray-300"
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      val ? "translate-x-6" : "translate-x-1"
                    }`}
                  />
                </button>
              ) : (
                <input
                  type={typeof val === "number" ? "number" : "text"}
                  value={
                    typeof val === "object"
                      ? JSON.stringify(val)
                      : String(val ?? "")
                  }
                  onChange={(e) =>
                    updateOutput(
                      key,
                      typeof val === "number"
                        ? Number(e.target.value)
                        : e.target.value
                    )
                  }
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
                />
              )}
            </div>
          ))}
          {Object.keys(editedConfig.output ?? {}).length === 0 && (
            <p className="text-sm text-gray-400 italic">
              No output configuration fields available.
            </p>
          )}
        </div>
      </CollapsibleSection>

      {/* ================================================================= */}
      {/* 4. Sticky bottom save bar (visible when changes exist)             */}
      {/* ================================================================= */}
      {hasChanges && (
        <div className="fixed bottom-0 left-64 right-0 bg-white border-t border-gray-200 px-6 py-3 flex items-center justify-between shadow-lg z-40">
          <span className="text-sm text-gray-600">
            You have unsaved changes.
          </span>
          <div className="flex gap-3">
            <button
              onClick={handleReset}
              className="flex items-center gap-2 px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <RotateCcw className="h-4 w-4" />
              Reset
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-2 px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {saving ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              Save Changes
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
