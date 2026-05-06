import { useEffect, useState, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  ChevronDown,
  ChevronRight,
  Download,
  FileCode,
  GitBranch,
  Loader2,
  TestTubes,
  X,
} from 'lucide-react';
import {
  listApiTests,
  getApiTest,
  listPipelineRuns,
  type ApiTestFile,
  type PipelineRunSummary,
} from '../api/client';
import StatusBadge from '../components/StatusBadge';
import CodeViewer from '../components/CodeViewer';

// ---------------------------------------------------------------------------
// Colour palette (mirrors BddCode.tsx / TestCases.tsx)
// ---------------------------------------------------------------------------

const RUN_COLORS = [
  { bg: 'bg-indigo-50 dark:bg-indigo-900/20', border: 'border-indigo-200 dark:border-indigo-700', header: 'bg-indigo-100 dark:bg-indigo-900/40', text: 'text-indigo-700 dark:text-indigo-300', dot: 'bg-indigo-500', active: 'border-l-indigo-500' },
  { bg: 'bg-emerald-50 dark:bg-emerald-900/20', border: 'border-emerald-200 dark:border-emerald-700', header: 'bg-emerald-100 dark:bg-emerald-900/40', text: 'text-emerald-700 dark:text-emerald-300', dot: 'bg-emerald-500', active: 'border-l-emerald-500' },
  { bg: 'bg-amber-50 dark:bg-amber-900/20', border: 'border-amber-200 dark:border-amber-700', header: 'bg-amber-100 dark:bg-amber-900/40', text: 'text-amber-700 dark:text-amber-300', dot: 'bg-amber-500', active: 'border-l-amber-500' },
  { bg: 'bg-rose-50 dark:bg-rose-900/20', border: 'border-rose-200 dark:border-rose-700', header: 'bg-rose-100 dark:bg-rose-900/40', text: 'text-rose-700 dark:text-rose-300', dot: 'bg-rose-500', active: 'border-l-rose-500' },
  { bg: 'bg-cyan-50 dark:bg-cyan-900/20', border: 'border-cyan-200 dark:border-cyan-700', header: 'bg-cyan-100 dark:bg-cyan-900/40', text: 'text-cyan-700 dark:text-cyan-300', dot: 'bg-cyan-500', active: 'border-l-cyan-500' },
  { bg: 'bg-purple-50 dark:bg-purple-900/20', border: 'border-purple-200 dark:border-purple-700', header: 'bg-purple-100 dark:bg-purple-900/40', text: 'text-purple-700 dark:text-purple-300', dot: 'bg-purple-500', active: 'border-l-purple-500' },
];

