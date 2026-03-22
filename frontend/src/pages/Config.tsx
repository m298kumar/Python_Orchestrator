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
} from "lucide-react";
import { getConfig, updateConfig } from "../api/client";
import type { ConfigResponse } from "../api/client";

interface ToastState {
  message: string;
  type: "success" | "error";
}

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
  defaultOpen = true,
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

function ConfigField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: any;
  onChange: (val: any) => void;
}) {
  const strVal = typeof value === "object" ? JSON.stringify(value) : String(value ?? "");

  // Detect type for input
  if (typeof value === "boolean") {
    return (
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium text-gray-700">{label}</label>
        <button
          onClick={() => onChange(!value)}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
            value ? "bg-blue-600" : "bg-gray-300"
          }`}
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
              value ? "translate-x-6" : "translate-x-1"
            }`}
          />
        </button>
      </div>
    );
  }

  if (typeof value === "number") {
    return (
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {label}
        </label>
        <input
          type="number"
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
        />
      </div>
    );
  }

  // String or unknown
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {label}
      </label>
      <input
        type="text"
        value={strVal}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
      />
    </div>
  );
}

export default function Config() {
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [editedConfig, setEditedConfig] = useState<ConfigResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastState | null>(null);

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

  function updateSection(
    section: keyof ConfigResponse,
    key: string,
    value: any
  ) {
    if (!editedConfig) return;
    setEditedConfig({
      ...editedConfig,
      [section]: {
        ...editedConfig[section],
        [key]: value,
      },
    });
  }

  async function handleSave() {
    if (!editedConfig) return;
    setSaving(true);
    try {
      await updateConfig(editedConfig);
      setConfig(structuredClone(editedConfig));
      setToast({ message: "Configuration saved successfully.", type: "success" });
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
    }
  }

  const hasChanges =
    config &&
    editedConfig &&
    JSON.stringify(config) !== JSON.stringify(editedConfig);

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

  const sectionMeta: {
    key: keyof ConfigResponse;
    title: string;
    icon: React.ReactNode;
  }[] = [
    {
      key: "project",
      title: "Project Config",
      icon: <Settings className="h-4 w-4" />,
    },
    {
      key: "ollama",
      title: "LLM Config (Ollama)",
      icon: <Cpu className="h-4 w-4" />,
    },
    {
      key: "output",
      title: "Output Config",
      icon: <FolderOutput className="h-4 w-4" />,
    },
  ];

  return (
    <div className="p-6 space-y-6">
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
        </div>
      )}

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Configuration</h1>
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

      {sectionMeta.map(({ key, title, icon }) => (
        <CollapsibleSection key={key} title={title} icon={icon}>
          {Object.entries(editedConfig[key] ?? {}).map(([fieldKey, fieldVal]) => (
            <ConfigField
              key={fieldKey}
              label={fieldKey}
              value={fieldVal}
              onChange={(val) => updateSection(key, fieldKey, val)}
            />
          ))}
          {Object.keys(editedConfig[key] ?? {}).length === 0 && (
            <p className="text-sm text-gray-400 italic">
              No configuration fields in this section.
            </p>
          )}
        </CollapsibleSection>
      ))}
    </div>
  );
}
