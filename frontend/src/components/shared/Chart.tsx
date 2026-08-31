import { Line, LineChart, ResponsiveContainer, YAxis } from "recharts";
import { chart } from "../../theme/tokens";

export interface ChartProps {
  title: string;
  values: number[];
  /**
   * The text alternative for the chart, not decoration (plan §8: "every
   * chart is accompanied by a sentence describing the trend"). Required,
   * not optional — a chart with no sentence has no accessible content.
   */
  trendSentence: string;
}

/**
 * Readable at 375px: no gridlines, no legend, a single line, larger type.
 * Renders nothing if there isn't enough data for a trend — see EmptyState
 * usage at the call site for the "not enough data" case instead.
 */
export function Chart({ title, values, trendSentence }: ChartProps) {
  const data = values.map((v, i) => ({ index: i, value: v }));
  return (
    <div>
      <h3 className="text-sm font-medium text-ink-primary">{title}</h3>
      {data.length >= 2 ? (
        // Hardening-pass fix: was a fixed 80px height at every width. Plan
        // §8 requires charts to "gain height" from 640px up — h-20/28/32
        // (80/112/128px) via Tailwind's responsive classes instead of an
        // inline style, since ResponsiveContainer needs a real class to
        // pick up the breakpoint change.
        <div className="h-20 w-full sm:h-28 lg:h-32" aria-hidden="true">
          <ResponsiveContainer>
            <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
              <YAxis hide domain={["dataMin", "dataMax"]} />
              <Line
                type="monotone"
                dataKey="value"
                stroke={chart.line}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : null}
      <p className="text-sm text-ink-secondary">{trendSentence}</p>
    </div>
  );
}
