import { useState, useEffect } from 'react';
import {
  Globe,
  FileText,
  Layers,
  ClipboardList,
  Clock,
  ArrowRight,
  X,
  Loader2,
  AlertCircle,
  Link as LinkIcon,
} from 'lucide-react';
import { getSiteModel, listCrawlerPages } from '../api/client';
import type { SiteModelResponse, PageSummary } from '../api/client';

export default function Crawler() {
  const [siteModel, setSiteModel] = useState<SiteModelResponse | null>(null);
  const [pages, setPages] = useState<PageSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPage, setSelectedPage] = useState<PageSummary | null>(null);

  useEffect(() => {
    async function fetchData() {
      setLoading(true);
      setError(null);
      try {
        const [modelRes, pagesRes] = await Promise.all([getSiteModel(), listCrawlerPages()]);
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
    }
    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
        <span className="ml-3 text-gray-500 dark:text-gray-400">Loading site model...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64 text-red-600">
        <AlertCircle className="h-6 w-6 mr-2" />
        {error}
      </div>
    );
  }

  if (!siteModel || pages.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-gray-500 dark:text-gray-400">
        <Globe className="h-12 w-12 mb-3 text-gray-300 dark:text-gray-600" />
        <p className="text-lg font-medium">No site model available.</p>
        <p className="text-sm mt-1">Run a crawler pipeline first.</p>
      </div>
    );
  }

  const stats = [
    {
      label: 'Total Pages',
      value: siteModel.total_pages,
      icon: FileText,
      color: 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30',
    },
    {
      label: 'Total Elements',
      value: siteModel.total_elements,
      icon: Layers,
      color: 'text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-900/30',
    },
    {
      label: 'Total Forms',
      value: siteModel.total_forms,
      icon: ClipboardList,
      color: 'text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/30',
    },
    {
      label: 'Crawl Time',
      value: new Date(siteModel.crawl_timestamp).toLocaleString(),
      icon: Clock,
      color: 'text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/30',
    },
  ];

  // Build connections list from navigation graph
  const connections: { from: string; to: string }[] = [];
  for (const [source, targets] of Object.entries(siteModel.navigation_graph)) {
    for (const target of targets) {
      connections.push({ from: source, to: target });
    }
  }

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Crawler - Site Model</h1>

      {/* Stats Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((s) => (
          <div
            key={s.label}
            className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 flex items-center gap-4"
          >
            <div className={`p-2.5 rounded-lg ${s.color}`}>
              <s.icon className="h-5 w-5" />
            </div>
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
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3">Crawled Pages</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {pages.map((page) => (
            <button
              key={page.url}
              onClick={() => setSelectedPage(page)}
              className={`text-left bg-white dark:bg-gray-800 rounded-lg border p-4 hover:shadow-md transition-shadow cursor-pointer ${
                selectedPage?.url === page.url
                  ? 'border-blue-500 ring-2 ring-blue-200 dark:ring-blue-800'
                  : 'border-gray-200 dark:border-gray-700'
              }`}
            >
              <h3 className="font-medium text-gray-900 dark:text-gray-100 truncate">{page.title || 'Untitled'}</h3>
              <p className="text-xs font-mono text-gray-500 dark:text-gray-400 truncate mt-1">{page.url}</p>
              <div className="flex gap-4 mt-3 text-xs text-gray-500 dark:text-gray-400">
                <span className="flex items-center gap-1">
                  <Layers className="h-3.5 w-3.5" />
                  {page.element_count} elements
                </span>
                <span className="flex items-center gap-1">
                  <ClipboardList className="h-3.5 w-3.5" />
                  {page.form_count} forms
                </span>
                <span className="flex items-center gap-1">
                  <LinkIcon className="h-3.5 w-3.5" />
                  {page.link_count} links
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Navigation Graph Connections */}
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

      {/* Page Detail Panel */}
      {selectedPage && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-lg mx-4 p-6 relative">
            <button
              onClick={() => setSelectedPage(null)}
              className="absolute top-4 right-4 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
            >
              <X className="h-5 w-5" />
            </button>
            <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-1">
              {selectedPage.title || 'Untitled Page'}
            </h2>
            <p className="text-sm font-mono text-blue-600 dark:text-blue-400 mb-4">{selectedPage.url}</p>
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

            {/* Navigation from this page */}
            {siteModel.navigation_graph[selectedPage.url] &&
              siteModel.navigation_graph[selectedPage.url].length > 0 && (
                <div className="mt-4">
                  <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Links to:</h3>
                  <ul className="space-y-1">
                    {siteModel.navigation_graph[selectedPage.url].map((target) => (
                      <li key={target} className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                        <ArrowRight className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500" />
                        <span className="font-mono">{target}</span>
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
