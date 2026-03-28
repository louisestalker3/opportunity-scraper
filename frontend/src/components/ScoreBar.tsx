interface ScoreBarProps {
  score: number;   // 0-100
  label?: string;
  showValue?: boolean;
  height?: "sm" | "md" | "lg";
}

function scoreColor(score: number): string {
  if (score >= 70) return "bg-green-500";
  if (score >= 40) return "bg-yellow-400";
  return "bg-red-400";
}

function scoreTextColor(score: number): string {
  if (score >= 70) return "text-green-700";
  if (score >= 40) return "text-yellow-700";
  return "text-red-600";
}

const heightClasses = {
  sm: "h-1.5",
  md: "h-2.5",
  lg: "h-4",
};

export default function ScoreBar({
  score,
  label,
  showValue = true,
  height = "md",
}: ScoreBarProps) {
  const clamped = Math.max(0, Math.min(100, score));

  return (
    <div className="w-full">
      {(label || showValue) && (
        <div className="flex justify-between items-center mb-1">
          {label && <span className="text-xs text-gray-500 font-medium">{label}</span>}
          {showValue && (
            <span className={`text-xs font-bold tabular-nums ${scoreTextColor(clamped)}`}>
              {clamped.toFixed(0)}
            </span>
          )}
        </div>
      )}
      <div className={`w-full bg-gray-200 rounded-full overflow-hidden ${heightClasses[height]}`}>
        <div
          className={`${heightClasses[height]} rounded-full transition-all duration-500 ${scoreColor(clamped)}`}
          style={{ width: `${clamped}%` }}
          role="progressbar"
          aria-valuenow={clamped}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>
    </div>
  );
}
