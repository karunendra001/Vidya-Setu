import { Fragment, useEffect, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { api, setToken, openDocument } from "./api";
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, CartesianGrid, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";

const label = (s) => s.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
const Badge = ({ s }) => <span className={"badge " + s}>{s}</span>;
const Err = ({ e }) => (e ? <p className="error">{e}</p> : null);

export function Login({ onLogin }) {
  const [mode, setMode] = useState("login");
  const [f, setF] = useState({ email: "", password: "", full_name: "" });
  const [err, setErr] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function go(e) {
    e.preventDefault(); setErr("");
    try {
      const r = await api(mode === "login" ? "/auth/login" : "/auth/register", { method: "POST", body: f });
      setToken(r.token);
      onLogin(await api("/me"));
    } catch (x) { setErr(x.message); }
  }
  return (
    <form className="card narrow" onSubmit={go}>
      <h2>{mode === "login" ? "Sign in" : "Create applicant account"}</h2>
      {mode === "register" && <label>Full name<input value={f.full_name} onChange={set("full_name")} required /></label>}
      <label>Email<input type="email" value={f.email} onChange={set("email")} required /></label>
      <label>Password<input type="password" value={f.password} onChange={set("password")} required minLength={6} /></label>
      <Err e={err} />
      <button className="btn">{mode === "login" ? "Sign in" : "Register"}</button>
      <p className="muted">
        {mode === "login" ? "New applicant? " : "Already registered? "}
        <button type="button" className="link" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "Create an account" : "Sign in"}
        </button>
      </p>
    </form>
  );
}

export function Dashboard() {
  const [schemes, setSchemes] = useState([]);
  const [apps, setApps] = useState([]);
  const [err, setErr] = useState("");
  const nav = useNavigate();
  useEffect(() => {
    Promise.all([api("/schemes"), api("/applications/mine")]).then(([s, a]) => { setSchemes(s); setApps(a); }).catch((e) => setErr(e.message));
  }, []);
  const name = (id) => schemes.find((s) => s.id === id)?.name || "Scheme #" + id;
  async function start(id) {
    try { nav("/apply/" + (await api("/applications", { method: "POST", body: { scheme_id: id } })).id); }
    catch (e) { setErr(e.message); }
  }
  return (
    <>
      <Err e={err} />
      <section className="card">
        <h2>Available schemes</h2>
        {schemes.map((s) => (
          <div className="row" key={s.id}><span>{s.name}</span><button className="btn" onClick={() => start(s.id)}>Apply</button></div>
        ))}
      </section>
      <section className="card">
        <h2>My applications</h2>
        {apps.length === 0 && <p className="muted">You have not started any application.</p>}
        {apps.map((a) => (
          <div className="row" key={a.id}>
            <span>#{a.id} · {name(a.scheme_id)}</span>
            <span><Badge s={a.status} /> <Link to={"/apply/" + a.id}>{a.status === "DRAFT" || a.status === "DEFICIENT" ? "Continue" : "View"}</Link></span>
          </div>
        ))}
      </section>
    </>
  );
}

const STEPS = ["DRAFT", "SUBMITTED", "VERIFIED", "RESULT"];
const STEP_LABEL = { DRAFT: "Draft", SUBMITTED: "Under verification", VERIFIED: "Verified", RESULT: "Result" };
function Tracker({ status }) {
  const key = status === "DEFICIENT" ? "DRAFT"
    : ["SELECTED", "WAITLISTED", "NOT_SELECTED"].includes(status) ? "RESULT"
    : status === "REJECTED" ? "SUBMITTED" : status;
  const i = Math.max(0, STEPS.indexOf(key));
  return (
    <ol className="tracker">
      {STEPS.map((s, n) => <li key={s} className={n <= i ? "done" : ""}>{STEP_LABEL[s]}</li>)}
    </ol>
  );
}

export function Eligibility({ e }) {
  if (!e?.result) return null;
  return (
    <div className="card">
      <h3>Eligibility check: <Badge s={e.result} /></h3>
      <ul>{e.reasons.map((r, n) => <li key={n}>{r.passed === true ? "✔" : r.passed === false ? "✘" : "?"} {r.rule} <span className="muted">({r.why})</span></li>)}</ul>
    </div>
  );
}

