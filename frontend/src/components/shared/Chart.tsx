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
        <div style={{ width: "100%", height: 80 }} aria-hidden="true">
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
