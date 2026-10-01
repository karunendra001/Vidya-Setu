import { useEffect, useState } from "react";
import { Routes, Route, Navigate, Link, useNavigate } from "react-router-dom";
import { api, getToken, setToken } from "./api";
import { Login, Dashboard, ApplicationPage, Queue, Review, Ranking, Ministry} from "./pages.jsx";

export default function App() {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const nav = useNavigate();

  useEffect(() => {
    if (!getToken()) return setReady(true);
    api("/me").then(setUser).catch(() => setToken(null)).finally(() => setReady(true));
  }, []);

  const logout = () => { setToken(null); setUser(null); nav("/login"); };
  if (!ready) return <p className="center">Loading…</p>;
  const staff = user && user.role !== "applicant";

  return (
    <>
      <div className="tricolour"><i /><i /><i /></div>
      <header className="masthead">
        <div>
          <div className="gov">Ministry of Tribal Affairs · Government of India</div>
          <h1>Vidya Setu</h1>
          <div className="sub">Scholarship &amp; Fellowship Portal</div>
        </div>
        {user && (
          <div className="who">
            <span>{user.full_name || user.email} <em>({user.role})</em></span>
            <button className="link" onClick={logout}>Logout</button>
          </div>
        )}
      </header>

      {user && (
        <nav className="nav">
          <Link to="/">{staff ? "Verification queue" : "My applications"}</Link>
          {staff && <Link to="/ranking">Merit list</Link>}
          {user && ["approver", "admin"].includes(user.role) && <Link to="/ministry">Dashboard</Link>}
        </nav>
      )}

      <main className="page">
        <Routes>
          <Route path="/login" element={user ? <Navigate to="/" /> : <Login onLogin={setUser} />} />
          <Route path="/" element={!user ? <Navigate to="/login" /> : staff ? <Queue /> : <Dashboard />} />
          <Route path="/apply/:id" element={user ? <ApplicationPage /> : <Navigate to="/login" />} />
          <Route path="/review/:id" element={staff ? <Review /> : <Navigate to="/" />} />
          <Route path="/ranking" element={staff ? <Ranking user={user} /> : <Navigate to="/" />} />
          <Route path="/ministry" element={user && ["approver", "admin"].includes(user.role) ? <Ministry /> : <Navigate to="/" />} />
        </Routes>
      </main>
      <footer className="foot">Vidya Setu | Scholarship & Fellowship Portal</footer>
    </>
  );
}