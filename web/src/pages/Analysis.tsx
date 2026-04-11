import { useEffect, useState } from "react";
import { fetchJson } from "../api/client";
import DatePicker from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";
import { LineChart, Line, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer } from "recharts";

function fmt(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const LEVEL_COLORS: Record<string, string> = {
  INFO: "var(--text-secondary)",
  WARNING: "var(--yellow)",
  ERROR: "var(--red)",
};

export default function Analysis() {
  const [selectedDate, setSelectedDate] = useState<Date>(new Date());
  const [level, setLevel] = useState("");
  const [search, setSearch] = useState("");
  const [lines, setLines] = useState<string[]>([]);
  const [trades, setTrades] = useState<any[]>([]);
  const [selectedTrade, setSelectedTrade] = useState<any>(null);
  const [ticks, setTicks] = useState<any[]>([]);
  const [tab, setTab] = useState<"trades" | "logs">("trades");

  // Load trades for selected date
  useEffect(() => {
    const date = fmt(selectedDate);
    fetchJson<any[]>(`/trades?date=${date}&limit=200`).then(setTrades);
  }, [selectedDate]);

  // Load logs
  useEffect(() => {
    if (tab !== "logs") return;
    const date = fmt(selectedDate);
    let path = `/logs/${date}`;
    const params: string[] = [];
    if (level) params.push(`level=${level}`);
    if (search) params.push(`search=${encodeURIComponent(search)}`);
    if (params.length > 0) path += `?${params.join("&")}`;
    fetchJson<string[]>(path).then(setLines);
  }, [selectedDate, level, search, tab]);

  // Load trade detail + ticks
  const selectTrade = (t: any) => {
    setSelectedTrade(t);
    fetchJson<any>(`/trades/${t.id}`).then((detail) => {
      setSelectedTrade(detail);
    });
    fetchJson<any[]>(`/trades/${t.id}/ticks`).then(setTicks);
  };

  const chartData = ticks.map((t: any, i: number) => ({
    idx: i,
    price: t.price,
    time: t.timestamp?.slice(11, 19),
    volume: t.volume,
  }));

  const getLineLevel = (line: string): string => {
    if (line.includes("[ERROR]") || line.includes("[CRITICAL]")) return "ERROR";
    if (line.includes("[WARNING]")) return "WARNING";
    return "INFO";
  };

  const daySummary = trades.filter((t) => t.status === "done");
  const dayWins = daySummary.filter((t) => (t.pnl_amount ?? 0) > 0).length;
  const dayPnl = daySummary.reduce((s, t) => s + (t.pnl_amount ?? 0), 0);

  return (
    <div className="page">
      <h1 className="page-title">Analysis</h1>

      {/* Date + Tab */}
      <div style={{ display: "flex", gap: 10, marginBottom: 20, alignItems: "center", flexWrap: "wrap" }}>
        <DatePicker
          selected={selectedDate}
          onChange={(date: Date | null) => date && setSelectedDate(date)}
          dateFormat="yyyy-MM-dd"
          className="datepicker-input"
          showPopperArrow={false}
        />
        <div style={{ display: "flex", gap: 0, border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
          <button
            className={`btn btn-sm ${tab === "trades" ? "btn-primary" : "btn-ghost"}`}
            onClick={() => setTab("trades")}
            style={{ borderRadius: 0 }}
          >
            거래 분석
          </button>
          <button
            className={`btn btn-sm ${tab === "logs" ? "btn-primary" : "btn-ghost"}`}
            onClick={() => setTab("logs")}
            style={{ borderRadius: 0 }}
          >
            로그
          </button>
        </div>
        {tab === "logs" && (
          <>
            <select value={level} onChange={(e) => setLevel(e.target.value)}>
              <option value="">All Levels</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="ERROR">ERROR</option>
            </select>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="검색어..."
              style={{ width: 200 }}
            />
            <span style={{ color: "var(--text-muted)", fontSize: 13 }}>{lines.length}줄</span>
          </>
        )}
        {tab === "trades" && daySummary.length > 0 && (
          <span style={{ color: "var(--text-muted)", fontSize: 13 }}>
            {daySummary.length}건 | 승 {dayWins} | 패 {daySummary.length - dayWins} |{" "}
            <span style={{ color: dayPnl >= 0 ? "var(--red)" : "var(--accent)", fontWeight: 600 }}>
              {dayPnl >= 0 ? "+" : ""}{dayPnl.toLocaleString()} KRW
            </span>
          </span>
        )}
      </div>

      {tab === "trades" ? (
        <div style={{ display: "flex", gap: 20 }}>
          {/* Trade List */}
          <div style={{ width: 360, flexShrink: 0 }}>
            <div className="card" style={{ height: "calc(100vh - 220px)", overflow: "auto" }}>
              <div className="section-header" style={{ marginBottom: 8 }}>
                <span className="section-title">거래 목록</span>
                <span className="badge badge-green">{trades.length}</span>
              </div>
              {trades.length === 0 ? (
                <p style={{ color: "var(--text-muted)", fontSize: 13, padding: 12 }}>거래 없음</p>
              ) : (
                trades.map((t) => {
                  const pnl = t.pnl_amount ?? 0;
                  const isSelected = selectedTrade?.id === t.id;
                  return (
                    <div
                      key={t.id}
                      onClick={() => selectTrade(t)}
                      style={{
                        padding: "10px 12px",
                        borderBottom: "1px solid var(--border)",
                        cursor: "pointer",
                        background: isSelected ? "rgba(59,130,246,0.1)" : "transparent",
                        borderLeft: isSelected ? "3px solid var(--accent)" : "3px solid transparent",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div>
                          <span style={{ fontWeight: 600, fontSize: 13 }}>{t.stock_name}</span>
                          <span style={{ color: "var(--text-muted)", fontSize: 11, marginLeft: 4 }}>{t.stock_code}</span>
                        </div>
                        <span className={`badge ${t.status === "done" ? (pnl >= 0 ? "badge-red" : "badge-green") : "badge-yellow"}`} style={{ fontSize: 10 }}>
                          {t.status}
                        </span>
                      </div>
                      {t.status === "done" && (
                        <div style={{ display: "flex", gap: 12, marginTop: 4, fontSize: 12 }}>
                          <span style={{ color: pnl >= 0 ? "var(--red)" : "var(--accent)", fontWeight: 600 }}>
                            {pnl >= 0 ? "+" : ""}{pnl.toLocaleString()}
                          </span>
                          <span style={{ color: "var(--text-muted)" }}>{t.pnl_pct?.toFixed(2)}%</span>
                          <span style={{ color: "var(--text-muted)" }}>{t.sell_reason}</span>
                          <span style={{ color: "var(--text-muted)" }}>{t.created_at?.slice(11, 19)}</span>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Trade Detail + Chart */}
          <div style={{ flex: 1 }}>
            {selectedTrade ? (
              <>
                {/* Trade Info */}
                <div className="card" style={{ marginBottom: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                    <div>
                      <span style={{ fontSize: 18, fontWeight: 700 }}>{selectedTrade.stock_name}</span>
                      <span style={{ color: "var(--text-muted)", marginLeft: 8 }}>{selectedTrade.stock_code}</span>
                    </div>
                    <span className={`badge ${selectedTrade.news_source === "telegram" ? "badge-green" : "badge-yellow"}`}>
                      {selectedTrade.news_source}
                    </span>
                  </div>
                  <div className="grid-4" style={{ gap: 12 }}>
                    <div>
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>매수가</div>
                      <div style={{ fontSize: 16, fontWeight: 600 }}>{selectedTrade.buy_price?.toLocaleString() ?? "-"}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>매도가</div>
                      <div style={{ fontSize: 16, fontWeight: 600 }}>{selectedTrade.sell_price?.toLocaleString() ?? "-"}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>손익</div>
                      <div style={{ fontSize: 16, fontWeight: 600, color: (selectedTrade.pnl_amount ?? 0) >= 0 ? "var(--red)" : "var(--accent)" }}>
                        {selectedTrade.pnl_amount != null ? `${selectedTrade.pnl_amount >= 0 ? "+" : ""}${selectedTrade.pnl_amount.toLocaleString()}` : "-"}
                        <span style={{ fontSize: 12, marginLeft: 4 }}>({selectedTrade.pnl_pct?.toFixed(2) ?? "-"}%)</span>
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>매도사유 / 보유</div>
                      <div style={{ fontSize: 14, fontWeight: 600 }}>
                        {selectedTrade.sell_reason ?? "-"}
                        <span style={{ color: "var(--text-muted)", fontSize: 12, marginLeft: 8 }}>
                          {selectedTrade.hold_seconds?.toFixed(0) ?? "-"}s
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Tick Chart */}
                <div className="card" style={{ marginBottom: 16 }}>
                  <div className="section-header">
                    <span className="section-title">틱 차트</span>
                    <span style={{ color: "var(--text-muted)", fontSize: 12 }}>{ticks.length} ticks</span>
                  </div>
                  {ticks.length > 0 ? (
                    <div style={{ marginTop: 12 }}>
                      <ResponsiveContainer width="100%" height={300}>
                        <LineChart data={chartData}>
                          <XAxis dataKey="time" tick={{ fontSize: 10, fill: "#8892a8" }} tickLine={false} axisLine={{ stroke: "#1e2940" }} />
                          <YAxis domain={["auto", "auto"]} tick={{ fontSize: 10, fill: "#8892a8" }} tickLine={false} axisLine={false}
                            tickFormatter={(v) => v.toLocaleString()} />
                          <Tooltip
                            contentStyle={{ background: "#1a1f35", border: "1px solid #2a3555", borderRadius: 8, fontSize: 13 }}
                            labelStyle={{ color: "#8892a8" }}
                            formatter={(value) => [Number(value).toLocaleString(), "Price"]}
                          />
                          <Line type="monotone" dataKey="price" stroke="var(--accent)" dot={false} strokeWidth={1.5} />
                          {selectedTrade.buy_price && (
                            <ReferenceLine y={selectedTrade.buy_price} stroke="var(--red)" strokeDasharray="4 4" label={{ value: `Buy ${selectedTrade.buy_price.toLocaleString()}`, fill: "var(--red)", fontSize: 11 }} />
                          )}
                          {selectedTrade.sell_price && (
                            <ReferenceLine y={selectedTrade.sell_price} stroke="var(--accent)" strokeDasharray="4 4" label={{ value: `Sell ${selectedTrade.sell_price.toLocaleString()}`, fill: "var(--accent)", fontSize: 11 }} />
                          )}
                          {selectedTrade.highest_price && (
                            <ReferenceLine y={selectedTrade.highest_price} stroke="var(--yellow)" strokeDasharray="2 4" label={{ value: `High ${selectedTrade.highest_price.toLocaleString()}`, fill: "var(--yellow)", fontSize: 11 }} />
                          )}
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <p style={{ color: "var(--text-muted)", fontSize: 13, padding: 20 }}>틱 데이터 없음</p>
                  )}
                </div>

                {/* Executions */}
                {selectedTrade.executions && selectedTrade.executions.length > 0 && (
                  <div className="card">
                    <div className="section-header">
                      <span className="section-title">체결 내역</span>
                    </div>
                    <table>
                      <thead>
                        <tr>
                          <th>구분</th>
                          <th>가격</th>
                          <th>수량</th>
                          <th>시간</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedTrade.executions.map((e: any, i: number) => (
                          <tr key={i}>
                            <td>
                              <span className={`badge ${e.side === "buy" ? "badge-red" : "badge-green"}`}>
                                {e.side === "buy" ? "매수" : "매도"}
                              </span>
                            </td>
                            <td style={{ fontVariantNumeric: "tabular-nums" }}>{e.price?.toLocaleString()}</td>
                            <td style={{ fontVariantNumeric: "tabular-nums" }}>{e.quantity}</td>
                            <td style={{ color: "var(--text-secondary)", fontSize: 12 }}>{e.executed_at?.slice(11, 19)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            ) : (
              <div className="card" style={{ height: "calc(100vh - 220px)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <p style={{ color: "var(--text-muted)", fontSize: 14 }}>좌측에서 거래를 선택하세요</p>
              </div>
            )}
          </div>
        </div>
      ) : (
        /* Logs Tab */
        <div className="card">
          <div
            style={{
              height: "calc(100vh - 240px)",
              overflow: "auto",
              background: "var(--bg-primary)",
              borderRadius: 8,
              padding: "10px 14px",
              fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
              fontSize: 12,
              lineHeight: 1.7,
            }}
          >
            {lines.length === 0 ? (
              <span style={{ color: "var(--text-muted)" }}>로그가 없습니다</span>
            ) : (
              lines.map((line, i) => {
                const lv = getLineLevel(line);
                return (
                  <div key={i} style={{ color: LEVEL_COLORS[lv] || "var(--text-secondary)", whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                    {search ? highlightSearch(line, search) : line}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function highlightSearch(text: string, search: string) {
  if (!search) return text;
  const idx = text.toLowerCase().indexOf(search.toLowerCase());
  if (idx === -1) return text;
  return (
    <>
      {text.slice(0, idx)}
      <span style={{ background: "var(--yellow)", color: "#000", borderRadius: 2, padding: "0 2px" }}>
        {text.slice(idx, idx + search.length)}
      </span>
      {text.slice(idx + search.length)}
    </>
  );
}
