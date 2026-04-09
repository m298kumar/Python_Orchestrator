import { useState, useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  AlertCircle,
  ArrowRight,
  ClipboardList,
  Clock,
  FileText,
  GitBranch,
  Globe,
  Layers,
  Link as LinkIcon,
  Loader2,
  X,
} from 'lucide-react';
import {
  getSiteModel,
  listCrawlerPages,
  listCrawlerRuns,
  listPipelineRuns,
  type SiteModelResponse,
  type PageSummary,
  type PipelineRunSummary,
} from '../api/client';

// ---------------------------------------------------------------------------
// Colour palette (mirrors other pages)
// ---------------------------------------------------------------------------

const RUN_COLORS = [
  { bg: 'bg-indigo-100 dark:bg-indigo-900/40', text: 'text-indigo-700 dark:text-indigo-300', dot: 'bg-indigo-500', ring: 'ring-indigo-400' },
  { bg: 'bg-emerald-100 dark:bg-emerald-900/40', text: 'text-emerald-700 dark:text-emerald-300', dot: 'bg-emerald-500', ring: 'ring-emerald-400' },
  { bg: 'bg-amber-100 dark:bg-amber-900/40', text: 'text-amber-700 dark:text-amber-300', dot: 'bg-amber-500', ring: 'ring-amber-400' },
  { bg: 'bg-rose-100 dark:bg-rose-900/40', text: 'text-rose-700 dark:text-rose-300', dot: 'bg-rose-500', ring: 'ring-rose-400' },
  { bg: 'bg-cyan-100 dark:bg-cyan-900/40', text: 'text-cyan-700 dark:text-cyan-300', dot: 'bg-cyan-500', ring: 'ring-cyan-400' },
  { bg: 'bg-purple-100 dark:bg-purple-900/40', text: 'text-purple-700 dark:text-purple-300', dot: 'bg-purple-500', ring: 'ring-purple-400' },
];

function shortRunId(id: string) { return id.slice(0, 8); }

