import { useEffect, useState } from "react";
import { fetchJson, postJson, deleteJson, putJson } from "../api/client";

type ConfigData = Record<string, Record<string, string | number> | string | number>;

const CONFIG_SECTIONS = [
  {
    key: "telegram_listener",
    label: "텔레그램 리스너",
    desc: "리딩방 수신",
    fields: [
      { key: "api_id", label: "API ID", type: "number" },
      { key: "api_hash", label: "API Hash", type: "password" },
      { key: "phone", label: "Phone", type: "text", placeholder: "+821012345678" },
      { key: "session_name", label: "Session Name", type: "text" },
    ],
  },
  {
    key: "telegram_bot",
    label: "텔레그램 봇",
    desc: "알림 발송",
    fields: [
      { key: "token", label: "Bot Token", type: "password" },
      { key: "chat_id", label: "Chat ID", type: "number" },
    ],
  },
  {
    key: "cybos",
    label: "CYBOS Plus",
    desc: "증권사 연결",
    fields: [
      { key: "exe_path", label: "실행 경로", type: "text" },
    ],
  },
  {
    key: "web",
    label: "웹 서버",
    desc: "서버 설정",
    fields: [
      { key: "host", label: "Host", type: "text" },
      { key: "port", label: "Port", type: "number" },
    ],
  },
];

