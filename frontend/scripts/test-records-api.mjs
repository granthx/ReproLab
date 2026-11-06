import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { afterEach, test } from "node:test";
import ts from "typescript";

// Load the real module without a bundler, generated files, or additional dependencies.
const source = await readFile(new URL("../app/lib/api.ts", import.meta.url), "utf8");
const { outputText, diagnostics } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
  reportDiagnostics: true,
});
assert.equal(diagnostics.filter((entry) => entry.category === ts.DiagnosticCategory.Error).length, 0);
const { API_URL, api, ApiError, recordsApi, fetchVerifiedExport, downloadReportExport } = await import(
  `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
);

const originalFetch = globalThis.fetch;
const originalDocument = Object.getOwnPropertyDescriptor(globalThis, "document");
const originalCreateURL = URL.createObjectURL;
const originalRevokeURL = URL.revokeObjectURL;
const originalCrypto = Object.getOwnPropertyDescriptor(globalThis, "crypto");
afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalDocument) Object.defineProperty(globalThis, "document", originalDocument);
  else delete globalThis.document;
  URL.createObjectURL = originalCreateURL;
  URL.revokeObjectURL = originalRevokeURL;
  if (originalCrypto) Object.defineProperty(globalThis, "crypto", originalCrypto);
  else delete globalThis.crypto;
});

const jsonResponse = (value, status = 200) => new Response(JSON.stringify(value), { status });
const iid = "investigation /?#%";
const rid = "report /?#%";
const fid = "finding /?#%";
const vid = "version /?#%";
const scoped = `/investigations/${encodeURIComponent(iid)}`;
const findingPath = `${scoped}/findings/${encodeURIComponent(fid)}`;
const reportPath = `${scoped}/reports/${encodeURIComponent(rid)}`;
const versionPath = `${reportPath}/versions/${encodeURIComponent(vid)}`;
const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
const jsonBytes = new TextEncoder().encode('\uFEFF{\r\n  "text": "μ-value"\r\n}\r\n');
const markdownBytes = new Uint8Array([...new TextEncoder().encode("# Report\r\nμ\n"), 0, 255]);
function metadata(json = jsonBytes, markdown = markdownBytes) {
  return {
    id: "export /?#%", report_version_id: vid, investigation_id: iid,
    report_content_hash: "a".repeat(64), created_at: "2026-10-19T00:00:00Z",
    json_size_bytes: json.length, markdown_size_bytes: markdown.length,
    json_sha256: sha256(json), markdown_sha256: sha256(markdown),
  };
}
const isApiError = (status, message) => (error) => {
  assert.ok(error instanceof ApiError);
  assert.ok(error instanceof Error);
  assert.equal(error.name, "ApiError");
  assert.equal(error.status, status);
  if (message) assert.match(error.message, message);
  return true;
};
const isAbortError = (error) => { assert.equal(error.name, "AbortError"); return true; };
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

test("generic api preserves JSON callers, RequestInit, all HeadersInit forms, and empty responses", async () => {
  const signal = new AbortController().signal;
  for (const headers of [{ "X-Test": "yes" }, [["X-Test", "yes"]], new Headers({ "X-Test": "yes" })]) {
    globalThis.fetch = async (url, init) => {
      assert.equal(url, `${API_URL}/existing`);
      assert.equal(init.method, "POST");
      assert.equal(init.body, '{"value":1}');
      assert.equal(init.signal, signal);
      assert.equal(init.cache, "no-store");
      assert.equal(init.headers.get("content-type"), "application/json");
      assert.equal(init.headers.get("x-test"), "yes");
      return jsonResponse({ id: "existing" });
    };
    assert.deepEqual(await api("/existing", { method: "POST", body: '{"value":1}', headers, signal }), { id: "existing" });
  }
  globalThis.fetch = async () => new Response(null, { status: 204 });
  assert.equal(await api("/empty"), null);
});

test("FastAPI validation arrays retain structured errors and produce readable field messages", async () => {
  const detail = [{ loc: ["body", "finding", "assertions", 0, "text"], msg: "Field required", type: "missing", input: {}, ctx: { expected: "text" } }];
  globalThis.fetch = async () => jsonResponse({ detail }, 422);
  await assert.rejects(api("/invalid"), (error) => {
    isApiError(422, /body.finding.assertions.0.text: Field required/)(error);
    assert.deepEqual(error.validationErrors, detail);
    return true;
  });
});

test("string details, JSON strings, plaintext errors, and missing details become ApiError", async () => {
  for (const [body, message] of [
    ['{"detail":"Hash conflict"}', /Hash conflict/], ['"Unavailable"', /Unavailable/],
    ["Plaintext failure", /Plaintext failure/], ['{"other":true}', /Request failed \(409\)/],
  ]) {
    globalThis.fetch = async () => new Response(body, { status: 409 });
    await assert.rejects(api("/error"), isApiError(409, message));
  }
});

test("network/body failures normalize to status zero while AbortError remains recognizable", async () => {
  globalThis.fetch = async () => { throw new TypeError("fetch failed"); };
  await assert.rejects(api("/offline"), isApiError(0, /connection/));
  globalThis.fetch = async () => ({ ok: true, text: async () => { throw new TypeError("stream failed"); } });
  await assert.rejects(api("/broken-body"), isApiError(0));
  const abort = new DOMException("Cancelled", "AbortError");
  globalThis.fetch = async () => { throw abort; };
  await assert.rejects(api("/aborted"), (error) => { assert.equal(error, abort); return true; });
  const controller = new AbortController();
  controller.abort("custom reason");
  globalThis.fetch = async () => assert.fail("Pre-aborted requests must not fetch");
  await assert.rejects(api("/aborted", { signal: controller.signal }), isAbortError);
});

test("every recordsApi method uses its exact encoded scope, method, body, and read signal", async () => {
  const attribution = { recorder_label: "Manual recorder", entry_method: "manual_entry" };
  const finding = { record_kind: "limitation", title: "Source limitation", assertions: [], evidence_links: [], limitations: [] };
  const version = { report_kind: "analysis_record", title: "Analysis", scope_claim_ids: [], finding_links: [], limitations: [], unresolved_questions: [] };
  const findingCreate = { attribution, finding };
  const findingRevision = { ...findingCreate, parent_version_id: "parent" };
  const reportCreate = { attribution, version };
  const reportRevision = { ...reportCreate, parent_version_id: "parent" };
  const review = { attribution, expected_content_hash: "b".repeat(64), outcome: "abstained", notes: "Unresolved", citations_checked: false, limitations_checked: true, execution_wording_checked: true };
  const transition = { attribution, notes: "Manual action", report_version_id: vid };
  const signal = new AbortController().signal;
  const findingVersion = `${findingPath}/versions/${encodeURIComponent(vid)}`;
  const cases = [
    [() => recordsApi.capabilities(signal), "/capabilities"],
    [() => recordsApi.scientists(signal), "/scientists"],
    [() => recordsApi.findings(iid, signal), `${scoped}/findings`],
    [() => recordsApi.finding(iid, fid, signal), findingPath],
    [() => recordsApi.findingVersion(iid, fid, vid, signal), findingVersion],
    [() => recordsApi.createFinding(iid, findingCreate), `${scoped}/findings`, findingCreate],
    [() => recordsApi.createFindingVersion(iid, fid, findingRevision), `${findingPath}/versions`, findingRevision],
    [() => recordsApi.findingReviews(iid, fid, vid, signal), `${findingVersion}/reviews`],
    [() => recordsApi.createFindingReview(iid, fid, vid, review), `${findingVersion}/reviews`, review],
    [() => recordsApi.reports(iid, signal), `${scoped}/reports`],
    [() => recordsApi.report(iid, rid, signal), reportPath],
    [() => recordsApi.reportVersion(iid, rid, vid, signal), versionPath],
    [() => recordsApi.createReport(iid, reportCreate), `${scoped}/reports`, reportCreate],
    [() => recordsApi.createReportVersion(iid, rid, reportRevision), `${reportPath}/versions`, reportRevision],
    [() => recordsApi.reportEvents(iid, rid, signal), `${reportPath}/events`],
    [() => recordsApi.publishReport(iid, rid, transition), `${reportPath}/publish`, transition],
    [() => recordsApi.withdrawReport(iid, rid, transition), `${reportPath}/withdraw`, transition],
    [() => recordsApi.exports(iid, rid, vid, signal), `${versionPath}/exports`],
    [() => recordsApi.createExport(iid, rid, vid), `${versionPath}/exports`, null],
  ];
  for (const [call, path, payload] of cases) {
    globalThis.fetch = async (url, init) => {
      assert.equal(url, `${API_URL}${path}`);
      assert.equal(init.cache, "no-store");
      if (payload === undefined) {
        assert.equal(init.method ?? "GET", "GET");
        assert.equal(init.signal, signal);
        assert.equal(init.body, undefined);
      } else {
        assert.equal(init.method, "POST");
        assert.equal(init.body, payload === null ? undefined : JSON.stringify(payload));
      }
      return jsonResponse({ returned: path });
    };
    assert.deepEqual(await call(), { returned: path });
  }
});

test("JSON/Markdown verification preserves exact bytes and uses metadata without custom headers", async () => {
  const reportExport = metadata();
  const signal = new AbortController().signal;
  for (const [format, bytes] of [["json", jsonBytes], ["markdown", markdownBytes]]) {
    globalThis.fetch = async (url, init) => {
      assert.equal(url, `${API_URL}${versionPath}/exports/${encodeURIComponent(reportExport.id)}/${format}`);
      assert.equal(init.signal, signal);
      return new Response(bytes); // No Content-Length, SHA, or Content-Disposition headers.
    };
    const blob = await fetchVerifiedExport(iid, rid, reportExport, format, signal);
    assert.deepEqual(new Uint8Array(await blob.arrayBuffer()), bytes);
    assert.equal(blob.type, format === "json" ? "application/json" : "text/markdown");
  }
});

test("HTTP failures are checked before touching binary bodies", async () => {
  globalThis.fetch = async () => ({
    ok: false, status: 404, text: async () => '{"detail":"Export not found"}',
    get body() { assert.fail("Must not read a failed response as an export"); },
    blob() { assert.fail("Must not create a blob from a failed response"); },
  });
  await assert.rejects(fetchVerifiedExport(iid, rid, metadata(), "json"), isApiError(404, /Export not found/));
});

test("invalid sizes, hashes, scopes, and formats are rejected before fetching", async () => {
  globalThis.fetch = async () => assert.fail("Invalid metadata must not fetch");
  for (const size of [-1, 0.5, NaN, Infinity, 2_097_153]) {
    await assert.rejects(fetchVerifiedExport(iid, rid, { ...metadata(), json_size_bytes: size }, "json"), isApiError(0, /byte length/));
  }
  await assert.rejects(fetchVerifiedExport(iid, rid, { ...metadata(), json_sha256: "bad" }, "json"), isApiError(0, /SHA-256/));
  await assert.rejects(fetchVerifiedExport("other", rid, metadata(), "json"), isApiError(0, /another investigation/));
  await assert.rejects(fetchVerifiedExport(iid, rid, metadata(), "html"), isApiError(0, /format/));
});

test("length and SHA-256 mismatches are rejected even with misleading response headers", async () => {
  const reportExport = metadata();
  for (const bytes of [jsonBytes.slice(0, -1), new Uint8Array(jsonBytes.length), new Uint8Array(jsonBytes.length + 1)]) {
    globalThis.fetch = async () => new Response(bytes, { headers: {
      "Content-Length": String(reportExport.json_size_bytes), "X-Content-SHA256": reportExport.json_sha256,
    } });
    await assert.rejects(fetchVerifiedExport(iid, rid, reportExport, "json"), isApiError(200, /byte length|SHA-256/));
  }
});

test("2 MiB is inclusive and overlong streams are cancelled without buffering the rest", async () => {
  const bytes = new Uint8Array(2_097_152).fill(65);
  globalThis.fetch = async () => new Response(bytes);
  assert.equal((await fetchVerifiedExport(iid, rid, metadata(bytes), "json")).size, 2_097_152);
  let cancelled = false;
  globalThis.fetch = async () => new Response(new ReadableStream({
    start(controller) { controller.enqueue(bytes); controller.enqueue(new Uint8Array([66])); },
    cancel() { cancelled = true; },
  }));
  await assert.rejects(fetchVerifiedExport(iid, rid, metadata(bytes), "json"), isApiError(200, /2 MiB/));
  assert.equal(cancelled, true);
});

function mockDownloads() {
  const calls = { blobs: [], revoked: [], downloads: [], removed: 0 };
  URL.createObjectURL = (blob) => { calls.blobs.push(blob); return "blob:verified-export"; };
  URL.revokeObjectURL = (url) => { calls.revoked.push(url); };
  Object.defineProperty(globalThis, "document", { configurable: true, value: {
    createElement(tag) {
      assert.equal(tag, "a");
      return {
        href: "", download: "",
        click() { calls.downloads.push({ href: this.href, filename: this.download }); },
        remove() { calls.removed += 1; },
      };
    },
    body: { appendChild() {} },
  } });
  return calls;
}

test("download creates and revokes a verified blob URL with a safe attachment filename", async () => {
  const calls = mockDownloads();
  for (const [format, bytes, extension] of [["json", jsonBytes, "json"], ["markdown", markdownBytes, "md"]]) {
    globalThis.fetch = async () => new Response(bytes, { headers: { "Content-Disposition": 'attachment; filename="../../unsafe.html"' } });
    await downloadReportExport(iid, rid, metadata(), format);
    const { filename, href } = calls.downloads.at(-1);
    assert.equal(href, "blob:verified-export");
    assert.match(filename, new RegExp(`^report-[a-zA-Z0-9_-]+\\.${extension}$`));
    assert.deepEqual(new Uint8Array(await calls.blobs.at(-1).arrayBuffer()), bytes);
    await tick();
  }
  assert.equal(calls.removed, 2);
  assert.deepEqual(calls.revoked, ["blob:verified-export", "blob:verified-export"]);
});

test("failed verification never creates a download", async () => {
  const calls = mockDownloads();
  globalThis.fetch = async () => new Response(new Uint8Array(jsonBytes.length));
  await assert.rejects(downloadReportExport(iid, rid, metadata(), "json"), isApiError(200, /SHA-256/));
  assert.equal(calls.blobs.length, 0);
  assert.equal(calls.downloads.length, 0);
});

test("abort during streaming cancels the reader and never creates a download", async () => {
  const calls = mockDownloads();
  const controller = new AbortController();
  let cancelled = false;
  globalThis.fetch = async () => new Response(new ReadableStream({ cancel() { cancelled = true; } }));
  const pending = downloadReportExport(iid, rid, metadata(), "json", controller.signal);
  await tick();
  controller.abort();
  await assert.rejects(pending, isAbortError);
  assert.equal(cancelled, true);
  assert.equal(calls.blobs.length, 0);
  assert.equal(calls.downloads.length, 0);
});

test("abort during WebCrypto verification prevents download after hashing resolves", async () => {
  const calls = mockDownloads();
  const controller = new AbortController();
  const subtle = globalThis.crypto.subtle;
  Object.defineProperty(globalThis, "crypto", { configurable: true, value: { subtle: {
    async digest(algorithm, bytes) {
      assert.equal(algorithm, "SHA-256");
      controller.abort();
      return subtle.digest(algorithm, bytes);
    },
  } } });
  globalThis.fetch = async () => new Response(jsonBytes);
  await assert.rejects(downloadReportExport(iid, rid, metadata(), "json", controller.signal), isAbortError);
  assert.equal(calls.blobs.length, 0);
  assert.equal(calls.downloads.length, 0);
});

test("an abort just before click still revokes any created object URL", async () => {
  const calls = mockDownloads();
  const controller = new AbortController();
  URL.createObjectURL = () => { controller.abort(); return "blob:cancelled"; };
  globalThis.fetch = async () => new Response(jsonBytes);
  await assert.rejects(downloadReportExport(iid, rid, metadata(), "json", controller.signal), isAbortError);
  await tick();
  assert.equal(calls.downloads.length, 0);
  assert.deepEqual(calls.revoked, ["blob:cancelled"]);
});
