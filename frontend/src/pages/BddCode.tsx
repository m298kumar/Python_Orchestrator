import { useEffect, useState } from "react";
import {
  Code,
  Download,
  FileCode,
  Loader2,
  Package,
  X,
} from "lucide-react";
import {
  listFeatures,
  getFeature,
  downloadBddProject,
  type FeatureFile,
} from "../api/client";

// ---------------------------------------------------------------------------
// Feature List Item
// ---------------------------------------------------------------------------

interface ListItemProps {
  feature: FeatureFile;
  selected: boolean;
  onClick: () => void;
}

function FeatureListItem({ feature, selected, onClick }: ListItemProps) {
  return (
    <button
      onClick={onClick}
      className={[
        "w-full text-left px-4 py-3 border-b border-gray-100 transition-colors",
        selected
          ? "bg-indigo-50 border-l-[3px] border-l-indigo-500"
          : "hover:bg-gray-50",
      ].join(" ")}
    >
      <div className="flex items-center gap-2">
        <FileCode className="h-4 w-4 text-gray-400 flex-shrink-0" />
        <span className="text-sm font-medium text-gray-900 truncate">
          {feature.filename}
        </span>
      </div>
      <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
        <span>Req: {feature.req_id}</span>
        <span>
          {feature.scenario_count} scenario{feature.scenario_count !== 1 ? "s" : ""}
        </span>
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Gherkin Viewer (simple keyword-highlighted code viewer)
// ---------------------------------------------------------------------------

function GherkinViewer({ content }: { content: string }) {
  const lines = content.split("\n");

  return (
    <pre className="text-sm leading-relaxed font-mono overflow-auto">
      {lines.map((line, i) => {
        const trimmed = line.trimStart();
        let className = "text-gray-700";

        if (trimmed.startsWith("Feature:"))
          className = "text-indigo-700 font-bold";
        else if (
          trimmed.startsWith("Scenario:") ||
          trimmed.startsWith("Scenario Outline:")
        )
          className = "text-blue-700 font-semibold";
        else if (trimmed.startsWith("Background:"))
          className = "text-blue-700 font-semibold";
        else if (
          trimmed.startsWith("Given ") ||
          trimmed.startsWith("When ") ||
          trimmed.startsWith("Then ") ||
          trimmed.startsWith("And ") ||
          trimmed.startsWith("But ")
        )
          className = "text-green-700";
        else if (trimmed.startsWith("@")) className = "text-purple-600";
        else if (trimmed.startsWith("#")) className = "text-gray-400 italic";
        else if (trimmed.startsWith("Examples:"))
          className = "text-amber-700 font-semibold";
        else if (trimmed.startsWith("|")) className = "text-gray-600";

        return (
          <div key={i} className="flex">
            <span className="inline-block w-10 text-right pr-3 text-gray-300 select-none">
              {i + 1}
            </span>
            <span className={className}>{line}</span>
          </div>
        );
      })}
    </pre>
  );
}

// ---------------------------------------------------------------------------
// BddCode Page
// ---------------------------------------------------------------------------

export default function BddCode() {
  const [features, setFeatures] = useState<FeatureFile[]>([]);
  const [selectedFilename, setSelectedFilename] = useState<string | null>(null);
  const [selectedContent, setSelectedContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [contentLoading, setContentLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectFeature = async (filename: string) => {
    setSelectedFilename(filename);
    setContentLoading(true);
    try {
      const res = await getFeature(filename);
      setSelectedContent(res.data.content ?? "");
    } catch (err: any) {
      setError(err.message ?? "Failed to load feature content");
      setSelectedContent(null);
    } finally {
      setContentLoading(false);
    }
  };

  useEffect(() => {
    (async () => {
      try {
        const res = await listFeatures();
        setFeatures(res.data);
        if (res.data.length > 0) {
          selectFeature(res.data[0].filename);
        }
      } catch (err: any) {
        setError(err.message ?? "Failed to load features");
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDownloadFile = () => {
    if (!selectedContent || !selectedFilename) return;
    const blob = new Blob([selectedContent], { type: "text/plain" });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = selectedFilename;
    link.click();
    window.URL.revokeObjectURL(url);
  };

  const handleDownloadProject = async () => {
    try {
      const res = await downloadBddProject();
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement("a");
      link.href = url;
      link.download = "bdd_project.zip";
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      setError(err.message ?? "Failed to download BDD project");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
      </div>
    );
  }

  // Empty state
  if (features.length === 0) {
    return (
      <div className="p-6 max-w-7xl mx-auto">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">BDD Code</h1>
          <p className="text-gray-500 mt-1">View and download generated feature files</p>
        </div>
        <div className="bg-white rounded-lg shadow p-12 text-center mt-8">
          <Code className="h-12 w-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500 text-lg font-medium">
            No BDD features generated yet
          </p>
          <p className="text-gray-400 text-sm mt-1">
            Run the BDD pipeline stage to generate feature files.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center justify-between">
          <span className="text-sm">{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">BDD Code</h1>
          <p className="text-gray-500 mt-1">
            {features.length} feature file{features.length !== 1 ? "s" : ""} generated
          </p>
        </div>
        <button
          onClick={handleDownloadProject}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700"
        >
          <Package className="h-4 w-4" /> Download Project
        </button>
      </div>

      {/* Two-panel layout */}
      <div className="flex gap-6 min-h-[500px]">
        {/* Left panel: feature list */}
        <div className="w-1/3 bg-white rounded-lg shadow overflow-hidden flex flex-col">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
            <h3 className="text-sm font-medium text-gray-700">Feature Files</h3>
          </div>
          <div className="flex-1 overflow-y-auto">
            {features.map((f) => (
              <FeatureListItem
                key={f.filename}
                feature={f}
                selected={selectedFilename === f.filename}
                onClick={() => selectFeature(f.filename)}
              />
            ))}
          </div>
        </div>

        {/* Right panel: code viewer */}
        <div className="w-2/3 bg-white rounded-lg shadow overflow-hidden flex flex-col">
          {selectedFilename ? (
            <>
              <div className="px-4 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <FileCode className="h-4 w-4 text-gray-500" />
                  <span className="text-sm font-medium text-gray-700">
                    {selectedFilename}
                  </span>
                </div>
                <button
                  onClick={handleDownloadFile}
                  className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-medium text-gray-600 bg-gray-100 rounded hover:bg-gray-200"
                >
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
                  <p className="text-gray-500 text-sm">Failed to load content</p>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
              Select a feature file to view its content
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
