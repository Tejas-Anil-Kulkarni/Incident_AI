const apiRoot = import.meta.env?.DEV ? "/api" : "";

export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${apiRoot}${path}`, {
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
  } catch (error) {
    throw new ApiError("Cannot reach the IncidentMind API. Check that FastAPI is running.");
  }

  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError("IncidentMind returned an unreadable response.", response.status);
  }
  if (!response.ok) {
    throw new ApiError(payload?.detail || `Request failed (${response.status}).`, response.status);
  }
  return payload;
}

export const api = {
  health: () => request("/health"),
  incidents: (limit = 200) => request(`/incidents?limit=${limit}`),
  incident: (id) => request(`/incidents/${encodeURIComponent(id)}`),
  feedbackHistory: (id) => request(`/incidents/${encodeURIComponent(id)}/feedback`),
  analyze: (id) => request(`/incidents/${encodeURIComponent(id)}/analyze?innovation_enabled=true`, { method: "POST" }),
  feedback: (id, payload) => request(`/incidents/${encodeURIComponent(id)}/feedback`, { method: "POST", body: JSON.stringify(payload) }),
  memory: () => request("/stats/memory"),
  memoryOrigins: () => request("/stats/memory/origins"),
  outcomes: () => request("/stats/outcomes"),
  replay: (incidentIds) => request("/innovation/replay", { method: "POST", body: JSON.stringify({ incident_ids: incidentIds }) }),
  reflect: (question, refresh = false) => request("/innovation/insights", { method: "POST", body: JSON.stringify({ question, refresh }) }),
};
