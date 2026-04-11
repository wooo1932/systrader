import { useEffect, useState } from "react";
import { fetchJson } from "../api/client";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import DatePicker from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";

function fmt(d: Date | null): string {
  if (!d) return "";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function Statistics() {
  const [daily, setDaily] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [dateFrom, setDateFrom] = useState<Date | null>(null);
  const [dateTo, setDateTo] = useState<Date | null>(null);
  const [source, setSource] = useState("");

  useEffect(() => {
    const qFrom = fmt(dateFrom);
    const qTo = fmt(dateTo);
    const params: string[] = [];
    if (qFrom) params.push(`date_from=${qFrom}`);
    if (qTo) params.push(`date_to=${qTo}`);
    if (source) params.push(`source=${source}`);
    const qs = params.length > 0 ? `?${params.join("&")}` : "";
    fetchJson<any>(`/stats/summary${qs}`).then(setSummary).catch(() => {});
    fetchJson<any[]>(`/stats/daily?days=365${params.length > 0 ? "&" + params.join("&") : ""}`).then(setDaily).catch(() => {});
  }, [dateFrom, dateTo, source]);

  const chartData = [...daily].reverse();

  return (
    <div className="page">
      <h1 className="page-title">Statistics</h1>

      {/* Filters */}
      <div style={{ display: "flex", gap: 10, marginBottom: 24, alignItems: "center", flexWrap: "wrap" }}>
        <DatePicker
          selected={dateFrom}
          onChange={(date: Date | null) => setDateFrom(date)}
          dateFormat="yyyy-MM-dd"
          placeholderText="시작일"
          isClearable
          className="datepicker-input"
          showPopperArrow={false}
          selectsStart
          startDate={dateFrom}
          endDate={dateTo}
        />
        <span style={{ color: "var(--text-muted)" }}>~</span>
        <DatePicker
          selected={dateTo}
          onChange={(date: Date | null) => setDateTo(date)}
          dateFormat="yyyy-MM-dd"
          placeholderText="종료일"
          isClearable
          className="datepicker-input"
          showPopperArrow={false}
          selectsEnd
          startDate={dateFrom}
          endDate={dateTo}
          minDate={dateFrom ?? undefined}
        />
        <select value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="">전체 소스</option>
          <option value="cybos">Cybos</option>
          <option value="telegram">Telegram</option>
        </select>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => { setDateFrom(null); setDateTo(null); setSource(""); }}
        >
          초기화
        </button>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid-4" style={{ marginBottom: 24 }}>
          <div className="stat-card">
            <div className="label">총 매매</div>
            <div className="value">{summary.total_trades}</div>
          </div>
          <div className="stat-card">
            <div className="label">승률</div>
            <div className="value">
              {summary.wins && summary.total_trades
                ? ((summary.wins / summary.total_trades) * 100).toFixed(1)
                : 0}%
            </div>
          </div>
          <div className="stat-card">
            <div className="label">승 / 패</div>
            <div className="value">
              <span style={{ color: "var(--red)" }}>{summary.wins ?? 0}</span>
              <span style={{ color: "var(--text-muted)", margin: "0 4px" }}>/</span>
              <span style={{ color: "var(--accent)" }}>{(summary.total_trades ?? 0) - (summary.wins ?? 0)}</span>
            </div>
          </div>
          <div className="stat-card">
            <div className="label">총 손익</div>
            <div className="value" style={{ color: (summary.total_pnl ?? 0) >= 0 ? "var(--red)" : "var(--accent)" }}>
              {(summary.total_pnl ?? 0) >= 0 ? "+" : ""}{(summary.total_pnl ?? 0).toLocaleString()}
            </div>
          </div>
        </div>
      )}

      {/* Daily PnL Chart */}
      <div className="card">
        <div className="section-header">
          <span className="section-title">일별 손익</span>
          <span style={{ color: "var(--text-muted)", fontSize: 12 }}>{chartData.length}일</span>
        </div>
        <div style={{ marginTop: 12 }}>
          <ResponsiveContainer width="100%" height={350}>
            <BarChart data={chartData}>
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#8892a8" }} tickLine={false} axisLine={{ stroke: "#1e2940" }} />
              <YAxis tick={{ fontSize: 11, fill: "#8892a8" }} tickLine={false} axisLine={false} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
              <Tooltip
                contentStyle={{
                  background: "#1a1f35",
                  border: "1px solid #2a3555",
                  borderRadius: 8,
                  fontSize: 13,
                }}
                labelStyle={{ color: "#8892a8" }}
                formatter={(value) => [`${Number(value).toLocaleString()} KRW`, "PnL"]}
              />
              <Bar dataKey="total_pnl" radius={[4, 4, 0, 0]}>
                {chartData.map((entry, i) => (
                  <Cell key={i} fill={entry.total_pnl >= 0 ? "#ef4444" : "#3b82f6"} opacity={0.85} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