function Docs({ docs }) {
  return docs.length ? (
    <ul>{docs.map((d) => <li key={d.id}>{label(d.doc_type)}: <button className="link" onClick={() => openDocument(d.id).catch((e) => alert(e.message))}>{d.filename}</button></li>)}</ul>
  ) : <p className="muted">No documents uploaded.</p>;
}

export function ApplicationPage() {
  const { id } = useParams();
  const [app, setApp] = useState(null);
  const [cfg, setCfg] = useState(null);
  const [data, setData] = useState({});
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  const load = () => api("/applications/" + id).then(async (a) => {
    setApp(a); setData(a.form_data);
    if (!cfg) setCfg((await api("/schemes/" + a.scheme.id)).config);
  }).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, [id]);

  if (!app || !cfg) return <><Err e={err} /><p>Loading…</p></>;
  const run = async (fn, ok) => { setErr(""); setMsg(""); try { await fn(); setMsg(ok); await load(); } catch (e) { setErr(e.message); } };
  const save = () => run(() => api("/applications/" + id, { method: "PUT", body: data }), "Draft saved.");
  const upload = (type, file) => { const fd = new FormData(); fd.append("file", file); return run(() => api(`/applications/${id}/documents?doc_type=${type}`, { method: "POST", form: fd }), label(type) + " uploaded."); };
  const submit = () => run(async () => { await api("/applications/" + id, { method: "PUT", body: data }); await api(`/applications/${id}/submit`, { method: "POST" }); }, "Application submitted.");
  const unfilled = cfg.form_fields.filter((f) => data[f.name] === undefined || data[f.name] === "");
  const setField = (f, v) => setData({ ...data, [f.name]: v });

  return (
    <>
      <h2>{app.scheme.name} · Application #{app.id}</h2>
      <Tracker status={app.status} />
      <p>Status: <Badge s={app.status} /></p>
      {app.officer_note && <div className={"notice " + app.status}><b>Officer's remark:</b> {app.officer_note}</div>}
      <Err e={err} />{msg && <p className="ok">{msg}</p>}

      <section className="card">
        <h3>Application details</h3>
        {cfg.form_fields.map((f) => (
          <label key={f.name}>{f.label}
            {f.type === "select" ? (
              <select disabled={!app.editable} value={data[f.name] ?? ""} onChange={(e) => setField(f, e.target.value)}>
                <option value="">Select…</option>{f.options.map((o) => <option key={o}>{o}</option>)}
              </select>
            ) : f.type === "boolean" ? (
              <select disabled={!app.editable} value={data[f.name] === undefined ? "" : String(data[f.name])} onChange={(e) => setField(f, e.target.value === "" ? "" : e.target.value === "true")}>
                <option value="">Select…</option><option value="true">Yes</option><option value="false">No</option>
              </select>
            ) : (
              <input disabled={!app.editable} type={f.type === "number" ? "number" : "text"} value={data[f.name] ?? ""} onChange={(e) => setField(f, f.type === "number" && e.target.value !== "" ? Number(e.target.value) : e.target.value)} />
            )}
          </label>
        ))}
      </section>

      <section className="card">
        <h3>Documents <span className="muted">(PDF, JPG or PNG, up to 5 MB)</span></h3>
        {cfg.required_documents.map((t) => {
          const d = app.documents.find((x) => x.doc_type === t);
          return (
            <div className="row" key={t}>
              <span>{label(t)} {d ? <span className="ok">✔ {d.filename}</span> : <span className="error">required</span>}</span>
              {app.editable && <input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={(e) => e.target.files[0] && upload(t, e.target.files[0])} />}
            </div>
          );
        })}
      </section>

      {app.editable && (
        <div className="actions">
          <button className="btn secondary" onClick={save}>Save draft</button>
          <button className="btn" disabled={app.missing_documents.length > 0 || unfilled.length > 0} onClick={submit}>Submit application</button>
          {(app.missing_documents.length > 0 || unfilled.length > 0) && <span className="muted">Fill all details and upload all documents to submit.</span>}
        </div>
      )}
      <Eligibility e={app.eligibility} />
    </>
  );
}

