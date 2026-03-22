import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useRef,
} from "react";
import { X, CheckCircle2, AlertCircle, Info, AlertTriangle } from "lucide-react";

type NotificationType = "success" | "error" | "info" | "warning";

interface Notification {
  id: number;
  message: string;
  type: NotificationType;
  visible: boolean;
}

interface NotificationContextValue {
  notify: (message: string, type?: NotificationType) => void;
}

const NotificationContext = createContext<NotificationContextValue>({
  notify: () => {},
});

export function useNotification() {
  return useContext(NotificationContext);
}

const typeStyles: Record<
  NotificationType,
  { bg: string; border: string; text: string; icon: React.ReactNode }
> = {
  success: {
    bg: "bg-green-50",
    border: "border-green-200",
    text: "text-green-800",
    icon: <CheckCircle2 className="h-4 w-4 text-green-500" />,
  },
  error: {
    bg: "bg-red-50",
    border: "border-red-200",
    text: "text-red-800",
    icon: <AlertCircle className="h-4 w-4 text-red-500" />,
  },
  info: {
    bg: "bg-blue-50",
    border: "border-blue-200",
    text: "text-blue-800",
    icon: <Info className="h-4 w-4 text-blue-500" />,
  },
  warning: {
    bg: "bg-yellow-50",
    border: "border-yellow-200",
    text: "text-yellow-800",
    icon: <AlertTriangle className="h-4 w-4 text-yellow-500" />,
  },
};

const AUTO_DISMISS_MS = 5000;

export default function NotificationProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const counterRef = useRef(0);

  const dismiss = useCallback((id: number) => {
    // Start hide animation
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, visible: false } : n))
    );
    // Remove after animation
    setTimeout(() => {
      setNotifications((prev) => prev.filter((n) => n.id !== id));
    }, 300);
  }, []);

  const notify = useCallback(
    (message: string, type: NotificationType = "info") => {
      const id = ++counterRef.current;
      setNotifications((prev) => [
        ...prev,
        { id, message, type, visible: true },
      ]);
    },
    []
  );

  // Auto-dismiss
  useEffect(() => {
    const timers = notifications
      .filter((n) => n.visible)
      .map((n) =>
        setTimeout(() => dismiss(n.id), AUTO_DISMISS_MS)
      );
    return () => timers.forEach(clearTimeout);
  }, [notifications, dismiss]);

  return (
    <NotificationContext.Provider value={{ notify }}>
      {children}

      {/* Toast stack */}
      <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none">
        {notifications.map((n) => {
          const style = typeStyles[n.type];
          return (
            <div
              key={n.id}
              className={`pointer-events-auto flex items-start gap-3 px-4 py-3 rounded-lg shadow-lg border text-sm font-medium transition-all duration-300 ease-in-out ${
                style.bg
              } ${style.border} ${style.text} ${
                n.visible
                  ? "translate-x-0 opacity-100"
                  : "translate-x-full opacity-0"
              }`}
            >
              <span className="mt-0.5 flex-shrink-0">{style.icon}</span>
              <span className="flex-1">{n.message}</span>
              <button
                onClick={() => dismiss(n.id)}
                className="flex-shrink-0 ml-2 hover:opacity-70 transition-opacity"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          );
        })}
      </div>
    </NotificationContext.Provider>
  );
}
