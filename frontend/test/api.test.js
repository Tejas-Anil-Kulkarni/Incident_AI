import assert from "node:assert/strict";
import test from "node:test";

import { api, ApiError } from "../src/api.js";

test("GET helpers target the FastAPI read routes", async (context) => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return Response.json({ ok: true });
  };
  context.after(() => { globalThis.fetch = originalFetch; });

  await api.incidents(27);
  await api.feedbackHistory("incident/with space");
  await api.memory();
  await api.memoryOrigins();
  await api.outcomes();

  assert.deepEqual(calls.map((call) => call.url), [
    "/incidents?limit=27",
    "/incidents/incident%2Fwith%20space/feedback",
    "/stats/memory",
    "/stats/memory/origins",
    "/stats/outcomes",
  ]);
});

test("write helpers preserve the backend's JSON contracts", async (context) => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return Response.json({ accepted: true });
  };
  context.after(() => { globalThis.fetch = originalFetch; });

  await api.analyze("incident-1");
  await api.feedback("incident-1", { verified_cause: "confirmed", outcome: "resolved" });
  await api.replay(["incident-1", "incident-2"]);
  await api.reflect("Which fixes failed?", true);

  assert.equal(calls[0].url, "/incidents/incident-1/analyze?innovation_enabled=true");
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[1].url, "/incidents/incident-1/feedback");
  assert.deepEqual(JSON.parse(calls[1].options.body), { verified_cause: "confirmed", outcome: "resolved" });
  assert.equal(calls[2].url, "/innovation/replay");
  assert.deepEqual(JSON.parse(calls[2].options.body), { incident_ids: ["incident-1", "incident-2"] });
  assert.equal(calls[3].url, "/innovation/insights");
  assert.deepEqual(JSON.parse(calls[3].options.body), { question: "Which fixes failed?", refresh: true });
});

test("API errors retain the backend message and status", async (context) => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => Response.json({ detail: "Incident not found." }, { status: 404 });
  context.after(() => { globalThis.fetch = originalFetch; });

  await assert.rejects(api.incidents(), (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 404);
    assert.equal(error.message, "Incident not found.");
    return true;
  });
});