function formatTimestamp(ts: string) {
  if (!ts) return '';
  return new Date(ts).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

// ---------------------------------------------------------------------------
// Crawler Page
// ---------------------------------------------------------------------------

export default function Crawler() {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlRunId = searchParams.get('run_id') ?? '';

  const [crawlerRunIds, setCrawlerRunIds] = useState<string[]>([]);
  const [pipelineRuns, setPipelineRuns] = useState<PipelineRunSummary[]>([]);
  const [activeRunId, setActiveRunId] = useState(urlRunId);
  const [siteModel, setSiteModel] = useState<SiteModelResponse | null>(null);
  const [pages, setPages] = useState<PageSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPage, setSelectedPage] = useState<PageSummary | null>(null);

  // Build run metadata map (run_id → { colorIdx, label, startedAt })
  // crawlerRunIds is newest-first from the API, so reverse for colour assignment
  // Filter out archived runs
  const runMeta = useMemo(() => {
    const map = new Map<string, { colorIdx: number; label: string; startedAt: string }>();
    const oldest = [...crawlerRunIds].reverse();
    let idx = 0;
    oldest.forEach((rid) => {
      const run = pipelineRuns.find((r) => r.run_id === rid);
      if (run?.archived) return;
      map.set(rid, {
        colorIdx: idx,
        label: `#${idx + 1}`,
        startedAt: run?.started_at ?? '',
      });
      idx += 1;
    });
    return map;
  }, [crawlerRunIds, pipelineRuns]);

  const archivedRunCount = pipelineRuns.filter((r) => r.archived && crawlerRunIds.includes(r.run_id)).length;

  // Fetch the list of runs that have crawler data + pipeline metadata
  useEffect(() => {
    (async () => {
      try {
        const [crRes, prRes] = await Promise.all([listCrawlerRuns(), listPipelineRuns()]);
        setCrawlerRunIds(crRes.data);         // newest first
        setPipelineRuns(prRes.data);
        // Default to latest run if no URL param
        if (!activeRunId && crRes.data.length > 0) {
          setActiveRunId(crRes.data[0]);
        }
      } catch {
        // Silently ignore — no crawler runs yet
      }
    })();
  }, []);

  // Fetch site model + pages whenever activeRunId changes
  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      setSelectedPage(null);
      try {
        const [modelRes, pagesRes] = await Promise.all([
          getSiteModel(activeRunId || undefined),
          listCrawlerPages(activeRunId || undefined),
        ]);
        setSiteModel(modelRes.data);
        setPages(pagesRes.data);
      } catch (err: any) {
        if (err.status === 404) {
          setSiteModel(null);
          setPages([]);
        } else {
          setError(err.message ?? 'Failed to load crawler data');
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [activeRunId]);

  // Sync activeRunId → URL param
  useEffect(() => {
    if (activeRunId) setSearchParams({ run_id: activeRunId }, { replace: true });
    else setSearchParams({}, { replace: true });
  }, [activeRunId]);

  const handleSelectRun = (rid: string) => {
    setActiveRunId(rid === activeRunId ? '' : rid);
  };

  // Active run colour
  const activeMeta = activeRunId ? runMeta.get(activeRunId) : undefined;
  const activeColor = activeMeta ? RUN_COLORS[activeMeta.colorIdx % RUN_COLORS.length] : RUN_COLORS[0];

  // Navigation connections
  const connections = useMemo(() => {
    if (!siteModel) return [];
    const list: { from: string; to: string }[] = [];
    for (const [src, targets] of Object.entries(siteModel.navigation_graph)) {
      for (const tgt of targets) list.push({ from: src, to: tgt });
    }
    return list;
  }, [siteModel]);

  // ── Empty state (no crawler runs at all) ──────────────────────────────────
  if (!loading && crawlerRunIds.length === 0) {
    return (
      <div className="p-6 max-w-7xl mx-auto">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">Crawler — Site Model</h1>
        <p className="text-gray-500 dark:text-gray-400 mb-8">
          Web application structure discovered by the crawler agent
        </p>
        <div className="flex flex-col items-center justify-center h-64 text-gray-500 dark:text-gray-400">
          <Globe className="h-12 w-12 mb-3 text-gray-300 dark:text-gray-600" />
          <p className="text-lg font-medium">No crawler data available.</p>
          <p className="text-sm mt-1">
            Add a <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">base_url</code> to your config and run the pipeline.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Crawler — Site Model</h1>
        <p className="text-gray-500 dark:text-gray-400 mt-1">
          Web application structure discovered by the crawler agent
          {archivedRunCount > 0 && (
            <span className="ml-2 text-gray-400 dark:text-gray-500">({archivedRunCount} archived)</span>
          )}
        </p>
      </div>

      {/* Run selector */}
      {crawlerRunIds.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mr-1 flex-shrink-0">
              Crawler Runs:
            </span>
            {crawlerRunIds.map((rid) => {
              const meta = runMeta.get(rid);
              const c = RUN_COLORS[(meta?.colorIdx ?? 0) % RUN_COLORS.length];
              const isActive = activeRunId === rid;
              return (
                <button
                  key={rid}
                  onClick={() => handleSelectRun(rid)}
                  title={rid}
                  className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                    isActive
                      ? `${c.bg} ${c.text} border-transparent ring-2 ring-offset-1 ${c.ring}`
                      : `border-gray-200 dark:border-gray-700 ${c.text} hover:${c.bg}`
                  }`}
                >
                  <span className={`w-2 h-2 rounded-full ${c.dot}`} />
                  <GitBranch className="h-3 w-3" />
                  Run {meta?.label ?? '?'}
                  {meta?.startedAt && (
                    <span className="opacity-70">{formatTimestamp(meta.startedAt)}</span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 rounded-lg flex items-center justify-between">
          <span className="flex items-center gap-2 text-sm"><AlertCircle className="h-4 w-4" />{error}</span>
          <button onClick={() => setError(null)}><X className="h-4 w-4" /></button>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center h-40">
          <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
          <span className="ml-3 text-gray-500 dark:text-gray-400">Loading site model…</span>
        </div>
      )}

      {/* No data for selected run */}
      {!loading && (!siteModel || pages.length === 0) && (
        <div className="flex flex-col items-center justify-center h-40 text-gray-500 dark:text-gray-400">
          <Globe className="h-10 w-10 mb-3 text-gray-300 dark:text-gray-600" />
          <p className="font-medium">No site model for this run.</p>
          <p className="text-sm mt-1">The crawler may have been skipped or failed.</p>
        </div>
      )}

      {/* Main content */}
      {!loading && siteModel && pages.length > 0 && (
        <>
          {/* Active run badge */}
          {activeMeta && activeRunId && (
            <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium ${activeColor.bg} ${activeColor.text}`}>
              <span className={`w-2 h-2 rounded-full ${activeColor.dot}`} />
              Viewing Run {activeMeta.label}
              {activeMeta.startedAt && <span className="opacity-70">· {formatTimestamp(activeMeta.startedAt)}</span>}
              <span className="opacity-60 font-mono">({shortRunId(activeRunId)}…)</span>
            </div>
          )}

          {/* Stats Row */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { label: 'Total Pages', value: siteModel.total_pages, icon: FileText, color: 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30' },
              { label: 'Total Elements', value: siteModel.total_elements, icon: Layers, color: 'text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-900/30' },
              { label: 'Total Forms', value: siteModel.total_forms, icon: ClipboardList, color: 'text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/30' },
              { label: 'Crawl Time', value: formatTimestamp(siteModel.crawl_timestamp) || '—', icon: Clock, color: 'text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/30' },
            ].map((s) => (
              <div key={s.label} className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 flex items-center gap-4">
                <div className={`p-2.5 rounded-lg ${s.color}`}><s.icon className="h-5 w-5" /></div>
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">{s.label}</p>
                  <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                    {typeof s.value === 'number' ? s.value.toLocaleString() : s.value}
                  </p>
                </div>
              </div>
            ))}
          </div>

          {/* Base URL */}
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
            <span className="text-sm text-gray-500 dark:text-gray-400">Base URL:</span>
            <span className="ml-2 font-mono text-sm text-blue-600 dark:text-blue-400">{siteModel.base_url}</span>
          </div>

          {/* Page Cards Grid */}
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3">
              Crawled Pages ({pages.length})
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {pages.map((page) => (
                <button
                  key={page.url}
                  onClick={() => setSelectedPage(page)}
                  className={`text-left bg-white dark:bg-gray-800 rounded-lg border p-4 hover:shadow-md transition-shadow ${
                    selectedPage?.url === page.url
                      ? 'border-blue-500 ring-2 ring-blue-200 dark:ring-blue-800'
                      : 'border-gray-200 dark:border-gray-700'
                  }`}
                >
                  <h3 className="font-medium text-gray-900 dark:text-gray-100 truncate">{page.title || 'Untitled'}</h3>
                  <p className="text-xs font-mono text-gray-500 dark:text-gray-400 truncate mt-1">{page.url}</p>
                  <div className="flex gap-4 mt-3 text-xs text-gray-500 dark:text-gray-400">
                    <span className="flex items-center gap-1"><Layers className="h-3.5 w-3.5" />{page.element_count} elements</span>
                    <span className="flex items-center gap-1"><ClipboardList className="h-3.5 w-3.5" />{page.form_count} forms</span>
                    <span className="flex items-center gap-1"><LinkIcon className="h-3.5 w-3.5" />{page.link_count} links</span>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Navigation Graph */}
          {connections.length > 0 && (
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3">
                Navigation Graph ({connections.length} connections)
              </h2>
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 divide-y divide-gray-100 dark:divide-gray-700 max-h-64 overflow-y-auto">
                {connections.map((conn, idx) => (
                  <div key={idx} className="flex items-center gap-3 px-4 py-2 text-sm">
                    <span className="font-mono text-gray-700 dark:text-gray-300 truncate max-w-[40%]">{conn.from}</span>
                    <ArrowRight className="h-4 w-4 text-gray-400 dark:text-gray-500 flex-shrink-0" />
                    <span className="font-mono text-gray-700 dark:text-gray-300 truncate max-w-[40%]">{conn.to}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Page Detail Modal */}
      {selectedPage && siteModel && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-lg mx-4 p-6 relative">
            <button onClick={() => setSelectedPage(null)}
              className="absolute top-4 right-4 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300">
              <X className="h-5 w-5" />
            </button>
            <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-1 pr-8">
              {selectedPage.title || 'Untitled Page'}
            </h2>
            <p className="text-sm font-mono text-blue-600 dark:text-blue-400 mb-4 break-all">{selectedPage.url}</p>
            <div className="grid grid-cols-3 gap-4">
              <div className="bg-purple-50 dark:bg-purple-900/30 rounded-lg p-3 text-center">
                <p className="text-2xl font-bold text-purple-700 dark:text-purple-300">{selectedPage.element_count}</p>
                <p className="text-xs text-purple-600 dark:text-purple-400 mt-1">Elements</p>
              </div>
              <div className="bg-amber-50 dark:bg-amber-900/30 rounded-lg p-3 text-center">
                <p className="text-2xl font-bold text-amber-700 dark:text-amber-300">{selectedPage.form_count}</p>
                <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">Forms</p>
              </div>
              <div className="bg-blue-50 dark:bg-blue-900/30 rounded-lg p-3 text-center">
                <p className="text-2xl font-bold text-blue-700 dark:text-blue-300">{selectedPage.link_count}</p>
                <p className="text-xs text-blue-600 dark:text-blue-400 mt-1">Links</p>
              </div>
            </div>
            {siteModel.navigation_graph[selectedPage.url]?.length > 0 && (
              <div className="mt-4">
                <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Links to:</h3>
                <ul className="space-y-1 max-h-40 overflow-y-auto">
                  {siteModel.navigation_graph[selectedPage.url].map((target) => (
                    <li key={target} className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                      <ArrowRight className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500 flex-shrink-0" />
                      <span className="font-mono break-all">{target}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
