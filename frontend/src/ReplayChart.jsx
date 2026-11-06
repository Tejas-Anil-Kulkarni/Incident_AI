import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

export default function ReplayChart({ chartData }) {
  return <div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><LineChart data={chartData} margin={{ top: 12, right: 18, left: 0, bottom: 0 }}>
    <CartesianGrid stroke="var(--line)" vertical={false} strokeDasharray="3 5"/>
    <XAxis dataKey="sequence" tickLine={false} axisLine={false} tick={{ fill: "var(--muted)", fontSize: 11 }} label={{ value: "Incident sequence", position: "insideBottom", offset: -2, fill: "var(--muted)", fontSize: 11 }}/>
    <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fill: "var(--muted)", fontSize: 11 }} width={30}/>
    <Tooltip contentStyle={{ borderRadius: 0, borderColor: "var(--line)", background: "var(--paper)", color: "var(--ink)" }} formatter={(value, name) => [value == null ? "Not measured" : value, name]}/>
    <Line type="linear" dataKey="Memory disabled" stroke="#89877f" strokeWidth={2} dot={{ r: 3, fill: "#89877f" }} connectNulls={false} isAnimationActive={false}/>
    <Line type="linear" dataKey="Memory enabled" stroke="#185b3b" strokeWidth={2} dot={{ r: 3, fill: "#185b3b" }} connectNulls={false} isAnimationActive={false}/>
  </LineChart></ResponsiveContainer></div>;
}
