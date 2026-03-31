import { useRef, useEffect } from "react";
import { ExternalLink } from "lucide-react";

function useAutoScroll(dep: unknown) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [dep]);
  return ref;
}

export default function BuildConsole({
  log,
  status,
  repoUrl,
}: {
  log: string | null;
  status: string | null;
  repoUrl: string | null;
}) {
  const ref = useAutoScroll(log);
  const lines = (log ?? "Waiting for build runner...").split("\n").filter(Boolean);

  return (
    <div className="bg-gray-950 border border-gray-800 rounded-2xl overflow-hidden">
      {/* Title bar */}
      <div className="flex items-center gap-2 px-4 py-2.5 bg-gray-900 border-b border-gray-800">
        <span className="w-3 h-3 rounded-full bg-red-500/70" />
        <span className="w-3 h-3 rounded-full bg-yellow-500/70" />
        <span className="w-3 h-3 rounded-full bg-green-500/70" />
        <span className="ml-2 text-xs text-gray-400 font-mono">build output</span>
        {status === "building" && (
          <span className="ml-auto flex items-center gap-1.5 text-xs text-blue-400 animate-pulse">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-400 inline-block" />
            running
          </span>
        )}
        {status === "built" && repoUrl && (
          <a href={repoUrl} target="_blank" rel="noopener noreferrer"
            className="ml-auto text-xs text-green-400 hover:text-green-300 flex items-center gap-1">
            <ExternalLink size={11} /> View repo
          </a>
        )}
        {status === "failed" && (
          <span className="ml-auto text-xs text-red-400">failed</span>
        )}
      </div>

      {/* Log output */}
      <div ref={ref} className="px-4 py-3 font-mono text-xs leading-6 text-green-400 max-h-96 overflow-y-auto">
        {lines.map((line, i) => {
          const isError = line.startsWith("❌");
          const isDone = line.startsWith("✅");
          const isCmd = line.startsWith("▶");
          const isWrite = line.startsWith("✍") || line.startsWith("✏");
          return (
            <div key={i} className={
              isError ? "text-red-400" :
              isDone ? "text-green-300 font-semibold" :
              isCmd ? "text-yellow-300" :
              isWrite ? "text-cyan-400" :
              "text-green-400"
            }>
              <span className="select-none text-gray-600 mr-3">{String(i + 1).padStart(3, " ")}</span>
              {line}
            </div>
          );
        })}
        {status === "building" && (
          <div className="text-gray-500 animate-pulse mt-1">
            <span className="select-none text-gray-700 mr-3">{String(lines.length + 1).padStart(3, " ")}</span>
            █
          </div>
        )}
      </div>
    </div>
  );
}
