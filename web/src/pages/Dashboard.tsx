import { useEffect, useState, useRef } from "react";
import {
  fetchJson,
  connectWebSocket,
  fetchStatus,
  launchCybos,
  startEngine,
  stopEngine,
  fetchLiveLogs,
  submitTelegramCode,
  fetchNewsFeed,
  emergencySellAll,
} from "../api/client";
import type { WsMessage, SystemStatus, LogEntry, NewsFeedItem } from "../api/client";

type Trade = {
  id: number;
  stock_code: string;
  stock_name: string;
  status: string;
  buy_price: number | null;
  buy_qty: number | null;
  sell_price: number | null;
  sell_qty: number | null;
  pnl_pct: number | null;
  pnl_amount: number | null;
  highest_price: number | null;
  hold_seconds: number | null;
  sell_reason: string | null;
  news_source: string | null;
  created_at: string | null;
};

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: "#4a5568",
  INFO: "#8892a8",
  WARNING: "#f59e0b",
  ERROR: "#ef4444",
  CRITICAL: "#ef4444",
};

export default function Dashboard() {
  const [status, setStatus] = useState<SystemStatus>({
    cybos_connected: false,
    server_type: "unknown",
    engine_running: false,
    active_workers: 0,
    account_number: "",
    error: null,
    telegram_code_pending: false,
  });
  const [holdings, setHoldings] = useState<Trade[]>([]);
  const [todayTrades, setTodayTrades] = useState<Trade[]>([]);
  const [newsEvents, setNewsEvents] = useState<NewsFeedItem[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [logFilter, setLogFilter] = useState("ALL");
  const logEndRef = useRef<HTMLDivElement>(null);
  const [showCodeModal, setShowCodeModal] = useState(false);
  const [telegramCode, setTelegramCode] = useState("");
  const [lastStatusAt, setLastStatusAt] = useState<number>(0);
  const [, forceTick] = useState(0);
  const newsScrollRef = useRef<HTMLDivElement>(null);
  const tradesScrollRef = useRef<HTMLDivElement>(null);
  const holdingsScrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const refresh = () => {
      fetchStatus().then((s) => { setStatus(s); setLastStatusAt(Date.now()); }).catch(() => {});
      // API returns chronological (oldest-first); reverse to match WS prepend convention
      // (storage is always newest-first; render reverse() shows oldest→newest top→bottom).
      fetchNewsFeed().then((arr) => setNewsEvents([...arr].reverse())).catch(() => {});
    };
    refresh();
    const interval = setInterval(refresh, 3000);
    const tick = setInterval(() => forceTick((n) => n + 1), 1000);
    // Page Visibility: immediately refresh when user returns to the tab (bypasses timer throttling)
    const onVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(interval);
      clearInterval(tick);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  const serverHealthy = lastStatusAt > 0 && (Date.now() - lastStatusAt) < 10000;

  useEffect(() => {
    if (status.telegram_code_pending && !showCodeModal) {
      setTelegramCode("");
      setShowCodeModal(true);
    }
    if (!status.telegram_code_pending && showCodeModal) {
      setShowCodeModal(false);
    }
  }, [status.telegram_code_pending]);

  useEffect(() => {
    const today = () => {
      const d = new Date();
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    };
    const refreshTrades = () => {
      fetchJson<Trade[]>("/trades?status=holding").then(setHoldings).catch(() => {});
      fetchJson<Trade[]>(`/trades?status=done&date=${today()}`).then(setTodayTrades).catch(() => {});
    };
    refreshTrades();
    // Periodic refresh catches cancelled/timeout updates that have no dedicated WS event
    const tradesInterval = setInterval(refreshTrades, 5000);
    const ws = connectWebSocket((msg: WsMessage) => {
      if (msg.type === "engine_status" || msg.type === "cybos_status") {
        // Immediately reflect server-pushed status changes (no dependency on HTTP polling)
        fetchStatus().then((s) => { setStatus(s); setLastStatusAt(Date.now()); }).catch(() => {});
      }
      if (msg.type === "news_feed" || msg.type === "news_detected") {
        const d = msg.data as Record<string, string>;
        setNewsEvents((prev) => [
          { stock_name: d.stock_name, stock_code: d.stock_code, source: d.source, category: d.category, text: d.text || "", time: d.timestamp || new Date().toLocaleTimeString() },
          ...prev.slice(0, 199),
        ]);
      }
      // Refresh on any worker state change (incl. screening/cancelled) or fill
      if (msg.type === "buy_filled" || msg.type === "sell_filled" || msg.type === "worker_state") {
        refreshTrades();
      }
      if (msg.type === "telegram_code_required") {
        setTelegramCode("");
        setShowCodeModal(true);
      }
      if (msg.type === "telegram_auth_result") {
        setShowCodeModal(false);
      }
    });
    return () => { clearInterval(tradesInterval); ws.close(); };
  }, []);

  const logSeqRef = useRef(0);
  useEffect(() => {
    const fetchLogs = () => {
      fetchLiveLogs(logSeqRef.current).then(({ logs: newLogs, seq }) => {
        if (newLogs.length > 0) {
          setLogs((prev) => [...prev, ...newLogs].slice(-500));
          logSeqRef.current = seq;
        }
      }).catch(() => {});
    };
    const timer = setInterval(fetchLogs, 1000);
    // Force immediate log fetch when tab becomes visible (bypasses Chrome's 1min throttle)
    const onVisible = () => {
      if (document.visibilityState === "visible") fetchLogs();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // Auto-scroll news/trades/holdings panels to bottom when new items arrive
  useEffect(() => {
    if (newsScrollRef.current) {
      newsScrollRef.current.scrollTop = newsScrollRef.current.scrollHeight;
    }
  }, [newsEvents.length]);
  useEffect(() => {
    if (tradesScrollRef.current) {
      tradesScrollRef.current.scrollTop = tradesScrollRef.current.scrollHeight;
    }
  }, [todayTrades.length]);
  useEffect(() => {
    if (holdingsScrollRef.current) {
      holdingsScrollRef.current.scrollTop = holdingsScrollRef.current.scrollHeight;
    }
  }, [holdings.length]);

  const handleStart = () => {
    startEngine().then(() => fetchStatus().then(setStatus));
  };
  const handleStop = () => stopEngine().then(() => fetchStatus().then(setStatus));
  const handleLaunch = () => launchCybos();
  const handleEmergencySell = () => {
    const n = holdings.length;
    if (!window.confirm(
      `긴급 전량 매도: 보유 ${n}종목 시장가 즉시 청산 + 엔진 정지합니다.\n계속하시겠습니까?`
    )) return;
    emergencySellAll().then((r) => {
      alert(`긴급 매도 발동: ${r.count ?? 0}건 매도 주문 제출`);
      fetchStatus().then(setStatus);
    }).catch((e) => alert(`실패: ${e}`));
  };

  const filteredLogs = logFilter === "ALL" ? logs : logs.filter((l) => l.level === logFilter);
  const wins = todayTrades.filter((t) => (t.pnl_amount ?? 0) > 0).length;
  const losses = todayTrades.filter((t) => (t.pnl_amount ?? 0) < 0).length;
  const totalPnl = todayTrades.reduce((s, t) => s + (t.pnl_amount ?? 0), 0);
  const winRate = todayTrades.length > 0 ? ((wins / todayTrades.length) * 100).toFixed(1) : "0.0";
  const avgPnlPct = todayTrades.length > 0
    ? (todayTrades.reduce((s, t) => s + (t.pnl_pct ?? 0), 0) / todayTrades.length) * 100
    : 0;

  return (
    <div className="page">
      {/* Status Bar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "12px 20px",
          background: "var(--bg-secondary)",
          border: "1px solid var(--border)",
          borderRadius: 12,
          marginBottom: 20,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
          {/* Server health (heartbeat-based) */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "4px 10px",
              borderRadius: 999,
              background: serverHealthy ? "rgba(16,185,129,0.12)" : "rgba(239,68,68,0.12)",
              border: `1px solid ${serverHealthy ? "rgba(16,185,129,0.4)" : "rgba(239,68,68,0.4)"}`,
            }}
          >
            <div
              style={{
                width: 10,
                height: 10,
                borderRadius: "50%",
                background: serverHealthy ? "var(--green)" : "var(--red)",
                boxShadow: serverHealthy
                  ? "0 0 10px rgba(16,185,129,0.7)"
                  : "0 0 10px rgba(239,68,68,0.7)",
                animation: serverHealthy ? "pulse 1.6s ease-in-out infinite" : "none",
              }}
            />
            <span style={{ fontSize: 13, fontWeight: 700, color: serverHealthy ? "var(--green)" : "var(--red)" }}>
              {serverHealthy ? "서버 정상" : "서버 응답없음"}
            </span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: status.cybos_connected ? "var(--green)" : "var(--red)",
                boxShadow: status.cybos_connected
                  ? "0 0 8px rgba(16,185,129,0.5)"
                  : "0 0 8px rgba(239,68,68,0.5)",
              }}
            />
            <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>CYBOS</span>
            <span style={{ fontSize: 13, fontWeight: 600 }}>
              {status.cybos_connected ? "연결됨" : "미연결"}
            </span>
          </div>

          {status.cybos_connected && (
            <span className={`badge ${status.server_type === "real" ? "badge-red" : "badge-green"}`}>
              {status.server_type === "real" ? "실전매매" : "모의투자"}
            </span>
          )}

          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: status.error
                  ? "var(--red)"
                  : status.engine_running
                  ? "var(--green)"
                  : "var(--text-muted)",
                boxShadow: status.engine_running
                  ? "0 0 8px rgba(16,185,129,0.5)"
                  : "none",
              }}
            />
            <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>엔진</span>
            <span style={{ fontSize: 13, fontWeight: 600 }}>
              {status.error ? "오류" : status.engine_running ? "실행중" : "정지"}
            </span>
          </div>

          <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            워커 <strong style={{ color: "var(--text-primary)" }}>{status.active_workers}</strong>
          </span>

          {status.account_number && (
            <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
              계좌 <strong style={{ color: "var(--text-primary)" }}>{status.account_number}</strong>
            </span>
          )}
        </div>

        {/* Control Buttons */}
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-primary btn-sm" onClick={handleLaunch} disabled={status.cybos_connected}>
            CYBOS 실행
          </button>
          <button className="btn btn-success btn-sm" onClick={handleStart} disabled={!status.cybos_connected || status.engine_running}>
            자동매매 시작
          </button>
          <button className="btn btn-danger btn-sm" onClick={handleStop} disabled={!status.engine_running}>
            자동매매 중지
          </button>
          <button
            className="btn btn-danger btn-sm"
            onClick={handleEmergencySell}
            disabled={holdings.length === 0}
            title="보유 전량 시장가 매도 + 엔진 정지"
            style={{ background: "#7f1d1d", fontWeight: 700 }}
          >
            🚨 긴급 전량매도
          </button>
        </div>
      </div>

      {/* Telegram Auth Code Modal */}
      {showCodeModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.6)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              background: "var(--bg-secondary)",
              border: "1px solid var(--border)",
              borderRadius: 12,
              padding: 24,
              width: 360,
            }}
          >
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>
              텔레그램 인증 코드 입력
            </div>
            <div style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 16 }}>
              텔레그램 앱에서 받은 로그인 코드를 입력해주세요.
            </div>
            <input
              type="text"
              value={telegramCode}
              onChange={(e) => setTelegramCode(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && telegramCode.trim()) {
                  submitTelegramCode(telegramCode.trim());
                  setTelegramCode("");
                }
              }}
              placeholder="12345"
              autoFocus
              style={{
                width: "100%",
                padding: "10px 12px",
                fontSize: 18,
                letterSpacing: 8,
                textAlign: "center",
                borderRadius: 8,
                border: "1px solid var(--border)",
                background: "var(--bg-primary)",
                color: "var(--text-primary)",
                marginBottom: 16,
                boxSizing: "border-box",
              }}
            />
            <div style={{ display: "flex", gap: 8 }}>
              <button
                className="btn btn-primary btn-sm"
                style={{ flex: 1 }}
                disabled={!telegramCode.trim()}
                onClick={() => {
                  submitTelegramCode(telegramCode.trim());
                  setTelegramCode("");
                }}
              >
                확인
              </button>
              <button
                className="btn btn-sm"
                style={{ flex: 1 }}
                onClick={() => setShowCodeModal(false)}
              >
                취소
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Error */}
      {status.error && (
        <div
          style={{
            padding: 14,
            background: "var(--red-bg)",
            border: "1px solid rgba(239,68,68,0.3)",
            borderRadius: 12,
            marginBottom: 20,
            fontSize: 13,
            color: "var(--red)",
          }}
        >
          {status.error}
        </div>
      )}

      {/* Stats Cards */}
      <div className="grid-4" style={{ marginBottom: 20 }}>
        <div className="stat-card">
          <div className="label">오늘 매매</div>
          <div className="value">{todayTrades.length}</div>
        </div>
        <div className="stat-card">
          <div className="label">승률</div>
          <div className="value">{winRate}%</div>
        </div>
        <div className="stat-card">
          <div className="label">승 / 패</div>
          <div className="value">
            <span style={{ color: "var(--red)" }}>{wins}</span>
            <span style={{ color: "var(--text-muted)", margin: "0 4px" }}>/</span>
            <span style={{ color: "var(--accent)" }}>{losses}</span>
          </div>
        </div>
        <div className="stat-card">
          <div className="label">손익</div>
          <div className="value" style={{ color: totalPnl >= 0 ? "var(--red)" : "var(--accent)" }}>
            {totalPnl >= 0 ? "+" : ""}{totalPnl.toLocaleString()}
            <span style={{ fontSize: 13, fontWeight: 500, marginLeft: 6, opacity: 0.8 }}>
              ({avgPnlPct >= 0 ? "+" : ""}{avgPnlPct.toFixed(2)}%)
            </span>
          </div>
        </div>
      </div>

      {/* Holdings */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="section-header">
          <span className="section-title">보유 종목</span>
          <span className="badge badge-green">{holdings.length}</span>
        </div>
        <div ref={holdingsScrollRef} style={{ height: 220, overflow: "auto" }}>
        <table style={{ tableLayout: "fixed" }}>
            <thead>
              <tr>
                <th style={{ width: "12%" }}>종목코드</th>
                <th style={{ width: "14%" }}>종목명</th>
                <th style={{ width: "12%" }}>매수수량</th>
                <th style={{ width: "16%" }}>매수단가</th>
                <th style={{ width: "22%" }}>평가손익</th>
                <th style={{ width: "16%" }}>수익률</th>
              </tr>
            </thead>
            <tbody>
              {holdings.length === 0 ? (
                <tr><td colSpan={6} style={{ color: "var(--text-muted)", textAlign: "center", padding: 20 }}>보유 종목 없음</td></tr>
              ) : holdings.map((h) => {
                const pnlColor = (h.pnl_pct ?? 0) >= 0 ? "var(--red)" : "var(--accent)";
                return (
                  <tr key={h.id}>
                    <td style={{ color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums" }}>{h.stock_code}</td>
                    <td style={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{h.stock_name}</td>
                    <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                      {h.buy_qty?.toLocaleString() ?? "-"}
                    </td>
                    <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                      {h.buy_price != null ? Math.round(h.buy_price).toLocaleString() : "-"}
                    </td>
                    <td style={{ textAlign: "right", fontWeight: 600, fontVariantNumeric: "tabular-nums", color: pnlColor }}>
                      {h.pnl_amount != null ? `${h.pnl_amount >= 0 ? "+" : ""}${h.pnl_amount.toLocaleString()}` : "-"}
                    </td>
                    <td style={{ textAlign: "right", fontWeight: 600, fontVariantNumeric: "tabular-nums", color: pnlColor }}>
                      {h.pnl_pct != null ? `${h.pnl_pct >= 0 ? "+" : ""}${h.pnl_pct.toFixed(2)}%` : "-"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* News Feed */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="section-header">
          <span className="section-title">뉴스 포착</span>
          <span className="badge badge-yellow">{newsEvents.length}</span>
        </div>
        <div ref={newsScrollRef} style={{ height: 330, overflow: "auto" }}>
          <table style={{ tableLayout: "fixed" }}>
            <thead>
              <tr>
                <th style={{ width: "9%" }}>시간</th>
                <th style={{ width: "9%" }}>종목코드</th>
                <th style={{ width: "13%" }}>종목명</th>
                <th style={{ width: "49%" }}>뉴스 제목</th>
                <th style={{ width: "10%" }}>카테고리</th>
                <th style={{ width: "10%" }}>소스</th>
              </tr>
            </thead>
            <tbody>
              {newsEvents.length === 0 ? (
                <tr><td colSpan={6} style={{ color: "var(--text-muted)", textAlign: "center", padding: 20 }}>대기중...</td></tr>
              ) : (
                [...newsEvents].reverse().map((n, i) => (
                  <tr key={i}>
                    <td style={{ color: "var(--text-muted)", fontSize: 12, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>{n.time || n.timestamp}</td>
                    <td style={{ color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums" }}>{n.stock_code}</td>
                    <td style={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{n.stock_name}</td>
                    <td style={{ color: "var(--text-secondary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{n.text}</td>
                    <td style={{ fontSize: 12, color: "var(--text-muted)" }}>{n.category || "-"}</td>
                    <td>
                      <span className={`badge ${n.source === "telegram" ? "badge-green" : "badge-yellow"}`} style={{ fontSize: 10 }}>
                        {n.source}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Today Trades Detail */}
      {todayTrades.length > 0 && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="section-header">
            <span className="section-title">오늘 거래 내역</span>
            <span className="badge badge-green">{todayTrades.length}건</span>
          </div>
          <div ref={tradesScrollRef} style={{ maxHeight: 380, overflow: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>시간</th>
                <th>종목</th>
                <th>소스</th>
                <th>매수가</th>
                <th>매도가</th>
                <th>수량</th>
                <th>수익률</th>
                <th>실현손익</th>
                <th>최고가</th>
                <th>보유</th>
                <th>매도사유</th>
              </tr>
            </thead>
            <tbody>
              {[...todayTrades].sort((a, b) => (a.id ?? 0) - (b.id ?? 0)).map((t) => {
                const pnl = t.pnl_amount ?? 0;
                const pnlColor = pnl > 0 ? "var(--red)" : pnl < 0 ? "var(--accent)" : "var(--text-secondary)";
                return (
                  <tr key={t.id}>
                    <td style={{ fontVariantNumeric: "tabular-nums", color: "var(--text-secondary)", fontSize: 12 }}>
                      {t.created_at?.slice(11, 19) ?? "-"}
                    </td>
                    <td>
                      <span style={{ fontWeight: 600 }}>{t.stock_name}</span>
                      <span style={{ color: "var(--text-muted)", marginLeft: 4, fontSize: 11 }}>{t.stock_code}</span>
                    </td>
                    <td>
                      <span className={`badge ${t.news_source === "telegram" ? "badge-green" : "badge-yellow"}`} style={{ fontSize: 10 }}>
                        {t.news_source}
                      </span>
                    </td>
                    <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                      {t.buy_price != null ? Math.round(t.buy_price).toLocaleString() : "-"}
                    </td>
                    <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                      {t.sell_price != null ? Math.round(t.sell_price).toLocaleString() : "-"}
                    </td>
                    <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums", color: "var(--text-secondary)" }}>
                      {t.buy_qty?.toLocaleString() ?? "-"}
                    </td>
                    <td style={{ textAlign: "right", fontWeight: 600, fontVariantNumeric: "tabular-nums", color: pnlColor }}>
                      {t.pnl_pct != null ? `${t.pnl_pct >= 0 ? "+" : ""}${t.pnl_pct.toFixed(2)}%` : "-"}
                    </td>
                    <td style={{ textAlign: "right", fontWeight: 600, fontVariantNumeric: "tabular-nums", color: pnlColor }}>
                      {pnl !== 0 ? `${pnl >= 0 ? "+" : ""}${pnl.toLocaleString()}` : "-"}
                    </td>
                    <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums", color: "var(--text-secondary)" }}>
                      {t.highest_price != null ? Math.round(t.highest_price).toLocaleString() : "-"}
                    </td>
                    <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums", color: "var(--text-secondary)", fontSize: 12 }}>
                      {t.hold_seconds != null ? `${t.hold_seconds.toFixed(0)}s` : "-"}
                    </td>
                    <td>
                      <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{t.sell_reason ?? "-"}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          </div>
        </div>
      )}

      {/* Log Panel */}
      <div className="card">
        <div className="section-header">
          <span className="section-title">실시간 로그</span>
          <select
            value={logFilter}
            onChange={(e) => setLogFilter(e.target.value)}
            style={{ padding: "4px 8px", fontSize: 12, borderRadius: 6 }}
          >
            <option value="ALL">All</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
          </select>
        </div>
        <div
          style={{
            height: 140,
            overflow: "auto",
            background: "var(--bg-primary)",
            borderRadius: 8,
            padding: "10px 14px",
            fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
            fontSize: 12,
            lineHeight: 1.7,
          }}
        >
          {filteredLogs.length === 0 && (
            <span style={{ color: "var(--text-muted)" }}>로그 대기중...</span>
          )}
          {filteredLogs.map((log, i) => (
            <div key={i} style={{ color: LEVEL_COLORS[log.level] || "var(--text-secondary)" }}>
              <span style={{ color: "var(--text-muted)" }}>{log.timestamp}</span>{" "}
              <span
                style={{
                  fontWeight: log.level === "ERROR" || log.level === "CRITICAL" ? 700 : 400,
                  color: LEVEL_COLORS[log.level],
                }}
              >
                {log.level.padEnd(7)}
              </span>{" "}
              {log.message}
            </div>
          ))}
          <div ref={logEndRef} />
        </div>
      </div>
    </div>
  );
}
