import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Check,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  Download,
  Filter,
  GitBranch,
  Loader2,
  Pencil,
  Search,
  X,
  XCircle,
} from 'lucide-react';
import StatusBadge from '../components/StatusBadge';
import {
  listTestCases,
  listPipelineRuns,
  approveTestCase,
  rejectTestCase,
  updateTestCase,
  bulkApproveTestCases,
  bulkRejectTestCases,
  type TestCase,
  type PipelineRunSummary,
} from '../api/client';
import { exportToCSV, exportToJSON } from '../utils/export';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TEST_TYPES = [
  'all', 'positive', 'negative', 'edge_case', 'boundary',
  'destructive', 'performance', 'security',
];
const PRIORITIES = ['all', 'High', 'Medium', 'Low'];
const STATUSES = ['all', 'generated', 'approved', 'rejected'];

// Distinct palette — one colour per run slot (cycles if > 10 runs)
const RUN_COLORS = [
  { bg: 'bg-indigo-100 dark:bg-indigo-900/40', text: 'text-indigo-700 dark:text-indigo-300', dot: 'bg-indigo-500' },
  { bg: 'bg-emerald-100 dark:bg-emerald-900/40', text: 'text-emerald-700 dark:text-emerald-300', dot: 'bg-emerald-500' },
  { bg: 'bg-amber-100 dark:bg-amber-900/40', text: 'text-amber-700 dark:text-amber-300', dot: 'bg-amber-500' },
  { bg: 'bg-rose-100 dark:bg-rose-900/40', text: 'text-rose-700 dark:text-rose-300', dot: 'bg-rose-500' },
  { bg: 'bg-cyan-100 dark:bg-cyan-900/40', text: 'text-cyan-700 dark:text-cyan-300', dot: 'bg-cyan-500' },
  { bg: 'bg-purple-100 dark:bg-purple-900/40', text: 'text-purple-700 dark:text-purple-300', dot: 'bg-purple-500' },
  { bg: 'bg-orange-100 dark:bg-orange-900/40', text: 'text-orange-700 dark:text-orange-300', dot: 'bg-orange-500' },
  { bg: 'bg-teal-100 dark:bg-teal-900/40', text: 'text-teal-700 dark:text-teal-300', dot: 'bg-teal-500' },
  { bg: 'bg-pink-100 dark:bg-pink-900/40', text: 'text-pink-700 dark:text-pink-300', dot: 'bg-pink-500' },
  { bg: 'bg-lime-100 dark:bg-lime-900/40', text: 'text-lime-700 dark:text-lime-300', dot: 'bg-lime-500' },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function shortRunId(runId: string) {
  return runId.slice(0, 8);
}

function formatTimestamp(ts: string) {
  return new Date(ts).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

// ---------------------------------------------------------------------------
// Run Badge component
// ---------------------------------------------------------------------------

interface RunBadgeProps {
  runId: string;
  colorIdx: number;
  label?: string; // short label override (e.g. "#1")
}

function RunBadge({ runId, colorIdx, label }: RunBadgeProps) {
  // colorIdx === -1 means the TC has no run_id (legacy data) — use a neutral gray
  if (colorIdx === -1) {
    return (
      <span
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-mono font-medium bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400"
        title="No run ID — legacy data"
      >
        <span className="w-1.5 h-1.5 rounded-full flex-shrink-0 bg-gray-400 dark:bg-gray-500" />
        {label ?? '—'}
      </span>
    );
  }
  const c = RUN_COLORS[colorIdx % RUN_COLORS.length];
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-mono font-medium ${c.bg} ${c.text}`}
      title={runId}
    >
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${c.dot}`} />
      {label ?? shortRunId(runId)}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Expandable Row
// ---------------------------------------------------------------------------

interface RowProps {
  tc: TestCase;
  expanded: boolean;
  selected: boolean;
  runColorIdx: number;
  runLabel: string;
  onToggle: () => void;
  onSelect: (tcId: string) => void;
  onApprove: (tcId: string) => void;
  onReject: (tcId: string) => void;
  onSave: (tcId: string, data: Partial<TestCase>) => void;
}

function TestCaseRow({
  tc, expanded, selected, runColorIdx, runLabel,
  onToggle, onSelect, onApprove, onReject, onSave,
}: RowProps) {
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(tc.title);
  const [editSteps, setEditSteps] = useState(tc.steps ?? []);

  const handleSave = () => { onSave(tc.tc_id, { title: editTitle, steps: editSteps }); setEditing(false); };
  const handleCancelEdit = () => { setEditTitle(tc.title); setEditSteps(tc.steps ?? []); setEditing(false); };
  const updateStep = (idx: number, field: 'action' | 'expected_result', value: string) =>
    setEditSteps((prev) => prev.map((s, i) => (i === idx ? { ...s, [field]: value } : s)));
  const addStep = () => setEditSteps((prev) => [...prev, { action: '', expected_result: '' }]);
  const removeStep = (idx: number) => setEditSteps((prev) => prev.filter((_, i) => i !== idx));

  return (
    <>
      <tr
        className="hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer"
        onClick={onToggle}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onToggle(); } }}
        tabIndex={0}
        aria-expanded={expanded}
        aria-label={`Expand to view details for test case ${tc.tc_id}`}
      >
        {/* Checkbox */}
        <td className="px-4 py-3 text-sm" onClick={(e) => e.stopPropagation()}>
          <input type="checkbox" checked={selected} onChange={() => onSelect(tc.tc_id)}
            className="h-4 w-4 rounded border-gray-300 dark:border-gray-600 text-indigo-600 focus:ring-indigo-500"
            aria-label={`Select ${tc.tc_id}`} />
        </td>
        {/* Expand icon */}
        <td className="px-4 py-3 text-sm">
          {expanded
            ? <ChevronDown className="h-4 w-4 text-gray-400 dark:text-gray-500" />
            : <ChevronRight className="h-4 w-4 text-gray-400 dark:text-gray-500" />}
        </td>
        {/* Run badge */}
        <td className="px-4 py-3 text-sm">
          {tc.run_id
            ? <RunBadge runId={tc.run_id} colorIdx={runColorIdx} label={runLabel} />
            : <span className="text-xs text-gray-400 dark:text-gray-500">—</span>}
        </td>
        <td className="px-4 py-3 text-sm font-mono text-gray-900 dark:text-gray-100">{tc.tc_id}</td>
        <td className="px-4 py-3 text-sm font-mono text-gray-500 dark:text-gray-400">{tc.req_id}</td>
        <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{tc.title}</td>
        <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400 capitalize">
          {tc.test_type.replace(/_/g, ' ')}
        </td>
        <td className="px-4 py-3">
          <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
            tc.priority.toLowerCase() === 'high' ? 'bg-red-100 text-red-700'
            : tc.priority.toLowerCase() === 'medium' ? 'bg-yellow-100 text-yellow-700'
            : 'bg-green-100 text-green-700'}`}>
            {tc.priority}
          </span>
        </td>
        <td className="px-4 py-3"><StatusBadge status={tc.status} size="sm" /></td>
        <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center gap-1">
            <button onClick={() => onApprove(tc.tc_id)}
              className="p-1 rounded text-green-500 hover:bg-green-50 dark:hover:bg-green-900/30"
              title="Approve" aria-label={`Approve ${tc.tc_id}`}>
              <Check className="h-4 w-4" />
            </button>
            <button onClick={() => onReject(tc.tc_id)}
              className="p-1 rounded text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30"
              title="Reject" aria-label={`Reject ${tc.tc_id}`}>
              <XCircle className="h-4 w-4" />
            </button>
            <button onClick={() => setEditing(!editing)}
              className="p-1 rounded text-gray-400 dark:text-gray-500 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-900/30"
              title="Edit" aria-label={`Edit ${tc.tc_id}`}>
              <Pencil className="h-4 w-4" />
            </button>
          </div>
        </td>
      </tr>

      {expanded && (
        <tr>
          <td colSpan={10} className="bg-gray-50 dark:bg-gray-700 px-8 py-5">
            {editing ? (
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Title</label>
                  <input type="text" value={editTitle} onChange={(e) => setEditTitle(e.target.value)}
                    className="w-full rounded border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-sm dark:bg-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">Test Steps</label>
                  <div className="space-y-2">
                    {editSteps.map((step, idx) => (
                      <div key={idx} className="flex items-start gap-2">
                        <span className="text-xs font-medium text-gray-400 dark:text-gray-500 mt-2 w-6 text-right flex-shrink-0">{idx + 1}.</span>
                        <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-2">
                          <input type="text" value={step.action} onChange={(e) => updateStep(idx, 'action', e.target.value)}
                            placeholder="Action"
                            className="rounded border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-sm dark:bg-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                          <input type="text" value={step.expected_result} onChange={(e) => updateStep(idx, 'expected_result', e.target.value)}
                            placeholder="Expected result"
                            className="rounded border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-sm dark:bg-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                        </div>
                        <button onClick={() => removeStep(idx)} className="mt-1.5 p-1 rounded text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30" title="Remove step">
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    ))}
                    <button onClick={addStep} className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline mt-1">+ Add Step</button>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={handleSave} className="px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded hover:bg-indigo-700">Save Changes</button>
                  <button onClick={handleCancelEdit} className="px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-200 dark:bg-gray-600 rounded hover:bg-gray-300 dark:hover:bg-gray-500">Cancel</button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Run metadata pill in expanded view */}
                {tc.run_id && (
                  <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                    <GitBranch className="h-3.5 w-3.5" />
                    <span>Run:</span>
                    <RunBadge runId={tc.run_id} colorIdx={runColorIdx} />
                  </div>
                )}
                {tc.description && (
                  <div>
                    <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Description</span>
                    <p className="text-sm text-gray-700 dark:text-gray-300 mt-1">{tc.description}</p>
                  </div>
                )}
                {tc.preconditions && (
                  <div>
                    <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Preconditions</span>
                    <p className="text-sm text-gray-700 dark:text-gray-300 mt-1">{tc.preconditions}</p>
                  </div>
                )}
                {tc.steps && tc.steps.length > 0 ? (
                  <div>
                    <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Test Steps</span>
                    <div className="mt-2 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="bg-gray-50 dark:bg-gray-700 text-left text-xs text-gray-500 dark:text-gray-400 uppercase">
                            <th className="px-3 py-2 w-10">#</th>
                            <th className="px-3 py-2">Action</th>
                            <th className="px-3 py-2">Expected Result</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                          {tc.steps.map((step, idx) => (
                            <tr key={idx}>
                              <td className="px-3 py-2 text-gray-400 dark:text-gray-500 font-mono">{idx + 1}</td>
                              <td className="px-3 py-2 text-gray-700 dark:text-gray-300">{step.action}</td>
                              <td className="px-3 py-2 text-gray-700 dark:text-gray-300">{step.expected_result}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : (
                  (tc.given || tc.when || tc.then) && (
                    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 font-mono text-sm space-y-2">
                      {tc.given && <p><span className="text-purple-600 font-semibold">Given </span><span className="text-gray-700 dark:text-gray-300">{tc.given}</span></p>}
                      {tc.when && <p><span className="text-blue-600 font-semibold">When </span><span className="text-gray-700 dark:text-gray-300">{tc.when}</span></p>}
                      {tc.then && <p><span className="text-green-600 font-semibold">Then </span><span className="text-gray-700 dark:text-gray-300">{tc.then}</span></p>}
                    </div>
                  )
                )}
                {tc.expected_outcome && (
                  <div>
                    <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Expected Outcome</span>
                    <p className="text-sm text-gray-700 dark:text-gray-300 mt-1">{tc.expected_outcome}</p>
                  </div>
                )}
                <div className="flex flex-wrap items-center gap-4">
                  {tc.component && (
                    <div>
                      <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Component</span>
                      <p className="text-sm text-gray-700 dark:text-gray-300 mt-0.5">{tc.component}</p>
                    </div>
                  )}
                  {tc.test_level && (
                    <div>
                      <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Test Level</span>
                      <p className="text-sm text-gray-700 dark:text-gray-300 mt-0.5 capitalize">{tc.test_level}</p>
                    </div>
                  )}
                  {tc.quality_score > 0 && (
                    <div>
                      <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Quality Score</span>
                      <p className={`text-sm font-medium mt-0.5 ${tc.quality_score >= 0.7 ? 'text-green-600' : tc.quality_score >= 0.4 ? 'text-yellow-600' : 'text-red-600'}`}>
                        {(tc.quality_score * 100).toFixed(0)}%
                      </p>
                    </div>
                  )}
                  {tc.tags.length > 0 && (
                    <div>
                      <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Tags</span>
                      <div className="flex flex-wrap gap-1 mt-0.5">
                        {tc.tags.map((tag) => (
                          <span key={tag} className="inline-block px-2 py-0.5 rounded-full bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 text-xs">{tag}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// TestCases Page
// ---------------------------------------------------------------------------

export default function TestCases() {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlRunId = searchParams.get('run_id') ?? '';

  const [allTestCases, setAllTestCases] = useState<TestCase[]>([]);
  const [runs, setRuns] = useState<PipelineRunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [filterType, setFilterType] = useState('all');
  const [filterPriority, setFilterPriority] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  const [searchText, setSearchText] = useState('');

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Helper to build a unique row key from a test case
  const rowKey = (tc: TestCase) => `${tc.tc_id}::${tc.run_id ?? ''}`;

  // Ref to the table/results section — used to scroll it into view on filter change
  const tableTopRef = useRef<HTMLDivElement>(null);

  // Scroll the <main> container back so the table is visible whenever a filter changes.
  // This fixes the case where the user is scrolled far down through 285 rows and then
  // applies a filter: the 7 matching rows render at the top but the scroll position
  // stays at the bottom, making the table appear blank.
  useEffect(() => {
    if (!loading) {
      tableTopRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [filterType, filterPriority, filterStatus, searchText, urlRunId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Build ordered, deduplicated run list: oldest pipeline run first (index 0 = color 0),
  // with disk-only runs (not in pipeline list) appended at the end.
  const orderedRunIds = useMemo(() => {
    const seen = new Set<string>();
    const pipelineOrder: string[] = [];
    const diskOnly: string[] = [];

    // runs from API is newest-first; reverse to oldest-first for colour assignment
    runs.filter((r) => !r.archived).forEach((r) => {
      if (!seen.has(r.run_id)) { seen.add(r.run_id); pipelineOrder.push(r.run_id); }
    });
    pipelineOrder.reverse(); // now oldest-first

    // TCs whose run_id isn't in the pipeline list (e.g. imported/legacy runs)
    allTestCases.forEach((tc) => {
      if (tc.run_id && !seen.has(tc.run_id)) { seen.add(tc.run_id); diskOnly.push(tc.run_id); }
    });

    return [...pipelineOrder, ...diskOnly];
  }, [runs, allTestCases]);

  const archivedRunCount = runs.filter((r) => r.archived).length;

  // Map run_id → { colorIdx, label, startedAt }
  const runMeta = useMemo(() => {
    const map = new Map<string, { colorIdx: number; label: string; startedAt: string }>();
    orderedRunIds.forEach((rid, idx) => {
      const run = runs.find((r) => r.run_id === rid);
      map.set(rid, {
        colorIdx: idx,
        label: `#${idx + 1}`,
        startedAt: run?.started_at ?? '',
      });
    });
    return map;
  }, [orderedRunIds, runs]);

  // Load all TCs (consolidated) + run summaries
  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const [tcRes, runRes] = await Promise.all([
          listTestCases(),
          listPipelineRuns(),
        ]);
        setAllTestCases(tcRes.data);
        setRuns(runRes.data);
        setError(null);
      } catch (err: any) {
        setError(err.message ?? 'Failed to load test cases');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const toggleSelect = (rk: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(rk)) next.delete(rk); else next.add(rk);
      return next;
    });
  };

  const handleBulkApprove = useCallback(async () => {
    const ids = Array.from(selectedIds);
    if (!ids.length) return;
    try {
      const res = await bulkApproveTestCases(ids);
      setAllTestCases((prev) =>
        prev.map((tc) => res.data.updated.includes(tc.tc_id) ? { ...tc, status: 'approved' } : tc)
      );
      setSelectedIds(new Set());
    } catch (err: any) { setError(err.message ?? 'Bulk approve failed'); }
  }, [selectedIds]);

  const handleBulkReject = useCallback(async () => {
    const ids = Array.from(selectedIds);
    if (!ids.length) return;
    try {
      const res = await bulkRejectTestCases(ids);
      setAllTestCases((prev) =>
        prev.map((tc) => res.data.updated.includes(tc.tc_id) ? { ...tc, status: 'rejected' } : tc)
      );
      setSelectedIds(new Set());
    } catch (err: any) { setError(err.message ?? 'Bulk reject failed'); }
  }, [selectedIds]);

  const filtered = useMemo(() => {
    return allTestCases.filter((tc) => {
      if (urlRunId && tc.run_id !== urlRunId) return false;
      if (filterType !== 'all' && tc.test_type !== filterType) return false;
      if (filterPriority !== 'all' && tc.priority !== filterPriority) return false;
      if (filterStatus !== 'all' && tc.status !== filterStatus) return false;
      if (searchText && !tc.title.toLowerCase().includes(searchText.toLowerCase()) &&
          !tc.tc_id.toLowerCase().includes(searchText.toLowerCase())) return false;
      return true;
    });
  }, [allTestCases, urlRunId, filterType, filterPriority, filterStatus, searchText]);

  const toggleSelectAll = useCallback(() => {
    setSelectedIds((prev) =>
      prev.size === filtered.length ? new Set() : new Set(filtered.map(rowKey))
    );
  }, [filtered]);

  const handleApprove = async (tcId: string) => {
    try {
      await approveTestCase(tcId);
      setAllTestCases((prev) => prev.map((tc) => tc.tc_id === tcId ? { ...tc, status: 'approved' } : tc));
    } catch (err: any) { setError(err.message ?? 'Failed to approve'); }
  };

  const handleReject = async (tcId: string) => {
    try {
      await rejectTestCase(tcId);
      setAllTestCases((prev) => prev.map((tc) => tc.tc_id === tcId ? { ...tc, status: 'rejected' } : tc));
    } catch (err: any) { setError(err.message ?? 'Failed to reject'); }
  };

  const handleSave = async (tcId: string, data: Partial<TestCase>) => {
    try {
      await updateTestCase(tcId, data);
      setAllTestCases((prev) => prev.map((tc) => tc.tc_id === tcId ? { ...tc, ...data } : tc));
    } catch (err: any) { setError(err.message ?? 'Failed to update'); }
  };

  // Run counts for the selector — must be before any early returns
  const runCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    allTestCases.forEach((tc) => {
      if (tc.run_id) counts[tc.run_id] = (counts[tc.run_id] ?? 0) + 1;
    });
    return counts;
  }, [allTestCases]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {error && (
        <div role="alert" className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 rounded-lg flex items-center justify-between">
          <span className="text-sm">{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600"><X className="h-4 w-4" /></button>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Test Cases</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            Browse, filter, and manage generated test cases across all pipeline runs
          </p>
        </div>
        {filtered.length > 0 && (
          <div className="flex gap-2">
            <button onClick={() => exportToCSV(filtered as object[], 'test_cases.csv')}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-gray-300 rounded-md hover:bg-gray-50 dark:border-gray-600 dark:hover:bg-gray-800"
              aria-label="Export CSV">
              <Download className="h-4 w-4" /> CSV
            </button>
            <button onClick={() => exportToJSON(filtered, 'test_cases.json')}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-gray-300 rounded-md hover:bg-gray-50 dark:border-gray-600 dark:hover:bg-gray-800"
              aria-label="Export JSON">
              <Download className="h-4 w-4" /> JSON
            </button>
          </div>
        )}
      </div>

      {/* Run legend — shows all known runs as colour chips */}
      {orderedRunIds.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mr-1 flex-shrink-0">
              Pipeline Runs:
            </span>
            {/* "All" pill */}
            <button
              onClick={() => setSearchParams({}, { replace: true })}
              className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                !urlRunId
                  ? 'bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 border-transparent'
                  : 'border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
            >
              All ({allTestCases.length})
            </button>
            {orderedRunIds.map((rid) => {
              const meta = runMeta.get(rid)!;
              const c = RUN_COLORS[meta.colorIdx % RUN_COLORS.length];
              const isActive = urlRunId === rid;
              return (
                <button
                  key={rid}
                  onClick={() =>
                    setSearchParams(isActive ? {} : { run_id: rid }, { replace: true })
                  }
                  title={`Run ${rid}${meta.startedAt ? ' · ' + formatTimestamp(meta.startedAt) : ''}`}
                  className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                    isActive
                      ? `${c.bg} ${c.text} border-transparent ring-2 ring-offset-1 ring-current`
                      : `border-gray-200 dark:border-gray-700 ${c.text} hover:${c.bg}`
                  }`}
                >
                  <span className={`w-2 h-2 rounded-full ${c.dot}`} />
                  Run {meta.label}
                  <span className="ml-0.5 opacity-60">({runCounts[rid] ?? 0})</span>
                </button>
              );
            })}
            {archivedRunCount > 0 && (
              <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 border border-gray-200 dark:border-gray-600">
                {archivedRunCount} archived
              </span>
            )}
          </div>
        </div>
      )}

      {/* Filter bar */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
        <div className="flex flex-wrap items-center gap-4">
          {/* Filter icon — badge shows count of active filters */}
          <div className="relative flex-shrink-0">
            <Filter className="h-4 w-4 text-gray-400 dark:text-gray-500" />
            {(filterType !== 'all' || filterPriority !== 'all' || filterStatus !== 'all' || searchText || urlRunId) && (
              <span className="absolute -top-1.5 -right-1.5 h-3 w-3 rounded-full bg-indigo-500 border border-white dark:border-gray-800" title="Filters active" />
            )}
          </div>
          <select value={filterType} onChange={(e) => setFilterType(e.target.value)}
            className="rounded-md border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-sm dark:bg-gray-700 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            aria-label="Filter by test type">
            {TEST_TYPES.map((t) => <option key={t} value={t}>{t === 'all' ? 'All Types' : t.replace(/_/g, ' ')}</option>)}
          </select>
          <select value={filterPriority} onChange={(e) => setFilterPriority(e.target.value)}
            className="rounded-md border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-sm dark:bg-gray-700 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            aria-label="Filter by priority">
            {PRIORITIES.map((p) => <option key={p} value={p}>{p === 'all' ? 'All Priorities' : p}</option>)}
          </select>
          <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}
            className="rounded-md border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-sm dark:bg-gray-700 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            aria-label="Filter by status">
            {STATUSES.map((s) => <option key={s} value={s}>{s === 'all' ? 'All Statuses' : s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
          </select>
          {/* Search with inline clear button */}
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 dark:text-gray-500" />
            <input type="text" placeholder="Search by title or TC ID…" value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 pl-9 pr-8 py-1.5 text-sm dark:bg-gray-700 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            {searchText && (
              <button
                onClick={() => setSearchText('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                aria-label="Clear search"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
          <span className="text-sm text-gray-500 dark:text-gray-400 flex-shrink-0" aria-live="polite">
            {filtered.length} / {allTestCases.length} test cases
          </span>
          {/* Clear all filters button — only visible when any filter is active */}
          {(filterType !== 'all' || filterPriority !== 'all' || filterStatus !== 'all' || searchText || urlRunId) && (
            <button
              onClick={() => {
                setFilterType('all');
                setFilterPriority('all');
                setFilterStatus('all');
                setSearchText('');
                setSearchParams({}, { replace: true });
              }}
              className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md hover:bg-red-100 dark:hover:bg-red-900/40 flex-shrink-0"
              aria-label="Clear all filters"
            >
              <XCircle className="h-3.5 w-3.5" />
              Clear filters
            </button>
          )}
        </div>
      </div>

      {/* Table — tableTopRef anchors scroll-into-view on filter changes */}
      <div ref={tableTopRef} />
      {allTestCases.length === 0 ? (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-12 text-center">
          <ClipboardList className="h-12 w-12 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
          <p className="text-gray-500 dark:text-gray-400 text-lg font-medium">No test cases generated yet</p>
          <p className="text-gray-400 dark:text-gray-500 text-sm mt-1">Run a pipeline to generate test cases.</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-8 text-center text-gray-500 dark:text-gray-400">
          No test cases match the current filters.
        </div>
      ) : (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
          {selectedIds.size > 0 && (
            <div className="bg-indigo-50 dark:bg-indigo-900/30 px-4 py-2 flex items-center gap-3 border-b border-indigo-100 dark:border-indigo-800">
              <span className="text-sm font-medium text-indigo-700 dark:text-indigo-300">{selectedIds.size} selected</span>
              <button onClick={handleBulkApprove}
                className="flex items-center gap-1 px-3 py-1 text-sm font-medium text-green-700 bg-green-100 rounded hover:bg-green-200">
                <Check className="h-3.5 w-3.5" /> Approve
              </button>
              <button onClick={handleBulkReject}
                className="flex items-center gap-1 px-3 py-1 text-sm font-medium text-red-700 bg-red-100 rounded hover:bg-red-200">
                <XCircle className="h-3.5 w-3.5" /> Reject
              </button>
              <button onClick={() => setSelectedIds(new Set())} className="ml-auto text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300">
                Clear selection
              </button>
            </div>
          )}
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-700">
                <tr>
                  <th className="px-4 py-3 w-8">
                    <input type="checkbox"
                      checked={filtered.length > 0 && selectedIds.size === filtered.length}
                      onChange={toggleSelectAll}
                      className="h-4 w-4 rounded border-gray-300 dark:border-gray-600 text-indigo-600 focus:ring-indigo-500"
                      aria-label="Select all" />
                  </th>
                  <th className="px-4 py-3 w-8" />
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Run</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">TC ID</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Req ID</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Title</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Type</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Priority</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {filtered.map((tc) => {
                  const meta = tc.run_id ? runMeta.get(tc.run_id) : undefined;
                  const rk = rowKey(tc);
                  // -1 signals "no run" → RunBadge renders neutral gray
                  const runColorIdx = meta?.colorIdx ?? (tc.run_id ? 0 : -1);
                  const runLabel = meta?.label ?? (tc.run_id ? shortRunId(tc.run_id) : '—');
                  return (
                    <TestCaseRow
                      key={rk}
                      tc={tc}
                      expanded={expandedId === rk}
                      selected={selectedIds.has(rk)}
                      runColorIdx={runColorIdx}
                      runLabel={runLabel}
                      onToggle={() => setExpandedId(expandedId === rk ? null : rk)}
                      onSelect={() => toggleSelect(rk)}
                      onApprove={handleApprove}
                      onReject={handleReject}
                      onSave={handleSave}
                    />
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
