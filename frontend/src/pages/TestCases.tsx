import { useEffect, useMemo, useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  Filter,
  Loader2,
  Pencil,
  Search,
  X,
  XCircle,
} from "lucide-react";
import StatusBadge from "../components/StatusBadge";
import {
  listTestCases,
  approveTestCase,
  rejectTestCase,
  updateTestCase,
  type TestCase,
} from "../api/client";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TEST_TYPES = [
  "all",
  "positive",
  "negative",
  "edge_case",
  "boundary",
  "destructive",
  "performance",
  "security",
];

const PRIORITIES = ["all", "High", "Medium", "Low"];
const STATUSES = ["all", "generated", "approved", "rejected"];

// ---------------------------------------------------------------------------
// Expandable Row
// ---------------------------------------------------------------------------

interface RowProps {
  tc: TestCase;
  expanded: boolean;
  onToggle: () => void;
  onApprove: (tcId: string) => void;
  onReject: (tcId: string) => void;
  onSave: (tcId: string, data: Partial<TestCase>) => void;
}

function TestCaseRow({ tc, expanded, onToggle, onApprove, onReject, onSave }: RowProps) {
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(tc.title);
  const [editGiven, setEditGiven] = useState(tc.given);
  const [editWhen, setEditWhen] = useState(tc.when);
  const [editThen, setEditThen] = useState(tc.then);

  const handleSave = () => {
    onSave(tc.tc_id, {
      title: editTitle,
      given: editGiven,
      when: editWhen,
      then: editThen,
    });
    setEditing(false);
  };

  const handleCancelEdit = () => {
    setEditTitle(tc.title);
    setEditGiven(tc.given);
    setEditWhen(tc.when);
    setEditThen(tc.then);
    setEditing(false);
  };

  return (
    <>
      <tr className="hover:bg-gray-50 cursor-pointer" onClick={onToggle}>
        <td className="px-4 py-3 text-sm">
          {expanded ? (
            <ChevronDown className="h-4 w-4 text-gray-400" />
          ) : (
            <ChevronRight className="h-4 w-4 text-gray-400" />
          )}
        </td>
        <td className="px-4 py-3 text-sm font-mono text-gray-900">{tc.tc_id}</td>
        <td className="px-4 py-3 text-sm font-mono text-gray-500">{tc.req_id}</td>
        <td className="px-4 py-3 text-sm text-gray-700">{tc.title}</td>
        <td className="px-4 py-3 text-sm text-gray-500 capitalize">
          {tc.test_type.replace(/_/g, " ")}
        </td>
        <td className="px-4 py-3">
          <span
            className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
              tc.priority.toLowerCase() === "high"
                ? "bg-red-100 text-red-700"
                : tc.priority.toLowerCase() === "medium"
                  ? "bg-yellow-100 text-yellow-700"
                  : "bg-green-100 text-green-700"
            }`}
          >
            {tc.priority}
          </span>
        </td>
        <td className="px-4 py-3">
          <StatusBadge status={tc.status} size="sm" />
        </td>
        <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center gap-1">
            <button
              onClick={() => onApprove(tc.tc_id)}
              className="p-1 rounded text-green-500 hover:bg-green-50"
              title="Approve"
            >
              <Check className="h-4 w-4" />
            </button>
            <button
              onClick={() => onReject(tc.tc_id)}
              className="p-1 rounded text-red-500 hover:bg-red-50"
              title="Reject"
            >
              <XCircle className="h-4 w-4" />
            </button>
            <button
              onClick={() => setEditing(!editing)}
              className="p-1 rounded text-gray-400 hover:text-indigo-600 hover:bg-indigo-50"
              title="Edit"
            >
              <Pencil className="h-4 w-4" />
            </button>
          </div>
        </td>
      </tr>

      {expanded && (
        <tr>
          <td colSpan={8} className="bg-gray-50 px-8 py-5">
            {editing ? (
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">
                    Title
                  </label>
                  <input
                    type="text"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">
                      Given
                    </label>
                    <textarea
                      value={editGiven}
                      onChange={(e) => setEditGiven(e.target.value)}
                      rows={3}
                      className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">
                      When
                    </label>
                    <textarea
                      value={editWhen}
                      onChange={(e) => setEditWhen(e.target.value)}
                      rows={3}
                      className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">
                      Then
                    </label>
                    <textarea
                      value={editThen}
                      onChange={(e) => setEditThen(e.target.value)}
                      rows={3}
                      className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={handleSave}
                    className="px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded hover:bg-indigo-700"
                  >
                    Save Changes
                  </button>
                  <button
                    onClick={handleCancelEdit}
                    className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-200 rounded hover:bg-gray-300"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="bg-white rounded-lg border border-gray-200 p-4 font-mono text-sm space-y-2">
                  <p>
                    <span className="text-purple-600 font-semibold">Given </span>
                    <span className="text-gray-700">{tc.given}</span>
                  </p>
                  <p>
                    <span className="text-blue-600 font-semibold">When </span>
                    <span className="text-gray-700">{tc.when}</span>
                  </p>
                  <p>
                    <span className="text-green-600 font-semibold">Then </span>
                    <span className="text-gray-700">{tc.then}</span>
                  </p>
                </div>

                <div>
                  <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Expected Outcome
                  </span>
                  <p className="text-sm text-gray-700 mt-1">{tc.expected_outcome}</p>
                </div>

                <div className="flex flex-wrap items-center gap-4">
                  {tc.component && (
                    <div>
                      <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Component
                      </span>
                      <p className="text-sm text-gray-700 mt-0.5">{tc.component}</p>
                    </div>
                  )}
                  {tc.tags.length > 0 && (
                    <div>
                      <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Tags
                      </span>
                      <div className="flex flex-wrap gap-1 mt-0.5">
                        {tc.tags.map((tag) => (
                          <span
                            key={tag}
                            className="inline-block px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700 text-xs"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// TestCases Page
// ---------------------------------------------------------------------------

export default function TestCases() {
  const [allTestCases, setAllTestCases] = useState<TestCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [filterType, setFilterType] = useState("all");
  const [filterPriority, setFilterPriority] = useState("all");
  const [filterStatus, setFilterStatus] = useState("all");
  const [searchText, setSearchText] = useState("");

  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await listTestCases();
        setAllTestCases(res.data);
      } catch (err: any) {
        setError(err.message ?? "Failed to load test cases");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const filtered = useMemo(() => {
    return allTestCases.filter((tc) => {
      if (filterType !== "all" && tc.test_type !== filterType) return false;
      if (filterPriority !== "all" && tc.priority !== filterPriority) return false;
      if (filterStatus !== "all" && tc.status !== filterStatus) return false;
      if (searchText && !tc.title.toLowerCase().includes(searchText.toLowerCase()))
        return false;
      return true;
    });
  }, [allTestCases, filterType, filterPriority, filterStatus, searchText]);

  const handleApprove = async (tcId: string) => {
    try {
      await approveTestCase(tcId);
      setAllTestCases((prev) =>
        prev.map((tc) => (tc.tc_id === tcId ? { ...tc, status: "approved" } : tc)),
      );
    } catch (err: any) {
      setError(err.message ?? "Failed to approve test case");
    }
  };

  const handleReject = async (tcId: string) => {
    try {
      await rejectTestCase(tcId);
      setAllTestCases((prev) =>
        prev.map((tc) => (tc.tc_id === tcId ? { ...tc, status: "rejected" } : tc)),
      );
    } catch (err: any) {
      setError(err.message ?? "Failed to reject test case");
    }
  };

  const handleSave = async (tcId: string, data: Partial<TestCase>) => {
    try {
      await updateTestCase(tcId, data);
      setAllTestCases((prev) =>
        prev.map((tc) => (tc.tc_id === tcId ? { ...tc, ...data } : tc)),
      );
    } catch (err: any) {
      setError(err.message ?? "Failed to update test case");
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
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center justify-between">
          <span className="text-sm">{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      <div>
        <h1 className="text-2xl font-bold text-gray-900">Test Cases</h1>
        <p className="text-gray-500 mt-1">Browse, filter, and manage generated test cases</p>
      </div>

      {/* Filter bar */}
      <div className="bg-white rounded-lg shadow p-4">
        <div className="flex flex-wrap items-center gap-4">
          <Filter className="h-4 w-4 text-gray-400 flex-shrink-0" />

          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {TEST_TYPES.map((t) => (
              <option key={t} value={t}>
                {t === "all" ? "All Types" : t.replace(/_/g, " ")}
              </option>
            ))}
          </select>

          <select
            value={filterPriority}
            onChange={(e) => setFilterPriority(e.target.value)}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {p === "all" ? "All Priorities" : p}
              </option>
            ))}
          </select>

          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s === "all" ? "All Statuses" : s.charAt(0).toUpperCase() + s.slice(1)}
              </option>
            ))}
          </select>

          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search by title..."
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              className="w-full rounded-md border border-gray-300 pl-9 pr-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <span className="text-sm text-gray-500 flex-shrink-0">
            Showing {filtered.length} of {allTestCases.length} test cases
          </span>
        </div>
      </div>

      {/* Table */}
      {allTestCases.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-12 text-center">
          <ClipboardList className="h-12 w-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500 text-lg font-medium">
            No test cases generated yet
          </p>
          <p className="text-gray-400 text-sm mt-1">
            Run a pipeline to generate test cases.
          </p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
          No test cases match the current filters.
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 w-8" />
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  TC ID
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Req ID
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Title
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Type
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Priority
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map((tc) => (
                <TestCaseRow
                  key={tc.tc_id}
                  tc={tc}
                  expanded={expandedId === tc.tc_id}
                  onToggle={() =>
                    setExpandedId(expandedId === tc.tc_id ? null : tc.tc_id)
                  }
                  onApprove={handleApprove}
                  onReject={handleReject}
                  onSave={handleSave}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
