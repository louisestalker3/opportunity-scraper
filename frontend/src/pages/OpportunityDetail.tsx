import { useParams, Link, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  ExternalLink,
  CheckCircle,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Clock,
  PlusCircle,
  FileText,
  Hammer,
  BookOpen,
  Boxes,
} from "lucide-react";
import ScoreBar from "@/components/ScoreBar";
import {
  useOpportunity,
  useRescore,
  useAddToPipeline,
  usePipeline,
  useBuildApp,
} from "@/hooks/useOpportunities";

const SOURCE_LABELS: Record<string, string> = {
  reddit: "Reddit",
  hackernews: "Hacker News",
  g2: "G2",
  capterra: "Capterra",
  trustpilot: "Trustpilot",
  twitter: "Twitter/X",
};

const SIGNAL_COLORS: Record<string, string> = {
  complaint: "bg-red-100 text-red-700",
  alternative_seeking: "bg-orange-100 text-orange-700",
  pricing_objection: "bg-yellow-100 text-yellow-700",
  praise: "bg-green-100 text-green-700",
  general: "bg-gray-100 text-gray-600",
};

function SkeletonDetail() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="skeleton h-6 w-48 rounded" />
      <div className="skeleton h-10 w-72 rounded" />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="skeleton h-8 w-full rounded" />
          ))}
        </div>
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="skeleton h-5 w-full rounded" />
          ))}
        </div>
      </div>
    </div>
  );
}

