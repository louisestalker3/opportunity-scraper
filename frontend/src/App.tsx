import { Outlet, NavLink } from "react-router-dom";
import { TrendingUp, Kanban, Home } from "lucide-react";

function NavItem({
  to,
  icon: Icon,
  label,
  end,
}: {
  to: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string;
  end?: boolean;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        [
          "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors",
          isActive
            ? "bg-green-100 text-green-800"
            : "text-gray-600 hover:text-gray-900 hover:bg-gray-100",
        ].join(" ")
      }
    >
      <Icon size={16} />
      {label}
    </NavLink>
  );
}

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Top nav */}
      <header className="sticky top-0 z-10 bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-14">
            {/* Logo */}
            <div className="flex items-center gap-2">
              <TrendingUp size={22} className="text-green-600" />
              <span className="font-bold text-gray-900 text-base tracking-tight">
                OpportunityScraper
              </span>
            </div>

            {/* Nav links */}
            <nav className="flex items-center gap-1">
              <NavItem to="/" icon={Home} label="Dashboard" end />
              <NavItem to="/pipeline" icon={Kanban} label="My Pipeline" />
            </nav>
          </div>
        </div>
      </header>

      {/* Page content */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8">
        <Outlet />
      </main>

      <footer className="border-t border-gray-200 py-4 text-center text-xs text-gray-400">
        OpportunityScraper &mdash; market intelligence for indie developers
      </footer>
    </div>
  );
}