const levelColors: Record<string, string> = {
  api: 'running',
  unit: 'running',
  integration: 'generated',
  e2e: 'failed',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function shortRunId(runId: string) { return runId.slice(0, 8); }

function formatTimestamp(ts: string) {
  return new Date(ts).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function languageFromFile(file: ApiTestFile): string {
  if (file.language === 'python' || file.framework === 'pytest_requests') return 'python';
  if (file.language === 'java' || file.framework === 'rest_assured') return 'java';
  if (file.language === 'javascript' || file.framework === 'jest') return 'javascript';
  if (file.framework === 'karate') return 'gherkin';
  const ext = file.filename.split('.').pop()?.toLowerCase();
  if (ext === 'py') return 'python';
  if (ext === 'java') return 'java';
  if (ext === 'js' || ext === 'ts') return 'javascript';
  if (ext === 'feature') return 'gherkin';
  return 'text';
}

// ---------------------------------------------------------------------------
// RunGroup — collapsible section in the left panel
// ---------------------------------------------------------------------------

interface RunGroupProps {
  runId: string;
  label: string;
  startedAt: string;
  colorIdx: number;
  files: ApiTestFile[];
  selectedFilename: string | null;
  defaultOpen: boolean;
  onSelectFile: (f: ApiTestFile) => void;
}

function RunGroup({
  runId, label, startedAt, colorIdx, files, selectedFilename, defaultOpen, onSelectFile,
}: RunGroupProps) {
  const [open, setOpen] = useState(defaultOpen);
  const c = RUN_COLORS[colorIdx % RUN_COLORS.length];
  const totalTests = files.reduce((s, f) => s + f.test_count, 0);

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
            Run {label}{' '}
            <span className="opacity-60 font-normal font-sans">({shortRunId(runId)}…)</span>
          </span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0 ml-2">
          {startedAt && (
            <span className="text-xs text-gray-500 dark:text-gray-400 hidden sm:block">
              {formatTimestamp(startedAt)}
            </span>
          )}
          <span className={`text-xs font-medium px-1.5 py-0.5 rounded-full ${c.bg} ${c.text}`}>
            {files.length} file{files.length !== 1 ? 's' : ''} · {totalTests} tests
          </span>
          {open
            ? <ChevronDown className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500" />
            : <ChevronRight className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500" />
          }
        </div>
      </button>

      {/* File list */}
      {open && (
        <div>
          {files.map((f) => {
            const isSelected = selectedFilename === f.filename;
            return (
              <button
                key={f.filename}
                onClick={() => onSelectFile(f)}
                className={[
                  'w-full text-left px-4 py-2.5 border-t border-gray-100 dark:border-gray-700 transition-colors',
                  isSelected
                    ? `${c.bg} border-l-[3px] ${c.active}`
                    : 'hover:bg-gray-50 dark:hover:bg-gray-700 border-l-[3px] border-l-transparent',
                ].join(' ')}
              >
                <div className="flex items-center gap-2">
                  <FileCode className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500 flex-shrink-0" />
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate font-mono">
                    {f.filename}
                  </span>
                </div>
                <div className="flex items-center gap-3 mt-0.5 text-xs text-gray-500 dark:text-gray-400 pl-5">
                  <span>{f.framework}</span>
                  <span>·</span>
                  <span>{f.language}</span>
                  <span>·</span>
                  <span>{f.test_count} test{f.test_count !== 1 ? 's' : ''}</span>
                  {f.test_level && (
                    <>
                      <span>·</span>
                      <span className="capitalize">{f.test_level}</span>
                    </>
                  )}
                </div>
                {f.endpoint_path && (
                  <div className="mt-0.5 pl-5 text-xs text-gray-400 dark:text-gray-500 font-mono truncate">
                    {f.endpoint_path}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ApiTests Page
// ---------------------------------------------------------------------------

export default function ApiTests() {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlRunId = searchParams.get('run_id') ?? '';

  const [testFiles, setTestFiles] = useState<ApiTestFile[]>([]);
  const [runs, setRuns] = useState<PipelineRunSummary[]>([]);
  const [selectedFilename, setSelectedFilename] = useState<string | null>(null);
  const [selectedContent, setSelectedContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [contentLoading, setContentLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch all test files (no run_id filter — we group client-side)
  // and pipeline runs for metadata
  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [tfRes, rRes] = await Promise.all([
          listApiTests(),      // fetch ALL files across all runs
          listPipelineRuns(),
        ]);
        setTestFiles(tfRes.data);
        setRuns(rRes.data);
      } catch (err: any) {
        if (err.status !== 404) {
          setError(err.message ?? 'Failed to load API tests');
        }
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // When urlRunId changes, auto-select the first file of the (filtered) pool.
  // When data first loads with no run filter, select the first file globally.
  useEffect(() => {
    if (testFiles.length === 0) return;
    const pool = urlRunId
      ? testFiles.filter((f) => f.run_id === urlRunId)
      : testFiles;
    if (pool.length > 0) {
      // On run-switch always pick the first file of that run; on first load only if nothing selected
      const shouldAutoSelect = urlRunId
        ? pool.every((f) => f.filename !== selectedFilename)   // selected file not in this run
        : !selectedFilename;
      if (shouldAutoSelect) selectFile(pool[0]);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlRunId, testFiles]);

  async function selectFile(file: ApiTestFile) {
    setSelectedFilename(file.filename);
    if (file.content) { setSelectedContent(file.content); return; }
    setContentLoading(true);
    try {
      const res = await getApiTest(file.filename);
      const full = res.data;
      setTestFiles((prev) => prev.map((f) => (f.filename === file.filename ? full : f)));
      setSelectedContent(full.content ?? '');
    } catch (err: any) {
      setError(err.message ?? 'Failed to load test file content');
      setSelectedContent(null);
    } finally {
      setContentLoading(false);
    }
  }

  // Build ordered run list (oldest → newest) for consistent colour assignment
  const orderedRunIds = useMemo(() => {
    const seen = new Set<string>();
    const order: string[] = [];
    // Pipeline runs oldest → newest (listPipelineRuns returns newest first, so reverse)
    [...runs].reverse().filter((r) => !r.archived).forEach((r) => {
      if (!seen.has(r.run_id)) { seen.add(r.run_id); order.push(r.run_id); }
    });
    // Also capture any run_ids from files not in the pipeline run list
    testFiles.forEach((f) => {
      if (f.run_id && !seen.has(f.run_id)) { seen.add(f.run_id); order.push(f.run_id); }
    });
    return order;
  }, [runs, testFiles]);

  const archivedRunCount = runs.filter((r) => r.archived).length;

  // Run metadata map: run_id → { colorIdx, label, startedAt }
  const runMeta = useMemo(() => {
    const map = new Map<string, { colorIdx: number; label: string; startedAt: string }>();
    orderedRunIds.forEach((rid, idx) => {
      const run = runs.find((r) => r.run_id === rid);
      map.set(rid, { colorIdx: idx, label: `#${idx + 1}`, startedAt: run?.started_at ?? '' });
    });
    return map;
  }, [orderedRunIds, runs]);

  // Apply URL run filter, then group by run (newest first)
  const filteredFiles = useMemo(() =>
    urlRunId ? testFiles.filter((f) => f.run_id === urlRunId) : testFiles,
    [testFiles, urlRunId],
  );

  const groupedByRun = useMemo(() => {
    const groups = new Map<string, ApiTestFile[]>();
    filteredFiles.forEach((f) => {
      const key = f.run_id ?? '__unknown__';
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(f);
    });
    // Order: newest run first
    const runOrder = [...orderedRunIds].reverse();
    const sorted = new Map<string, ApiTestFile[]>();
    runOrder.forEach((rid) => { if (groups.has(rid)) sorted.set(rid, groups.get(rid)!); });
    if (groups.has('__unknown__')) sorted.set('__unknown__', groups.get('__unknown__')!);
    return sorted;
  }, [filteredFiles, orderedRunIds]);

  // Download selected file
  function handleDownloadFile() {
    if (!selectedContent || !selectedFilename) return;
    const blob = new Blob([selectedContent], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = selectedFilename; a.click();
    window.URL.revokeObjectURL(url);
  }

  // ── Derived stats ──────────────────────────────────────────────────────────
  const totalTests = filteredFiles.reduce((s, f) => s + f.test_count, 0);
  const frameworks = [...new Set(filteredFiles.map((f) => f.framework))];
  const uniqueRuns = groupedByRun.size;

  // ── Loading / error states ─────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
      </div>
    );
  }

  if (!loading && testFiles.length === 0) {
    return (
      <div className="p-6 max-w-7xl mx-auto">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">API Tests</h1>
        <p className="text-gray-500 dark:text-gray-400 mt-1">Generated API test files from all pipeline runs</p>
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-12 text-center mt-8">
          <TestTubes className="h-12 w-12 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
          <p className="text-gray-500 dark:text-gray-400 text-lg font-medium">No API tests generated yet</p>
          <p className="text-gray-400 dark:text-gray-500 text-sm mt-1">
            Run the STLC pipeline with an OpenAPI spec or API paths in requirements.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Error banner */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 rounded-lg flex items-center justify-between">
          <span className="text-sm">{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">API Tests</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            {filteredFiles.length} file{filteredFiles.length !== 1 ? 's' : ''} ·{' '}
            {totalTests} test{totalTests !== 1 ? 's' : ''} across {uniqueRuns} run{uniqueRuns !== 1 ? 's' : ''}
            {urlRunId && (
              <span className="ml-2 text-blue-600 dark:text-blue-400">
                (filtered to 1 run)
              </span>
            )}
            {archivedRunCount > 0 && !urlRunId && (
              <span className="ml-2 text-gray-400 dark:text-gray-500">({archivedRunCount} archived)</span>
            )}
          </p>
        </div>

        {/* Stats pills */}
        <div className="flex gap-4 text-sm">
          <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-4 py-2 text-center min-w-[80px]">
            <div className="text-xl font-bold text-gray-900 dark:text-gray-100">{filteredFiles.length}</div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Files</div>
          </div>
          <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-4 py-2 text-center min-w-[80px]">
            <div className="text-xl font-bold text-gray-900 dark:text-gray-100">{totalTests}</div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Tests</div>
          </div>
          <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-4 py-2 text-center min-w-[80px]">
            <div className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
              {frameworks.length > 0 ? frameworks[0] : '—'}
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Framework</div>
          </div>
        </div>
      </div>

      {/* Run legend pills */}
      {orderedRunIds.length > 0 && (
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mr-1">
              Runs:
            </span>
            {/* "All" pill */}
            <button
              onClick={() => setSearchParams({})}
              className={[
                'inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border transition-colors',
                !urlRunId
                  ? 'bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 border-gray-900 dark:border-gray-100'
                  : 'bg-gray-50 dark:bg-gray-700 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-600 hover:border-gray-400',
              ].join(' ')}
            >
              All runs
            </button>
            {[...orderedRunIds].reverse().map((rid) => {
              const meta = runMeta.get(rid);
              if (!meta) return null;
              const c = RUN_COLORS[meta.colorIdx % RUN_COLORS.length];
              const isActive = urlRunId === rid;
              const count = testFiles.filter((f) => f.run_id === rid).length;
              return (
                <button
                  key={rid}
                  onClick={() => setSearchParams({ run_id: rid })}
                  title={rid}
                  className={[
                    'inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border transition-colors',
                    isActive
                      ? `${c.bg} ${c.text} ${c.border}`
                      : 'bg-gray-50 dark:bg-gray-700 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-600 hover:border-gray-400 dark:hover:border-gray-500',
                  ].join(' ')}
                >
                  <span className={`w-2 h-2 rounded-full ${c.dot}`} />
                  Run {meta.label}
                  <span className="opacity-60">({count})</span>
                  {meta.startedAt && (
                    <span className="opacity-50 hidden sm:inline">
                      · {formatTimestamp(meta.startedAt)}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Two-panel layout */}
      <div className="flex gap-6 min-h-[600px]">
        {/* Left panel — grouped by run */}
        <div className="w-1/3 flex flex-col gap-0">
          <div className="px-1 py-2 mb-1">
            <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
              Test Files by Run
            </h3>
          </div>
          <div className="flex-1 overflow-y-auto space-y-0">
            {[...groupedByRun.entries()].map(([rid, files]) => {
              const meta = rid !== '__unknown__' ? runMeta.get(rid) : undefined;
              const colorIdx = meta?.colorIdx ?? 0;
              const label = meta?.label ?? '?';
              const startedAt = meta?.startedAt ?? '';
              // Auto-expand: run matching URL param, or run containing selected file, or newest
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
                  files={files}
                  selectedFilename={selectedFilename}
                  defaultOpen={isDefault}
                  onSelectFile={selectFile}
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
              <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 min-w-0">
                  <FileCode className="h-4 w-4 text-gray-500 dark:text-gray-400 flex-shrink-0" />
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300 truncate font-mono">
                    {selectedFilename}
                  </span>
                  {/* Run badge */}
                  {(() => {
                    const tf = testFiles.find((f) => f.filename === selectedFilename);
                    const meta = tf?.run_id ? runMeta.get(tf.run_id) : undefined;
                    if (!meta || !tf?.run_id) return null;
                    const c = RUN_COLORS[meta.colorIdx % RUN_COLORS.length];
                    return (
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-mono ${c.bg} ${c.text} flex-shrink-0`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
                        Run {meta.label}
                      </span>
                    );
                  })()}
                  {/* Level badge */}
                  {(() => {
                    const tf = testFiles.find((f) => f.filename === selectedFilename);
                    if (!tf?.test_level) return null;
                    return (
                      <StatusBadge
                        status={levelColors[tf.test_level] ?? tf.test_level}
                        size="sm"
                      />
                    );
                  })()}
                </div>
                <button
                  onClick={handleDownloadFile}
                  className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-medium text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 rounded hover:bg-gray-200 dark:hover:bg-gray-600 flex-shrink-0"
                >
                  <Download className="h-3.5 w-3.5" /> Download
                </button>
              </div>

              {/* File metadata strip */}
              {(() => {
                const tf = testFiles.find((f) => f.filename === selectedFilename);
                if (!tf) return null;
                return (
                  <div className="px-4 py-2 bg-gray-50/60 dark:bg-gray-750 border-b border-gray-100 dark:border-gray-700 flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
                    <span><span className="font-medium text-gray-700 dark:text-gray-300">Framework:</span> {tf.framework}</span>
                    <span><span className="font-medium text-gray-700 dark:text-gray-300">Language:</span> {tf.language}</span>
                    <span><span className="font-medium text-gray-700 dark:text-gray-300">Tests:</span> {tf.test_count}</span>
                    {tf.endpoint_path && (
                      <span className="font-mono truncate"><span className="font-medium text-gray-700 dark:text-gray-300 font-sans">Endpoint:</span> {tf.endpoint_path}</span>
                    )}
                  </div>
                );
              })()}

              {/* Code content */}
              <div className="flex-1 overflow-auto">
                {contentLoading ? (
                  <div className="flex items-center justify-center h-full">
                    <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
                  </div>
                ) : selectedContent != null ? (
                  <CodeViewer
                    code={selectedContent}
                    language={(() => {
                      const tf = testFiles.find((f) => f.filename === selectedFilename);
                      return tf ? languageFromFile(tf) : 'text';
                    })()}
                    filename={selectedFilename}
                  />
                ) : (
                  <p className="p-8 text-center text-gray-500 dark:text-gray-400 text-sm">
                    Failed to load content.
                  </p>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-500 text-sm">
              Select a test file to view its content
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
