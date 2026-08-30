import { useState, useEffect, useMemo } from 'react';
import {
  Loader2,
  AlertCircle,
  BarChart3,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Cpu,
  Target,
  AlertTriangle,
  Search,
} from 'lucide-react';
import { getMetricsTrends, listMetrics } from '../api/client';
import type { MetricsRun, MetricsTrend } from '../api/client';

function qualityColor(score: number): string {
  if (score >= 0.85) return 'text-green-600';
  if (score >= 0.65) return 'text-blue-600';
  if (score >= 0.4) return 'text-yellow-600';
  return 'text-red-600';
}

function qualityBg(score: number): string {
  if (score >= 0.85) return 'bg-green-50 dark:bg-green-900/30 border-green-200 dark:border-green-800';
  if (score >= 0.65) return 'bg-blue-50 dark:bg-blue-900/30 border-blue-200 dark:border-blue-800';
  if (score >= 0.4) return 'bg-yellow-50 dark:bg-yellow-900/30 border-yellow-200 dark:border-yellow-800';
  return 'bg-red-50 dark:bg-red-900/30 border-red-200 dark:border-red-800';
}

function QualityBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-gray-200 dark:bg-gray-600 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${
            score >= 0.85
              ? 'bg-green-500'
              : score >= 0.65
                ? 'bg-blue-500'
                : score >= 0.4
                  ? 'bg-yellow-500'
                  : 'bg-red-500'
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`text-sm font-medium ${qualityColor(score)}`}>{pct}%</span>
    </div>
  );
}

export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '-';
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const wholeSeconds = Math.round(seconds);
  const minutes = Math.floor(wholeSeconds / 60);
  const remainder = wholeSeconds % 60;
  return `${minutes}m ${remainder.toString().padStart(2, '0')}s`;
}

