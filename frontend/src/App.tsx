import { useState } from "react";
import { Outlet, NavLink } from "react-router-dom";
import { TrendingUp, Kanban, Home, RefreshCw, Boxes, FlaskConical, Settings } from "lucide-react";
import { api } from "@/api/client";
import RunnerStatus from "@/components/RunnerStatus";

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

function ScraperButton() {
  const [state, setState] = useState<"idle" | "running" | "done">("idle");

  const trigger = async () => {
    if (state === "running") return;
    setState("running");
    try {
      await api.post("/api/scrape/trigger/all");
      setState("done");
      setTimeout(() => setState("idle"), 3000);
    } catch {
      setState("idle");
    }
  };

  return (
    <button
      onClick={trigger}
      disabled={state === "running"}
      title="Run scraper now"
      className={[
        "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
        state === "done"
          ? "bg-green-100 text-green-700"
          : state === "running"
          ? "bg-gray-100 text-gray-400 cursor-not-allowed"
          : "bg-gray-100 text-gray-600 hover:bg-gray-200",
      ].join(" ")}
    >
      <RefreshCw size={13} className={state === "running" ? "animate-spin" : ""} />
      {state === "done" ? "Queued!" : state === "running" ? "Queuing…" : "Run Scraper"}
    </button>
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
              <NavItem to="/projects" icon={Boxes} label="Projects" />
              <NavItem to="/analyze" icon={FlaskConical} label="Analyze" />
              <NavItem to="/settings" icon={Settings} label="Settings" />
              <ScraperButton />
              <RunnerStatus />
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
