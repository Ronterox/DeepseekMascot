// Thin client for tools/editor_server.py. Every call resolves to the parsed JSON body or throws an
// Error carrying `.errors` (validation messages from the server) and `.status`.

async function call(method, path, body) {
  const init = { method, headers: {} };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const res = await fetch(path, init);
  let data = null;
  try {
    data = await res.json();
  } catch {
    // non-JSON error page
  }
  if (!res.ok) {
    const err = new Error(data?.error || `${method} ${path}: HTTP ${res.status}`);
    err.errors = data?.errors || [];
    err.status = res.status;
    throw err;
  }
  return data;
}

const moodPath = (name) => `/api/moods/${encodeURIComponent(name)}`;

export const api = {
  state: () => call("GET", "/api/state"),
  save: (name, mood) => call("PUT", moodPath(name), mood),
  remove: (name) => call("DELETE", moodPath(name)),
  rename: (from, to, mood) => call("POST", `${moodPath(from)}/rename`, { to, mood }),
  build: () => call("POST", "/api/build", {}),
  async svg() {
    const res = await fetch(`/assets/whale-chan.svg?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`could not load assets/whale-chan.svg (HTTP ${res.status})`);
    return res.text();
  },
};