export default function Settings() {
  const [params, setParams] = useState<Record<string, any>>({});
  const [channels, setChannels] = useState<any[]>([]);
  const [history, setHistory] = useState<any[]>([]);
  const [newUrl, setNewUrl] = useState("");
  const [newName, setNewName] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [config, setConfig] = useState<ConfigData>({});
  const [configDraft, setConfigDraft] = useState<ConfigData>({});
  const [configSaved, setConfigSaved] = useState(false);
  const [showSecrets, setShowSecrets] = useState(false);

  const loadAll = () => {
    fetchJson<Record<string, any>>("/settings/params").then(setParams);
    fetchJson<any[]>("/settings/channels").then(setChannels);
    fetchJson<any[]>("/settings/params/history").then(setHistory);
    fetchJson<ConfigData>("/settings/config").then((c) => {
      setConfig(c);
      setConfigDraft(JSON.parse(JSON.stringify(c)));
    });
  };
  useEffect(loadAll, []);

  const saveParam = async (key: string) => {
    await putJson(`/settings/params/${key}`, { value: editValue, updated_by: "web" });
    setEditing(null);
    loadAll();
  };

  const updateDraft = (section: string, field: string, value: string) => {
    setConfigDraft((prev) => ({
      ...prev,
      [section]: { ...(prev[section] as Record<string, any>), [field]: value },
    }));
    setConfigSaved(false);
  };

  const saveConfig = async () => {
    const toSave: ConfigData = JSON.parse(JSON.stringify(configDraft));
    for (const sec of CONFIG_SECTIONS) {
      const secData = toSave[sec.key];
      if (typeof secData !== "object") continue;
      for (const f of sec.fields) {
        if (f.type === "number" && secData[f.key] !== undefined) {
          secData[f.key] = Number(secData[f.key]) || 0;
        }
      }
    }
    await putJson("/settings/config", toSave);
    setConfigSaved(true);
    setConfig(JSON.parse(JSON.stringify(toSave)));
    setTimeout(() => setConfigSaved(false), 3000);
  };

  const configChanged = JSON.stringify(config) !== JSON.stringify(configDraft);

  return (
    <div className="page">
      <h1 className="page-title">Settings</h1>

      {/* System Config */}
      <div style={{ marginBottom: 32 }}>
        <div className="section-header" style={{ marginBottom: 16 }}>
          <span className="section-title">시스템 설정</span>
          <label style={{ fontSize: 12, color: "var(--text-muted)", cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}>
            <input type="checkbox" checked={showSecrets} onChange={(e) => setShowSecrets(e.target.checked)} />
            키 값 표시
          </label>
        </div>

        <div className="grid-2">
          {CONFIG_SECTIONS.map((sec) => {
            const secData = (configDraft[sec.key] || {}) as Record<string, any>;
            return (
              <div key={sec.key} className="card">
                <div style={{ marginBottom: 14 }}>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{sec.label}</span>
                  <span style={{ color: "var(--text-muted)", fontSize: 12, marginLeft: 8 }}>{sec.desc}</span>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "110px 1fr", gap: "8px 12px", alignItems: "center" }}>
                  {sec.fields.map((f) => (
                    <label key={f.key} style={{ display: "contents" }}>
                      <span style={{ color: "var(--text-secondary)", fontSize: 12 }}>{f.label}</span>
                      <input
                        type={f.type === "password" && !showSecrets ? "password" : "text"}
                        value={secData[f.key] ?? ""}
                        placeholder={f.placeholder || ""}
                        onChange={(e) => updateDraft(sec.key, f.key, e.target.value)}
                        style={{ width: "100%" }}
                      />
                    </label>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 16 }}>
          <button className={`btn ${configChanged ? "btn-success" : "btn-ghost"}`} onClick={saveConfig} disabled={!configChanged}>
            설정 저장
          </button>
          {configSaved && <span style={{ color: "var(--green)", fontSize: 12 }}>저장되었습니다</span>}
          {configChanged && !configSaved && <span style={{ color: "var(--yellow)", fontSize: 12 }}>변경사항 있음</span>}
        </div>
      </div>

      {/* Trading Parameters */}
      <div style={{ marginBottom: 32 }}>
        <div className="section-header" style={{ marginBottom: 12 }}>
          <span className="section-title">매매 파라미터</span>
        </div>
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>Parameter</th>
                <th>Value</th>
                <th style={{ width: 120 }}></th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(params).sort().map(([key, val]) => (
                <tr key={key}>
                  <td style={{ fontWeight: 500 }}>{key}</td>
                  <td>
                    {editing === key ? (
                      <input
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        autoFocus
                        onKeyDown={(e) => e.key === "Enter" && saveParam(key)}
                        style={{ width: 200 }}
                      />
                    ) : (
                      <span style={{ fontVariantNumeric: "tabular-nums" }}>{typeof val === "number" || (typeof val === "string" && /^\d+$/.test(val)) ? Number(val).toLocaleString() : String(val)}</span>
                    )}
                  </td>
                  <td>
                    {editing === key ? (
                      <div style={{ display: "flex", gap: 4 }}>
                        <button className="btn btn-success btn-sm" onClick={() => saveParam(key)}>Save</button>
                        <button className="btn btn-ghost btn-sm" onClick={() => setEditing(null)}>Cancel</button>
                      </div>
                    ) : (
                      <button className="btn btn-ghost btn-sm" onClick={() => { setEditing(key); setEditValue(String(val)); }}>Edit</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Telegram Channels */}
      <div style={{ marginBottom: 32 }}>
        <div className="section-header" style={{ marginBottom: 12 }}>
          <span className="section-title">텔레그램 채널</span>
        </div>
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <input placeholder="Channel URL" value={newUrl} onChange={(e) => setNewUrl(e.target.value)} style={{ flex: 1 }} />
          <input placeholder="Name" value={newName} onChange={(e) => setNewName(e.target.value)} style={{ width: 150 }} />
          <button
            className="btn btn-primary btn-sm"
            onClick={async () => {
              await postJson("/settings/channels", { channel_url: newUrl, channel_name: newName });
              setNewUrl(""); setNewName(""); loadAll();
            }}
          >
            Add
          </button>
        </div>
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>Channel</th>
                <th style={{ width: 80 }}>Status</th>
                <th style={{ width: 80 }}></th>
              </tr>
            </thead>
            <tbody>
              {channels.map((c: any) => (
                <tr key={c.id}>
                  <td>{c.channel_name || c.channel_url}</td>
                  <td>
                    <button
                      className={`btn btn-sm ${c.enabled ? "btn-success" : "btn-ghost"}`}
                      onClick={async () => { await putJson(`/settings/channels/${c.id}/toggle`, {}); loadAll(); }}
                    >
                      {c.enabled ? "ON" : "OFF"}
                    </button>
                  </td>
                  <td>
                    <button className="btn btn-ghost btn-sm" onClick={async () => { await deleteJson(`/settings/channels/${c.id}`); loadAll(); }}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* History */}
      <div>
        <div className="section-header" style={{ marginBottom: 12 }}>
          <span className="section-title">변경 이력</span>
        </div>
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Key</th>
                <th>Old</th>
                <th>New</th>
                <th>By</th>
              </tr>
            </thead>
            <tbody>
              {history.map((h: any, i: number) => (
                <tr key={i}>
                  <td style={{ color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums" }}>{h.updated_at}</td>
                  <td style={{ fontWeight: 500 }}>{h.key}</td>
                  <td style={{ color: "var(--text-muted)" }}>{h.old_value}</td>
                  <td>{h.new_value}</td>
                  <td>
                    <span className="badge badge-green">{h.updated_by}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
