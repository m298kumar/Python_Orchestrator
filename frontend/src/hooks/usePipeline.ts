import { useState, useCallback } from 'react';
import {
  listPipelineRuns,
  triggerPipelineRun,
  getPipelineRun,
  type PipelineRunRequest,
  type PipelineRunSummary,
  type PipelineRunStatus,
} from '../api/client';

interface UsePipelineReturn {
  runs: PipelineRunSummary[];
  currentRun: PipelineRunStatus | null;
  loading: boolean;
  error: string | null;
  triggerRun: (req: PipelineRunRequest) => Promise<PipelineRunStatus | null>;
  refreshRuns: () => Promise<void>;
  selectRun: (runId: string) => Promise<void>;
}

export function usePipeline(): UsePipelineReturn {
  const [runs, setRuns] = useState<PipelineRunSummary[]>([]);
  const [currentRun, setCurrentRun] = useState<PipelineRunStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshRuns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listPipelineRuns();
      setRuns(res.data);
    } catch (err: any) {
      setError(err.message ?? 'Failed to fetch pipeline runs');
    } finally {
      setLoading(false);
    }
  }, []);

  const selectRun = useCallback(async (runId: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await getPipelineRun(runId);
      setCurrentRun(res.data);
    } catch (err: any) {
      setError(err.message ?? 'Failed to fetch pipeline run details');
    } finally {
      setLoading(false);
    }
  }, []);

  const triggerRun = useCallback(async (req: PipelineRunRequest): Promise<PipelineRunStatus | null> => {
    setLoading(true);
    setError(null);
    try {
      const res = await triggerPipelineRun(req);
      setCurrentRun(res.data);
      // Refresh the list so it includes the newly created run.
      await refreshRuns();
      return res.data;
    } catch (err: any) {
      setError(err.message ?? 'Failed to trigger pipeline run');
      return null;
    } finally {
      setLoading(false);
    }
  }, [refreshRuns]);

  return { runs, currentRun, loading, error, triggerRun, refreshRuns, selectRun };
}
