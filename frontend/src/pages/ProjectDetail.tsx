import { useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  ArrowLeft, ExternalLink, GitBranch, TrendingUp, Hammer, AlertCircle,
  Trash2, RefreshCw, Sparkles, CheckCircle2, Plus, X, ChevronDown, ChevronUp,
  Bug, Wrench, Star, Zap, Clock, PlayCircle, PauseCircle, Upload, Pencil,
  Palette, Settings2,
} from "lucide-react";
import BuildConsole from "@/components/BuildConsole";
import RunPanel from "@/components/RunPanel";
import {
  usePipeline, useOpportunity, useBuildApp, useStartProject, useStopProject,
  useForceStopProject, useRemovePipelineItem,
  useNameSuggestions, useGenerateNames, useSelectName, useDeleteName, useSetManualName,
  useLogoSuggestions, useGenerateLogos, useSelectLogo, useDeleteLogo, useUploadLogo,
  useTasks, useCreateTask, useUpdateTask, useDeleteTask,
} from "@/hooks/useOpportunities";
import type { ProjectTask, TaskType, TaskStatus } from "@/api/client";

type Tab = "branding" | "build" | "tasks";

// ─── Name Panel ───────────────────────────────────────────────────────────────

function NamePanel({ itemId }: { itemId: string }) {
  const { data: names = [], isLoading } = useNameSuggestions(itemId);
  const generateMutation = useGenerateNames(itemId);
  const selectMutation = useSelectName(itemId);
  const deleteMutation = useDeleteName(itemId);
  const setManualMutation = useSetManualName(itemId);
  const [hint, setHint] = useState("");
  const [manualName, setManualName] = useState("");

  const chosen = names.find((n) => n.status === "chosen");
  const suggestions = names.filter((n) => n.status !== "rejected");

  const handleGenerate = () => {
    generateMutation.mutate({ count: 6, hint: hint.trim() || undefined });
  };

  const handleSetManual = () => {
    const name = manualName.trim();
    if (!name) return;
    setManualMutation.mutate(name, { onSuccess: () => setManualName("") });
  };

  return (
    <div className="space-y-4">
      {/* Header row */}
      <div className="flex items-start justify-between gap-4">
        <div>
          {chosen ? (
            <p className="text-sm text-green-700 font-medium flex items-center gap-1.5">
              <CheckCircle2 size={14} />
              Chosen: <span className="font-bold">{chosen.name}</span>
            </p>
          ) : (
            <p className="text-xs text-gray-400">Choose a name before generating logos.</p>
          )}
        </div>
        <button
          onClick={handleGenerate}
          disabled={generateMutation.isPending}
          className="shrink-0 flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50 transition-colors"
        >
          <Sparkles size={12} />
          {generateMutation.isPending ? "Generating…" : suggestions.length === 0 ? "Generate Names" : "More Names"}
        </button>
      </div>

      {/* AI hint */}
      <div className="flex gap-2">
        <input
          type="text"
          value={hint}
          onChange={(e) => setHint(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleGenerate()}
          placeholder='Hint for AI, e.g. "add Guild to the end" or "make it more playful"…'
          className="flex-1 text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-purple-400 placeholder:text-gray-300"
        />
        {hint.trim() && (
          <button onClick={() => setHint("")} className="text-gray-300 hover:text-gray-500 px-1">
            <X size={14} />
          </button>
        )}
      </div>

      {/* Manual entry */}
      <div className="border-t border-gray-100 pt-3">
        <label className="text-xs font-medium text-gray-500 mb-1.5 block flex items-center gap-1">
          <Pencil size={11} /> Enter a name manually
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={manualName}
            onChange={(e) => setManualName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSetManual()}
            placeholder="e.g. FlowDesk, Taskr, Planly…"
            className="flex-1 text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-400 placeholder:text-gray-300"
          />
          <button
            onClick={handleSetManual}
            disabled={!manualName.trim() || setManualMutation.isPending}
            className="shrink-0 text-xs font-medium px-3 py-2 rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 transition-colors"
          >
            {setManualMutation.isPending ? "Setting…" : "Set Name"}
          </button>
        </div>
      </div>

      {isLoading && <div className="text-sm text-gray-400">Loading…</div>}

      {suggestions.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {suggestions.map((name) => (
            <div
              key={name.id}
              className={`relative border rounded-xl p-4 transition-all ${
                name.status === "chosen"
                  ? "border-green-400 bg-green-50 ring-1 ring-green-300"
                  : "border-gray-200 bg-gray-50 hover:border-gray-300"
              }`}
            >
              <button
                onClick={() => deleteMutation.mutate(name.id)}
                className="absolute top-2 right-2 p-1 text-gray-300 hover:text-gray-500 rounded"
              >
                <X size={12} />
              </button>
              <div className="font-bold text-gray-900 text-base pr-5">{name.name}</div>
              {name.tagline && <div className="text-xs text-gray-500 mt-0.5">{name.tagline}</div>}
              {name.rationale && (
                <div className="text-xs text-gray-400 mt-2 leading-relaxed">{name.rationale}</div>
              )}
              {name.status !== "chosen" && (
                <button
                  onClick={() => selectMutation.mutate(name.id)}
                  disabled={selectMutation.isPending}
                  className="mt-3 text-xs font-medium px-3 py-1 rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 transition-colors"
                >
                  Choose This Name
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {!isLoading && suggestions.length === 0 && (
        <p className="text-sm text-gray-400">
          No name suggestions yet. Click "Generate Names" to get AI suggestions, or enter one manually above.
        </p>
      )}
    </div>
  );
}

// ─── Logo Panel ───────────────────────────────────────────────────────────────

function LogoPanel({ itemId, chosenName }: { itemId: string; chosenName: string | null }) {
  const { data: logos = [], isLoading } = useLogoSuggestions(itemId);
  const generateMutation = useGenerateLogos(itemId);
  const selectMutation = useSelectLogo(itemId);
  const deleteMutation = useDeleteLogo(itemId);
  const uploadMutation = useUploadLogo(itemId);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const chosen = logos.find((l) => l.status === "chosen");
  const suggestions = logos.filter((l) => l.status !== "rejected");

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) uploadMutation.mutate(file);
    e.target.value = "";
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          {chosen && (
            <p className="text-sm text-green-700 font-medium flex items-center gap-1.5">
              <CheckCircle2 size={14} />
              Chosen: <span className="font-bold">{chosen.concept_name}</span>
            </p>
          )}
          {!chosenName && (
            <p className="text-xs text-amber-600 flex items-center gap-1">
              <AlertCircle size={11} /> Choose a name first to generate AI logos
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Upload button */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".svg,.png,.jpg,.jpeg,.webp"
            onChange={handleFileChange}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadMutation.isPending}
            className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            <Upload size={12} />
            {uploadMutation.isPending ? "Uploading…" : "Upload Logo"}
          </button>

          {/* AI generate button */}
          <button
            onClick={() => generateMutation.mutate(3)}
            disabled={generateMutation.isPending || !chosenName}
            title={!chosenName ? "Choose a name first" : undefined}
            className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Sparkles size={12} />
            {generateMutation.isPending ? "Generating…" : suggestions.length === 0 ? "Generate Logos" : "More Logos"}
          </button>
        </div>
      </div>

      <p className="text-xs text-gray-400">
        Upload an SVG, PNG, JPEG, or WebP file — or let AI generate SVG logo concepts from your chosen name.
      </p>

      {(generateMutation.isPending || uploadMutation.isPending) && (
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <div className="animate-spin rounded-full h-4 w-4 border-2 border-gray-300 border-t-purple-600" />
          {generateMutation.isPending ? "Claude is designing logos…" : "Uploading…"}
        </div>
      )}

      {isLoading && <div className="text-sm text-gray-400">Loading…</div>}

      {suggestions.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {suggestions.map((logo) => (
            <div
              key={logo.id}
              className={`relative border rounded-xl p-4 space-y-3 transition-all ${
                logo.status === "chosen"
                  ? "border-green-400 bg-green-50 ring-1 ring-green-300"
                  : "border-gray-200 hover:border-gray-300"
              }`}
            >
              <button
                onClick={() => deleteMutation.mutate(logo.id)}
                className="absolute top-2 right-2 p-1 text-gray-300 hover:text-gray-500 rounded"
              >
                <X size={12} />
              </button>

              {/* Preview */}
              <div
                className="w-full bg-white rounded-lg p-3 flex items-center justify-center border border-gray-100"
                style={{ minHeight: 72 }}
                dangerouslySetInnerHTML={{ __html: logo.svg_content }}
              />

              <div>
                <div className="font-semibold text-sm text-gray-900">{logo.concept_name}</div>
                <div className="text-xs text-gray-400 capitalize">{logo.style}</div>
              </div>

              {/* Color swatches — only for AI-generated logos */}
              {logo.style !== "custom" && (
                <div className="flex gap-1.5">
                  {Object.values(logo.color_palette).map((hex, i) => (
                    <div
                      key={i}
                      className="w-5 h-5 rounded-full border border-white shadow-sm ring-1 ring-gray-200"
                      style={{ background: hex as string }}
                      title={hex as string}
                    />
                  ))}
                </div>
              )}

              {logo.description && logo.description !== "Manually uploaded logo" && (
                <p className="text-xs text-gray-400 leading-relaxed">{logo.description}</p>
              )}

              {logo.status !== "chosen" && (
                <button
                  onClick={() => selectMutation.mutate(logo.id)}
                  disabled={selectMutation.isPending}
                  className="w-full text-xs font-medium py-1.5 rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 transition-colors"
                >
                  Choose This Logo
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {!isLoading && !generateMutation.isPending && !uploadMutation.isPending && suggestions.length === 0 && (
        <p className="text-sm text-gray-400">
          No logos yet. Upload your own or generate AI concepts once a name is chosen.
        </p>
      )}
    </div>
  );
}

// ─── Task Panel ───────────────────────────────────────────────────────────────

const TYPE_ICONS: Record<TaskType, React.ReactNode> = {
  feature: <Star size={13} className="text-blue-500" />,
  bug: <Bug size={13} className="text-red-500" />,
  fix: <Wrench size={13} className="text-yellow-600" />,
  improvement: <Zap size={13} className="text-purple-500" />,
};

const STATUS_CLASSES: Record<TaskStatus, string> = {
  draft: "bg-gray-100 text-gray-600",
  ready: "bg-blue-100 text-blue-700",
  in_progress: "bg-yellow-100 text-yellow-700",
  done: "bg-green-100 text-green-700",
  waiting_for_agent: "bg-orange-100 text-orange-700",
  paused: "bg-gray-100 text-gray-500",
};

const STATUS_LABELS: Record<TaskStatus, string> = {
  draft: "Draft",
  ready: "Ready",
  in_progress: "In Progress",
  done: "Done",
  waiting_for_agent: "Waiting (Rate Limit)",
  paused: "Paused",
};

function TaskRow({
  task,
  onUpdate,
  onDelete,
}: {
  task: ProjectTask;
  itemId: string;
  onUpdate: (taskId: string, payload: object) => void;
  onDelete: (taskId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(task.title);
  const [editDesc, setEditDesc] = useState(task.description ?? "");

  const saveEdit = () => {
    onUpdate(task.id, { title: editTitle, description: editDesc || null });
    setEditing(false);
  };

  return (
    <div className={`border rounded-xl transition-all ${
      task.status === "in_progress" ? "border-yellow-300 bg-yellow-50" :
      task.status === "done" ? "border-green-200 bg-green-50" :
      task.status === "waiting_for_agent" ? "border-orange-300 bg-orange-50" :
      "border-gray-200 bg-white"
    }`}>
      <div className="flex items-start gap-3 p-4">
        <div className="mt-0.5 shrink-0">{TYPE_ICONS[task.type]}</div>

        <div className="flex-1 min-w-0">
          {editing ? (
            <div className="space-y-2">
              <input
                className="w-full text-sm border border-gray-300 rounded-lg px-2 py-1 focus:outline-none focus:ring-2 focus:ring-blue-400"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
              />
              <textarea
                className="w-full text-xs border border-gray-300 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-400 resize-none"
                rows={3}
                placeholder="Description (optional)…"
                value={editDesc}
                onChange={(e) => setEditDesc(e.target.value)}
              />
              <div className="flex gap-2">
                <button onClick={saveEdit} className="text-xs px-3 py-1 bg-blue-600 text-white rounded-lg hover:bg-blue-700">Save</button>
                <button onClick={() => setEditing(false)} className="text-xs px-3 py-1 text-gray-500 hover:text-gray-700">Cancel</button>
              </div>
            </div>
          ) : (
            <div
              className="text-sm font-medium text-gray-900 cursor-pointer hover:text-blue-700"
              onClick={() => setEditing(true)}
            >
              {task.title}
            </div>
          )}

          {!editing && task.description && (
            <div className="text-xs text-gray-500 mt-0.5 line-clamp-2">{task.description}</div>
          )}

          {task.status === "in_progress" && (
            <div className="flex items-center gap-1.5 mt-1 text-xs text-yellow-700">
              <div className="animate-spin rounded-full h-3 w-3 border border-yellow-400 border-t-yellow-700" />
              Agent is working on this…
            </div>
          )}

          {task.status === "waiting_for_agent" && task.retry_after && (
            <div className="text-xs text-orange-600 mt-1">
              <Clock size={11} className="inline mr-1" />
              Waiting for Claude rate limit to reset. Will retry automatically.
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_CLASSES[task.status]}`}>
            {STATUS_LABELS[task.status]}
          </span>

          {task.status === "draft" && (
            <button
              onClick={() => onUpdate(task.id, { status: "ready" })}
              title="Mark ready for AI"
              className="text-xs px-2 py-0.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors"
            >
              <PlayCircle size={13} />
            </button>
          )}
          {task.status === "ready" && (
            <button
              onClick={() => onUpdate(task.id, { status: "draft" })}
              title="Move back to draft"
              className="text-xs px-2 py-0.5 rounded-lg bg-gray-200 text-gray-700 hover:bg-gray-300 transition-colors"
            >
              <PauseCircle size={13} />
            </button>
          )}

          {task.agent_response && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="text-gray-400 hover:text-gray-600"
            >
              {expanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
            </button>
          )}

          <button
            onClick={() => onDelete(task.id)}
            className="p-1 text-gray-300 hover:text-red-400 transition-colors"
          >
            <X size={13} />
          </button>
        </div>
      </div>

      {expanded && task.agent_response && (
        <div className="border-t border-gray-100 px-4 pb-4 pt-3">
          <div className="text-xs font-medium text-gray-500 mb-2">Agent Output</div>
          <pre className="text-xs bg-gray-900 text-green-400 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap max-h-64 overflow-y-auto font-mono">
            {task.agent_response}
          </pre>
        </div>
      )}
    </div>
  );
}

function AddTaskForm({ onAdd, onCancel }: { onAdd: (payload: object) => void; onCancel: () => void }) {
  const [type, setType] = useState<TaskType>("feature");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("medium");
  const [startAsReady, setStartAsReady] = useState(false);

  return (
    <div className="border border-blue-200 bg-blue-50 rounded-xl p-4 space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-600">Type</label>
          <select
            value={type}
            onChange={(e) => setType(e.target.value as TaskType)}
            className="text-sm border border-gray-200 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
          >
            <option value="feature">Feature</option>
            <option value="bug">Bug</option>
            <option value="fix">Fix</option>
            <option value="improvement">Improvement</option>
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-600">Priority</label>
          <select
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            className="text-sm border border-gray-200 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-gray-600">Title *</label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g. Add dark mode, Fix login bug, Improve loading speed…"
          className="text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-gray-600">
          Description <span className="text-gray-400">(optional)</span>
        </label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Describe the feature, bug, or what needs fixing…"
          rows={3}
          className="text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400 resize-none"
        />
      </div>

      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="startReady"
          checked={startAsReady}
          onChange={(e) => setStartAsReady(e.target.checked)}
          className="rounded"
        />
        <label htmlFor="startReady" className="text-xs text-gray-600">
          Mark as <strong>Ready for AI</strong> immediately
        </label>
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => {
            if (!title.trim()) return;
            onAdd({ type, title: title.trim(), description: description.trim() || null, priority, status: startAsReady ? "ready" : "draft" });
          }}
          disabled={!title.trim()}
          className="text-sm px-4 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          Add Task
        </button>
        <button onClick={onCancel} className="text-sm px-4 py-1.5 text-gray-500 hover:text-gray-700">
          Cancel
        </button>
      </div>
    </div>
  );
}

function TasksPanel({ itemId }: { itemId: string }) {
  const { data: tasks = [], isLoading } = useTasks(itemId);
  const createMutation = useCreateTask(itemId);
  const updateMutation = useUpdateTask(itemId);
  const deleteMutation = useDeleteTask(itemId);
  const [showAdd, setShowAdd] = useState(false);
  const [filter, setFilter] = useState<string>("all");

  const readyCount = tasks.filter((t) => t.status === "ready").length;
  const inProgressCount = tasks.filter((t) => t.status === "in_progress").length;
  const waitingCount = tasks.filter((t) => t.status === "waiting_for_agent").length;

  const FILTERS = ["all", "draft", "ready", "in_progress", "done", "paused"];
  const filtered = filter === "all" ? tasks : tasks.filter((t) => t.status === filter);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3 text-xs text-gray-500">
          {readyCount > 0 && <span className="text-blue-600 font-medium">{readyCount} ready</span>}
          {inProgressCount > 0 && <span className="text-yellow-600 font-medium animate-pulse">{inProgressCount} running</span>}
          {waitingCount > 0 && <span className="text-orange-600 font-medium">{waitingCount} waiting</span>}
          {readyCount === 0 && inProgressCount === 0 && waitingCount === 0 && tasks.length > 0 && (
            <span className="text-gray-400">{tasks.length} task{tasks.length !== 1 ? "s" : ""}</span>
          )}
        </div>

        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 transition-colors"
        >
          <Plus size={13} /> Add Task
        </button>
      </div>

      {tasks.length > 0 && (
        <div className="flex gap-1 flex-wrap">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`text-xs px-2.5 py-1 rounded-full capitalize transition-colors ${
                filter === f ? "bg-gray-800 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {f === "all" ? `All (${tasks.length})` : `${f.replace("_", " ")} (${tasks.filter(t => t.status === f).length})`}
            </button>
          ))}
        </div>
      )}

      {showAdd && (
        <AddTaskForm
          onAdd={(payload) => {
            createMutation.mutate(payload as Parameters<typeof createMutation.mutate>[0]);
            setShowAdd(false);
          }}
          onCancel={() => setShowAdd(false)}
        />
      )}

      {isLoading && <div className="text-sm text-gray-400">Loading tasks…</div>}

      {filtered.length > 0 ? (
        <div className="space-y-2">
          {filtered.map((task) => (
            <TaskRow
              key={task.id}
              task={task}
              itemId={itemId}
              onUpdate={(taskId, payload) => updateMutation.mutate({ taskId, payload })}
              onDelete={(taskId) => deleteMutation.mutate(taskId)}
            />
          ))}
        </div>
      ) : (
        !isLoading && !showAdd && (
          <p className="text-sm text-gray-400">
            {filter === "all"
              ? 'No tasks yet. Click "Add Task" to start listing features and bugs.'
              : `No ${filter.replace("_", " ")} tasks.`}
          </p>
        )
      )}

      {readyCount > 0 && inProgressCount === 0 && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl px-4 py-3 text-sm text-blue-700 flex items-center gap-2">
          <PlayCircle size={15} />
          <span>{readyCount} task{readyCount !== 1 ? "s" : ""} ready — the build runner will pick them up automatically.</span>
        </div>
      )}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "branding", label: "Branding", icon: <Palette size={14} /> },
  { id: "build", label: "Build", icon: <Hammer size={14} /> },
  { id: "tasks", label: "Tasks", icon: <Settings2 size={14} /> },
];

export default function ProjectDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: items, isLoading } = usePipeline();
  const item = items?.find((i) => i.id === id);

  const { data: opp } = useOpportunity(item?.opportunity_id ?? "");
  const buildMutation = useBuildApp();
  const startMutation = useStartProject();
  const stopMutation = useStopProject();
  const forceStopMutation = useForceStopProject();
  const removeMutation = useRemovePipelineItem();

  const [tab, setTab] = useState<Tab>("branding");

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="skeleton h-6 w-40 rounded" />
        <div className="skeleton h-12 w-72 rounded" />
        <div className="skeleton h-64 w-full rounded-2xl" />
      </div>
    );
  }

  if (!item) {
    return (
      <div className="text-center py-24">
        <p className="text-gray-500">Project not found.</p>
        <Link to="/projects" className="mt-4 inline-block text-emerald-600 underline text-sm">
          Back to Projects
        </Link>
      </div>
    );
  }

  let plan: Record<string, unknown> = {};
  try { plan = JSON.parse(item.app_plan ?? "{}"); } catch { /* ignore */ }

  const appName = item.chosen_name || (plan.app_name as string) || opp?.app_profile?.name || "Unnamed App";
  const tagline = plan.tagline as string | undefined;
  const scale = plan.scale as string | undefined;
  const stack = plan.tech_stack as Record<string, string> | undefined;
  const buildStatus = item.build_status;
  const runStatus = item.run_status ?? null;

  // Badge counts for tab labels
  const { data: tasks = [] } = useTasks(item.id);
  const activeTaskCount = tasks.filter((t) => t.status === "ready" || t.status === "in_progress").length;

  return (
    <div className="space-y-6">
      {/* Build console — shown above everything when building */}
      {(buildStatus === "building" || item.build_log) && (
        <BuildConsole log={item.build_log} status={buildStatus} repoUrl={item.built_repo_url} />
      )}

      {/* Breadcrumb */}
      <Link to="/projects" className="inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-700 transition-colors">
        <ArrowLeft size={14} /> Back to Projects
      </Link>

      {/* Hero */}
      <div className="bg-white border border-gray-200 rounded-2xl p-6">
        <div className="flex flex-col sm:flex-row sm:items-start gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 flex-wrap">
              {item.chosen_logo_svg && (
                <div
                  className="h-10 w-auto"
                  dangerouslySetInnerHTML={{ __html: item.chosen_logo_svg }}
                  style={{ maxWidth: 160 }}
                />
              )}
              <h1 className="text-2xl font-bold text-gray-900">{appName}</h1>
              {scale && (
                <span className={`text-xs font-medium rounded-full px-2.5 py-0.5 border ${
                  scale === "small"
                    ? "bg-blue-50 text-blue-600 border-blue-200"
                    : "bg-purple-50 text-purple-600 border-purple-200"
                }`}>
                  {scale}
                </span>
              )}
            </div>
            {tagline && <p className="mt-1 text-sm text-gray-500">{tagline}</p>}

            {stack && (
              <div className="mt-3 flex flex-wrap gap-2">
                {Object.entries(stack).map(([k, v]) => (
                  <span key={k} className="text-xs bg-gray-100 text-gray-600 rounded-full px-2.5 py-0.5">
                    <span className="font-medium capitalize text-gray-500">{k}:</span> {v}
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="flex flex-col gap-2 shrink-0">
            {item.built_repo_url && (
              <a href={item.built_repo_url} target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-2 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg px-3 py-2 transition-colors">
                <GitBranch size={13} /> View on GitHub <ExternalLink size={10} />
              </a>
            )}
            <Link to={`/opportunity/${item.opportunity_id}`}
              className="flex items-center gap-2 text-xs font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 rounded-lg px-3 py-2 transition-colors">
              <TrendingUp size={13} /> Market Opportunity
            </Link>
          </div>
        </div>
      </div>

      {/* Tab navigation */}
      <div className="flex gap-1 bg-gray-100 rounded-xl p-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex-1 flex items-center justify-center gap-2 text-sm font-medium py-2 rounded-lg transition-all ${
              tab === t.id
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {t.icon}
            {t.label}
            {t.id === "tasks" && activeTaskCount > 0 && (
              <span className="text-xs bg-blue-100 text-blue-700 rounded-full px-1.5 py-0.5 font-semibold">
                {activeTaskCount}
              </span>
            )}
            {t.id === "build" && buildStatus === "building" && (
              <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="bg-white border border-gray-200 rounded-2xl p-6">
        {/* ── Branding tab ── */}
        {tab === "branding" && (
          <div className="space-y-8">
            <div>
              <h2 className="text-base font-semibold text-gray-900 mb-4">App Name</h2>
              <NamePanel itemId={item.id} />
            </div>
            <div className="border-t border-gray-100 pt-6">
              <h2 className="text-base font-semibold text-gray-900 mb-4">Logo</h2>
              <LogoPanel itemId={item.id} chosenName={item.chosen_name} />
            </div>
          </div>
        )}

        {/* ── Build tab ── */}
        {tab === "build" && (
          <div className="space-y-6">
            {buildStatus === "built" ? (
              <RunPanel
                itemId={item.id}
                runStatus={runStatus}
                runUrl={item.run_url ?? null}
                onStart={() => startMutation.mutate(item.id)}
                onStop={() => stopMutation.mutate(item.id)}
                onForceStop={() => forceStopMutation.mutate(item.id)}
                startPending={startMutation.isPending}
                stopPending={stopMutation.isPending}
                forceStopPending={forceStopMutation.isPending}
              />
            ) : (
              <div className="space-y-3">
                <h2 className="text-sm font-semibold text-gray-700">Build App</h2>
                {buildStatus === "building" ? (
                  <div className="flex items-center gap-2 text-blue-600 text-sm animate-pulse">
                    <Hammer size={15} /> Building…
                  </div>
                ) : buildStatus === "failed" ? (
                  <button
                    onClick={() => buildMutation.mutate(item.id)}
                    disabled={buildMutation.isPending}
                    className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-200 hover:bg-red-100 rounded-xl px-4 py-2.5 transition-colors disabled:opacity-50"
                  >
                    <AlertCircle size={15} /> Build Failed — Retry
                  </button>
                ) : (
                  <button
                    onClick={() => buildMutation.mutate(item.id)}
                    disabled={buildMutation.isPending}
                    className="flex items-center gap-2 text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-xl px-4 py-2.5 transition-colors disabled:opacity-50"
                  >
                    <Hammer size={15} /> Build This App
                  </button>
                )}
              </div>
            )}

            {/* Regenerate plan */}
            <div className="border-t border-gray-100 pt-4">
              <p className="text-xs text-gray-400 mb-2">Re-generate the app plan if you want a fresh take.</p>
              <Link
                to={`/opportunity/${item.opportunity_id}`}
                className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700"
              >
                <RefreshCw size={12} /> View opportunity & regenerate plan
              </Link>
            </div>
          </div>
        )}

        {/* ── Tasks tab ── */}
        {tab === "tasks" && (
          <div>
            <h2 className="text-base font-semibold text-gray-900 mb-4">Tasks</h2>
            <TasksPanel itemId={item.id} />
          </div>
        )}
      </div>

      {/* Danger zone — always visible */}
      <div className="flex items-center justify-between border border-red-100 rounded-2xl px-5 py-4">
        <div>
          <p className="text-sm font-medium text-gray-700">Remove from pipeline</p>
          <p className="text-xs text-gray-400 mt-0.5">Deletes this pipeline entry. The built repo is not affected.</p>
        </div>
        <button
          onClick={() => removeMutation.mutate(item.id)}
          disabled={removeMutation.isPending}
          className="flex items-center gap-1.5 text-xs font-medium text-red-500 hover:text-red-700 bg-red-50 hover:bg-red-100 border border-red-200 rounded-lg px-3 py-2 transition-colors disabled:opacity-50"
        >
          <Trash2 size={13} />
          {removeMutation.isPending ? "Removing…" : "Remove"}
        </button>
      </div>
    </div>
  );
}
