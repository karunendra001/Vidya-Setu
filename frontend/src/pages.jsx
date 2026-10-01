import { useEffect, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { api, setToken, openDocument } from "./api";

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

const STEPS = ["DRAFT", "SUBMITTED", "VERIFIED"];
function Tracker({ status }) {
  const i = status === "REJECTED" ? 1 : Math.max(0, STEPS.indexOf(status === "DEFICIENT" ? "DRAFT" : status));
  return (
    <ol className="tracker">
      {STEPS.map((s, n) => <li key={s} className={n <= i ? "done" : ""}>{s === "DRAFT" ? "Draft" : s === "SUBMITTED" ? "Under verification" : "Verified"}</li>)}
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