export function Queue() {
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState("");
  useEffect(() => { api("/officer/queue").then(setRows).catch((e) => setErr(e.message)); }, []);
  return (
    <section className="card">
      <h2>Applications awaiting verification</h2><Err e={err} />
      {rows.length === 0 && <p className="muted">No pending applications.</p>}
      <table>
        <thead><tr><th>ID</th><th>Applicant</th><th>Scheme</th><th>Eligibility</th><th /></tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.id}><td>#{r.id}</td><td>{r.applicant_name}</td><td>{r.scheme_name}</td>
            <td><Badge s={r.eligibility?.result || "—"} /></td><td><Link to={"/review/" + r.id}>Review</Link></td></tr>
        ))}</tbody>
      </table>
    </section>
  );
}

const CHECK_COLOR = { match: "#138808", review: "#d97706", mismatch: "#b91c1c", not_found: "#6b7280", info: "#6b7280" };

function DocChecks({ checks }) {
  if (!checks?.length) return null;
  return (
    <section className="card">
      <h3>AI document cross-check <span className="muted">(assistive: the officer decides)</span></h3>
      <table>
        <thead><tr><th>Document</th><th>Field</th><th>Entered by applicant</th><th>Read from document</th><th>Result</th></tr></thead>
        <tbody>{checks.map((c, i) => (
          <tr key={i}>
            <td>{label(c.doc_type)}</td><td>{label(c.field)}</td>
            <td>{c.form_value || "—"}</td><td>{c.extracted_value || "—"}</td>
            <td style={{ color: CHECK_COLOR[c.status], fontWeight: 600 }}>
              {c.status.replace("_", " ").toUpperCase()}{c.score ? ` (${Math.round(c.score)}%)` : ""}
            </td>
          </tr>
        ))}</tbody>
      </table>
    </section>
  );
}

export function Review() {
  const { id } = useParams();
  const nav = useNavigate();
  const [app, setApp] = useState(null);
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => { api("/applications/" + id).then(setApp).catch((e) => setErr(e.message)); }, [id]);
  if (!app) return <><Err e={err} /><p>Loading…</p></>;
  async function decide(decision) {
    setErr("");
    try { await api(`/officer/applications/${id}/decision`, { method: "POST", body: { decision, note } }); nav("/"); }
    catch (e) { setErr(e.message); }
  }
  return (
    <>
      <h2>Review application #{app.id} <Badge s={app.status} /></h2>
      <p>{app.scheme.name} · Applicant: <b>{app.applicant?.full_name || app.applicant?.email}</b></p>
      <section className="card">
        <h3>Form data</h3>
        <table><tbody>{Object.entries(app.form_data).map(([k, v]) => <tr key={k}><th>{label(k)}</th><td>{String(v)}</td></tr>)}</tbody></table>
      </section>
      <section className="card"><h3>Documents</h3><Docs docs={app.documents} /></section>
      <DocChecks checks={app.doc_checks} />
      <Eligibility e={app.eligibility} />
      {app.status === "SUBMITTED" ? (
        <section className="card">
          <h3>Decision</h3>
          <label>Remarks <span className="muted">(mandatory unless verifying)</span>
            <textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} /></label>
          <Err e={err} />
          <div className="actions">
            <button className="btn" onClick={() => decide("VERIFIED")}>Verify</button>
            <button className="btn warn" onClick={() => decide("DEFICIENT")}>Mark deficient</button>
            <button className="btn danger" onClick={() => decide("REJECTED")}>Reject</button>
          </div>
        </section>
      ) : <p className="muted">This application has already been decided.</p>}
    </>
  );
}

