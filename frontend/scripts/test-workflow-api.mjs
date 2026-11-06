import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { afterEach, test } from "node:test";
import ts from "typescript";

// Load the real api.ts module without a bundler (same approach as test-records-api.mjs).
const source = await readFile(new URL("../app/lib/api.ts", import.meta.url), "utf8");
const { outputText, diagnostics } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
  reportDiagnostics: true,
});
assert.equal(diagnostics.filter((entry) => entry.category === ts.DiagnosticCategory.Error).length, 0);
const { API_URL, ApiError, governanceApi, workflowApi } = await import(
  `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
);

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

const iid = "investigation /?#%";
const rid = "run /?#%";
const aid = "assignment /?#%";
const scoped = `/investigations/${encodeURIComponent(iid)}`;
const runScoped = `${scoped}/workflow-runs/${encodeURIComponent(rid)}`;
const attribution = { recorder_label: "Workflow operator" };

function capture(responseBody = [], status = 200) {
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url: String(url), method: init.method ?? "GET", body: init.body === undefined ? undefined : JSON.parse(init.body) });
    return new Response(JSON.stringify(responseBody), { status });
  };
  return calls;
}

test("workflow read endpoints are investigation scoped and encoded", async () => {
  const calls = capture();
  await workflowApi.runs(iid);
  await workflowApi.run(iid, rid);
  await workflowApi.checkpoints(iid, rid);
  await workflowApi.events(iid, rid);
  await workflowApi.modelCalls(iid, rid);
  assert.deepEqual(calls.map((call) => [call.method, call.url]), [
    ["GET", `${API_URL}${scoped}/workflow-runs`],
    ["GET", `${API_URL}${runScoped}`],
    ["GET", `${API_URL}${runScoped}/checkpoints`],
    ["GET", `${API_URL}${runScoped}/events`],
    ["GET", `${API_URL}${runScoped}/model-calls`],
  ]);
});

test("workflow control endpoints post exactly the typed payloads", async () => {
  const calls = capture({ id: rid });
  await workflowApi.start(iid, { provider_mode: "source_grounded", idempotency_key: null, attribution });
  await workflowApi.decideGate(iid, rid, { decision: "approve", expected_lifecycle_version: 2, notes: "Reviewed.", attribution });
  await workflowApi.resume(iid, rid, { expected_lifecycle_version: 3, notes: null, attribution });
  await workflowApi.cancel(iid, rid, { expected_lifecycle_version: 4, reason: "Superseded.", attribution });
  assert.deepEqual(calls.map((call) => [call.method, call.url]), [
    ["POST", `${API_URL}${scoped}/workflow-runs`],
    ["POST", `${API_URL}${runScoped}/review-gate`],
    ["POST", `${API_URL}${runScoped}/resume`],
    ["POST", `${API_URL}${runScoped}/cancel`],
  ]);
  assert.deepEqual(calls[1].body, { decision: "approve", expected_lifecycle_version: 2, notes: "Reviewed.", attribution });
  assert.equal(calls[3].body.reason, "Superseded.");
});

test("governance read endpoints are investigation scoped and encoded", async () => {
  const calls = capture();
  await governanceApi.assignments(iid);
  await governanceApi.assignmentEvents(iid, aid);
  await governanceApi.assignmentDeliverables(iid, aid);
  await governanceApi.reviewDelegations(iid);
  assert.deepEqual(calls.map((call) => call.url), [
    `${API_URL}${scoped}/assignments`,
    `${API_URL}${scoped}/assignments/${encodeURIComponent(aid)}/events`,
    `${API_URL}${scoped}/assignments/${encodeURIComponent(aid)}/deliverables`,
    `${API_URL}${scoped}/review-delegations`,
  ]);
});

test("stale lifecycle conflicts surface as ApiError with the server detail", async () => {
  capture({ detail: "Workflow lifecycle_version is stale; reload before submitting gate decision." }, 409);
  await assert.rejects(
    workflowApi.decideGate(iid, rid, { decision: "reject", expected_lifecycle_version: 1, notes: "No.", attribution }),
    (error) => error instanceof ApiError && error.status === 409 && error.message.includes("stale"),
  );
});

