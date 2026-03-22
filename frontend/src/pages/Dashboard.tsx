import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Activity,
  Bot,
  ClipboardList,
  Download,
  FileText,
  Loader2,
  Play,
  Upload,
  X,
  Rocket,
  ArrowRight,
} from "lucide-react";
import StatusBadge from "../components/StatusBadge";
import {
  getHealth,
  getConfig,
  listPipelineRuns,
  listRequirements,
  listTestCases,
  triggerPipelineRun,
  downloadBddProject,
  type PipelineRunSummary,
  type PipelineRunRequest,
  type ConfigResponse,
} from "../api/client";

// ---------------------------------------------------------------------------
// Stat Card
// ---------------------------------------------------------------------------

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  accent: string;
}

function StatCard({ icon, label, value, accent }: StatCardProps) {
  return (
    <div className="bg-white rounded-lg shadow p-5 flex items-center gap-4">
      <div className={`p-3 rounded-lg ${accent}`}>{icon}</div>
      <div>
        <p className="text-2xl font-bold text-gray-900">{value}</p>
        <p className="text-sm text-gray-500">{label}</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Trigger Run Modal
// ---------------------------------------------------------------------------

interface TriggerModalProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (req: PipelineRunRequest) => void;
  loading: boolean;
}

function TriggerRunModal({ open, onClose, onSubmit, loading }: TriggerModalProps) {
  const [pipelinePath, setPipelinePath] = useState("config/pipelines/full_stlc.yaml");
  const [profile, setProfile] = useState("");
  const [maxWorkers, setMaxWorkers] = useState(2);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900">Trigger New Run</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Pipeline Path
            </label>
            <input
              type="text"
              value={pipelinePath}
              onChange={(e) => setPipelinePath(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Profile (optional)
            </label>
            <select
              value={profile}
              onChange={(e) => setProfile(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">Default</option>
              <option value="smoke">Smoke</option>
              <option value="targeted">Targeted</option>
              <option value="regression">Regression</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Max Workers
            </label>
            <input
              type="number"
              min={1}
              max={8}
              value={maxWorkers}
              onChange={(e) => setMaxWorkers(Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        </div>

        <div className="flex justify-end gap-3 mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
          >
            Cancel
          </button>
          <button
            disabled={loading}
            onClick={() =>
              onSubmit({
                pipeline_path: pipelinePath,
                profile: profile || undefined,
                max_workers: maxWorkers,
              })
            }
            className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2"
          >
            {loading && <Loader2 className="h-4 w-4 animate-spin" />}
            Run Pipeline
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dashboard Page
// ---------------------------------------------------------------------------

export default function Dashboard() {
  const navigate = useNavigate();

  const [agentCount, setAgentCount] = useState<number>(0);
  const [runs, setRuns] = useState<PipelineRunSummary[]>([]);
  const [reqCount, setReqCount] = useState<number>(0);
  const [tcCount, setTcCount] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [triggerLoading, setTriggerLoading] = useState(false);
  const [showSetupBanner, setShowSetupBanner] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function fetchAll() {
      try {
        const [healthRes, runsRes, reqRes, tcRes, configRes] = await Promise.all([
          getHealth(),
          listPipelineRuns(),
          listRequirements(),
          listTestCases(),
          getConfig(),
        ]);
        if (cancelled) return;
        setAgentCount(healthRes.data.agents_registered);
        setRuns(runsRes.data);
        setReqCount(reqRes.data.length);
        setTcCount(tcRes.data.length);

        // Check if first-run setup banner should be shown
        const dismissed = localStorage.getItem("stlc_setup_dismissed") === "true";
        if (!dismissed) {
          const cfg: ConfigResponse = configRes.data;
          const llm = cfg.llm ?? {};
          const provider = llm.provider ?? "";
          const apiKey = llm.api_key ?? "";
          const needsSetup =
            !provider ||
            (provider !== "ollama" && (!apiKey || apiKey === ""));
          setShowSetupBanner(needsSetup);
        }
      } catch (err: any) {
        if (!cancelled) setError(err.message ?? "Failed to load dashboard data");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchAll();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleTrigger = async (req: PipelineRunRequest) => {
    setTriggerLoading(true);
    try {
      await triggerPipelineRun(req);
      setModalOpen(false);
      const res = await listPipelineRuns();
      setRuns(res.data);
    } catch (err: any) {
      setError(err.message ?? "Failed to trigger pipeline");
    } finally {
      setTriggerLoading(false);
    }
  };

  const handleDownloadBdd = async () => {
    try {
      const res = await downloadBddProject();
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement("a");
      link.href = url;
      link.download = "bdd_project.zip";
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      setError(err.message ?? "Failed to download BDD project");
    }
  };

  const formatDuration = (seconds?: number) => {
    if (seconds == null) return "--";
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8">
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center justify-between">
          <span className="text-sm">{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* First-run setup banner */}
      {showSetupBanner && (
        <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg p-5">
          <div className="flex items-start gap-4">
            <div className="p-2 bg-blue-100 rounded-lg flex-shrink-0">
              <Rocket className="h-6 w-6 text-blue-600" />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="text-base font-semibold text-gray-900">
                Welcome! Set up your AI provider to get started
              </h3>
              <p className="text-sm text-gray-600 mt-1">
                Configure your LLM (OpenAI, Anthropic, or local Ollama) to start
                generating test cases automatically.
              </p>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                onClick={() => navigate("/config")}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors"
              >
                Set Up Now
                <ArrowRight className="h-4 w-4" />
              </button>
              <button
                onClick={() => {
                  localStorage.setItem("stlc_setup_dismissed", "true");
                  setShowSetupBanner(false);
                }}
                className="px-3 py-2 text-sm text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
              >
                Dismiss
              </button>
            </div>
          </div>
        </div>
      )}

      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-500 mt-1">STLC Platform overview and quick actions</p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={<Bot className="h-6 w-6 text-indigo-600" />}
          label="Total Agents"
          value={agentCount}
          accent="bg-indigo-100"
        />
        <StatCard
          icon={<Activity className="h-6 w-6 text-blue-600" />}
          label="Pipeline Runs"
          value={runs.length}
          accent="bg-blue-100"
        />
        <StatCard
          icon={<FileText className="h-6 w-6 text-emerald-600" />}
          label="Requirements"
          value={reqCount}
          accent="bg-emerald-100"
        />
        <StatCard
          icon={<ClipboardList className="h-6 w-6 text-amber-600" />}
          label="Test Cases"
          value={tcCount}
          accent="bg-amber-100"
        />
      </div>

      {/* Recent Runs */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Recent Runs</h2>
          <button
            onClick={() => setModalOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700"
          >
            <Play className="h-4 w-4" /> Trigger New Run
          </button>
        </div>

        {runs.length === 0 ? (
          <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
            No pipeline runs yet. Trigger your first run to get started.
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Run ID
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Pipeline
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Duration
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Started
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {runs.slice(0, 10).map((run) => (
                  <tr key={run.run_id} className="hover:bg-gray-50 cursor-pointer">
                    <td className="px-4 py-3 text-sm font-mono text-gray-900">
                      {run.run_id.slice(0, 8)}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700">
                      {run.pipeline_name}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={run.status} size="sm" />
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {formatDuration(run.total_duration_seconds)}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {new Date(run.started_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Quick Actions */}
      <section>
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <button
            onClick={() => navigate("/requirements")}
            className="bg-white rounded-lg shadow p-5 flex items-center gap-4 hover:shadow-md transition-shadow text-left"
          >
            <div className="p-3 rounded-lg bg-emerald-100">
              <Upload className="h-5 w-5 text-emerald-600" />
            </div>
            <div>
              <p className="font-medium text-gray-900">Upload Requirements</p>
              <p className="text-sm text-gray-500">Add new requirement files</p>
            </div>
          </button>

          <button
            onClick={() => navigate("/test-cases")}
            className="bg-white rounded-lg shadow p-5 flex items-center gap-4 hover:shadow-md transition-shadow text-left"
          >
            <div className="p-3 rounded-lg bg-amber-100">
              <ClipboardList className="h-5 w-5 text-amber-600" />
            </div>
            <div>
              <p className="font-medium text-gray-900">View Test Cases</p>
              <p className="text-sm text-gray-500">Browse and manage test cases</p>
            </div>
          </button>

          <button
            onClick={handleDownloadBdd}
            className="bg-white rounded-lg shadow p-5 flex items-center gap-4 hover:shadow-md transition-shadow text-left"
          >
            <div className="p-3 rounded-lg bg-blue-100">
              <Download className="h-5 w-5 text-blue-600" />
            </div>
            <div>
              <p className="font-medium text-gray-900">Download BDD Project</p>
              <p className="text-sm text-gray-500">Get scaffolded BDD project</p>
            </div>
          </button>
        </div>
      </section>

      <TriggerRunModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSubmit={handleTrigger}
        loading={triggerLoading}
      />
    </div>
  );
}
