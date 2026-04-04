import { type ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import {
  FlaskConical,
  LayoutDashboard,
  FileText,
  CheckSquare,
  Code,
  Globe,
  Zap,
  Settings,
  Clock,
  BarChart3,
  Moon,
  Sun,
} from 'lucide-react';
import { useDarkMode } from '../hooks/useDarkMode';

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/requirements', label: 'Requirements', icon: FileText },
  { to: '/test-cases', label: 'Test Cases', icon: CheckSquare },
  { to: '/bdd', label: 'BDD Code', icon: Code },
  { to: '/crawler', label: 'Crawler', icon: Globe },
  { to: '/api-tests', label: 'API Tests', icon: Zap },
  { to: '/metrics', label: 'Metrics', icon: BarChart3 },
  { to: '/config', label: 'Config', icon: Settings },
  { to: '/history', label: 'History', icon: Clock },
];

export default function Layout({ children }: { children: ReactNode }) {
  const [dark, toggleDark] = useDarkMode();

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 flex-shrink-0 bg-gray-900 text-white flex flex-col" role="navigation" aria-label="Main navigation">
        {/* Logo */}
        <div className="flex items-center gap-3 px-5 py-5 border-b border-gray-700/50">
          <FlaskConical className="h-7 w-7 text-indigo-400" aria-hidden="true" />
          <span className="text-lg font-semibold tracking-tight">STLC Platform</span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1" aria-label="Sidebar navigation">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                [
                  'flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:outline-none',
                  isActive
                    ? 'bg-gray-800 text-white border-l-[3px] border-indigo-400 pl-[9px]'
                    : 'text-gray-400 hover:text-white hover:bg-gray-800/50',
                ].join(' ')
              }
            >
              <Icon className="h-[18px] w-[18px] flex-shrink-0" aria-hidden="true" />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Dark mode toggle + Footer */}
        <div className="px-5 py-4 border-t border-gray-700/50 flex items-center justify-between">
          <span className="text-xs text-gray-500">v0.1.0</span>
          <button
            onClick={toggleDark}
            className="p-1.5 rounded-md text-gray-400 hover:text-white hover:bg-gray-800 transition-colors focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:outline-none"
            aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto bg-gray-50 dark:bg-gray-900 dark:text-gray-100" role="main">{children}</main>
    </div>
  );
}
