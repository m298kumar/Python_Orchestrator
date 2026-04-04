import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Check,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  Download,
  Filter,
  Loader2,
  Pencil,
  Search,
  X,
  XCircle,
} from 'lucide-react';
import StatusBadge from '../components/StatusBadge';
import {
  listTestCases,
  listTestCasesByRun,
  approveTestCase,
  rejectTestCase,
  updateTestCase,
  bulkApproveTestCases,
  bulkRejectTestCases,
  type TestCase,
} from '../api/client';
import { exportToCSV, exportToJSON } from '../utils/export';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TEST_TYPES = [
  'all',
  'positive',
  'negative',
  'edge_case',
  'boundary',
  'destructive',
  'performance',
  'security',
];

const PRIORITIES = ['all', 'High', 'Medium', 'Low'];
const STATUSES = ['all', 'generated', 'approved', 'rejected'];

// ---------------------------------------------------------------------------
// Expandable Row
// ---------------------------------------------------------------------------

interface RowProps {
  tc: TestCase;
  expanded: boolean;
  selected: boolean;
  onToggle: () => void;
  onSelect: (tcId: string) => void;
  onApprove: (tcId: string) => void;
  onReject: (tcId: string) => void;
  onSave: (tcId: string, data: Partial<TestCase>) => void;
}

