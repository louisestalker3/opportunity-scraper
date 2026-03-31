import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Settings as SettingsIcon, FolderSearch, Check, AlertCircle, GitBranch, ExternalLink, Wrench } from "lucide-react";
import { getSettings, patchSettings, scanRepos, migrateProjects, ScannedRepo } from "@/api/client";

export default function Settings() {
  const qc = useQueryClient();
  const [reposPath, setReposPath] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [scanResult, setScanResult] = useState<{ repos_path: string; found: ScannedRepo[]; imported: number } | null>(null);
  const [migrateResult, setMigrateResult] = useState<{ queued: number; already_done: number; total: number } | null>(null);

  const { data: settings, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
    staleTime: 0,
    select: (d) => {
      if (reposPath === null) setReposPath(d.repos_path);
      return d;
    },
  });

  const saveMutation = useMutation({
    mutationFn: (path: string) => patchSettings(path),
    onSuccess: (d) => {
      setReposPath(d.repos_path);
      setSaveError(null);
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to save";
      setSaveError(msg);
    },
  });

  const scanMutation = useMutation({
    mutationFn: scanRepos,
    onSuccess: (d) => {
      setScanResult(d);
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });

  const migrateMutation = useMutation({
    mutationFn: migrateProjects,
    onSuccess: (d) => setMigrateResult(d),
  });

  const currentPath = reposPath ?? settings?.repos_path ?? "";
  const isDirty = settings && currentPath !== settings.repos_path;

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <div className="flex items-center gap-3">
        <SettingsIcon size={24} className="text-gray-600" />
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
      </div>

      {/* Repos folder */}
      <section className="bg-white border border-gray-200 rounded-xl p-6 space-y-4">
        <div>
          <h2 className="text-base font-semibold text-gray-900">Projects Folder</h2>
          <p className="text-sm text-gray-500 mt-1">
            Local directory where your git repos live. Each subdirectory that is a git repo can be imported as a project.
          </p>
        </div>

        {isLoading ? (
          <div className="h-10 bg-gray-100 animate-pulse rounded-lg" />
        ) : (
          <div className="flex gap-2">
            <input
              type="text"
              value={currentPath}
              onChange={(e) => { setReposPath(e.target.value); setSaveError(null); }}
              placeholder="/Users/you/repos"
              className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500 font-mono"
            />
            <button
              onClick={() => saveMutation.mutate(currentPath)}
              disabled={!isDirty || saveMutation.isPending}
              className={[
                "px-4 py-2 rounded-lg text-sm font-medium transition-colors",
                isDirty && !saveMutation.isPending
                  ? "bg-green-600 text-white hover:bg-green-700"
                  : "bg-gray-100 text-gray-400 cursor-not-allowed",
              ].join(" ")}
            >
              {saveMutation.isPending ? "Saving…" : saveMutation.isSuccess && !isDirty ? "Saved" : "Save"}
            </button>
          </div>
        )}

        {saveError && (
          <div className="flex items-center gap-2 text-sm text-red-600">
            <AlertCircle size={14} />
            {saveError}
          </div>
        )}
      </section>

      {/* Migrate projects to native */}
      <section className="bg-white border border-gray-200 rounded-xl p-6 space-y-4">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Migrate Projects to Native</h2>
            <p className="text-sm text-gray-500 mt-1">
              Generate <code className="font-mono text-xs bg-gray-100 px-1 rounded">start.sh</code> and{" "}
              <code className="font-mono text-xs bg-gray-100 px-1 rounded">stop.sh</code> for every built project
              that doesn't have them yet. Removes Docker dependencies and standardises port injection.
            </p>
          </div>
          <button
            onClick={() => { setMigrateResult(null); migrateMutation.mutate(); }}
            disabled={migrateMutation.isPending}
            className={[
              "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ml-4",
              migrateMutation.isPending
                ? "bg-gray-100 text-gray-400 cursor-not-allowed"
                : "bg-indigo-600 text-white hover:bg-indigo-700",
            ].join(" ")}
          >
            <Wrench size={15} />
            {migrateMutation.isPending ? "Queuing…" : "Migrate All"}
          </button>
        </div>

        {migrateMutation.isError && (
          <div className="flex items-center gap-2 text-sm text-red-600">
            <AlertCircle size={14} />
            {(migrateMutation.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Migration failed"}
          </div>
        )}

        {migrateResult && (
          <div className="flex items-center gap-2 text-sm">
            <Check size={14} className="text-indigo-600" />
            <span className="text-gray-700">
              <strong className="text-indigo-700">{migrateResult.queued} tasks queued</strong>
              {migrateResult.already_done > 0 && (
                <> — {migrateResult.already_done} already migrated</>
              )}
              {" "}({migrateResult.total} total projects). The build runner will process them automatically.
            </span>
          </div>
        )}
      </section>

      {/* Scan repos */}
      <section className="bg-white border border-gray-200 rounded-xl p-6 space-y-4">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Import Local Repos</h2>
            <p className="text-sm text-gray-500 mt-1">
              Scan the projects folder and import any git repos not yet tracked in OpportunityScraper.
            </p>
          </div>
          <button
            onClick={() => { setScanResult(null); scanMutation.mutate(); }}
            disabled={scanMutation.isPending}
            className={[
              "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap",
              scanMutation.isPending
                ? "bg-gray-100 text-gray-400 cursor-not-allowed"
                : "bg-green-600 text-white hover:bg-green-700",
            ].join(" ")}
          >
            <FolderSearch size={15} />
            {scanMutation.isPending ? "Scanning…" : "Scan & Import"}
          </button>
        </div>

        {scanMutation.isError && (
          <div className="flex items-center gap-2 text-sm text-red-600">
            <AlertCircle size={14} />
            {(scanMutation.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Scan failed"}
          </div>
        )}

        {scanResult && (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm">
              <Check size={14} className="text-green-600" />
              <span className="text-gray-700">
                Found <strong>{scanResult.found.length}</strong> repo{scanResult.found.length !== 1 ? "s" : ""} —{" "}
                <strong className="text-green-700">{scanResult.imported} newly imported</strong>
                {scanResult.imported === 0 ? " (all already tracked)" : ""}
              </span>
            </div>

            {scanResult.found.length > 0 && (
              <div className="border border-gray-200 rounded-lg divide-y divide-gray-100 overflow-hidden">
                {scanResult.found.map((repo) => (
                  <div key={repo.slug} className="flex items-center gap-3 px-4 py-3">
                    <GitBranch size={14} className="text-gray-400 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-gray-900 font-mono">{repo.slug}</span>
                        {repo.already_tracked ? (
                          <span className="text-xs px-1.5 py-0.5 bg-gray-100 text-gray-500 rounded">tracked</span>
                        ) : (
                          <span className="text-xs px-1.5 py-0.5 bg-green-100 text-green-700 rounded">imported</span>
                        )}
                      </div>
                      {repo.description && (
                        <p className="text-xs text-gray-500 truncate mt-0.5">{repo.description}</p>
                      )}
                    </div>
                    {repo.remote && (
                      <a
                        href={repo.remote.startsWith("http") ? repo.remote : undefined}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-gray-400 hover:text-gray-600 shrink-0"
                        title={repo.remote}
                      >
                        <ExternalLink size={13} />
                      </a>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