export default function OpportunityDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: opp, isLoading, isError } = useOpportunity(id!);
  const rescore = useRescore();
  const addMutation = useAddToPipeline();
  const buildMutation = useBuildApp();
  const { data: pipelineItems } = usePipeline();
  const pipelineItem = pipelineItems?.find((i) => i.opportunity_id === id);
  const isSaved = Boolean(pipelineItem);
  const proposal = pipelineItem?.proposal ?? null;
  const appPlan = pipelineItem?.app_plan ?? null;
  const buildStatus = pipelineItem?.build_status ?? null;

  const handleBuild = () => {
    if (!pipelineItem) return;
    buildMutation.mutate(pipelineItem.id);
    navigate(`/project/${pipelineItem.id}`);
  };

  if (isLoading) return <SkeletonDetail />;

  if (isError || !opp) {
    return (
      <div className="text-center py-24">
        <p className="text-gray-500">Opportunity not found.</p>
        <Link to="/" className="mt-4 inline-block text-green-600 underline text-sm">
          Back to Dashboard
        </Link>
      </div>
    );
  }

  const app = opp.app_profile;
  const score = opp.viability_score;

  const scoreColor =
    score === null ? "text-gray-400" : score >= 70 ? "text-green-600" : score >= 40 ? "text-yellow-600" : "text-red-500";

  const subScores = [
    { label: "Market Demand", value: opp.market_demand_score },
    { label: "Complaint Severity", value: opp.complaint_severity_score },
    { label: "Competition Density", value: opp.competition_density_score },
    { label: "Pricing Gap", value: opp.pricing_gap_score },
    { label: "Build Simplicity", value: opp.build_complexity_score },
    { label: "Differentiation", value: opp.differentiation_score },
  ];

  return (
    <div className="space-y-8">
      {/* Breadcrumb */}
      <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-700 transition-colors">
        <ArrowLeft size={14} />
        Back to Dashboard
      </Link>

      {/* Hero */}
      <div className="bg-white border border-gray-200 rounded-2xl p-6 flex flex-col sm:flex-row sm:items-center gap-6">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl font-bold text-gray-900">{app?.name ?? "Unknown App"}</h1>
            {app?.url && (
              <a href={app.url} target="_blank" rel="noopener noreferrer" className="text-gray-400 hover:text-gray-700">
                <ExternalLink size={16} />
              </a>
            )}
          </div>
          {app?.category && (
            <span className="mt-1 inline-block text-xs bg-gray-100 text-gray-500 rounded-full px-2.5 py-0.5">
              {app.category}
            </span>
          )}
          {app?.description && (
            <p className="mt-2 text-sm text-gray-500 max-w-prose">{app.description}</p>
          )}
        </div>
        <div className="flex flex-col items-center shrink-0">
          <div className={`text-5xl font-extrabold tabular-nums ${scoreColor}`}>
            {score !== null ? score.toFixed(0) : "—"}
          </div>
          <div className="text-xs text-gray-400 mt-1">Viability Index</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: scores + mentions */}
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-white border border-gray-200 rounded-2xl p-6">
            <h2 className="text-base font-semibold text-gray-800 mb-4">Score Breakdown</h2>
            <div className="space-y-4">
              {subScores.map(({ label, value }) => (
                <ScoreBar key={label} score={value} label={label} height="md" />
              ))}
            </div>
            <div className="mt-5 pt-4 border-t border-gray-100 grid grid-cols-3 gap-4 text-center text-sm">
              <div>
                <div className="font-bold text-gray-800">{opp.mention_count.toLocaleString()}</div>
                <div className="text-xs text-gray-400">Mentions</div>
              </div>
              <div>
                <div className="font-bold text-red-600">{opp.complaint_count.toLocaleString()}</div>
                <div className="text-xs text-gray-400">Complaints</div>
              </div>
              <div>
                <div className="font-bold text-orange-500">{opp.alternative_seeking_count.toLocaleString()}</div>
                <div className="text-xs text-gray-400">Alt. Seeking</div>
              </div>
            </div>
          </div>

          {/* Recent mentions */}
          <div className="bg-white border border-gray-200 rounded-2xl p-6">
            <h2 className="text-base font-semibold text-gray-800 mb-4">Recent Mentions</h2>
            {opp.recent_mentions.length === 0 ? (
              <p className="text-sm text-gray-400">No mentions scraped yet.</p>
            ) : (
              <div className="space-y-3">
                {opp.recent_mentions.map((m) => (
                  <div key={m.id} className="rounded-xl border border-gray-100 bg-gray-50 p-4 space-y-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-medium text-gray-500 bg-gray-200 rounded px-2 py-0.5">
                        {SOURCE_LABELS[m.source] ?? m.source}
                      </span>
                      <span className={`text-xs rounded px-2 py-0.5 font-medium ${SIGNAL_COLORS[m.signal_type] ?? "bg-gray-100 text-gray-500"}`}>
                        {m.signal_type.replace("_", " ")}
                      </span>
                      <span className="ml-auto flex items-center gap-1 text-xs text-gray-400">
                        <Clock size={11} />
                        {new Date(m.scraped_at).toLocaleDateString()}
                      </span>
                    </div>
                    <p className="text-sm text-gray-700 line-clamp-4">{m.content}</p>
                    {m.url && (
                      <a href={m.url} target="_blank" rel="noopener noreferrer"
                        className="text-xs text-green-600 hover:underline inline-flex items-center gap-1">
                        View source <ExternalLink size={10} />
                      </a>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right: pros/cons + actions */}
        <div className="space-y-6">
          {/* Pros */}
          <div className="bg-white border border-gray-200 rounded-2xl p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
              <CheckCircle size={15} className="text-green-500" /> What users love
            </h2>
            {app?.pros?.length ? (
              <ul className="space-y-2">
                {app.pros.filter(Boolean).map((pro, i) => (
                  <li key={i} className="text-sm text-gray-600 flex items-start gap-2">
                    <CheckCircle size={13} className="text-green-400 shrink-0 mt-0.5" />
                    {pro}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-gray-400">Not yet analysed.</p>
            )}
          </div>

          {/* Cons */}
          <div className="bg-white border border-gray-200 rounded-2xl p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
              <XCircle size={15} className="text-red-400" /> Pain points (your opportunity)
            </h2>
            {app?.cons?.length ? (
              <ul className="space-y-2">
                {app.cons.filter(Boolean).map((con, i) => (
                  <li key={i} className="text-sm text-gray-600 flex items-start gap-2">
                    <XCircle size={13} className="text-red-300 shrink-0 mt-0.5" />
                    {con}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-gray-400">Not yet analysed.</p>
            )}
          </div>

          {/* Actions */}
          <div className="space-y-2">
            {/* Not saved yet */}
            {!isSaved && (
              <button
                onClick={() => addMutation.mutate({ opportunityId: opp.id })}
                disabled={addMutation.isPending}
                className="w-full flex items-center justify-center gap-2 bg-green-600 hover:bg-green-700 text-white font-medium text-sm rounded-xl px-4 py-3 transition-colors disabled:opacity-50"
              >
                <PlusCircle size={16} />
                {addMutation.isPending ? "Generating plan & proposal..." : "Save & Generate Plan"}
              </button>
            )}

            {/* Saved, not yet built */}
            {isSaved && buildStatus !== "built" && buildStatus !== "building" && appPlan && (
              <button
                onClick={handleBuild}
                disabled={buildMutation.isPending}
                className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-medium text-sm rounded-xl px-4 py-3 transition-colors disabled:opacity-50"
              >
                <Hammer size={16} />
                Build This App
              </button>
            )}

            {/* Building — link to project page */}
            {buildStatus === "building" && pipelineItem && (
              <Link
                to={`/project/${pipelineItem.id}`}
                className="w-full flex items-center justify-center gap-2 bg-blue-50 border border-blue-200 text-blue-700 font-medium text-sm rounded-xl px-4 py-3 transition-colors animate-pulse"
              >
                <Hammer size={16} />
                Building… View Progress
              </Link>
            )}

            {/* Built — go to project */}
            {buildStatus === "built" && pipelineItem && (
              <Link
                to={`/project/${pipelineItem.id}`}
                className="w-full flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white font-medium text-sm rounded-xl px-4 py-3 transition-colors"
              >
                <Boxes size={16} />
                View Project
              </Link>
            )}

            {/* Saved — indicate it's tracked */}
            {isSaved && !appPlan && (
              <div className="w-full flex items-center justify-center gap-2 bg-green-50 border border-green-200 text-green-700 font-medium text-sm rounded-xl px-4 py-3">
                <CheckCircle2 size={16} />
                Saved to Pipeline
              </div>
            )}

            {/* Re-score */}
            <button
              onClick={() => rescore.mutate(opp.id)}
              disabled={rescore.isPending}
              className="w-full flex items-center justify-center gap-2 bg-white border border-gray-200 text-gray-600 hover:bg-gray-50 font-medium text-sm rounded-xl px-4 py-3 transition-colors disabled:opacity-50"
            >
              <RefreshCw size={14} className={rescore.isPending ? "animate-spin" : ""} />
              {rescore.isPending ? "Queued..." : "Re-score Now"}
            </button>

            {addMutation.isError && (
              <p className="text-xs text-red-500 text-center">
                Could not save — may already be in pipeline.
              </p>
            )}
          </div>
        </div>
      </div>

      {/* App Plan — shown when saved */}
      {appPlan ? (
        <AppPlanSection planJson={appPlan} />
      ) : isSaved ? (
        <div className="bg-gray-50 border border-gray-200 rounded-2xl p-6 text-center text-sm text-gray-400">
          No app plan generated yet.
        </div>
      ) : null}

      {/* Proposal — shown when saved */}
      {proposal ? (
        <div className="bg-white border border-indigo-200 rounded-2xl p-6">
          <div className="flex items-center gap-2 mb-5">
            <FileText size={18} className="text-indigo-500" />
            <h2 className="text-base font-semibold text-gray-800">Competitive Product Proposal</h2>
            <span className="ml-auto text-xs text-indigo-400 bg-indigo-50 rounded-full px-2.5 py-0.5 border border-indigo-100">
              AI-generated
            </span>
          </div>
          <ProposalContent markdown={proposal} />
        </div>
      ) : isSaved ? (
        <div className="bg-gray-50 border border-gray-200 rounded-2xl p-6 text-center text-sm text-gray-400">
          No proposal generated yet.
        </div>
      ) : null}
    </div>
  );
}

function AppPlanSection({ planJson }: { planJson: string }) {
  try {
    const plan = JSON.parse(planJson);
    const mvp = (plan.features ?? []).filter((f: { priority: string }) => f.priority === "mvp");
    const v2 = (plan.features ?? []).filter((f: { priority: string }) => f.priority === "v2");
    return (
      <div className="bg-white border border-emerald-200 rounded-2xl p-6">
        <div className="flex items-center gap-2 mb-5">
          <BookOpen size={18} className="text-emerald-500" />
          <h2 className="text-base font-semibold text-gray-800">App Plan</h2>
          {plan.app_name && (
            <span className="text-sm font-bold text-emerald-700 ml-1">— {plan.app_name}</span>
          )}
          <span className="ml-auto text-xs text-emerald-500 bg-emerald-50 rounded-full px-2.5 py-0.5 border border-emerald-100">
            AI-generated
          </span>
        </div>

        {plan.tagline && <p className="text-base italic text-gray-600 mb-4">{plan.tagline}</p>}
        {plan.description && <p className="text-sm text-gray-600 mb-5">{plan.description}</p>}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          {plan.tech_stack && (
            <div>
              <h3 className="text-sm font-semibold text-gray-700 mb-2">Tech Stack</h3>
              <ul className="space-y-1">
                {Object.entries(plan.tech_stack).map(([k, v]) => (
                  <li key={k} className="text-sm text-gray-600">
                    <span className="font-medium capitalize text-gray-700">{k}:</span> {String(v)}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="space-y-4">
            {plan.target_audience && (
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-1">Target Audience</h3>
                <p className="text-sm text-gray-600">{plan.target_audience}</p>
              </div>
            )}
            {plan.pricing_model && (
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-1">Pricing</h3>
                <p className="text-sm text-gray-600">{plan.pricing_model}</p>
              </div>
            )}
          </div>
        </div>

        {mvp.length > 0 && (
          <div className="mt-5">
            <h3 className="text-sm font-semibold text-gray-700 mb-2">MVP Features</h3>
            <ul className="space-y-2">
              {mvp.map((f: { name: string; description: string }) => (
                <li key={f.name} className="text-sm text-gray-600 flex items-start gap-2">
                  <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />
                  <span><strong className="text-gray-800">{f.name}</strong> — {f.description}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {v2.length > 0 && (
          <div className="mt-4">
            <h3 className="text-sm font-semibold text-gray-500 mb-2">v2 Features</h3>
            <ul className="space-y-2">
              {v2.map((f: { name: string; description: string }) => (
                <li key={f.name} className="text-sm text-gray-500 flex items-start gap-2">
                  <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-gray-300 shrink-0" />
                  <span><strong className="text-gray-600">{f.name}</strong> — {f.description}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {plan.mvp_summary && (
          <p className="mt-4 text-sm text-gray-500 italic border-t border-gray-100 pt-4">{plan.mvp_summary}</p>
        )}
      </div>
    );
  } catch {
    return null;
  }
}

function ProposalContent({ markdown }: { markdown: string }) {
  const lines = markdown.split("\n");
  return (
    <div className="space-y-1 text-gray-700">
      {lines.map((line, i) => {
        if (line.startsWith("## "))
          return <h2 key={i} className="text-base font-bold text-gray-900 mt-6 first:mt-0 mb-2">{line.slice(3)}</h2>;
        if (line.startsWith("### "))
          return <h3 key={i} className="text-sm font-semibold text-gray-800 mt-4 mb-1">{line.slice(4)}</h3>;
        if (line.startsWith("- ") || line.startsWith("* "))
          return (
            <div key={i} className="flex items-start gap-2 text-sm leading-relaxed">
              <span className="mt-1.5 w-1 h-1 rounded-full bg-gray-400 shrink-0" />
              <span>{line.slice(2)}</span>
            </div>
          );
        if (line.trim() === "") return <div key={i} className="h-1" />;
        const parts = line.split(/(\*\*[^*]+\*\*)/g);
        return (
          <p key={i} className="text-sm leading-relaxed">
            {parts.map((part, j) =>
              part.startsWith("**") && part.endsWith("**")
                ? <strong key={j}>{part.slice(2, -2)}</strong>
                : part
            )}
          </p>
        );
      })}
    </div>
  );
}
