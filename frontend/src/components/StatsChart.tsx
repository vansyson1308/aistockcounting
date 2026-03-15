'use client';

interface BarData {
  label: string;
  value: number;
}

interface StatsChartProps {
  data: BarData[];
  title: string;
  color?: string;
  height?: number;
}

export default function StatsChart({
  data,
  title,
  color = '#6366f1',
  height = 200,
}: StatsChartProps) {
  if (data.length === 0) return null;

  const maxVal = Math.max(...data.map((d) => d.value), 1);
  const barWidth = Math.max(20, Math.min(60, 600 / data.length));
  const chartWidth = data.length * (barWidth + 8) + 40;
  const chartHeight = height;
  const barArea = chartHeight - 40;

  return (
    <div className="rounded-xl bg-white p-4 shadow dark:bg-slate-800">
      <h3 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-300">{title}</h3>
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${chartWidth} ${chartHeight}`}
          width={chartWidth}
          height={chartHeight}
          className="mx-auto"
        >
          {/* Grid lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((pct) => {
            const y = 10 + barArea * (1 - pct);
            return (
              <g key={pct}>
                <line
                  x1={30}
                  y1={y}
                  x2={chartWidth}
                  y2={y}
                  stroke="#e2e8f0"
                  strokeWidth={0.5}
                />
                <text x={0} y={y + 4} fontSize={9} fill="#94a3b8">
                  {Math.round(maxVal * pct)}
                </text>
              </g>
            );
          })}

          {/* Bars */}
          {data.map((d, i) => {
            const barH = (d.value / maxVal) * barArea;
            const x = 40 + i * (barWidth + 8);
            const y = 10 + barArea - barH;
            return (
              <g key={i}>
                <rect
                  x={x}
                  y={y}
                  width={barWidth}
                  height={barH}
                  rx={4}
                  fill={color}
                  opacity={0.85}
                />
                <text
                  x={x + barWidth / 2}
                  y={y - 4}
                  textAnchor="middle"
                  fontSize={9}
                  fill="#475569"
                >
                  {d.value}
                </text>
                <text
                  x={x + barWidth / 2}
                  y={chartHeight - 2}
                  textAnchor="middle"
                  fontSize={8}
                  fill="#64748b"
                >
                  {d.label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
