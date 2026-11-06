# ReproLab — Evidence-First AI Research Workbench

ReproLab is an evidence-first AI research workbench designed for professors, principal investigators, peer reviewers, and computational researchers. It provides an isolated, deterministic execution sandbox, a 14-node LangGraph multi-agent deliberation engine across 12 constitutional scientist personas, a bilingual (English / Hindi) dual-lens interface, and statistical verification anchored by Wilson 95% score confidence intervals.

---

## 1. System Architecture & High-Level Design

```text
       +--------------------------------------------------------------+
       |               ReproLab Workbench (Next.js 16)               |
       |  - Plain Words Lens (Non-technical clarity, zero data loss)  |
       |  - Full Record Lens (Mathematical and statistical telemetry) |
       |  - Bilingual Engine (Native Hindi & English Localization)    |
       |  - Interactive SSE Terminal & Live Log Streaming              |
       +------------------------------+-------------------------------+
                                      |
                                      v
       +--------------------------------------------------------------+
       |                  ReproLab Backend (FastAPI)                  |
       |  - Cryptographic Content-Addressed Vault (SHA-256)           |
       |  - Document Parser & Canonical Protocol Freezer              |
       |  - Deep Readiness & Diagnostics Probes (/health/*)           |
       |  - OpenTelemetry GenAI Semantic Conventions & /metrics       |
       +--------------+-------------------------------+---------------+
                      |                               |
                      v                               v
       +------------------------------+  +----------------------------+
       |  14-Node LangGraph Engine   |  | Isolated Execution Sandbox |
       |  - 12 Constitutional Personas|  | - AST Security Checker     |
       |  - Shannon Entropy Consensus |  | - Prohibited Module Traps  |
       |  - Cryptographic PI Review   |  | - Offline Credential-Free  |
       +------------------------------+  +--------------+-------------+
                                                        |
                                                        v
                                         +----------------------------+
                                         |   Statistical Scorer       |
                                         |   - Wilson 95% Score CI    |
                                         |   - "The Rail" SVG Gauge   |
                                         |   - Categorical Verdicts   |
                                         +----------------------------+
```

### 12 Constitutional Scientist Personas
All 12 personas are strictly governed by formal constitutions defined in `backend/reprolab/scientists/constitutions.yaml`:
1. `principal_investigator`: Research synthesis, scope alignment, and Stage 7 cryptographic gate execution.
2. `statistical_auditor`: Wilson score intervals, sample-size validity, power calculations, and p-value checks.
3. `experimental_protocolist`: Hardware environment specifications, random seed matrices, and dependency locks.
4. `data_provenance_officer`: Content-addressed storage hashes, dataset splits, and lineage verification.
5. `computational_reproducibility_specialist`: Container environments, determinism, and software stack replication.
6. `peer_review_skeptic`: Counterfactual challenges, ablation inquiry, and baseline skepticism.
7. `domain_methodologist`: Scientific domain rigor, metric selection, and mathematical bounds.
8. `code_quality_and_security_auditor`: AST inspection, credential discovery defense, and memory safety.
9. `literature_contextualizer`: Citation alignment, prior art baseline cross-examination, and reproducibility history.
10. `meta_science_analyst`: Publication bias detection, vibration of effects, and multi-analyst robustness.
11. `ethics_and_biosafety_reviewer`: Dual-use evaluation, licensing compliance, and data privacy safeguards.
12. `plain_language_and_multilingual_bridge`: Bilingual translation fidelity and dual-lens clarity without data loss.

---

## 2. Requirements & Product Specifications

### Core Requirements
1. **Evidence-First Ingestion**: Academic papers (PDFs) are validated via magic-byte checking (`%PDF-`), hashed using SHA-256, and stored in a content-addressed vault with directory traversal defense.
2. **Canonical Protocol Freezing**: Computational protocols must be deterministically serialized to canonical JSON and locked before any execution can take place.
3. **Isolated Execution**: Scripts execute in an offline, credential-sanitized environment. Dynamic evaluation (`eval`, `exec`), subprocess invocation, socket communication, and unsafe deserialization (`pickle`, `shelve`) are prohibited.
4. **Wilson 95% Score Confidence Intervals**: Empirical replication results are evaluated using analytical Wilson score intervals ($Z = 1.95996$):
   $$\text{Center} = \frac{p + \frac{z^2}{2n}}{1 + \frac{z^2}{n}}, \quad \text{Margin} = \frac{z \sqrt{\frac{p(1-p)}{n} + \frac{z^2}{4n^2}}}{1 + \frac{z^2}{n}}$$
5. **Strict Categorical Classification**:
   - `VERIFIED_REPRODUCED`: Replicated mean falls within claimed 95% CI and exceeds baseline.
   - `PARTIALLY_REPRODUCED`: Beats baseline but deviates slightly outside the claimed interval.
   - `FAILED_TO_REPRODUCE`: Falls below baseline or fails empirical replication.
   - `EXECUTION_FAILED`: Runtime crash or non-zero exit code (strictly distinguished from empirical disconfirmation).
6. **Bilingual Dual-Lens UI**: Next.js 16 frontend supporting Plain Words (intuitive) and Full Record (deep telemetry) views in both English and Hindi with 0 ghost controls.

