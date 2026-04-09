import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Loader2,
  AlertCircle,
  History as HistoryIcon,
  ChevronDown,
  ChevronRight,
  Download,
  Clock,
  CheckCircle2,
  XCircle,
  SkipForward,
  Archive,
  RotateCcw,
  Trash2,
  Trash,
  CalendarClock,
} from 'lucide-react';
import {
  listPipelineRuns,
  getPipelineRun,
  archiveRun,
  restoreRun,
  deleteRun,
  clearAllRuns,
} from '../api/client';
import type { PipelineRunSummary, PipelineRunStatus } from '../api/client';
import StatusBadge from '../components/StatusBadge';

function formatDuration(seconds?: number): string {
  if (seconds == null) return '-';
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(0);
  return `${m}m ${s}s`;
}

function formatTimestamp(ts: string): string {
  return new Date(ts).toLocaleString();
}

function daysSince(ts: string): number {
  const diff = Date.now() - new Date(ts).getTime();
  return Math.floor(diff / (1000 * 60 * 60 * 24));
}

function ageBadge(startedAt: string): { label: string; cls: string } {
  const d = daysSince(startedAt);
  if (d === 0) return { label: 'Today', cls: 'text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/30' };
  if (d === 1) return { label: '1d ago', cls: 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30' };
  if (d < 7) return { label: `${d}d ago`, cls: 'text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-900/30' };
  if (d < 30) return { label: `${d}d ago`, cls: 'text-orange-600 dark:text-orange-400 bg-orange-50 dark:bg-orange-900/30' };
  return { label: `${d}d ago`, cls: 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/30' };
}

export default function History() {
  const [runs, setRuns] = useState<PipelineRunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedRun, setExpandedRun] = useState<string | null>(null);
  const [runDetail, setRunDetail] = useState<PipelineRunStatus | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const activeRuns = runs.filter((r) => !r.archived);
  const archivedRuns = runs.filter((r) => r.archived);

  const fetchRuns = useCallback(async () => {
    try {
      const res = await listPipelineRuns();
      setRuns(res.data);
      setError(null);
    } catch (err: any) {
      if (!runs.length) {
        setError(err.message ?? 'Failed to load pipeline runs');
      }
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    fetchRuns().finally(() => setLoading(false));
  }, [fetchRuns]);

  useEffect(() => {
    const hasRunning = runs.some((r) => r.status.toLowerCase() === 'running');
    if (hasRunning) {
      pollRef.current = setInterval(fetchRuns, 10000);
    } else if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [runs, fetchRuns]);

  async function handleExpand(runId: string) {
    if (expandedRun === runId) {
      setExpandedRun(null);
      setRunDetail(null);
      return;
    }
    setExpandedRun(runId);
    setDetailLoading(true);
    try {
      const res = await getPipelineRun(runId);
      setRunDetail(res.data);
    } catch {
      setRunDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleArchive(runId: string) {
    setActionLoading(runId);
    try {
      await archiveRun(runId);
      setRuns((prev) => prev.map((r) => r.run_id === runId ? { ...r, archived: true, archived_at: new Date().toISOString() } : r));
      if (expandedRun === runId) { setExpandedRun(null); setRunDetail(null); }
    } catch (err: any) { setError(err.message ?? 'Failed to archive run'); }
    finally { setActionLoading(null); }
  }

  async function handleRestore(runId: string) {
    setActionLoading(runId);
    try {
      await restoreRun(runId);
      setRuns((prev) => prev.map((r) => r.run_id === runId ? { ...r, archived: false, archived_at: undefined } : r));
    } catch (err: any) { setError(err.message ?? 'Failed to restore run'); }
    finally { setActionLoading(null); }
  }

  async function handleDelete(runId: string) {
    setActionLoading(runId);
    try {
      await deleteRun(runId);
      setRuns((prev) => prev.filter((r) => r.run_id !== runId));
      if (expandedRun === runId) { setExpandedRun(null); setRunDetail(null); }
    } catch (err: any) { setError(err.message ?? 'Failed to delete run'); }
    finally { setActionLoading(null); }
  }

  async function handleClearAll() {
    setActionLoading('clear-all');
    try {
      const res = await clearAllRuns();
      setRuns((prev) => prev.filter((r) => r.status.toLowerCase() === 'running' || r.status.toLowerCase() === 'pending'));
      setConfirmClear(false);
      if (res.data.deleted > 0) setError(null);
    } catch (err: any) { setError(err.message ?? 'Failed to clear all runs'); }
    finally { setActionLoading(null); }
  }

  function renderDetailRow(run: PipelineRunSummary) {
    return (
      <>
        <tr
          key={run.run_id}
          onClick={() => handleExpand(run.run_id)}
          className="cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
        >
          <td className="px-4 py-3">
            {expandedRun === run.run_id ? (
              <ChevronDown className="h-4 w-4 text-gray-400 dark:text-gray-500" />
            ) : (
              <ChevronRight className="h-4 w-4 text-gray-400 dark:text-gray-500" />
            )}
          </td>
          <td className="px-4 py-3 font-mono text-xs">{run.run_id.slice(0, 12)}...</td>
          <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{run.pipeline_name}</td>
          <td className="px-4 py-3">
            <StatusBadge status={run.status} size="sm" />
          </td>
          <td className="px-4 py-3 text-right font-medium">{run.stages_completed_count}</td>
          <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400">
            {formatDuration(run.total_duration_seconds)}
          </td>
          <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{formatTimestamp(run.started_at)}</td>
          <td className="px-4 py-3">
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${ageBadge(run.started_at).cls}`}>
              <CalendarClock className="h-3 w-3" />
              {ageBadge(run.started_at).label}
            </span>
          </td>
          <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-1">
              {!run.archived ? (
                <button
                  onClick={() => handleArchive(run.run_id)}
                  disabled={actionLoading === run.run_id}
                  className="p-1 rounded text-gray-400 hover:text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-900/30 disabled:opacity-40"
                  title="Archive"
                >
                  {actionLoading === run.run_id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Archive className="h-4 w-4" />}
                </button>
              ) : (
                <button
                  onClick={() => handleRestore(run.run_id)}
                  disabled={actionLoading === run.run_id}
                  className="p-1 rounded text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/30 disabled:opacity-40"
                  title="Restore"
                >
                  {actionLoading === run.run_id ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
                </button>
              )}
              <button
                onClick={() => handleDelete(run.run_id)}
                disabled={actionLoading === run.run_id}
                className="p-1 rounded text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 disabled:opacity-40"
                title="Delete"
              >
                {actionLoading === run.run_id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              </button>
            </div>
          </td>
        </tr>

        {expandedRun === run.run_id && (
          <tr key={run.run_id + '-detail'}>
            <td colSpan={9} className="bg-gray-50 dark:bg-gray-700 px-8 py-5">
              {detailLoading ? (
                <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading details...
                </div>
              ) : runDetail ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div>
                      <h4 className="flex items-center gap-2 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-2">
                        <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
                        Completed ({runDetail.stages_completed.length})
                      </h4>
                      {runDetail.stages_completed.length > 0 ? (
                        <ul className="space-y-1">
                          {runDetail.stages_completed.map((s) => (
                            <li key={s} className="text-sm text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-900/30 rounded px-2 py-1">
                              {s}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-sm text-gray-400 dark:text-gray-500">None</p>
                      )}
                    </div>

                    <div>
                      <h4 className="flex items-center gap-2 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-2">
                        <XCircle className="h-3.5 w-3.5 text-red-500" />
                        Failed ({runDetail.stages_failed.length})
                      </h4>
                      {runDetail.stages_failed.length > 0 ? (
                        <ul className="space-y-1">
                          {runDetail.stages_failed.map((s) => (
                            <li key={s} className="text-sm text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-900/30 rounded px-2 py-1">
                              {s}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-sm text-gray-400 dark:text-gray-500">None</p>
                      )}
                    </div>

                    <div>
                      <h4 className="flex items-center gap-2 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-2">
                        <SkipForward className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500" />
                        Skipped ({runDetail.stages_skipped.length})
                      </h4>
                      {runDetail.stages_skipped.length > 0 ? (
                        <ul className="space-y-1">
                          {runDetail.stages_skipped.map((s) => (
                            <li key={s} className="text-sm text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-600 rounded px-2 py-1">
                              {s}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-sm text-gray-400 dark:text-gray-500">None</p>
                      )}
                    </div>
                  </div>

                  {runDetail.error_message && (
                    <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg px-4 py-3">
                      <p className="text-xs font-semibold text-red-600 dark:text-red-400 uppercase mb-1">Error</p>
                      <p className="text-sm text-red-800 dark:text-red-300 font-mono whitespace-pre-wrap">
                        {runDetail.error_message}
                      </p>
                    </div>
                  )}

                  <div className="flex items-center gap-6 text-sm text-gray-600 dark:text-gray-400">
                    <span className="flex items-center gap-1.5">
                      <Clock className="h-4 w-4" />
                      Total: {formatDuration(runDetail.total_duration_seconds)}
                    </span>
                    <span>Started: {formatTimestamp(runDetail.started_at)}</span>
                    {runDetail.completed_at && (
                      <span>Completed: {formatTimestamp(runDetail.completed_at)}</span>
                    )}
                  </div>

                  <a
                    href={`/api/artifacts/${runDetail.run_id}/download`}
                    className="inline-flex items-center gap-2 px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                  >
                    <Download className="h-4 w-4" />
                    Download Artifacts
                  </a>
                </div>
              ) : (
                <p className="text-sm text-gray-500 dark:text-gray-400">Failed to load run details.</p>
              )}
            </td>
          </tr>
        )}
      </>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
        <span className="ml-3 text-gray-500 dark:text-gray-400">Loading pipeline history...</span>
      </div>
    );
  }

  if (error && runs.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-red-600">
        <AlertCircle className="h-6 w-6 mr-2" />
        {error}
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-gray-500 dark:text-gray-400">
        <HistoryIcon className="h-12 w-12 mb-3 text-gray-300 dark:text-gray-600" />
        <p className="text-lg font-medium">No pipeline runs yet.</p>
        <p className="text-sm mt-1">Trigger a pipeline run from the Dashboard to get started.</p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {error && (
        <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 rounded-lg flex items-center justify-between">
          <span className="text-sm">{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600"><XCircle className="h-4 w-4" /></button>
        </div>
      )}

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Pipeline History</h1>
        <div className="flex items-center gap-3">
          {runs.some((r) => r.status.toLowerCase() === 'running') && (
            <div className="flex items-center gap-2 text-sm text-blue-600">
              <Loader2 className="h-4 w-4 animate-spin" />
              Auto-refreshing
            </div>
          )}
          {activeRuns.length > 0 && (
            <button
              onClick={() => setConfirmClear(true)}
              disabled={actionLoading === 'clear-all'}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-red-600 dark:text-red-400 border border-red-200 dark:border-red-800 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/30 disabled:opacity-40"
            >
              {actionLoading === 'clear-all' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash className="h-4 w-4" />}
              Clear All
            </button>
          )}
        </div>
      </div>

      {confirmClear && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
            <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-2">Clear All Runs?</h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">
              This will permanently delete <strong>{activeRuns.length} terminal run{activeRuns.length !== 1 ? 's' : ''}</strong> and all associated artifacts.
            </p>
            <p className="text-xs text-red-600 dark:text-red-400 mb-6">
              Running and pending runs will be preserved. This cannot be undone.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setConfirmClear(false)}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600"
              >
                Cancel
              </button>
              <button
                onClick={handleClearAll}
                disabled={actionLoading === 'clear-all'}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-40"
              >
                {actionLoading === 'clear-all' ? <Loader2 className="h-4 w-4 animate-spin inline mr-1" /> : null}
                Delete All
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Active runs table */}
      {activeRuns.length > 0 ? (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 dark:bg-gray-700 border-b border-gray-200 dark:border-gray-700 text-left text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                <th className="px-4 py-3 w-8" />
                <th className="px-4 py-3">Run ID</th>
                <th className="px-4 py-3">Pipeline</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Stages</th>
                <th className="px-4 py-3 text-right">Duration</th>
                <th className="px-4 py-3">Started At</th>
                <th className="px-4 py-3">Age</th>
                <th className="px-4 py-3 w-24">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
              {activeRuns.map(renderDetailRow)}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-8 text-center text-gray-500 dark:text-gray-400">
          No active runs. All runs have been archived or deleted.
        </div>
      )}

      {/* Archived section */}
      {archivedRuns.length > 0 && (
        <div>
          <button
            onClick={() => setShowArchived(!showArchived)}
            className="flex items-center gap-2 text-sm font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 mb-3"
          >
            {showArchived ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            <Archive className="h-4 w-4" />
            {archivedRuns.length} archived run{archivedRuns.length !== 1 ? 's' : ''}
          </button>

          {showArchived && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden opacity-75">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 dark:bg-gray-700 border-b border-gray-200 dark:border-gray-700 text-left text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    <th className="px-4 py-3 w-8" />
                    <th className="px-4 py-3">Run ID</th>
                    <th className="px-4 py-3">Pipeline</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3 text-right">Stages</th>
                    <th className="px-4 py-3 text-right">Duration</th>
                    <th className="px-4 py-3">Started At</th>
                    <th className="px-4 py-3">Archived</th>
                    <th className="px-4 py-3 w-24">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                  {archivedRuns.map((run) => (
                    <tr key={run.run_id} className="cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
                      <td className="px-4 py-3">
                        {expandedRun === run.run_id ? (
                          <ChevronDown className="h-4 w-4 text-gray-400 dark:text-gray-500" />
                        ) : (
                          <ChevronRight className="h-4 w-4 text-gray-400 dark:text-gray-500" />
                        )}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">{run.run_id.slice(0, 12)}...</td>
                      <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{run.pipeline_name}</td>
                      <td className="px-4 py-3">
                        <StatusBadge status={run.status} size="sm" />
                      </td>
                      <td className="px-4 py-3 text-right font-medium">{run.stages_completed_count}</td>
                      <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400">
                        {formatDuration(run.total_duration_seconds)}
                      </td>
                      <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{formatTimestamp(run.started_at)}</td>
                      <td className="px-4 py-3">
                        {run.archived_at && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-700">
                            <CalendarClock className="h-3 w-3" />
                            {daysSince(run.archived_at)}d ago
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleRestore(run.run_id)}
                            disabled={actionLoading === run.run_id}
                            className="p-1 rounded text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/30 disabled:opacity-40"
                            title="Restore"
                          >
                            {actionLoading === run.run_id ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
                          </button>
                          <button
                            onClick={() => handleDelete(run.run_id)}
                            disabled={actionLoading === run.run_id}
                            className="p-1 rounded text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 disabled:opacity-40"
                            title="Delete"
                          >
                            {actionLoading === run.run_id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
