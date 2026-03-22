const colorMap: Record<string, { bg: string; text: string; dot?: string }> = {
  completed: { bg: "bg-green-100", text: "text-green-700", dot: "bg-green-500" },
  approved: { bg: "bg-green-100", text: "text-green-700", dot: "bg-green-500" },
  passed: { bg: "bg-green-100", text: "text-green-700", dot: "bg-green-500" },
  running: { bg: "bg-blue-100", text: "text-blue-700", dot: "bg-blue-500" },
  pending: { bg: "bg-blue-100", text: "text-blue-700", dot: "bg-blue-500" },
  failed: { bg: "bg-red-100", text: "text-red-700", dot: "bg-red-500" },
  rejected: { bg: "bg-red-100", text: "text-red-700", dot: "bg-red-500" },
  skipped: { bg: "bg-gray-100", text: "text-gray-600", dot: "bg-gray-400" },
  generated: { bg: "bg-yellow-100", text: "text-yellow-700", dot: "bg-yellow-500" },
};

const pulseStatuses = new Set(["running", "pending"]);

interface Props {
  status: string;
  size?: "sm" | "md";
}

export default function StatusBadge({ status, size = "md" }: Props) {
  const normalized = status.toLowerCase();
  const colors = colorMap[normalized] ?? {
    bg: "bg-gray-100",
    text: "text-gray-600",
    dot: "bg-gray-400",
  };
  const isPulsing = pulseStatuses.has(normalized);

  const sizeClasses =
    size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-xs";
  const dotSize = size === "sm" ? "h-1.5 w-1.5" : "h-2 w-2";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-medium ${colors.bg} ${colors.text} ${sizeClasses}`}
    >
      <span
        className={`${dotSize} rounded-full ${colors.dot} ${isPulsing ? "animate-pulse" : ""}`}
      />
      {status.charAt(0).toUpperCase() + status.slice(1).toLowerCase()}
    </span>
  );
}