---

## 3. Threat Model & Security Hardening

ReproLab enforces defense-in-depth against the **OWASP LLM Top 10 (2026)** and **Agent Security Issues (ASI01–ASI10)**.

### Mapped Threat Matrix & Neutralization Controls
- **LLM01 / ASI01 (Prompt Injection & Governance Bypass)**:
  - System prompts and untrusted inputs are strictly separated.
  - Stage 7 review gate enforces cryptographic digital signatures and reviewer attribution (`RecordAttribution`).
- **LLM02 (Insecure Output Handling)**:
  - React JSX automatically escapes HTML/XSS vectors; LaTeX output is rendered without shell escapes (`\write18` neutral).
- **LLM06 (Sensitive Information Disclosure)**:
  - Secret scanning pipeline ensures zero active credentials are committed.
  - OpenTelemetry collector features automatic regex PII scrubbers for emails, bearer tokens, and API keys.
- **ASI02 / ASI05 (Tool Abuse & Sandbox Escape)**:
  - `ASTSecurityChecker` statically scans Python code before execution, blocking `os`, `subprocess`, `socket`, `sys`, `pickle`, `_pickle`, `shelve`, `marshal`, and `dbm`.
- **ASI05 (Storage & Vault Tampering)**:
  - ContentAddressedVault detects in-place file modifications and directory traversal attacks (`../../`), enforcing read-only permissions and raising `VaultIntegrityError`.

Adversarial Red-Team Suite (`evals/red_team/adversarial_vectors.json`): 25 attack vectors audited with **0.0% Attack Success Rate (ASR)**.

---

## 4. Observability & Telemetry Plan

### Telemetry Architecture
- **OpenTelemetry GenAI Conventions**: Instrumented spans track token counts, execution latency, model versions, and cost attribution ($0.10/1M prompt tokens, $0.40/1M completion tokens on Gemini 2.5 Flash).
- **Prometheus Metrics (`/metrics`)**: Exposes request throughput, latency percentiles (p50, p95, p99), AST violation counters, sandbox queue depths, and token expenditures.
- **Multi-Window Multi-Burn-Rate SLO Alerting**:
  - P1 Fast Burn: 14.4x burn rate over 1h (2% error budget consumed).
  - P2 Slow Burn: 3.0x burn rate over 6h (5% error budget consumed).
  - Security Violations: Immediate alert on AST prohibited module detection.
  - FinOps Anomaly: Alert on token spend exceeding $0.25 per investigation.
- **Grafana Production Dashboards (`deploy/observability/dashboards/`)**:
  1. `SRE Reliability & Golden Signals` (Traffic, errors, latency, saturation)
  2. `LLM Quality & Evaluation Hub` (Wilson CI spreads, persona convergence)
  3. `Agent & Tool Runtime Performance` (LangGraph dispatch, node execution)
  4. `Security, AST Sandbox & Threat Auditing` (Neutralized injection vectors)
  5. `FinOps, Token Unit Economics & Budgeting` (Cost per task, token burn)
  6. `Academic & Business Outcomes` (Replication rates, PI gate throughput)

---

## 5. Directory Structure

```text
ReproLab/
├── backend/                  # FastAPI Application & Scientific Engines
│   ├── reprolab/
│   │   ├── api/routes/       # Endpoints: investigations, health, execution, papers, scientists
│   │   ├── core/             # Configuration, OTel telemetry, security, tokens
│   │   ├── db/               # PostgreSQL async session & SQLAlchemy models
│   │   ├── evaluation/       # Tri-partite scientific evaluation engine
│   │   ├── execution/        # AST security checker, sandbox runner, job queue
│   │   ├── orchestrator/     # 14-node LangGraph deliberation engine
│   │   ├── schemas/          # Pydantic v2 hardened contracts (extra="forbid")
│   │   ├── scoring/          # Wilson 95% CI statistical engine & "The Rail" SVG gauge
│   │   ├── scientists/       # 12 Constitutional personas and YAML constitutions
│   │   └── storage/          # SHA-256 Content-Addressed Vault
│   └── tests/                # Automated pytest test suites
├── deploy/                   # Production Deployment & Observability Configs
│   └── observability/        # Prometheus alert rules, OTel collector config, 6 Grafana dashboards
├── evals/                    # Evaluation Golden Set & Red-Team Vectors
│   ├── golden_set/           # Smoke benchmark test cases
│   ├── red_team/             # 25 OWASP/ASI formalized adversarial vectors
│   ├── benchmark_report.json # Golden benchmark evaluation results
│   └── harness.py            # Evaluation benchmark runner
├── frontend/                 # Next.js 16 Web Application
│   ├── app/                  # App router: investigations, papers, scientists, status
│   └── scripts/              # Ghost-control audit (0 ghost controls on 430 audited)
├── scripts/                  # Production rollback drills & maintenance scripts
├── storage/                  # Content-addressed artifact & paper vault
├── docker-compose.yml        # Multi-service container orchestration
├── pytest.ini                # Pytest configuration
└── README.md                 # Single consolidated master documentation