function TestCaseRow({ tc, expanded, selected, onToggle, onSelect, onApprove, onReject, onSave }: RowProps) {
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(tc.title);
  const [editSteps, setEditSteps] = useState(tc.steps ?? []);

  const handleSave = () => {
    onSave(tc.tc_id, {
      title: editTitle,
      steps: editSteps,
    });
    setEditing(false);
  };

  const handleCancelEdit = () => {
    setEditTitle(tc.title);
    setEditSteps(tc.steps ?? []);
    setEditing(false);
  };

  const updateStep = (idx: number, field: 'action' | 'expected_result', value: string) => {
    setEditSteps((prev) => prev.map((s, i) => (i === idx ? { ...s, [field]: value } : s)));
  };

  const addStep = () => {
    setEditSteps((prev) => [...prev, { action: '', expected_result: '' }]);
  };

  const removeStep = (idx: number) => {
    setEditSteps((prev) => prev.filter((_, i) => i !== idx));
  };

  return (
    <>
      <tr
        className="hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer"
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onToggle();
          }
        }}
        tabIndex={0}
        aria-expanded={expanded}
        aria-label={`Expand to view details for test case ${tc.tc_id}`}
      >
        <td className="px-4 py-3 text-sm" onClick={(e) => e.stopPropagation()}>
          <input
            type="checkbox"
            checked={selected}
            onChange={() => onSelect(tc.tc_id)}
            className="h-4 w-4 rounded border-gray-300 dark:border-gray-600 text-indigo-600 focus:ring-indigo-500"
            aria-label={`Select ${tc.tc_id}`}
          />
        </td>
        <td className="px-4 py-3 text-sm">
          {expanded ? (
            <ChevronDown className="h-4 w-4 text-gray-400 dark:text-gray-500" />
          ) : (
            <ChevronRight className="h-4 w-4 text-gray-400 dark:text-gray-500" />
          )}
        </td>
        <td className="px-4 py-3 text-sm font-mono text-gray-900 dark:text-gray-100">{tc.tc_id}</td>
        <td className="px-4 py-3 text-sm font-mono text-gray-500 dark:text-gray-400">{tc.req_id}</td>
        <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{tc.title}</td>
        <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400 capitalize">
          {tc.test_type.replace(/_/g, ' ')}
        </td>
        <td className="px-4 py-3">
          <span
            className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
              tc.priority.toLowerCase() === 'high'
                ? 'bg-red-100 text-red-700'
                : tc.priority.toLowerCase() === 'medium'
                  ? 'bg-yellow-100 text-yellow-700'
                  : 'bg-green-100 text-green-700'
            }`}
          >
            {tc.priority}
          </span>
        </td>
        <td className="px-4 py-3">
          <StatusBadge status={tc.status} size="sm" />
        </td>
        <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center gap-1">
            <button
              onClick={() => onApprove(tc.tc_id)}
              className="p-1 rounded text-green-500 hover:bg-green-50 dark:hover:bg-green-900/30"
              title="Approve"
              aria-label={`Approve test case ${tc.tc_id}`}
            >
              <Check className="h-4 w-4" />
            </button>
            <button
              onClick={() => onReject(tc.tc_id)}
              className="p-1 rounded text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30"
              title="Reject"
              aria-label={`Reject test case ${tc.tc_id}`}
            >
              <XCircle className="h-4 w-4" />
            </button>
            <button
              onClick={() => setEditing(!editing)}
              className="p-1 rounded text-gray-400 dark:text-gray-500 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-900/30"
              title="Edit"
              aria-label={`Edit test case ${tc.tc_id}`}
            >
              <Pencil className="h-4 w-4" />
            </button>
          </div>
        </td>
      </tr>

      {expanded && (
        <tr>
          <td colSpan={9} className="bg-gray-50 dark:bg-gray-700 px-8 py-5">
            {editing ? (
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Title</label>
                  <input
                    type="text"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    className="w-full rounded border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-sm dark:bg-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">Test Steps</label>
                  <div className="space-y-2">
                    {editSteps.map((step, idx) => (
                      <div key={idx} className="flex items-start gap-2">
                        <span className="text-xs font-medium text-gray-400 dark:text-gray-500 mt-2 w-6 text-right flex-shrink-0">{idx + 1}.</span>
                        <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-2">
                          <input
                            type="text"
                            value={step.action}
                            onChange={(e) => updateStep(idx, 'action', e.target.value)}
                            placeholder="Action"
                            className="rounded border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-sm dark:bg-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          />
                          <input
                            type="text"
                            value={step.expected_result}
                            onChange={(e) => updateStep(idx, 'expected_result', e.target.value)}
                            placeholder="Expected result"
                            className="rounded border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-sm dark:bg-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          />
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
                  <button
                    onClick={handleSave}
                    className="px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded hover:bg-indigo-700"
                  >
                    Save Changes
                  </button>
                  <button
                    onClick={handleCancelEdit}
                    className="px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-200 dark:bg-gray-600 rounded hover:bg-gray-300 dark:hover:bg-gray-500"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Description */}
                {tc.description && (
                  <div>
                    <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Description</span>
                    <p className="text-sm text-gray-700 dark:text-gray-300 mt-1">{tc.description}</p>
                  </div>
                )}

                {/* Preconditions */}
                {tc.preconditions && (
                  <div>
                    <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Preconditions</span>
                    <p className="text-sm text-gray-700 dark:text-gray-300 mt-1">{tc.preconditions}</p>
                  </div>
                )}

                {/* Test Steps */}
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
                  /* Fallback to Given/When/Then if no steps available */
                  (tc.given || tc.when || tc.then) && (
                    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 font-mono text-sm space-y-2">
                      {tc.given && <p><span className="text-purple-600 font-semibold">Given </span><span className="text-gray-700 dark:text-gray-300">{tc.given}</span></p>}
                      {tc.when && <p><span className="text-blue-600 font-semibold">When </span><span className="text-gray-700 dark:text-gray-300">{tc.when}</span></p>}
                      {tc.then && <p><span className="text-green-600 font-semibold">Then </span><span className="text-gray-700 dark:text-gray-300">{tc.then}</span></p>}
                    </div>
                  )
                )}

                {/* Expected Outcome */}
                {tc.expected_outcome && (
                  <div>
                    <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Expected Outcome</span>
                    <p className="text-sm text-gray-700 dark:text-gray-300 mt-1">{tc.expected_outcome}</p>
                  </div>
                )}

                {/* Metadata row */}
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
                          <span
                            key={tag}
                            className="inline-block px-2 py-0.5 rounded-full bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 text-xs"
                          >
                            {tag}
                          </span>
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
  const [searchParams] = useSearchParams();
  const runId = searchParams.get('run_id');

  const [allTestCases, setAllTestCases] = useState<TestCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [filterType, setFilterType] = useState('all');
  const [filterPriority, setFilterPriority] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  const [searchText, setSearchText] = useState('');

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const toggleSelect = (tcId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(tcId)) next.delete(tcId);
      else next.add(tcId);
      return next;
    });
  };

  const toggleSelectAll = useCallback(() => {
    setSelectedIds((prev) => {
      if (prev.size === filtered.length) {
        return new Set();
      }
      return new Set(filtered.map((tc) => tc.tc_id));
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleBulkApprove = useCallback(async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    try {
      const res = await bulkApproveTestCases(ids);
      setAllTestCases((prev) =>
        prev.map((tc) => (res.data.updated.includes(tc.tc_id) ? { ...tc, status: 'approved' } : tc)),
      );
      setSelectedIds(new Set());
    } catch (err: any) {
      setError(err.message ?? 'Bulk approve failed');
    }
  }, [selectedIds]);

  const handleBulkReject = useCallback(async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    try {
      const res = await bulkRejectTestCases(ids);
      setAllTestCases((prev) =>
        prev.map((tc) => (res.data.updated.includes(tc.tc_id) ? { ...tc, status: 'rejected' } : tc)),
      );
      setSelectedIds(new Set());
    } catch (err: any) {
      setError(err.message ?? 'Bulk reject failed');
    }
  }, [selectedIds]);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const res = runId
          ? await listTestCasesByRun(runId)
          : await listTestCases();
        setAllTestCases(res.data);
        setError(null);
      } catch (err: any) {
        setError(err.message ?? 'Failed to load test cases');
      } finally {
        setLoading(false);
      }
    })();
  }, [runId]);

  const filtered = useMemo(() => {
    return allTestCases.filter((tc) => {
      if (filterType !== 'all' && tc.test_type !== filterType) return false;
      if (filterPriority !== 'all' && tc.priority !== filterPriority) return false;
      if (filterStatus !== 'all' && tc.status !== filterStatus) return false;
      if (searchText && !tc.title.toLowerCase().includes(searchText.toLowerCase())) return false;
      return true;
    });
  }, [allTestCases, filterType, filterPriority, filterStatus, searchText]);

  const handleApprove = async (tcId: string) => {
    try {
      await approveTestCase(tcId);
      setAllTestCases((prev) =>
        prev.map((tc) => (tc.tc_id === tcId ? { ...tc, status: 'approved' } : tc)),
      );
    } catch (err: any) {
      setError(err.message ?? 'Failed to approve test case');
    }
  };

  const handleReject = async (tcId: string) => {
    try {
      await rejectTestCase(tcId);
      setAllTestCases((prev) =>
        prev.map((tc) => (tc.tc_id === tcId ? { ...tc, status: 'rejected' } : tc)),
      );
    } catch (err: any) {
      setError(err.message ?? 'Failed to reject test case');
    }
  };

  const handleSave = async (tcId: string, data: Partial<TestCase>) => {
    try {
      await updateTestCase(tcId, data);
      setAllTestCases((prev) => prev.map((tc) => (tc.tc_id === tcId ? { ...tc, ...data } : tc)));
    } catch (err: any) {
      setError(err.message ?? 'Failed to update test case');
    }
  };

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
        <div
          role="alert"
          className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 rounded-lg flex items-center justify-between"
        >
          <span className="text-sm">{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Test Cases</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">Browse, filter, and manage generated test cases</p>
        </div>
        {filtered.length > 0 && (
          <div className="flex gap-2">
            <button
              onClick={() => exportToCSV(filtered as object[], 'test_cases.csv')}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-gray-300 rounded-md hover:bg-gray-50 dark:border-gray-600 dark:hover:bg-gray-800 focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none"
              aria-label="Export test cases as CSV"
            >
              <Download className="h-4 w-4" aria-hidden="true" /> CSV
            </button>
            <button
              onClick={() => exportToJSON(filtered, 'test_cases.json')}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-gray-300 rounded-md hover:bg-gray-50 dark:border-gray-600 dark:hover:bg-gray-800 focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none"
              aria-label="Export test cases as JSON"
            >
              <Download className="h-4 w-4" aria-hidden="true" /> JSON
            </button>
          </div>
        )}
      </div>

      {/* Filter bar */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
        <div className="flex flex-wrap items-center gap-4">
          <Filter className="h-4 w-4 text-gray-400 dark:text-gray-500 flex-shrink-0" aria-hidden="true" />

          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="rounded-md border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-sm dark:bg-gray-700 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            aria-label="Filter by test type"
          >
            {TEST_TYPES.map((t) => (
              <option key={t} value={t}>
                {t === 'all' ? 'All Types' : t.replace(/_/g, ' ')}
              </option>
            ))}
          </select>

          <select
            value={filterPriority}
            onChange={(e) => setFilterPriority(e.target.value)}
            className="rounded-md border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-sm dark:bg-gray-700 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            aria-label="Filter by priority"
          >
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {p === 'all' ? 'All Priorities' : p}
              </option>
            ))}
          </select>

          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="rounded-md border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-sm dark:bg-gray-700 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            aria-label="Filter by status"
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s === 'all' ? 'All Statuses' : s.charAt(0).toUpperCase() + s.slice(1)}
              </option>
            ))}
          </select>

          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 dark:text-gray-500" />
            <input
              type="text"
              placeholder="Search by title..."
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 pl-9 pr-3 py-1.5 text-sm dark:bg-gray-700 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <span className="text-sm text-gray-500 dark:text-gray-400 flex-shrink-0" aria-live="polite">
            Showing {filtered.length} of {allTestCases.length} test cases
          </span>
        </div>
      </div>

      {/* Table */}
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
              <span className="text-sm font-medium text-indigo-700 dark:text-indigo-300">
                {selectedIds.size} selected
              </span>
              <button
                onClick={handleBulkApprove}
                className="flex items-center gap-1 px-3 py-1 text-sm font-medium text-green-700 bg-green-100 rounded hover:bg-green-200 focus-visible:ring-2 focus-visible:ring-green-500 focus-visible:outline-none"
                aria-label="Approve selected test cases"
              >
                <Check className="h-3.5 w-3.5" aria-hidden="true" /> Approve
              </button>
              <button
                onClick={handleBulkReject}
                className="flex items-center gap-1 px-3 py-1 text-sm font-medium text-red-700 bg-red-100 rounded hover:bg-red-200 focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:outline-none"
                aria-label="Reject selected test cases"
              >
                <XCircle className="h-3.5 w-3.5" aria-hidden="true" /> Reject
              </button>
              <button
                onClick={() => setSelectedIds(new Set())}
                className="ml-auto text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
              >
                Clear selection
              </button>
            </div>
          )}
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-700">
              <tr>
                <th className="px-4 py-3 w-8">
                  <input
                    type="checkbox"
                    checked={filtered.length > 0 && selectedIds.size === filtered.length}
                    onChange={toggleSelectAll}
                    className="h-4 w-4 rounded border-gray-300 dark:border-gray-600 text-indigo-600 focus:ring-indigo-500"
                    aria-label="Select all test cases"
                  />
                </th>
                <th className="px-4 py-3 w-8" />
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  TC ID
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Req ID
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Title
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Type
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Priority
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
              {filtered.map((tc) => (
                <TestCaseRow
                  key={tc.tc_id}
                  tc={tc}
                  expanded={expandedId === tc.tc_id}
                  selected={selectedIds.has(tc.tc_id)}
                  onToggle={() => setExpandedId(expandedId === tc.tc_id ? null : tc.tc_id)}
                  onSelect={toggleSelect}
                  onApprove={handleApprove}
                  onReject={handleReject}
                  onSave={handleSave}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
