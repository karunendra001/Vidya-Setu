const BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
export const getToken = () => localStorage.getItem("token");
export const setToken = (t) => (t ? localStorage.setItem("token", t) : localStorage.removeItem("token"));

function message(detail) {
  if (!detail) return "Something went wrong";
  if (typeof detail === "string") return detail;
  if (detail.message) return detail.message + (detail.missing ? ": " + detail.missing.join(", ") : "");
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join("; ");
  return "Something went wrong";
}

export async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  if (getToken()) headers.Authorization = "Bearer " + getToken();
  if (body) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(BASE + path, { method, headers, body: form || (body ? JSON.stringify(body) : undefined) });
  } catch {
    throw new Error("Cannot reach the server. Is the backend running?");
  }
  if (res.status === 401 && getToken()) { setToken(null); window.location.href = "/login"; }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(message(data.detail));
  return data;
}

// Documents need the auth header, so fetch as a blob and open in a new tab.
export async function openDocument(id) {
  const res = await fetch(`${BASE}/documents/${id}/download`, { headers: { Authorization: "Bearer " + getToken() } });
  if (!res.ok) throw new Error("Could not open document");
  window.open(URL.createObjectURL(await res.blob()), "_blank");
}