export function Ranking({ user }) {
  const [schemes, setSchemes] = useState([]);
  const [sid, setSid] = useState("");
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [f, setF] = useState({ application_id: "", action: "PIN", rank: 1, reason: "" });
  const canOverride = user && ["approver", "admin"].includes(user.role);

  useEffect(() => {
    api("/schemes").then((s) => { setSchemes(s); if (s[0]) setSid(s[0].id); }).catch((e) => setErr(e.message));
  }, []);
  const load = () => { if (sid) api(`/committee/schemes/${sid}/ranking`).then(setData).catch((e) => { setErr(e.message); setData(null); }); };
  useEffect(() => { load(); }, [sid]);

  const act = async (fn, ok) => { setErr(""); setMsg(""); try { await fn(); setMsg(ok); load(); } catch (e) { setErr(e.message); } };
  const override = () => act(() => api(`/committee/schemes/${sid}/overrides`, {
    method: "POST",
    body: { application_id: Number(f.application_id), action: f.action, rank: f.action === "PIN" ? Number(f.rank) : null, reason: f.reason },
  }), "Override saved and logged.");
  const publish = () => {
    if (window.confirm("Publish results? This locks the ranking and notifies every applicant's status.")) {
      act(() => api(`/committee/schemes/${sid}/publish`, { method: "POST" }), "Results published.");
    }
  };

  if (!data) return <><Err e={err} /><p>Loading…</p></>;
  const everyone = [...data.ranked, ...data.excluded];
  return (
    <>
      <h2>Merit list · {data.scheme.name}</h2>
      <p className="muted">Slots: {data.slots} · Waitlist: {data.waitlist} · Score = Σ (field value × weight). The ranking is a recommendation; the committee decides.</p>
      <select value={sid} onChange={(e) => setSid(e.target.value)}>
        {schemes.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select>
      <Err e={err} />{msg && <p className="ok">{msg}</p>}
      {data.published && <div className="notice">Results are published. The ranking is locked.</div>}

      <section className="card">
        <table>
          <thead><tr><th>Rank</th><th>Applicant</th><th>Score</th><th>Breakdown</th><th>Decision</th><th>Override</th></tr></thead>
          <tbody>
            {data.ranked.map((r) => (
              <Fragment key={r.application_id}>
                <tr>
                  <td>{r.rank}{r.rank !== r.auto_rank && <span className="muted"> (auto {r.auto_rank})</span>}</td>
                  <td>#{r.application_id} {r.name}</td>
                  <td>{r.score}</td>
                  <td className="muted">{r.breakdown.map((b) => `${label(b.field)}: ${b.value} × ${b.weight} = ${b.points}`).join("; ")}</td>
                  <td><Badge s={r.decision} /></td>
                  <td>{r.override ? `${r.override.action}: ${r.override.reason}` : "—"}</td>
                </tr>
                {r.rank === data.slots && (
                  <tr>
                    <td colSpan={6} style={{ borderTop: "3px solid #b91c1c", textAlign: "center", color: "#b91c1c" }}>
                      — cut-off: {data.slots} slots —
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            {data.excluded.map((r) => (
              <tr key={"x" + r.application_id}>
                <td>—</td><td>#{r.application_id} {r.name}</td><td>{r.score}</td><td />
                <td><Badge s="EXCLUDED" /></td><td>{r.override.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.ranked.length === 0 && <p className="muted">No verified applications yet.</p>}
      </section>

      {canOverride && !data.published && everyone.length > 0 && (
        <section className="card">
          <h3>Committee override <span className="muted">(approver / admin only, reason mandatory, logged)</span></h3>
          <label>Applicant
            <select value={f.application_id} onChange={(e) => setF({ ...f, application_id: e.target.value })}>
              <option value="">Select…</option>
              {everyone.map((r) => <option key={r.application_id} value={r.application_id}>#{r.application_id} {r.name}</option>)}
            </select>
          </label>
          <label>Action
            <select value={f.action} onChange={(e) => setF({ ...f, action: e.target.value })}>
              <option value="PIN">Move to rank position</option>
              <option value="EXCLUDE">Exclude from ranking</option>
              <option value="CLEAR">Clear override</option>
            </select>
          </label>
          {f.action === "PIN" && <label>Rank position<input type="number" min="1" value={f.rank} onChange={(e) => setF({ ...f, rank: e.target.value })} /></label>}
          <label>Reason<textarea rows={2} value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} /></label>
          <div className="actions">
            <button className="btn secondary" disabled={!f.application_id} onClick={override}>Apply override</button>
            <button className="btn" onClick={publish}>Publish results</button>
          </div>
        </section>
      )}
    </>
  );
}

const PALETTE = ["#FF9933", "#138808", "#1d4ed8", "#9333ea", "#b91c1c", "#0891b2"];
const Kpi = ({ t, v, s }) => (
  <div className="kpi"><div className="kpi-v">{v}</div><div className="kpi-t">{t}</div>{s && <div className="muted">{s}</div>}</div>
);
const Box = ({ title, children }) => (
  <section className="card"><h3>{title}</h3><div style={{ width: "100%", height: 260 }}>{children}</div></section>
);
const HBar = ({ data, color, w = 110 }) => (
  <ResponsiveContainer>
    <BarChart data={data} layout="vertical" margin={{ left: 10, right: 20 }}>
      <CartesianGrid strokeDasharray="3 3" />
      <XAxis type="number" allowDecimals={false} /><YAxis type="category" dataKey="name" width={w} />
      <Tooltip /><Bar dataKey="value" fill={color} />
    </BarChart>
  </ResponsiveContainer>
);
const VBar = ({ data, color }) => (
  <ResponsiveContainer>
    <BarChart data={data}>
      <CartesianGrid strokeDasharray="3 3" />
      <XAxis dataKey="name" /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="value" fill={color} />
    </BarChart>
  </ResponsiveContainer>
);
const Pie1 = ({ data }) => (
  <ResponsiveContainer>
    <PieChart>
      <Pie data={data} dataKey="value" nameKey="name" outerRadius={85} label>
        {data.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
      </Pie>
      <Tooltip /><Legend />
    </PieChart>
  </ResponsiveContainer>
);

export function Ministry() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { api("/ministry/dashboard").then(setD).catch((e) => setErr(e.message)); }, []);
  if (!d) return <><Err e={err} /><p>Loading…</p></>;
  const k = d.kpis;
  return (
    <>
      <h2>Ministry dashboard</h2>
      {d.has_demo_data && <div className="notice">This view contains <b>synthetic demo data</b> (accounts ending @example.test). No real applicant is shown.</div>}
      <div className="kpis">
        <Kpi t="Applications" v={k.total} />
        <Kpi t="Submitted" v={k.submitted} />
        <Kpi t="Verified" v={k.verified} />
        <Kpi t="Selected" v={k.selected} />
        <Kpi t="Pending review" v={k.pending} s={`oldest ${k.oldest_pending_days} days`} />
        <Kpi t="Avg. processing" v={k.avg_days === null ? "—" : k.avg_days + " d"} s={k.median_days === null ? "" : `median ${k.median_days} d`} />
        <Kpi t="Deficiency rate" v={k.deficiency_rate + "%"} s="of officer decisions" />
      </div>

      <div className="grid2">
        <Box title="Application funnel"><HBar data={d.funnel} color="#138808" w={90} /></Box>
        <Box title="Applications by state (top 12)"><HBar data={d.by_state} color="#FF9933" w={120} /></Box>
        <Box title="Gender split"><Pie1 data={d.by_gender} /></Box>
        <Box title="Automatic eligibility outcome"><Pie1 data={d.eligibility} /></Box>
        <Box title="Time taken per review (days)"><VBar data={d.processing_buckets} color="#1d4ed8" /></Box>
        <Box title="Ageing of pending applications"><VBar data={d.ageing} color="#b91c1c" /></Box>
        <Box title="Decisions per officer">
          <ResponsiveContainer>
            <BarChart data={d.by_officer}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" /><YAxis allowDecimals={false} /><Tooltip /><Legend />
              <Bar dataKey="VERIFIED" stackId="a" fill="#138808" />
              <Bar dataKey="DEFICIENT" stackId="a" fill="#d97706" />
              <Bar dataKey="REJECTED" stackId="a" fill="#b91c1c" />
            </BarChart>
          </ResponsiveContainer>
        </Box>
        <Box title="Status of all applications"><Pie1 data={d.status} /></Box>
      </div>

      <section className="card">
        <h3>Scheme-wise performance</h3>
        <table>
          <thead><tr><th>Scheme</th><th>Started</th><th>Submitted</th><th>Verified</th><th>Selected</th></tr></thead>
          <tbody>{d.by_scheme.map((s) => <tr key={s.scheme}><td>{s.scheme}</td><td>{s.started}</td><td>{s.submitted}</td><td>{s.verified}</td><td>{s.selected}</td></tr>)}</tbody>
        </table>
      </section>

      <section className="card">
        <h3>Top deficiency and rejection reasons</h3>
        {d.top_reasons.length === 0 && <p className="muted">No deficiency or rejection remarks yet.</p>}
        <table><tbody>{d.top_reasons.map((r) => <tr key={r.name}><td>{r.name}</td><td>{r.value}</td></tr>)}</tbody></table>
      </section>
    </>
  );
}