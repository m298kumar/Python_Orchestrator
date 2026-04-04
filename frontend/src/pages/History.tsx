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
} from 'lucide-react';
import { listPipelineRuns, getPipelineRun } from '../api/client';
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

export default function History() {
  const [runs, setRuns] = useState<PipelineRunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedRun, setExpandedRun] = useState<string | null>(null);
  const [runDetail, setRunDetail] = useState<PipelineRunStatus | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

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

  // Auto-refresh when any run is in running status
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
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Pipeline History</h1>
        {runs.some((r) => r.status.toLowerCase() === 'running') && (
          <div className="flex items-center gap-2 text-sm text-blue-600">
            <Loader2 className="h-4 w-4 animate-spin" />
            Auto-refreshing
          </div>
        )}
      </div>

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
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
            {runs.map((run) => (
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
                </tr>

                {/* Expanded detail row */}
                {expandedRun === run.run_id && (
                  <tr key={run.run_id + '-detail'}>
                    <td colSpan={7} className="bg-gray-50 dark:bg-gray-700 px-8 py-5">
                      {detailLoading ? (
                        <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
                          <Loader2 className="h-4 w-4 animate-spin" />
                          Loading details...
                        </div>
                      ) : runDetail ? (
                        <div className="space-y-4">
                          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                            {/* Completed stages */}
                            <div>
                              <h4 className="flex items-center gap-2 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-2">
                                <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
                                Completed ({runDetail.stages_completed.length})
                              </h4>
                              {runDetail.stages_completed.length > 0 ? (
                                <ul className="space-y-1">
                                  {runDetail.stages_completed.map((s) => (
                                    <li
                                      key={s}
                                      className="text-sm text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-900/30 rounded px-2 py-1"
                                    >
                                      {s}
                                    </li>
                                  ))}
                                </ul>
                              ) : (
                                <p className="text-sm text-gray-400 dark:text-gray-500">None</p>
                              )}
                            </div>

                            {/* Failed stages */}
                            <div>
                              <h4 className="flex items-center gap-2 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-2">
                                <XCircle className="h-3.5 w-3.5 text-red-500" />
                                Failed ({runDetail.stages_failed.length})
                              </h4>
                              {runDetail.stages_failed.length > 0 ? (
                                <ul className="space-y-1">
                                  {runDetail.stages_failed.map((s) => (
                                    <li
                                      key={s}
                                      className="text-sm text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-900/30 rounded px-2 py-1"
                                    >
                                      {s}
                                    </li>
                                  ))}
                                </ul>
                              ) : (
                                <p className="text-sm text-gray-400 dark:text-gray-500">None</p>
                              )}
                            </div>

                            {/* Skipped stages */}
                            <div>
                              <h4 className="flex items-center gap-2 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-2">
                                <SkipForward className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500" />
                                Skipped ({runDetail.stages_skipped.length})
                              </h4>
                              {runDetail.stages_skipped.length > 0 ? (
                                <ul className="space-y-1">
                                  {runDetail.stages_skipped.map((s) => (
                                    <li
                                      key={s}
                                      className="text-sm text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-600 rounded px-2 py-1"
                                    >
                                      {s}
                                    </li>
                                  ))}
                                </ul>
                              ) : (
                                <p className="text-sm text-gray-400 dark:text-gray-500">None</p>
                              )}
                            </div>
                          </div>

                          {/* Error message */}
                          {runDetail.error_message && (
                            <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg px-4 py-3">
                              <p className="text-xs font-semibold text-red-600 dark:text-red-400 uppercase mb-1">
                                Error
                              </p>
                              <p className="text-sm text-red-800 dark:text-red-300 font-mono whitespace-pre-wrap">
                                {runDetail.error_message}
                              </p>
                            </div>
                          )}

                          {/* Duration + timestamps */}
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

                          {/* Download artifacts */}
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
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
