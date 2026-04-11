import { useEffect, useState } from "react";
import { fetchJson } from "../api/client";
import { Link } from "react-router-dom";
import DatePicker from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";

const PAGE_SIZE = 30;

function formatDate(d: Date | null): string {
  if (!d) return "";
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export default function TradeHistory() {
  const [trades, setTrades] = useState<any[]>([]);
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);
  const [source, setSource] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    let path = "/trades?status=done&limit=1000";
    const dateStr = formatDate(selectedDate);
    if (dateStr) path += `&date=${dateStr}`;
    if (source) path += `&news_source=${source}`;
    fetchJson<any[]>(path).then((data) => {
      setTrades(data);
      setPage(1);
    });
  }, [selectedDate, source]);

  const totalPages = Math.max(1, Math.ceil(trades.length / PAGE_SIZE));
  const pagedTrades = trades.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div className="page">
      <h1 className="page-title">Trade History</h1>
      <div style={{ display: "flex", gap: 10, marginBottom: 20, alignItems: "center" }}>
        <DatePicker
          selected={selectedDate}
          onChange={(date: Date | null) => setSelectedDate(date)}
          dateFormat="yyyy-MM-dd"
          placeholderText="날짜 선택"
          isClearable
          className="datepicker-input"
          calendarClassName="datepicker-calendar"
          showPopperArrow={false}
        />
        <select value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="">All Sources</option>
          <option value="cybos">Cybos</option>
          <option value="telegram">Telegram</option>
        </select>
        <span style={{ color: "var(--text-muted)", fontSize: 13, marginLeft: 8 }}>
          총 {trades.length}건
        </span>
      </div>
      <div className="card">
        <table style={{ tableLayout: "fixed" }}>
          <thead>
            <tr>
              <th style={{ width: "7%" }}>시간</th>
              <th style={{ width: "8%" }}>종목코드</th>
              <th style={{ width: "10%" }}>종목명</th>
              <th style={{ width: "7%" }}>소스</th>
              <th style={{ width: "8%" }}>매수수량</th>
              <th style={{ width: "10%" }}>매수가</th>
              <th style={{ width: "10%" }}>매도가</th>
              <th style={{ width: "10%" }}>수익률</th>
              <th style={{ width: "12%" }}>실현손익</th>
              <th style={{ width: "7%" }}>매도사유</th>
              <th style={{ width: "4%" }}></th>
            </tr>
          </thead>
          <tbody>
            {pagedTrades.length === 0 ? (
              <tr><td colSpan={11} style={{ color: "var(--text-muted)", textAlign: "center", padding: 32 }}>매매 내역이 없습니다</td></tr>
            ) : pagedTrades.map((t: any) => {
              const pnl = t.pnl_amount ?? 0;
              const pnlColor = pnl > 0 ? "var(--red)" : pnl < 0 ? "var(--accent)" : "var(--text-secondary)";
              return (
                <tr key={t.id}>
                  <td style={{ fontVariantNumeric: "tabular-nums", color: "var(--text-secondary)", fontSize: 12 }}>
                    {t.created_at?.slice(11, 19)}
                  </td>
                  <td style={{ color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums" }}>{t.stock_code}</td>
                  <td style={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.stock_name}</td>
                  <td>
                    <span className={`badge ${t.news_source === "telegram" ? "badge-green" : "badge-yellow"}`} style={{ fontSize: 10 }}>
                      {t.news_source}
                    </span>
                  </td>
                  <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                    {t.buy_qty?.toLocaleString() ?? "-"}
                  </td>
                  <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                    {t.buy_price?.toLocaleString() ?? "-"}
                  </td>
                  <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                    {t.sell_price?.toLocaleString() ?? "-"}
                  </td>
                  <td style={{ textAlign: "right", fontWeight: 600, fontVariantNumeric: "tabular-nums", color: pnlColor }}>
                    {t.pnl_pct != null ? `${t.pnl_pct >= 0 ? "+" : ""}${t.pnl_pct.toFixed(2)}%` : "-"}
                  </td>
                  <td style={{ textAlign: "right", fontWeight: 600, fontVariantNumeric: "tabular-nums", color: pnlColor }}>
                    {pnl !== 0 ? `${pnl >= 0 ? "+" : ""}${pnl.toLocaleString()}` : "-"}
                  </td>
                  <td style={{ color: "var(--text-muted)", fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {t.sell_reason ?? "-"}
                  </td>
                  <td>
                    <Link to={`/trades/${t.id}`} className="btn btn-ghost btn-sm" style={{ textDecoration: "none", fontSize: 11, padding: "3px 6px" }}>
                      Replay
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {/* Pagination */}
        {(
          <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 4, padding: "16px 0 4px" }}>
            <button
              className="btn btn-ghost btn-sm"
              disabled={page === 1}
              onClick={() => setPage(1)}
            >
              &laquo;
            </button>
            <button
              className="btn btn-ghost btn-sm"
              disabled={page === 1}
              onClick={() => setPage(page - 1)}
            >
              &lsaquo;
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1)
              .filter((p) => p === 1 || p === totalPages || Math.abs(p - page) <= 2)
              .reduce<(number | string)[]>((acc, p, i, arr) => {
                if (i > 0 && p - (arr[i - 1] as number) > 1) acc.push("...");
                acc.push(p);
                return acc;
              }, [])
              .map((p, i) =>
                typeof p === "string" ? (
                  <span key={`dot-${i}`} style={{ color: "var(--text-muted)", padding: "0 4px" }}>{p}</span>
                ) : (
                  <button
                    key={p}
                    className={`btn btn-sm ${p === page ? "btn-primary" : "btn-ghost"}`}
                    onClick={() => setPage(p)}
                    style={{ minWidth: 32, minHeight: 32, display: "inline-flex", alignItems: "center", justifyContent: "center" }}
                  >
                    {p}
                  </button>
                )
              )}
            <button
              className="btn btn-ghost btn-sm"
              disabled={page === totalPages}
              onClick={() => setPage(page + 1)}
            >
              &rsaquo;
            </button>
            <button
              className="btn btn-ghost btn-sm"
              disabled={page === totalPages}
              onClick={() => setPage(totalPages)}
            >
              &raquo;
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
