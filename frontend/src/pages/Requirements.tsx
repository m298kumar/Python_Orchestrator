import { useEffect, useRef, useState } from "react";
import {
  FileUp,
  Loader2,
  Upload,
  X,
  Check,
  Pencil,
  AlertCircle,
} from "lucide-react";
import {
  uploadRequirements,
  listRequirements,
  updateRequirement,
  type Requirement,
} from "../api/client";

// ---------------------------------------------------------------------------
// Priority Badge
// ---------------------------------------------------------------------------

const priorityColors: Record<string, string> = {
  high: "bg-red-100 text-red-700",
  medium: "bg-yellow-100 text-yellow-700",
  low: "bg-green-100 text-green-700",
};

function PriorityBadge({ priority }: { priority: string }) {
  const normalized = priority.toLowerCase();
  const classes = priorityColors[normalized] ?? "bg-gray-100 text-gray-600";
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${classes}`}>
      {priority}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Upload Zone
// ---------------------------------------------------------------------------

interface UploadZoneProps {
  onUpload: (file: File) => void;
  uploading: boolean;
  uploadResult: { success: boolean; message: string } | null;
}

function UploadZone({ onUpload, uploading, uploadResult }: UploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const handleFiles = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    onUpload(files[0]);
  };

  return (
    <div
      className={[
        "border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer",
        dragOver
          ? "border-indigo-400 bg-indigo-50"
          : "border-gray-300 bg-white hover:border-gray-400",
      ].join(" ")}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        handleFiles(e.dataTransfer.files);
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".json,.yaml,.yml,.csv,.xlsx,.txt,.pdf,.docx,.md"
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />

      {uploading ? (
        <div className="flex flex-col items-center gap-2">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
          <p className="text-sm text-gray-600">Uploading...</p>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-2">
          <FileUp className="h-8 w-8 text-gray-400" />
          <p className="text-sm text-gray-600">
            Drag and drop a requirements file here, or{" "}
            <span className="text-indigo-600 font-medium">click to browse</span>
          </p>
          <p className="text-xs text-gray-400 mt-1">
            Supports: CSV, Excel, JSON, YAML, TXT, PDF, DOCX, Markdown
          </p>
        </div>
      )}

      {uploadResult && (
        <div
          className={`mt-4 inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium ${
            uploadResult.success
              ? "bg-green-100 text-green-700"
              : "bg-red-100 text-red-700"
          }`}
        >
          {uploadResult.success ? (
            <Check className="h-4 w-4" />
          ) : (
            <AlertCircle className="h-4 w-4" />
          )}
          {uploadResult.message}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Editable Row
// ---------------------------------------------------------------------------

interface EditableRowProps {
  req: Requirement;
  editing: boolean;
  onStartEdit: () => void;
  onSave: (reqId: string, data: Partial<Requirement>) => void;
  onCancel: () => void;
}

function RequirementRow({ req, editing, onStartEdit, onSave, onCancel }: EditableRowProps) {
  const [title, setTitle] = useState(req.title);
  const [description, setDescription] = useState(req.description);

  useEffect(() => {
    setTitle(req.title);
    setDescription(req.description);
  }, [req, editing]);

  return (
    <tr className="hover:bg-gray-50">
      <td className="px-4 py-3 text-sm font-mono text-gray-900">{req.req_id}</td>
      <td className="px-4 py-3 text-sm text-gray-700">
        {editing ? (
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        ) : (
          req.title
        )}
      </td>
      <td className="px-4 py-3">
        <PriorityBadge priority={req.priority} />
      </td>
      <td className="px-4 py-3 text-sm text-gray-500">{req.category}</td>
      <td className="px-4 py-3">
        <div className="flex flex-wrap gap-1">
          {req.tags.map((tag) => (
            <span
              key={tag}
              className="inline-block px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 text-xs"
            >
              {tag}
            </span>
          ))}
        </div>
      </td>
      <td className="px-4 py-3">
        {editing ? (
          <div className="flex items-center gap-2">
            <button
              onClick={() => onSave(req.req_id, { title, description })}
              className="p-1 rounded text-green-600 hover:bg-green-50"
              title="Save"
            >
              <Check className="h-4 w-4" />
            </button>
            <button
              onClick={onCancel}
              className="p-1 rounded text-gray-400 hover:bg-gray-100"
              title="Cancel"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <button
            onClick={onStartEdit}
            className="p-1 rounded text-gray-400 hover:text-indigo-600 hover:bg-indigo-50"
            title="Edit"
          >
            <Pencil className="h-4 w-4" />
          </button>
        )}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Requirements Page
// ---------------------------------------------------------------------------

export default function Requirements() {
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);

  const fetchRequirements = async () => {
    try {
      const res = await listRequirements();
      setRequirements(res.data);
    } catch (err: any) {
      setError(err.message ?? "Failed to load requirements");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRequirements();
  }, []);

  const handleUpload = async (file: File) => {
    setUploading(true);
    setUploadResult(null);
    try {
      await uploadRequirements(file);
      setUploadResult({ success: true, message: `Uploaded ${file.name} successfully` });
      const res = await listRequirements();
      setRequirements(res.data);
    } catch (err: any) {
      setUploadResult({
        success: false,
        message: err.message ?? "Upload failed",
      });
    } finally {
      setUploading(false);
    }
  };

  const handleSave = async (reqId: string, data: Partial<Requirement>) => {
    try {
      await updateRequirement(reqId, data);
      setRequirements((prev) =>
        prev.map((r) => (r.req_id === reqId ? { ...r, ...data } : r)),
      );
      setEditingId(null);
    } catch (err: any) {
      setError(err.message ?? "Failed to update requirement");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8">
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center justify-between">
          <span className="text-sm">{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      <div>
        <h1 className="text-2xl font-bold text-gray-900">Requirements</h1>
        <p className="text-gray-500 mt-1">Upload and manage project requirements</p>
      </div>

      <UploadZone onUpload={handleUpload} uploading={uploading} uploadResult={uploadResult} />

      {requirements.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-12 text-center">
          <Upload className="h-12 w-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500 text-lg font-medium">No requirements uploaded yet</p>
          <p className="text-gray-400 text-sm mt-1">
            Upload a CSV, Excel, JSON, YAML, TXT, PDF, or DOCX file to get started.
          </p>
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  ID
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Title
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Priority
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Category
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Tags
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {requirements.map((req) => (
                <RequirementRow
                  key={req.req_id}
                  req={req}
                  editing={editingId === req.req_id}
                  onStartEdit={() => setEditingId(req.req_id)}
                  onSave={handleSave}
                  onCancel={() => setEditingId(null)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
