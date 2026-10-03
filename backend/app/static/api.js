let token = localStorage.getItem("cronica_token");
let onExpired = () => {};

export function hasSession() {
  return Boolean(token);
}

export function setSession(value) {
  token = value;
  if (value) localStorage.setItem("cronica_token", value);
  else localStorage.removeItem("cronica_token");
}

export function whenSessionExpires(callback) {
  onExpired = callback;
}

export function errorMessage(detail) {
  if (!detail) return "Algo deu errado. Tente de novo.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const fields = detail.map((d) => d.loc[d.loc.length - 1]);
    if (fields.includes("password")) return "A senha precisa ter pelo menos 8 caracteres.";
    if (fields.includes("email")) return "Esse e-mail não parece válido.";
    if (fields.includes("message")) return "Conte em poucas palavras o que mudou nesta versão.";
    if (fields.includes("code")) return "O código tem 8 letras e números, como K7QM-4XPA.";
    const custom = detail.find((d) => typeof d.msg === "string" && d.msg.startsWith("Value error, "));
    if (custom) return custom.msg.replace("Value error, ", "");
    if (fields.includes("status")) return "A frase do perfil pode ter até 140 caracteres.";
    if (fields.includes("interests")) return "Escolha até 10 interesses.";
    return "Confira os campos preenchidos.";
  }
  return detail.message || "Algo deu errado. Tente de novo.";
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401 && token) {
    setSession(null);
    onExpired();
    throw new Error("Sua sessão expirou. Entre de novo.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const error = new Error(errorMessage(body.detail));
    error.status = response.status;
    error.detail = body.detail;
    throw error;
  }
  return response;
}

export async function api(path, options) {
  const response = await request(path, options);
  return response.status === 204 ? null : response.json();
}

export async function apiText(path) {
  return (await request(path)).text();
}

export async function send(path, method = "POST") {
  await request(path, { method });
}

export function sendJson(path, data, method = "POST") {
  return api(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
}

export function postJson(path, data) {
  return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
}

const blobCache = new Map();

export async function blobUrl(path) {
  if (!blobCache.has(path)) {
    const loading = request(path).then((r) => r.blob()).then((b) => URL.createObjectURL(b));
    loading.catch(() => blobCache.delete(path));
    blobCache.set(path, loading);
  }
  return blobCache.get(path);
}

export async function download(path, fallbackName) {
  const response = await request(path);
  const disposition = response.headers.get("content-disposition") || "";
  const name = (disposition.match(/filename="([^"]+)"/) || [])[1] || fallbackName;
  const url = URL.createObjectURL(await response.blob());
  const link = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
