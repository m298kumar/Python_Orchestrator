import { useEffect, useState, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  ChevronDown,
  ChevronRight,
  Code,
  Download,
  FileCode,
  GitBranch,
  Loader2,
  Package,
  X,
} from 'lucide-react';
import {
  listFeatures,
  listPipelineRuns,
  getFeature,
  downloadBddProject,
  type FeatureFile,
  type PipelineRunSummary,
} from '../api/client';

// ---------------------------------------------------------------------------
// Colour palette (mirrors TestCases.tsx)
// ---------------------------------------------------------------------------

const RUN_COLORS = [
  { bg: 'bg-indigo-50 dark:bg-indigo-900/20', border: 'border-indigo-200 dark:border-indigo-700', header: 'bg-indigo-100 dark:bg-indigo-900/40', text: 'text-indigo-700 dark:text-indigo-300', dot: 'bg-indigo-500', active: 'border-l-indigo-500' },
  { bg: 'bg-emerald-50 dark:bg-emerald-900/20', border: 'border-emerald-200 dark:border-emerald-700', header: 'bg-emerald-100 dark:bg-emerald-900/40', text: 'text-emerald-700 dark:text-emerald-300', dot: 'bg-emerald-500', active: 'border-l-emerald-500' },
  { bg: 'bg-amber-50 dark:bg-amber-900/20', border: 'border-amber-200 dark:border-amber-700', header: 'bg-amber-100 dark:bg-amber-900/40', text: 'text-amber-700 dark:text-amber-300', dot: 'bg-amber-500', active: 'border-l-amber-500' },
  { bg: 'bg-rose-50 dark:bg-rose-900/20', border: 'border-rose-200 dark:border-rose-700', header: 'bg-rose-100 dark:bg-rose-900/40', text: 'text-rose-700 dark:text-rose-300', dot: 'bg-rose-500', active: 'border-l-rose-500' },
  { bg: 'bg-cyan-50 dark:bg-cyan-900/20', border: 'border-cyan-200 dark:border-cyan-700', header: 'bg-cyan-100 dark:bg-cyan-900/40', text: 'text-cyan-700 dark:text-cyan-300', dot: 'bg-cyan-500', active: 'border-l-cyan-500' },
  { bg: 'bg-purple-50 dark:bg-purple-900/20', border: 'border-purple-200 dark:border-purple-700', header: 'bg-purple-100 dark:bg-purple-900/40', text: 'text-purple-700 dark:text-purple-300', dot: 'bg-purple-500', active: 'border-l-purple-500' },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function shortRunId(runId: string) { return runId.slice(0, 8); }

function formatTimestamp(ts: string) {
  return new Date(ts).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

// ---------------------------------------------------------------------------
// Gherkin Viewer
// ---------------------------------------------------------------------------

function GherkinViewer({ content }: { content: string }) {
  const lines = content.split('\n');
  return (
    <pre className="text-sm leading-relaxed font-mono overflow-auto">
      {lines.map((line, i) => {
        const trimmed = line.trimStart();
        let cls = 'text-gray-700 dark:text-gray-300';
        if (trimmed.startsWith('Feature:')) cls = 'text-indigo-700 dark:text-indigo-400 font-bold';
        else if (trimmed.startsWith('Scenario:') || trimmed.startsWith('Scenario Outline:') || trimmed.startsWith('Background:'))
          cls = 'text-blue-700 dark:text-blue-400 font-semibold';
        else if (/^(Given|When|Then|And|But) /.test(trimmed)) cls = 'text-green-700 dark:text-green-400';
        else if (trimmed.startsWith('@')) cls = 'text-purple-600 dark:text-purple-400';
        else if (trimmed.startsWith('#')) cls = 'text-gray-400 dark:text-gray-500 italic';
        else if (trimmed.startsWith('Examples:')) cls = 'text-amber-700 dark:text-amber-400 font-semibold';
        else if (trimmed.startsWith('|')) cls = 'text-gray-600 dark:text-gray-400';
        return (
          <div key={i} className="flex">
            <span className="inline-block w-10 text-right pr-3 text-gray-300 dark:text-gray-600 select-none">{i + 1}</span>
            <span className={cls}>{line}</span>
          </div>
        );
      })}
    </pre>
  );
}

// ---------------------------------------------------------------------------
// Run Group — collapsible section in the left panel
// ---------------------------------------------------------------------------

interface RunGroupProps {
  runId: string;
  label: string;
  startedAt: string;
  colorIdx: number;
  features: FeatureFile[];
  selectedFilename: string | null;
  defaultOpen: boolean;
  onSelectFeature: (f: FeatureFile) => void;
}

function RunGroup({ runId, label, startedAt, colorIdx, features, selectedFilename, defaultOpen, onSelectFeature }: RunGroupProps) {
  const [open, setOpen] = useState(defaultOpen);
  const c = RUN_COLORS[colorIdx % RUN_COLORS.length];

  // Re-open when this group becomes the active target (URL param changed without remount)
  useEffect(() => {
    if (defaultOpen) setOpen(true);
  }, [defaultOpen]);

  return (
    <div className={`border rounded-lg overflow-hidden mb-2 ${c.border}`}>
      {/* Group header */}
      <button
        onClick={() => setOpen((v) => !v)}
        className={`w-full flex items-center justify-between px-3 py-2 ${c.header} transition-colors`}
        aria-expanded={open}
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${c.dot}`} />
          <GitBranch className={`h-3.5 w-3.5 flex-shrink-0 ${c.text}`} />
          <span className={`text-xs font-semibold font-mono ${c.text}`} title={runId}>
            Run {label} <span className="opacity-60 font-normal font-sans">({shortRunId(runId)}…)</span>
          </span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0 ml-2">
          {startedAt && (
            <span className="text-xs text-gray-500 dark:text-gray-400 hidden sm:block">
              {formatTimestamp(startedAt)}
            </span>
          )}
          <span className={`text-xs font-medium px-1.5 py-0.5 rounded-full ${c.bg} ${c.text}`}>
            {features.length}
          </span>
          {open
            ? <ChevronDown className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500" />
            : <ChevronRight className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500" />}
        </div>
      </button>

      {/* Feature file list */}
      {open && (
        <div>
          {features.map((f) => {
            const isSelected = selectedFilename === f.filename;
            return (
              <button
                key={f.filename}
                onClick={() => onSelectFeature(f)}
                className={[
                  'w-full text-left px-4 py-2.5 border-t border-gray-100 dark:border-gray-700 transition-colors',
                  isSelected
                    ? `${c.bg} border-l-[3px] ${c.active}`
                    : 'hover:bg-gray-50 dark:hover:bg-gray-700 border-l-[3px] border-l-transparent',
                ].join(' ')}
              >
                <div className="flex items-center gap-2">
                  <FileCode className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500 flex-shrink-0" />
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                    {f.filename}
                  </span>
                </div>
                <div className="flex items-center gap-3 mt-0.5 text-xs text-gray-500 dark:text-gray-400 pl-5">
                  <span>Req: {f.req_id}</span>
                  <span>{f.scenario_count} scenario{f.scenario_count !== 1 ? 's' : ''}</span>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// BddCode Page
// ---------------------------------------------------------------------------

export default function BddCode() {
  const [searchParams] = useSearchParams();
  const urlRunId = searchParams.get('run_id') ?? '';

  const [features, setFeatures] = useState<FeatureFile[]>([]);
  const [runs, setRuns] = useState<PipelineRunSummary[]>([]);
  const [selectedFilename, setSelectedFilename] = useState<string | null>(null);
  const [selectedContent, setSelectedContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [contentLoading, setContentLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectFeature = async (f: FeatureFile) => {
    setSelectedFilename(f.filename);
    if (f.content) { setSelectedContent(f.content); return; }
    setContentLoading(true);
    try {
      const res = await getFeature(f.filename);
      setSelectedContent(res.data.content ?? '');
    } catch (err: any) {
      setError(err.message ?? 'Failed to load feature content');
      setSelectedContent(null);
    } finally {
      setContentLoading(false);
    }
  };

  // Fetch ALL features once on mount — grouping/filtering is done client-side via useMemo.
  // urlRunId only controls which RunGroup is auto-expanded; no server re-fetch needed.
  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const [fRes, rRes] = await Promise.all([
          listFeatures(),          // no run_id — load everything
          listPipelineRuns(),
        ]);
        setFeatures(fRes.data);
        setRuns(rRes.data);
        // Auto-select the first file (preferring the urlRunId run if set)
        if (fRes.data.length > 0 && !selectedFilename) {
          const pool = urlRunId
            ? fRes.data.filter((f) => f.run_id === urlRunId)
            : fRes.data;
          selectFeature((pool.length > 0 ? pool : fRes.data)[0]);
        }
        setError(null);
      } catch (err: any) {
        setError(err.message ?? 'Failed to load features');
      } finally {
        setLoading(false);
      }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Build ordered run list oldest→newest for consistent colour assignment
  const orderedRunIds = useMemo(() => {
    const seen = new Set<string>();
    const order: string[] = [];
    [...runs].reverse().filter((r) => !r.archived).forEach((r) => {
      if (!seen.has(r.run_id)) { seen.add(r.run_id); order.push(r.run_id); }
    });
    features.forEach((f) => {
      if (f.run_id && !seen.has(f.run_id)) { seen.add(f.run_id); order.push(f.run_id); }
    });
    return order;
  }, [runs, features]);

  const archivedRunCount = runs.filter((r) => r.archived).length;

  // Build run metadata map
  const runMeta = useMemo(() => {
    const map = new Map<string, { colorIdx: number; label: string; startedAt: string }>();
    orderedRunIds.forEach((rid, idx) => {
      const run = runs.find((r) => r.run_id === rid);
      map.set(rid, { colorIdx: idx, label: `#${idx + 1}`, startedAt: run?.started_at ?? '' });
    });
    return map;
  }, [orderedRunIds, runs]);

  // Group features by run_id (preserving orderedRunIds order, newest first for display)
  const groupedByRun = useMemo(() => {
    const groups = new Map<string, FeatureFile[]>();
    features.forEach((f) => {
      const key = f.run_id ?? '__unknown__';
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(f);
    });
    // Order groups: newest run first (reverse of orderedRunIds)
    const runOrder = [...orderedRunIds].reverse();
    const sorted = new Map<string, FeatureFile[]>();
    runOrder.forEach((rid) => { if (groups.has(rid)) sorted.set(rid, groups.get(rid)!); });
    // Append any unknown group at the end
    if (groups.has('__unknown__')) sorted.set('__unknown__', groups.get('__unknown__')!);
    return sorted;
  }, [features, orderedRunIds]);

  const handleDownloadFile = () => {
    if (!selectedContent || !selectedFilename) return;
    const blob = new Blob([selectedContent], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = selectedFilename; a.click();
    window.URL.revokeObjectURL(url);
  };

  const handleDownloadProject = async () => {
    try {
      const res = await downloadBddProject();
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url; a.download = 'bdd_project.zip'; a.click();
      window.URL.revokeObjectURL(url);
    } catch (err: any) { setError(err.message ?? 'Failed to download BDD project'); }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
      </div>
    );
  }

  if (features.length === 0) {
    return (
      <div className="p-6 max-w-7xl mx-auto">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">BDD Code</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">View and download generated feature files</p>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-12 text-center mt-8">
          <Code className="h-12 w-12 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
          <p className="text-gray-500 dark:text-gray-400 text-lg font-medium">No BDD features generated yet</p>
          <p className="text-gray-400 dark:text-gray-500 text-sm mt-1">Run the BDD pipeline stage to generate feature files.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {error && (
        <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 rounded-lg flex items-center justify-between">
          <span className="text-sm">{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600"><X className="h-4 w-4" /></button>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">BDD Code</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            {features.length} feature file{features.length !== 1 ? 's' : ''} across {groupedByRun.size} run{groupedByRun.size !== 1 ? 's' : ''}
            {archivedRunCount > 0 && (
              <span className="ml-2 text-gray-400 dark:text-gray-500">({archivedRunCount} archived)</span>
            )}
          </p>
        </div>
        <button onClick={handleDownloadProject}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700">
          <Package className="h-4 w-4" /> Download Project
        </button>
      </div>

      {/* Two-panel layout */}
      <div className="flex gap-6 min-h-[600px]">
        {/* Left panel — grouped by run */}
        <div className="w-1/3 flex flex-col gap-0">
          <div className="px-1 py-2 mb-1">
            <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
              Feature Files by Run
            </h3>
          </div>
          <div className="flex-1 overflow-y-auto space-y-0">
            {[...groupedByRun.entries()].map(([rid, files]) => {
              const meta = rid !== '__unknown__' ? runMeta.get(rid) : undefined;
              const colorIdx = meta?.colorIdx ?? 0;
              const label = meta?.label ?? '?';
              const startedAt = meta?.startedAt ?? '';
              // Auto-expand the run that contains the currently selected file,
              // or the run matching the URL param, or the newest run (first in list)
              const isDefault =
                urlRunId === rid ||
                files.some((f) => f.filename === selectedFilename) ||
                ([...groupedByRun.keys()][0] === rid && !urlRunId);

              return (
                <RunGroup
                  key={rid}
                  runId={rid === '__unknown__' ? 'unknown' : rid}
                  label={rid === '__unknown__' ? '?' : label}
                  startedAt={startedAt}
                  colorIdx={colorIdx}
                  features={files}
                  selectedFilename={selectedFilename}
                  defaultOpen={isDefault}
                  onSelectFeature={selectFeature}
                />
              );
            })}
          </div>
        </div>

        {/* Right panel — code viewer */}
        <div className="flex-1 bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden flex flex-col">
          {selectedFilename ? (
            <>
              {/* Viewer header */}
              <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
                <div className="flex items-center gap-2 min-w-0">
                  <FileCode className="h-4 w-4 text-gray-500 dark:text-gray-400 flex-shrink-0" />
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300 truncate">
                    {selectedFilename}
                  </span>
                  {/* Show which run this file belongs to */}
                  {(() => {
                    const ff = features.find((f) => f.filename === selectedFilename);
                    const meta = ff?.run_id ? runMeta.get(ff.run_id) : undefined;
                    if (!meta || !ff?.run_id) return null;
                    const c = RUN_COLORS[meta.colorIdx % RUN_COLORS.length];
                    return (
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-mono ${c.bg} ${c.text} flex-shrink-0`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
                        Run {meta.label}
                      </span>
                    );
                  })()}
                </div>
                <button onClick={handleDownloadFile}
                  className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-medium text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 rounded hover:bg-gray-200 dark:hover:bg-gray-600 flex-shrink-0">
                  <Download className="h-3.5 w-3.5" /> Download
                </button>
              </div>
              <div className="flex-1 overflow-auto p-4 bg-gray-900/[0.02]">
                {contentLoading ? (
                  <div className="flex items-center justify-center h-full">
                    <Loader2 className="h-6 w-6 animate-spin text-indigo-500" />
                  </div>
                ) : selectedContent != null ? (
                  <GherkinViewer content={selectedContent} />
                ) : (
                  <p className="text-gray-500 dark:text-gray-400 text-sm">Failed to load content.</p>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-500 text-sm">
              Select a feature file to view its content
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
