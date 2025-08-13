import React, { useEffect, useMemo, useState } from "react";
import "./App.css";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

function numberFmt(n) {
  if (n === null || n === undefined) return "-";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(n);
}

function percentFmt(n) {
  if (n === null || n === undefined) return "-";
  return `${(n * 100).toFixed(1)}%`;
}

const QuickLBOModal = ({ open, onClose, deal }) => {
  const [form, setForm] = useState({
    entry_ebitda: deal?.ebitda || 50,
    entry_ev_ebitda: Math.max(deal?.ev_ebitda || 9, 1),
    revenue_growth: 0.08,
    ebitda_margin: deal?.ebitda_margin || 0.2,
    capex_pct_of_revenue: 0.04,
    nwc_pct_change_of_revenue: 0.02,
    interest_rate: 0.08,
    leverage_multiple: 4.0,
    exit_ev_ebitda: Math.max((deal?.ev_ebitda || 9) - 1, 1),
    years: 5,
    tax_rate: 0.25,
  });
  const [res, setRes] = useState(null);
  const run = async () => {
    try {
      const { data } = await axios.post(`${API}/lbo/quick`, form);
      setRes(data);
    } catch (e) {
      alert(`LBO calc failed: ${e?.response?.data?.detail || e.message}`);
    }
  };
  useEffect(() => {
    if (open && deal) {
      setForm((f) => ({ ...f, entry_ebitda: deal.ebitda, entry_ev_ebitda: deal.ev_ebitda, ebitda_margin: deal.ebitda_margin, exit_ev_ebitda: Math.max((deal.ev_ebitda || 9) - 1, 1) }));
      setRes(null);
    }
  }, [open, deal]);
  if (!open) return null;
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Quick LBO: {deal?.name}</h3>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>
        <div className="grid grid-2">
          {Object.keys(form).map((k) => (
            <label key={k} className="field">
              <span>{k.replaceAll("_", " ")}</span>
              <input
                type={typeof form[k] === "number" ? "number" : "text"}
                step="0.01"
                value={form[k]}
                onChange={(e) => setForm({ ...form, [k]: Number(e.target.value) })}
              />
            </label>
          ))}
        </div>
        <div className="flex gap-2 mt-2">
          <button className="btn btn-primary" onClick={run}>Run LBO</button>
        </div>
        {res && (
          <div className="results">
            <div className="cards">
              <div className="card">
                <div className="label">Entry EV</div>
                <div className="value">${numberFmt(res.entry_ev)}m</div>
              </div>
              <div className="card">
                <div className="label">Entry Debt</div>
                <div className="value">${numberFmt(res.entry_debt)}m</div>
              </div>
              <div className="card">
                <div className="label">Entry Equity</div>
                <div className="value">${numberFmt(res.entry_equity)}m</div>
              </div>
              <div className="card">
                <div className="label">Exit EV</div>
                <div className="value">${numberFmt(res.exit_ev)}m</div>
              </div>
              <div className="card">
                <div className="label">Debt Remaining</div>
                <div className="value">${numberFmt(res.exit_debt)}m</div>
              </div>
              <div className="card">
                <div className="label">MOIC</div>
                <div className="value">{numberFmt(res.moic)}x</div>
              </div>
              <div className="card">
                <div className="label">IRR</div>
                <div className="value">{(res.irr * 100).toFixed(1)}%</div>
              </div>
            </div>
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Year</th>
                    <th>Revenue</th>
                    <th>EBITDA</th>
                    <th>Interest</th>
                    <th>Capex</th>
                    <th>NWC Δ</th>
                    <th>FCF</th>
                    <th>Debt End</th>
                  </tr>
                </thead>
                <tbody>
                  {res.yearly.map((y) => (
                    <tr key={y.year}>
                      <td>{y.year}</td>
                      <td>${numberFmt(y.revenue)}m</td>
                      <td>${numberFmt(y.ebitda)}m</td>
                      <td>${numberFmt(y.interest)}m</td>
                      <td>${numberFmt(y.capex)}m</td>
                      <td>${numberFmt(y.nwc_change)}m</td>
                      <td>${numberFmt(y.fcf)}m</td>
                      <td>${numberFmt(y.debt_end)}m</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const CSVUploader = ({ onComplete }) => {
  const [progress, setProgress] = useState(0);
  const [busy, setBusy] = useState(false);
  const chunkSize = 512 * 1024; // 512KB

  const upload = async (file) => {
    setBusy(true);
    try {
      const init = await axios.post(`${API}/upload/init`);
      const upload_id = init.data.upload_id;
      let idx = 0;
      for (let start = 0; start < file.size; start += chunkSize) {
        const end = Math.min(start + chunkSize, file.size);
        const chunk = file.slice(start, end);
        const fd = new FormData();
        fd.append("upload_id", upload_id);
        fd.append("index", String(idx));
        fd.append("chunk", new File([chunk], `chunk_${idx}`));
        await axios.post(`${API}/upload/chunk`, fd, { headers: { "Content-Type": "multipart/form-data" } });
        idx += 1;
        setProgress(Math.round((end / file.size) * 100));
      }
      const done = new FormData();
      done.append("upload_id", upload_id);
      const { data } = await axios.post(`${API}/upload/complete`, done);
      onComplete?.(data);
      alert(`Imported ${data.inserted} deals`);
    } catch (e) {
      alert(`Upload failed: ${e?.response?.data?.detail || e.message}`);
    } finally {
      setBusy(false);
      setProgress(0);
    }
  };

  return (
    <div className="uploader">
      <label className="btn">
        Upload CSV
        <input type="file" accept=".csv" style={{ display: "none" }} onChange={(e) => e.target.files[0] && upload(e.target.files[0])} />
      </label>
      {busy && (
        <div className="progress"><div style={{ width: `${progress}%` }} /></div>
      )}
    </div>
  );
};

function App() {
  const [deals, setDeals] = useState([]);
  const [filters, setFilters] = useState({ sector: "", geography: "", ev_ebitda_min: "", ev_ebitda_max: "" });
  const [metrics, setMetrics] = useState(null);
  const [selected, setSelected] = useState(null);

  const load = async () => {
    const params = {};
    if (filters.sector) params.sector = filters.sector;
    if (filters.geography) params.geography = filters.geography;
    if (filters.ev_ebitda_min) params.ev_ebitda_min = Number(filters.ev_ebitda_min);
    if (filters.ev_ebitda_max) params.ev_ebitda_max = Number(filters.ev_ebitda_max);
    const { data } = await axios.get(`${API}/deals`, { params });
    setDeals(data);
    const m = await axios.get(`${API}/deals/metrics`);
    setMetrics(m.data);
  };

  useEffect(() => {
    (async () => {
      try {
        await axios.get(`${API}/`);
      } catch (e) {
        console.warn("Backend health failed", e.message);
      }
      await load();
    })();
  }, []);

  const sectors = useMemo(() => Array.from(new Set(deals.map(d => d.sector))).sort(), [deals]);
  const geos = useMemo(() => Array.from(new Set(deals.map(d => d.geography))).sort(), [deals]);

  const seed = async () => {
    await axios.post(`${API}/seed`);
    await load();
  };

  return (
    <div className="page">
      <header className="topbar">
        <div className="brand">PE Deal Screener</div>
        <div className="actions">
          <CSVUploader onComplete={load} />
          <button className="btn btn-ghost" onClick={seed}>Seed Demo Data</button>
        </div>
      </header>

      <section className="dashboard">
        <div className="stat">
          <div className="label">Deals</div>
          <div className="value">{metrics ? metrics.count : "-"}</div>
        </div>
        <div className="stat">
          <div className="label">Avg EV/EBITDA</div>
          <div className="value">{metrics?.avg_multiple ?? "-"}</div>
        </div>
        <div className="stat">
          <div className="label">Median EV/EBITDA</div>
          <div className="value">{metrics?.median_multiple ?? "-"}</div>
        </div>
      </section>

      <section className="filters">
        <select value={filters.sector} onChange={(e) => setFilters({ ...filters, sector: e.target.value })}>
          <option value="">All Sectors</option>
          {sectors.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select value={filters.geography} onChange={(e) => setFilters({ ...filters, geography: e.target.value })}>
          <option value="">All Geographies</option>
          {geos.map((g) => (
            <option key={g} value={g}>{g}</option>
          ))}
        </select>
        <input placeholder="Min EV/EBITDA" value={filters.ev_ebitda_min} onChange={(e) => setFilters({ ...filters, ev_ebitda_min: e.target.value })} />
        <input placeholder="Max EV/EBITDA" value={filters.ev_ebitda_max} onChange={(e) => setFilters({ ...filters, ev_ebitda_max: e.target.value })} />
        <button className="btn" onClick={load}>Apply</button>
      </section>

      <section className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Company</th>
              <th>Sector</th>
              <th>Geo</th>
              <th>Revenue (m)</th>
              <th>EBITDA (m)</th>
              <th>Margin</th>
              <th>EV (m)</th>
              <th>EV/EBITDA</th>
              <th>Growth</th>
              <th>Score</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {deals.map(d => (
              <tr key={d.id}>
                <td>{d.name}</td>
                <td>{d.sector}</td>
                <td>{d.geography}</td>
                <td>{numberFmt(d.revenue)}</td>
                <td>{numberFmt(d.ebitda)}</td>
                <td>{percentFmt(d.ebitda_margin)}</td>
                <td>{numberFmt(d.ev)}</td>
                <td>{numberFmt(d.ev_ebitda)}</td>
                <td>{percentFmt(d.growth_rate)}</td>
                <td><span className="badge">{numberFmt(d.score)}</span></td>
                <td><button className="btn btn-primary" data-testid="open-lbo" onClick={() => setSelected(d)}>Quick LBO</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <QuickLBOModal open={!!selected} deal={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

export default App;