export default function Metrics() {
  const [trends, setTrends] = useState<MetricsTrend | null>(null);
  const [runs, setRuns] = useState<MetricsRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [qualityFilter, setQualityFilter] = useState<string>('all');

  const filteredRuns = useMemo(() => {
    let filtered = runs;
    if (search.trim()) {
      const q = search.toLowerCase();
      filtered = filtered.filter(
        (m) =>
          m.run_id.toLowerCase().includes(q) ||
          (m.pipeline_name || '').toLowerCase().includes(q),
      );
    }
    if (qualityFilter !== 'all') {
      filtered = filtered.filter((m) => {
        if (qualityFilter === 'excellent') return m.avg_quality_score >= 0.85;
        if (qualityFilter === 'good') return m.avg_quality_score >= 0.65 && m.avg_quality_score < 0.85;
        if (qualityFilter === 'fair') return m.avg_quality_score >= 0.4 && m.avg_quality_score < 0.65;
        if (qualityFilter === 'poor') return m.avg_quality_score < 0.4;
        return true;
      });
    }
    return filtered;
  }, [runs, search, qualityFilter]);

  const reversedTrend = useMemo(
    () => trends?.quality_trend?.slice().reverse() ?? [],
    [trends?.quality_trend],
  );

  useEffect(() => {
    async function load() {
      try {
        const [trendsRes, runsRes] = await Promise.all([
          getMetricsTrends(),
          listMetrics(),
        ]);
        setTrends(trendsRes.data);
        setRuns(runsRes.data);
        setError(null);
      } catch (err: any) {
        setError(err.message ?? 'Failed to load metrics');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
        <span className="ml-3 text-gray-500 dark:text-gray-400">Loading metrics...</span>
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

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Pipeline Metrics</h1>

      {/* Degradation warning */}
      {trends?.degradation_warning && (
        <div className="flex items-start gap-3 bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800 rounded-lg px-4 py-3">
          <AlertTriangle className="h-5 w-5 text-amber-600 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-sm font-semibold text-amber-800 dark:text-amber-300">Quality Degradation Detected</p>
            <p className="text-sm text-amber-700 dark:text-amber-400 mt-0.5">{trends.degradation_warning}</p>
          </div>
        </div>
      )}

      {/* Summary cards */}
      {trends && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className={`rounded-lg border p-4 ${qualityBg(trends.avg_quality_score)}`}>
            <div className="flex items-center gap-2 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-1">
              <Target className="h-4 w-4" />
              Avg Quality
            </div>
            <p className={`text-2xl font-bold ${qualityColor(trends.avg_quality_score)}`}>
              {(trends.avg_quality_score * 100).toFixed(1)}%
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">across {trends.run_count} runs</p>
          </div>

          <div className="rounded-lg border dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
            <div className="flex items-center gap-2 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-1">
              <Cpu className="h-4 w-4" />
              Total Tokens
            </div>
            <p className="text-2xl font-bold text-gray-800 dark:text-gray-200">{trends.total_tokens.toLocaleString()}</p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">cumulative usage</p>
          </div>

          <div className="rounded-lg border dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
            <div className="flex items-center gap-2 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-1">
              <DollarSign className="h-4 w-4" />
              Total Cost
            </div>
            <p className="text-2xl font-bold text-gray-800 dark:text-gray-200">${trends.total_cost_usd.toFixed(4)}</p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">estimated LLM cost</p>
          </div>

          <div className="rounded-lg border dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
            <div className="flex items-center gap-2 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-1">
              <BarChart3 className="h-4 w-4" />
              Avg Gen Time
            </div>
            <p className="text-2xl font-bold text-gray-800 dark:text-gray-200">{formatDuration(trends.avg_generation_time)}</p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">per pipeline run</p>
          </div>
        </div>
      )}

      {/* Quality trend sparkline */}
      {trends && trends.quality_trend.length > 1 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border dark:border-gray-700 p-5">
          <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
            {trends.quality_trend[0]?.score >= (trends.quality_trend[trends.quality_trend.length - 1]?.score ?? 0)
              ? <TrendingUp className="h-4 w-4 text-green-500" />
              : <TrendingDown className="h-4 w-4 text-red-500" />}
            Quality Trend (last {trends.quality_trend.length} runs)
          </h2>
          <div className="flex items-end gap-1 h-24">
            {reversedTrend.map((point, i) => {
              const pct = Math.max(point.score * 100, 3);
              return (
                <div key={i} className="flex-1 flex flex-col items-center gap-1">
                  <div
                    className={`w-full rounded-t ${
                      point.score >= 0.85
                        ? 'bg-green-400'
                        : point.score >= 0.65
                          ? 'bg-blue-400'
                          : point.score >= 0.4
                            ? 'bg-yellow-400'
                            : 'bg-red-400'
                    }`}
                    style={{ height: `${pct}%` }}
                    title={`${point.run_id}: ${(point.score * 100).toFixed(1)}%`}
                  />
                </div>
              );
            })}
          </div>
          <div className="flex justify-between text-xs text-gray-400 dark:text-gray-500 mt-1">
            <span>oldest</span>
            <span>newest</span>
          </div>
        </div>
      )}

      {/* Search & filter bar */}
      {runs.length > 0 && (
        <div className="flex items-center gap-3">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search by run ID or pipeline..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <select
            value={qualityFilter}
            onChange={(e) => setQualityFilter(e.target.value)}
            className="border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="all">All quality levels</option>
            <option value="excellent">Excellent (&ge;85%)</option>
            <option value="good">Good (65-84%)</option>
            <option value="fair">Fair (40-64%)</option>
            <option value="poor">Poor (&lt;40%)</option>
          </select>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {filteredRuns.length} of {runs.length} runs
          </span>
        </div>
      )}

      {/* Run details table */}
      {filteredRuns.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border dark:border-gray-700 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 dark:bg-gray-700 border-b dark:border-gray-700 text-left text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                <th className="px-4 py-3">Run ID</th>
                <th className="px-4 py-3">Pipeline</th>
                <th className="px-4 py-3 text-right">Quality</th>
                <th className="px-4 py-3 text-right">Test Cases</th>
                <th className="px-4 py-3 text-right">Tokens</th>
                <th className="px-4 py-3 text-right">Cost</th>
                <th className="px-4 py-3 text-right">Coverage</th>
                <th className="px-4 py-3 text-right">Duration</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
              {filteredRuns.map((m) => (
                <tr key={m.run_id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                  <td className="px-4 py-3 font-mono text-xs">{m.run_id.slice(0, 12)}...</td>
                  <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{m.pipeline_name || '-'}</td>
                  <td className="px-4 py-3 w-40">
                    <QualityBar score={m.avg_quality_score} />
                  </td>
                  <td className="px-4 py-3 text-right font-medium">{m.total_test_cases}</td>
                  <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400" title={`Input: ${(m.input_tokens ?? 0).toLocaleString()} · Output: ${(m.output_tokens ?? 0).toLocaleString()}`}>{m.tokens_used.toLocaleString()}</td>
                  <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400" title={`${m.llm_provider || 'unknown'}${m.llm_model ? ` / ${m.llm_model}` : ''}`}>${m.estimated_cost_usd.toFixed(4)}</td>
                  <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400">
                    {m.coverage_pct.toFixed(0)}%
                  </td>
                  <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400">{formatDuration(m.generation_time_seconds)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {runs.length === 0 && !error && (
        <div className="flex flex-col items-center justify-center h-32 text-gray-500 dark:text-gray-400">
          <BarChart3 className="h-10 w-10 mb-2 text-gray-300 dark:text-gray-600" />
          <p>No metrics data yet. Run a pipeline to generate metrics.</p>
        </div>
      )}
    </div>
  );
}
