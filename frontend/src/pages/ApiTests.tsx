import { useState, useEffect } from 'react';
import { FileCode, Loader2, AlertCircle, TestTubes, ArrowLeft } from 'lucide-react';
import { listApiTests, getApiTest } from '../api/client';
import type { ApiTestFile } from '../api/client';
import StatusBadge from '../components/StatusBadge';
import CodeViewer from '../components/CodeViewer';

const levelColors: Record<string, string> = {
  api: 'running',
  unit: 'running',
  integration: 'generated',
  e2e: 'failed',
};

function languageFromFile(file: ApiTestFile): string {
  if (file.language === 'python' || file.framework === 'pytest_requests') return 'python';
  if (file.language === 'java' || file.framework === 'rest_assured') return 'java';
  if (file.language === 'javascript' || file.framework === 'jest') return 'javascript';
  if (file.framework === 'karate') return 'gherkin';
  // Fallback: infer from filename extension
  const ext = file.filename.split('.').pop()?.toLowerCase();
  if (ext === 'py') return 'python';
  if (ext === 'java') return 'java';
  if (ext === 'js' || ext === 'ts') return 'javascript';
  if (ext === 'feature') return 'gherkin';
  return 'text';
}

export default function ApiTests() {
  const [testFiles, setTestFiles] = useState<ApiTestFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ApiTestFile | null>(null);
  const [loadingContent, setLoadingContent] = useState(false);

  useEffect(() => {
    async function fetchList() {
      setLoading(true);
      setError(null);
      try {
        const res = await listApiTests();
        setTestFiles(res.data);
      } catch (err: any) {
        if (err.status === 404) {
          setTestFiles([]);
        } else {
          setError(err.message ?? 'Failed to load API tests');
        }
      } finally {
        setLoading(false);
      }
    }
    fetchList();
  }, []);

  async function handleSelect(file: ApiTestFile) {
    if (file.content) {
      setSelected(file);
      return;
    }
    setLoadingContent(true);
    try {
      const res = await getApiTest(file.filename);
      const full = res.data;
      // Update the list entry with content
      setTestFiles((prev) => prev.map((f) => (f.filename === file.filename ? full : f)));
      setSelected(full);
    } catch (err: any) {
      setError(err.message ?? 'Failed to load test file content');
    } finally {
      setLoadingContent(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
        <span className="ml-3 text-gray-500 dark:text-gray-400">Loading API tests...</span>
      </div>
    );
  }

  if (error && testFiles.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-red-600">
        <AlertCircle className="h-6 w-6 mr-2" />
        {error}
      </div>
    );
  }

  if (testFiles.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-gray-500 dark:text-gray-400">
        <TestTubes className="h-12 w-12 mb-3 text-gray-300 dark:text-gray-600" />
        <p className="text-lg font-medium">No API tests generated yet.</p>
        <p className="text-sm mt-1">Run an API test pipeline to generate test files.</p>
      </div>
    );
  }

  const totalTests = testFiles.reduce((sum, f) => sum + f.test_count, 0);
  const frameworks = [...new Set(testFiles.map((f) => f.framework))];

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">API Tests</h1>

      {/* Stats Bar */}
      <div className="flex gap-6 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400">Test Files</p>
          <p className="text-xl font-bold text-gray-900 dark:text-gray-100">{testFiles.length}</p>
        </div>
        <div className="border-l border-gray-200 dark:border-gray-700 pl-6">
          <p className="text-sm text-gray-500 dark:text-gray-400">Total Tests</p>
          <p className="text-xl font-bold text-gray-900 dark:text-gray-100">{totalTests}</p>
        </div>
        <div className="border-l border-gray-200 dark:border-gray-700 pl-6">
          <p className="text-sm text-gray-500 dark:text-gray-400">Frameworks</p>
          <p className="text-xl font-bold text-gray-900 dark:text-gray-100">{frameworks.join(', ')}</p>
        </div>
      </div>

      {error && <div className="bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 px-4 py-2 rounded-lg text-sm">{error}</div>}

      <div className="flex gap-6">
        {/* File List */}
        <div className={`${selected ? 'w-1/3 flex-shrink-0' : 'w-full'} transition-all`}>
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 dark:bg-gray-700 border-b border-gray-200 dark:border-gray-700 text-left text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  <th className="px-4 py-3">Filename</th>
                  {!selected && <th className="px-4 py-3">Framework</th>}
                  {!selected && <th className="px-4 py-3">Language</th>}
                  {!selected && <th className="px-4 py-3">Endpoint</th>}
                  <th className="px-4 py-3 text-right">Tests</th>
                  <th className="px-4 py-3">Level</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {testFiles.map((file) => (
                  <tr
                    key={file.filename}
                    onClick={() => handleSelect(file)}
                    className={`cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors ${
                      selected?.filename === file.filename ? 'bg-blue-50 dark:bg-blue-900/30' : ''
                    }`}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <FileCode className="h-4 w-4 text-gray-400 dark:text-gray-500 flex-shrink-0" />
                        <span className="font-mono text-xs truncate">{file.filename}</span>
                      </div>
                    </td>
                    {!selected && <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{file.framework}</td>}
                    {!selected && <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{file.language}</td>}
                    {!selected && (
                      <td className="px-4 py-3 font-mono text-xs text-gray-600 dark:text-gray-400">
                        {file.endpoint_path}
                      </td>
                    )}
                    <td className="px-4 py-3 text-right font-medium">{file.test_count}</td>
                    <td className="px-4 py-3">
                      <StatusBadge
                        status={levelColors[file.test_level] ?? file.test_level}
                        size="sm"
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Code Viewer Panel */}
        {selected && (
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 mb-3">
              <button
                onClick={() => setSelected(null)}
                className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
              >
                <ArrowLeft className="h-5 w-5" />
              </button>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 truncate">{selected.filename}</h2>
              <span className="text-sm text-gray-500 dark:text-gray-400">
                {selected.framework} / {selected.language}
              </span>
            </div>
            {loadingContent ? (
              <div className="flex items-center justify-center h-40">
                <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
              </div>
            ) : selected.content ? (
              <CodeViewer
                code={selected.content}
                language={languageFromFile(selected)}
                filename={selected.filename}
              />
            ) : (
              <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-8 text-center text-gray-500 dark:text-gray-400">
                No content available for this file.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
