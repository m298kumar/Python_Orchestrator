import { useState, useCallback } from 'react';
import {
  listRequirements,
  uploadRequirements,
  updateRequirement,
  type Requirement,
} from '../api/client';

interface UseRequirementsReturn {
  requirements: Requirement[];
  loading: boolean;
  error: string | null;
  upload: (file: File) => Promise<boolean>;
  refresh: () => Promise<void>;
  update: (reqId: string, data: Partial<Requirement>) => Promise<boolean>;
}

export function useRequirements(): UseRequirementsReturn {
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listRequirements();
      setRequirements(res.data);
    } catch (err: any) {
      setError(err.message ?? 'Failed to fetch requirements');
    } finally {
      setLoading(false);
    }
  }, []);

  const upload = useCallback(async (file: File): Promise<boolean> => {
    setLoading(true);
    setError(null);
    try {
      await uploadRequirements(file);
      // Refresh the list so newly uploaded requirements appear immediately.
      await refresh();
      return true;
    } catch (err: any) {
      setError(err.message ?? 'Failed to upload requirements');
      return false;
    } finally {
      setLoading(false);
    }
  }, [refresh]);

  const update = useCallback(async (reqId: string, data: Partial<Requirement>): Promise<boolean> => {
    setLoading(true);
    setError(null);
    try {
      await updateRequirement(reqId, data);
      // Patch the local list optimistically so the UI reflects the change
      // without a full server round-trip.
      setRequirements((prev) =>
        prev.map((r) => (r.req_id === reqId ? { ...r, ...data } : r)),
      );
      return true;
    } catch (err: any) {
      setError(err.message ?? 'Failed to update requirement');
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  return { requirements, loading, error, upload, refresh, update };
}
