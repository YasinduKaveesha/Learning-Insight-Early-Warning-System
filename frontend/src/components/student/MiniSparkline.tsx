import { Line, LineChart, ResponsiveContainer } from "recharts";

export interface MiniSparklineProps {
  values: number[];
  width?: number;
  height?: number;
}

/**
 * Compact accuracy/engagement trend for a card. Decorative alongside a
 * TrajectoryChip that already states the direction in text — marked
 * aria-hidden so it never becomes the only source of the trend.
 */
export function MiniSparkline({ values, width = 64, height = 24 }: MiniSparklineProps) {
  if (values.length < 2) return null;
  const data = values.map((v, i) => ({ index: i, value: v }));
  return (
    <div style={{ width, height }} aria-hidden="true">
      <ResponsiveContainer>
        <LineChart data={data}>
          <Line
            type="monotone"
            dataKey="value"
            stroke="#64748b"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
