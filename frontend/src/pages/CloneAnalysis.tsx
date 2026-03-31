import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Search, TrendingUp, TrendingDown, Minus, AlertTriangle, CheckCircle, Clock, Wrench, Target, ShieldAlert, Lightbulb } from "lucide-react";
import { analyzeClone, type CloneAnalysisResult } from "@/api/client";

function VerdictBadge({ verdict, score }: { verdict: string; score: number }) {
  if (verdict === "worth_building") {
    return (
      <div className="flex items-center gap-3 bg-green-50 border border-green-200 rounded-xl p-4">
        <CheckCircle size={28} className="text-green-600 shrink-0" />
        <div>
          <div className="font-bold text-green-800 text-lg">Worth Building</div>
          <div className="text-sm text-green-600">Viability score: {score}/100</div>
        </div>
        <div className="ml-auto text-4xl font-black text-green-600">{score}</div>
      </div>
    );
  }
  if (verdict === "risky") {
    return (
      <div className="flex items-center gap-3 bg-yellow-50 border border-yellow-200 rounded-xl p-4">
        <AlertTriangle size={28} className="text-yellow-600 shrink-0" />
        <div>
          <div className="font-bold text-yellow-800 text-lg">Proceed with Caution</div>
          <div className="text-sm text-yellow-600">Viability score: {score}/100</div>
        </div>
        <div className="ml-auto text-4xl font-black text-yellow-600">{score}</div>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-3 bg-red-50 border border-red-200 rounded-xl p-4">
      <AlertTriangle size={28} className="text-red-600 shrink-0" />
      <div>
        <div className="font-bold text-red-800 text-lg">Not Worth It</div>
        <div className="text-sm text-red-600">Viability score: {score}/100</div>
      </div>
      <div className="ml-auto text-4xl font-black text-red-600">{score}</div>
    </div>
  );
}

function TrendIcon({ trend }: { trend: string }) {
  if (trend === "growing") return <TrendingUp size={16} className="text-green-500" />;
  if (trend === "declining") return <TrendingDown size={16} className="text-red-500" />;
  return <Minus size={16} className="text-gray-400" />;
}

function ComplexityBadge({ level }: { level: string }) {
  const classes = {
    low: "bg-green-100 text-green-700",
    medium: "bg-yellow-100 text-yellow-700",
    high: "bg-red-100 text-red-700",
  }[level] ?? "bg-gray-100 text-gray-600";
  return <span className={`px-2 py-0.5 rounded text-xs font-medium capitalize ${classes}`}>{level}</span>;
}

function AnalysisResult({ result }: { result: CloneAnalysisResult }) {
  return (
    <div className="space-y-6">
      {/* Verdict */}
      <VerdictBadge verdict={result.verdict} score={result.verdict_score} />

      {/* Summary */}
      <p className="text-gray-700 text-base">{result.verdict_summary}</p>

      {/* Quick stats grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-white border border-gray-200 rounded-xl p-4 text-center">
          <div className="flex items-center justify-center gap-1 text-xs text-gray-500 mb-1">
            <TrendIcon trend={result.growth_trend} />
            Market Trend
          </div>
          <div className="font-semibold text-gray-800 capitalize">{result.growth_trend}</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4 text-center">
          <div className="text-xs text-gray-500 mb-1">Market Size</div>
          <div className="font-semibold text-gray-800 text-sm">{result.market_size}</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4 text-center">
          <div className="flex items-center justify-center gap-1 text-xs text-gray-500 mb-1">
            <Clock size={13} />
            Time to MVP
          </div>
          <div className="font-semibold text-gray-800 text-sm">{result.time_to_mvp}</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4 text-center">
          <div className="flex items-center justify-center gap-1 text-xs text-gray-500 mb-1">
            <Wrench size={13} />
            Build Complexity
          </div>
          <ComplexityBadge level={result.build_complexity} />
        </div>
      </div>

      {/* Three columns: complaints, competitors, differentiation */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {result.top_complaints.length > 0 && (
          <div className="bg-red-50 border border-red-100 rounded-xl p-4">
            <h3 className="text-sm font-semibold text-red-800 mb-3 flex items-center gap-2">
              <AlertTriangle size={14} /> Top User Complaints
            </h3>
            <ul className="space-y-2">
              {result.top_complaints.map((c, i) => (
                <li key={i} className="text-sm text-red-700 flex items-start gap-2">
                  <span className="text-red-400 mt-0.5">•</span> {c}
                </li>
              ))}
            </ul>
          </div>
        )}

        {result.competitors.length > 0 && (
          <div className="bg-blue-50 border border-blue-100 rounded-xl p-4">
            <h3 className="text-sm font-semibold text-blue-800 mb-3 flex items-center gap-2">
              <Target size={14} /> Competitors
            </h3>
            <ul className="space-y-2">
              {result.competitors.map((c, i) => (
                <li key={i} className="text-sm">
                  <span className="font-medium text-blue-800">{c.name}</span>
                  <span className="text-blue-600 block text-xs mt-0.5">{c.weakness}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {result.differentiation_angles.length > 0 && (
          <div className="bg-green-50 border border-green-100 rounded-xl p-4">
            <h3 className="text-sm font-semibold text-green-800 mb-3 flex items-center gap-2">
              <Lightbulb size={14} /> Differentiation Angles
            </h3>
            <ul className="space-y-2">
              {result.differentiation_angles.map((a, i) => (
                <li key={i} className="text-sm text-green-700 flex items-start gap-2">
                  <span className="text-green-400 mt-0.5">→</span> {a}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Pricing gap + biggest risk + ideal target */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {result.pricing_gap && (
          <div className="bg-white border border-gray-200 rounded-xl p-4">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Pricing Gap</h3>
            <p className="text-sm text-gray-700">{result.pricing_gap}</p>
          </div>
        )}
        {result.biggest_risk && (
          <div className="bg-white border border-orange-200 rounded-xl p-4">
            <h3 className="text-xs font-semibold text-orange-600 uppercase tracking-wide mb-2 flex items-center gap-1">
              <ShieldAlert size={12} /> Biggest Risk
            </h3>
            <p className="text-sm text-gray-700">{result.biggest_risk}</p>
          </div>
        )}
        {result.ideal_target && (
          <div className="bg-white border border-gray-200 rounded-xl p-4">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Ideal Builder</h3>
            <p className="text-sm text-gray-700">{result.ideal_target}</p>
          </div>
        )}
      </div>

      {/* Full report */}
      {result.report && (
        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h2 className="text-base font-semibold text-gray-900 mb-4">Full Analysis Report</h2>
          <div className="text-sm text-gray-700 space-y-2">
            {result.report.split("\n").map((line, i) => {
              if (line.startsWith("## ")) return <h3 key={i} className="font-bold text-gray-900 text-base mt-4 first:mt-0">{line.slice(3)}</h3>;
              if (line.startsWith("### ")) return <h4 key={i} className="font-semibold text-gray-800 mt-3">{line.slice(4)}</h4>;
              if (line.startsWith("- ")) return <p key={i} className="pl-3 before:content-['•'] before:mr-2 before:text-gray-400">{line.slice(2)}</p>;
              if (line.trim() === "") return null;
              return <p key={i} className="leading-relaxed">{line}</p>;
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default function CloneAnalysis() {
  const [appName, setAppName] = useState("");
  const [appUrl, setAppUrl] = useState("");
  const [context, setContext] = useState("");

  const mutation = useMutation({
    mutationFn: () => analyzeClone(appName.trim(), appUrl.trim() || undefined, context.trim() || undefined),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!appName.trim()) return;
    mutation.mutate();
  };

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Clone / Alternative Analysis</h1>
        <p className="text-sm text-gray-500 mt-1">
          Tell Claude an app you want to copy or build an alternative to — get an honest market analysis.
        </p>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="bg-white border border-gray-200 rounded-xl p-6 space-y-4">
        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium text-gray-700">App Name *</label>
          <input
            type="text"
            value={appName}
            onChange={(e) => setAppName(e.target.value)}
            placeholder="e.g. Notion, Linear, Zapier, Intercom…"
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
            required
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-gray-700">App URL <span className="text-gray-400 font-normal">(optional)</span></label>
            <input
              type="url"
              value={appUrl}
              onChange={(e) => setAppUrl(e.target.value)}
              placeholder="https://..."
              className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-gray-700">Extra context <span className="text-gray-400 font-normal">(optional)</span></label>
            <input
              type="text"
              value={context}
              onChange={(e) => setContext(e.target.value)}
              placeholder="e.g. targeting freelancers, UK market…"
              className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={mutation.isPending || !appName.trim()}
          className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-green-600 text-white text-sm font-medium hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <Search size={15} />
          {mutation.isPending ? "Analysing…" : "Analyse Market"}
        </button>
      </form>

      {/* Loading */}
      {mutation.isPending && (
        <div className="flex items-center justify-center py-16 text-gray-400 gap-3">
          <div className="animate-spin rounded-full h-6 w-6 border-2 border-gray-300 border-t-green-600" />
          <span className="text-sm">Claude is researching the market…</span>
        </div>
      )}

      {/* Error */}
      {mutation.isError && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
          Analysis failed. Make sure the API is running and ANTHROPIC_API_KEY is set.
        </div>
      )}

      {/* Results */}
      {mutation.isSuccess && mutation.data && (
        <AnalysisResult result={mutation.data} />
      )}
    </div>
  );
}
