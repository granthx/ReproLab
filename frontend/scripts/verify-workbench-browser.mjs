/** Real Chrome + Next.js + PostgreSQL API acceptance. No mocked success responses.
 * Setup uses API-created, uniquely named synthetic records; UI writes are exercised
 * through actual DOM controls. Those audit records are retained, never deleted.
 * Requires the application API, production frontend and a Chrome CDP listener.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

const UI = process.env.WORKBENCH_UI_URL ?? "http://localhost:3000";
const API = process.env.WORKBENCH_API_URL ?? "http://127.0.0.1:8000/api/v1";
const CDP = process.env.WORKBENCH_CDP_URL ?? "http://127.0.0.1:9222";
const run = `Workbench browser ${new Date().toISOString()}`;
const results = [];
const runtimeErrors = [];
const downloads = new Map();
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let socket, contextId, sessionId, sequence = 0, fault = null;
const pending = new Map();
const evidence = { run, browser: "", ui: UI, api: API, results, records: {}, checks: {}, status: "running" };
const downloadPath = path.join(tmpdir(), "omnirush", `step3-downloads-${Date.now()}`);

function send(method, params = {}, page = true) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`CDP timed out: ${method}`)); }, 30000);
    pending.set(id, { resolve, reject, timer });
    socket.send(JSON.stringify({ id, method, params, ...(page && sessionId ? { sessionId } : {}) }));
  });
}
async function evaluate(expression) {
  const response = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  if (response.exceptionDetails) throw new Error(response.exceptionDetails.exception?.description ?? response.exceptionDetails.text);
  return response.result.value;
}
const pageCall = (fn, ...args) => evaluate(`(${fn.toString()})(...${JSON.stringify(args)})`);
async function until(check, description, timeout = 15000) {
  const start = Date.now();
  while (Date.now() - start < timeout) { if (await check()) return; await sleep(100); }
  throw new Error(`Timed out: ${description}`);
}
const waitText = (text) => until(() => pageCall((text) => document.body.innerText.includes(text), text), text);
async function check(name, action) { await action(); results.push({ name, passed: true }); console.log(`PASS ${name}`); }
async function request(endpoint, body, method = body === undefined ? "GET" : "POST") {
  const response = await fetch(`${API}${endpoint}`, { method, headers: { "Content-Type": "application/json" }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const data = await response.json();
  assert.ok(response.ok, `${method} ${endpoint}: ${response.status} ${JSON.stringify(data)}`);
  return data;
}

function installControls() {
  window.workbenchTest = {
    root(scope) {
      if (!scope) return document;
      if (scope.startsWith("heading:")) {
        const heading = [...document.querySelectorAll("h2,h3,h4,h5")].find((node) => node.textContent.trim() === scope.slice(8));
        if (!heading) throw new Error(`Heading not found: ${scope}`);
        return heading.closest("section") ?? heading.parentElement;
      }
      const root = document.querySelector(scope);
      if (!root) throw new Error(`Scope not found: ${scope}`);
      return root;
    },
    label(name, scope) {
      const labels = [...this.root(scope).querySelectorAll("label")];
      for (const label of labels) {
        const clone = label.cloneNode(true);
        clone.querySelectorAll("input,select,textarea").forEach((node) => node.remove());
        if (clone.textContent.trim().replace(/\s+/g, " ") === name) return label.control ?? document.getElementById(label.htmlFor) ?? label.querySelector("input,select,textarea");
      }
      throw new Error(`Label not found: ${name} in ${scope}`);
    },
    set(name, value, scope) {
      const control = this.label(name, scope);
      if (!control || control.disabled) throw new Error(`Control unavailable: ${name}`);
      control.focus();
      if (control.type === "checkbox") { if (control.checked !== value) control.click(); return; }
      const prototype = control instanceof HTMLSelectElement ? HTMLSelectElement.prototype : control instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(prototype, "value").set.call(control, value);
      control.dispatchEvent(new Event("input", { bubbles: true }));
      control.dispatchEvent(new Event("change", { bubbles: true }));
    },
    button(name, scope) {
      const button = [...this.root(scope).querySelectorAll("button")].find((node) => node.textContent.trim() === name);
      if (!button) throw new Error(`Button not found: ${name}`);
      return button;
    },
    click(name, scope) {
      const button = this.button(name, scope);
      if (button.disabled) throw new Error(`Button disabled: ${name}`);
      button.focus(); button.click();
    },
  };
}
const set = (name, value, scope) => pageCall((...args) => window.workbenchTest.set(...args), name, value, scope);
const click = (name, scope) => pageCall((...args) => window.workbenchTest.click(...args), name, scope);
const textIn = (text, scope) => pageCall((text, scope) => window.workbenchTest.root(scope).innerText.includes(text), text, scope);
const controlValue = (name, scope) => pageCall((name, scope) => window.workbenchTest.label(name, scope).value, name, scope);
const isDisabled = (name, scope) => pageCall((name, scope) => window.workbenchTest.button(name, scope).disabled, name, scope);
async function navigate(url) {
  await send("Page.navigate", { url });
  await until(() => pageCall(() => document.readyState === "complete"), "document loaded");
  await pageCall(installControls);
}
async function key(key, code = key, modifiers = 0) {
  const vk = key === "Escape" ? 27 : key === "Tab" ? 9 : 13;
  await send("Input.dispatchKeyEvent", { type: "keyDown", key, code, modifiers, windowsVirtualKeyCode: vk });
  await send("Input.dispatchKeyEvent", { type: "keyUp", key, code, modifiers, windowsVirtualKeyCode: vk });
}
async function interceptOnce(pattern, mode) {
  fault = { pattern, mode, handled: false };
  await send("Fetch.enable", { patterns: [{ urlPattern: pattern, requestStage: "Response" }] });
}
async function clearFault() { await send("Fetch.disable"); fault = null; }
async function paused(params) {
  if (!fault || fault.handled) { await send("Fetch.continueRequest", { requestId: params.requestId }); return; }
  fault.handled = true;
  if (fault.mode === "read-error") {
    await send("Fetch.fulfillRequest", { requestId: params.requestId, responseCode: 503, responseHeaders: [{ name: "Content-Type", value: "application/json" }, { name: "Access-Control-Allow-Origin", value: UI }], body: Buffer.from(JSON.stringify({ detail: "Controlled read-refresh failure for acceptance test" })).toString("base64") });
  } else {
    const reply = await send("Fetch.getResponseBody", { requestId: params.requestId });
    const original = Buffer.from(reply.body, reply.base64Encoded ? "base64" : "utf8");
    const modified = fault.mode === "length" ? original.subarray(1) : Buffer.from(original);
    if (fault.mode === "digest") modified[0] ^= 1;
    await send("Fetch.fulfillRequest", { requestId: params.requestId, responseCode: 200, responseHeaders: [{ name: "Content-Type", value: "application/octet-stream" }, { name: "Access-Control-Allow-Origin", value: UI }], body: modified.toString("base64") });
  }
}

async function main() {
  await mkdir(downloadPath, { recursive: true });
  const version = await (await fetch(`${CDP}/json/version`)).json(); evidence.browser = version.Browser;
  socket = new WebSocket(version.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.id) {
      const item = pending.get(message.id); if (!item) return;
      pending.delete(message.id); clearTimeout(item.timer);
      message.error ? item.reject(new Error(JSON.stringify(message.error))) : item.resolve(message.result);
    }
    if (message.method === "Runtime.exceptionThrown") runtimeErrors.push(message.params.exceptionDetails.exception?.description ?? message.params.exceptionDetails.text);
    if (message.method === "Browser.downloadWillBegin") downloads.set(message.params.guid, { ...message.params, state: "started" });
    if (message.method === "Browser.downloadProgress") downloads.set(message.params.guid, { ...downloads.get(message.params.guid), ...message.params });
    if (message.method === "Fetch.requestPaused") void paused(message.params).catch((error) => runtimeErrors.push(String(error)));
  };
  contextId = (await send("Target.createBrowserContext", { disposeOnDetach: true }, false)).browserContextId;
  const target = await send("Target.createTarget", { url: "about:blank", browserContextId: contextId }, false);
  sessionId = (await send("Target.attachToTarget", { targetId: target.targetId, flatten: true }, false)).sessionId;
  await send("Runtime.enable"); await send("Page.enable");
  await send("Browser.setDownloadBehavior", { behavior: "allowAndName", downloadPath, browserContextId: contextId, eventsEnabled: true }, false);
  const capabilities = await request("/capabilities");
  assert.equal(capabilities.reports, true);
  assert.equal(capabilities.experiment_runner, false);
  const investigation = await request("/investigations", { name: run, source_kind: "synthetic_framework_test" });
  const base = `/investigations/${investigation.id}`;
  const claim = await request(`${base}/claims`, { statement: "Synthetic source reports a framework-only percentage; no scientific experiment was run.", metric_name: "accuracy", reported_value: 0.75, metric_direction: "maximize", source_kind: "synthetic_framework_test", source_locator: "Browser verification synthetic source", published: false });
  const quote = "😀 Source reports 75% on a synthetic fixture; no uncertainty stated.";
  const source = await request(`${base}/evidence`, { claim_id: claim.id, source_url: "https://reprolab.invalid/step3-browser-fixture", source_locator: "Synthetic source, paragraph 1", quoted_text: quote });
  const finding = await request(`${base}/findings`, { attribution: { recorder_label: "API seed recorder" }, finding: { record_kind: "observation", title: "Browser-seeded synthetic observation", claim_id: claim.id, protocol_version_id: null, assertions: [{ key: "reported_result", assertion_kind: "source_reported", text: "The synthetic source reports a framework-only percentage.", grounding: "source_grounded", citation_keys: ["E1"], numbers: [{ metric_name: "accuracy", value: "0.75", unit: "proportion", citation_key: "E1", source_start: 17, source_end: 20, source_lexeme: "75%", normalization: "percent_to_fraction", context: "Source-reported accuracy; not a measured experiment result.", uncertainty_as_reported: null }], unresolved_reason: null }], evidence_links: [{ key: "E1", evidence_item_id: source.id, evidence_review_id: null, relationship: "supports", rationale: "The source quotation is the recorded basis for this observation." }], limitations: ["No experiment was run; this is a synthetic framework record."] } });
  evidence.records = { investigationId: investigation.id, claimId: claim.id, evidenceId: source.id };
  evidence.records.findingId = finding.id; evidence.records.findingVersionId = finding.versions[0].id;
  evidence.preview = `${UI}/investigations/${investigation.id}`;
  await navigate(evidence.preview);
  await waitText("No reports saved.");
  await check("Live PostgreSQL investigation, capabilities and truthful empty states", async () => {
    assert.ok(await textIn("framework test", ".detail-heading"));
    assert.ok(await textIn("not started", ".detail-heading"));
    assert.ok(await textIn("registered constitutions, not active agents", ".records-workspace"));
  });
  await waitText("Browser-seeded synthetic observation");
  await waitText("0.75");
  await check("Load persisted finding and Unicode numeric citation", async () => {
    assert.ok(await textIn("Browser-seeded synthetic observation", "heading:Findings"));
    assert.ok(await textIn("0.75", "heading:Findings"));
    assert.ok(await textIn("API seed recorder", "heading:Findings"));
  });
  await click("Open citation E1", "heading:Findings");
  await waitText("Snapshot quotation");
  await check("Open accessible citation drawer from persisted finding", async () => assert.equal(await pageCall(() => Boolean(document.querySelector("dialog[open]"))), true));
  await key("Escape");
  await until(() => pageCall(() => !document.querySelector("dialog[open]")), "citation drawer Escape close");
  await check("Escape closes citation drawer", async () => assert.equal(await pageCall(() => document.activeElement?.tagName), "BUTTON"));
  await click("Review this exact version", "heading:Findings");
  await set("Review outcome (required)", "accepted_for_inclusion", "heading:Manual review of version 1");
  await set("Human recorder label (required)", "Browser finding reviewer", "heading:Manual review of version 1");
  await set("Review notes (required)", "Checked exact citation, numeric span, limitations and execution wording.", "heading:Manual review of version 1");
  await pageCall((scope) => { const root = window.workbenchTest.root(scope); root.querySelectorAll('input[type="checkbox"]').forEach((box) => { if (!box.checked) box.click(); }); }, "heading:Manual review of version 1");
  await click("Save exact-version review", "heading:Manual review of version 1");
  await waitText("Saved accepted for inclusion review");
  await check("Record exact-hash attributed finding review", async () => assert.ok(await textIn("Browser finding reviewer", "heading:Findings")));
  await click("New report", "heading:Analysis/record reports");
  await set("Title", "Browser analysis record report", "heading:New analysis/record report");
  await set("Human recorder label (required)", "Browser report author", "heading:New analysis/record report");
  await set("Finding", finding.id, "heading:New analysis/record report");
  await until(() => pageCall((scope) => [...window.workbenchTest.root(scope).querySelectorAll("select")].some((item) => item.options.length > 1 && item.options[0].textContent === "Choose an exact version"), "heading:New analysis/record report"), "report finding history");
  await set("Saved version", evidence.records.findingVersionId, "heading:New analysis/record report");
  await click("Add selected version", "heading:New analysis/record report");
  await set("Section", "observations", "heading:New analysis/record report");
  await set("Position", "0", "heading:New analysis/record report");
  await click("Save report version", "heading:New analysis/record report");
  await waitText("Saved report version 1");
  await check("Compose and persist report from exact finding version", async () => assert.ok(await textIn("Immutable source-analysis versions", "heading:Analysis/record reports")));
  await until(async () => !(await isDisabled("Create stored JSON + Markdown pair", "heading:Stored exports for saved version 1")), "stored export action ready");
  await click("Create stored JSON + Markdown pair", "heading:Stored exports for saved version 1");
  await waitText("Stored JSON/Markdown pair");
  await check("Create immutable stored export pair", async () => assert.ok(await textIn("Verify and download JSON", "heading:Stored exports for saved version 1")));
  await click("Verify and download JSON", "heading:Stored exports for saved version 1");
  await until(() => [...downloads.values()].some((item) => item.state === "completed"), "verified JSON download completion");
  await check("Verify and download immutable JSON export", async () => assert.ok([...downloads.values()].some((item) => item.state === "completed")));
  const reportId = await pageCall(() => { const text = document.body.innerText; const match = text.match(/Report ([0-9a-f-]{36})/); return match?.[1] ?? ""; });
  evidence.records.reportId = reportId;
  await writeFile(path.join(downloadPath, "step3-browser-evidence.json"), JSON.stringify(evidence, null, 2));
  if (runtimeErrors.length) throw new Error(`Runtime exceptions: ${runtimeErrors.join("\n")}`);
  evidence.status = "passed";
  await writeFile(path.join(downloadPath, "step3-browser-evidence.json"), JSON.stringify(evidence, null, 2));
  console.log(`${results.length} live PostgreSQL browser checks passed. Evidence: ${path.join(downloadPath, "step3-browser-evidence.json")}`);
  socket?.close(); process.exit(0);
}

main().catch(async (error) => {
  evidence.status = "failed"; evidence.error = String(error); evidence.runtimeErrors = runtimeErrors;
  try { evidence.pageText = await evaluate(() => document.body.innerText.slice(-12000)); } catch { /* page may have closed */ }
  try { await writeFile(path.join(downloadPath, "step3-browser-evidence.json"), JSON.stringify(evidence, null, 2)); } catch { /* report original */ }
  console.error(error); console.error(evidence.pageText ?? ""); socket?.close(); process.exit(1);
});
