import { useMemo } from "react";
import {
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  WifiOff,
  Trophy,
} from "lucide-react";
import { useWebSocket } from "../hooks/useWebSocket";
import type { WsMessage } from "../hooks/useWebSocket";

interface Props {
  runId: string;
}

interface StageEvent {
  name: string;
  status: "running" | "completed" | "failed";
  startedAt?: string;
  completedAt?: string;
  duration?: number;
  message?: string;
}

function parseDuration(start?: string, end?: string): string | null {
  if (!start || !end) return null;
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 0) return null;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rem = (s % 60).toFixed(0);
  return `${m}m ${rem}s`;
}

export default function LiveProgress({ runId }: Props) {
  const { messages, isConnected, lastEvent } = useWebSocket(runId);

  // Derive stage list from messages
  const stages = useMemo(() => {
    const map = new Map<string, StageEvent>();
    for (const msg of messages) {
      const name = msg.stage;
      if (!name) continue;

      if (msg.type === "stage_started" || msg.status === "running") {
        if (!map.has(name)) {
          map.set(name, {
            name,
            status: "running",
            startedAt: msg.timestamp,
          });
        }
      } else if (
        msg.type === "stage_completed" ||
        msg.status === "completed"
      ) {
        const existing = map.get(name) ?? { name, status: "completed" as const };
        map.set(name, {
          ...existing,
          status: "completed",
          completedAt: msg.timestamp,
          message: msg.message,
        });
      } else if (
        msg.type === "stage_failed" ||
        msg.status === "failed"
      ) {
        const existing = map.get(name) ?? { name, status: "failed" as const };
        map.set(name, {
          ...existing,
          status: "failed",
          completedAt: msg.timestamp,
          message: msg.message,
        });
      }
    }
    return Array.from(map.values());
  }, [messages]);

  const pipelineComplete = lastEvent?.type === "pipeline_completed";
  const pipelineFailed = lastEvent?.type === "pipeline_failed";
  const isFinished = pipelineComplete || pipelineFailed;

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5">
      {/* Connection status */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-900">
          Pipeline Progress
        </h3>
        {isConnected ? (
          <span className="flex items-center gap-1.5 text-xs text-green-600">
            <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
            Live
          </span>
        ) : isFinished ? (
          <span className="flex items-center gap-1.5 text-xs text-gray-500">
            <Clock className="h-3.5 w-3.5" />
            Finished
          </span>
        ) : (
          <span className="flex items-center gap-1.5 text-xs text-amber-600">
            <WifiOff className="h-3.5 w-3.5" />
            Disconnected - reconnecting...
          </span>
        )}
      </div>

      {/* No messages yet */}
      {stages.length === 0 && !isFinished && (
        <div className="flex items-center gap-2 text-sm text-gray-500 py-4">
          <Loader2 className="h-4 w-4 animate-spin" />
          {isConnected ? "Waiting for stage events..." : "Connecting..."}
        </div>
      )}

      {/* Vertical timeline */}
      {stages.length > 0 && (
        <div className="relative">
          {/* Vertical line */}
          <div className="absolute left-3 top-2 bottom-2 w-0.5 bg-gray-200" />

          <div className="space-y-0">
            {stages.map((stage, idx) => (
              <div
                key={stage.name}
                className="relative flex items-start gap-4 py-3 animate-fadeIn"
                style={{ animationDelay: `${idx * 100}ms` }}
              >
                {/* Timeline dot */}
                <div className="relative z-10 flex-shrink-0">
                  {stage.status === "running" && (
                    <Loader2 className="h-6 w-6 text-blue-500 animate-spin" />
                  )}
                  {stage.status === "completed" && (
                    <CheckCircle2 className="h-6 w-6 text-green-500" />
                  )}
                  {stage.status === "failed" && (
                    <XCircle className="h-6 w-6 text-red-500" />
                  )}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-medium text-gray-900">
                      {stage.name}
                    </span>
                    {stage.startedAt && stage.completedAt && (
                      <span className="text-xs text-gray-400">
                        {parseDuration(stage.startedAt, stage.completedAt)}
                      </span>
                    )}
                  </div>
                  {stage.status === "running" && (
                    <p className="text-xs text-blue-600 mt-0.5">
                      In progress...
                    </p>
                  )}
                  {stage.message && stage.status !== "running" && (
                    <p
                      className={`text-xs mt-0.5 ${
                        stage.status === "failed"
                          ? "text-red-600"
                          : "text-gray-500"
                      }`}
                    >
                      {stage.message}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Summary bar */}
      {isFinished && (
        <div
          className={`mt-4 flex items-center gap-3 px-4 py-3 rounded-lg ${
            pipelineComplete
              ? "bg-green-50 text-green-800"
              : "bg-red-50 text-red-800"
          }`}
        >
          {pipelineComplete ? (
            <Trophy className="h-5 w-5 text-green-600" />
          ) : (
            <XCircle className="h-5 w-5 text-red-600" />
          )}
          <span className="text-sm font-medium">
            {pipelineComplete
              ? "Pipeline completed successfully"
              : "Pipeline failed"}
          </span>
          {lastEvent?.message && (
            <span className="text-xs ml-auto">{lastEvent.message as string}</span>
          )}
        </div>
      )}

      {/* Inline animation style */}
      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-fadeIn {
          animation: fadeIn 0.3s ease-out forwards;
        }
      `}</style>
    </div>
  );
}
