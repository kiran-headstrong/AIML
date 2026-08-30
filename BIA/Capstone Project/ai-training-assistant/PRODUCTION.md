# Production Readiness — MNC Deployment (1000+ Employees)

This document lists what a Generative-AI onboarding assistant needs to run in
production for a large enterprise, and maps each item to its current status in
this project: **✅ built**, **🟡 demo stand-in** (production-shaped but must be
swapped for real infrastructure), or **⬜ not yet**.

The goal is honesty: the app demonstrates the full shape of a production system
while staying runnable locally at zero cost.

---

## 1. Authentication & Access

| Capability | Status | Notes |
|-----------|--------|-------|
| Login required to use the app | ✅ built | Gradio native auth gate; no chat access without sign-in |
| Password hashing | ✅ built | bcrypt (`src/auth.py`), never plaintext |
| Role-based access control | ✅ built | `employee` / `admin`; admin unlocks the observability portal |
| Per-user session isolation | ✅ built | Each user gets an isolated `TrainingAssistant` + history |
| Enterprise SSO (OIDC / SAML) | 🟡 demo stand-in | Local bcrypt users stand in for Okta / Azure AD / Google Workspace. Replace `auth_fn` with an OIDC/SAML flow |
| Signed, expiring session tokens | ⬜ not yet | Native Gradio session in demo; use JWT/opaque tokens + refresh in prod |
| Secrets in a vault | 🟡 demo stand-in | `.env` locally; move to AWS Secrets Manager / Azure Key Vault / Vault |
| Secret rotation | ⬜ not yet | Rotate the Groq API key and any credentials on a schedule |

## 2. Scale & Reliability

| Capability | Status | Notes |
|-----------|--------|-------|
| Concurrent multi-user support | ✅ built | Per-user assistants; stateless request handling |
| Per-user rate limiting | ✅ built | Sliding-window limiter (`RATE_LIMIT_*` env vars) |
| Scalable vector database | 🟡 demo stand-in | Local persistent ChromaDB; use Chroma server mode, Pinecone, Weaviate, or pgvector for scale |
| Horizontal scaling / load balancing | ⬜ not yet | Run multiple stateless app replicas behind a load balancer |
| Shared session/state store | ⬜ not yet | Move per-user state to Redis so any replica can serve any user |
| Caching | ⬜ not yet | Cache embeddings and frequent answers |
| Cost caps / quotas | 🟡 demo stand-in | Rate limiting is in place; add per-user token/cost budgets |
| Health checks & graceful degradation | ⬜ not yet | Add `/health`, readiness probes, and fallback behavior |

## 3. Observability & Ops (Admin Portal)

| Capability | Status | Notes |
|-----------|--------|-------|
| Structured tracing (spans, latency) | ✅ built | `src/observability.py`, `trace_span` |
| JSONL event log | ✅ built | `data/logs/events.jsonl` |
| Live metrics snapshot | ✅ built | Latency p50/p95, tokens, routes, confidence, error/fallback rates |
| Category-filter metrics | ✅ built | Filter rate, unfiltered-retry rate, per-scope breakdown |
| Admin dashboard with charts | ✅ built | Latency-over-time, routes, confidence, filter-scope plots (admin-only) |
| Downloadable CSV reports | ✅ built | Per-query report + metrics-summary report |
| Audit logging (who asked what) | ✅ built | Every query attributed to its username in the event log |
| Alerting | ⬜ not yet | Wire thresholds to PagerDuty / Opsgenie / email |
| Log/metric shipping | ⬜ not yet | Export to OpenTelemetry / Prometheus / Loki / Grafana |
| Answer feedback (thumbs up/down) | ✅ built | 👍/👎 on answers feeds a satisfaction metric + admin feedback chart |

## 4. Content & Governance

| Capability | Status | Notes |
|-----------|--------|-------|
| Multi-format ingestion | ✅ built | `.txt .md .pdf .docx .pptx`, recursive |
| Category-scoped retrieval | ✅ built | Metadata filter by routing category with safe unfiltered retry |
| Safe refusals / guardrails | ✅ built | Grounded system prompt; refuses out-of-scope + redirects to HR/IT |
| Admin document upload + re-index (no redeploy) | ✅ built | Admin portal "Document Management" uploads files and rebuilds the index live |
| Content versioning & approval | ⬜ not yet | Track document versions and an approval workflow |

## 5. Security Hardening

| Capability | Status | Notes |
|-----------|--------|-------|
| Input validation | ✅ built | Validation in tools + router; treat model args as untrusted |
| PII redaction | ⬜ not yet | Redact PII before it enters prompts/logs |
| Encryption in transit | 🟡 demo stand-in | Terminate TLS at a reverse proxy / load balancer in prod |
| Encryption at rest | ⬜ not yet | Encrypt the vector DB, logs, and user store volumes |
| Prompt-injection defenses | 🟡 demo stand-in | Grounding + refusals help; add dedicated injection filtering |

## 6. Compliance

| Capability | Status | Notes |
|-----------|--------|-------|
| Audit trail | ✅ built | Per-user query log supports audit |
| Data retention policy | ⬜ not yet | Define retention + purge for logs and conversations |
| Right to be forgotten (GDPR) | ⬜ not yet | Support deleting a user's data on request |
| Consent & DPIA | ⬜ not yet | Capture consent; complete a Data Protection Impact Assessment |
| Data residency | ⬜ not yet | Pin data + model region to meet residency requirements |

---

## What to swap first for a real deployment

1. **Auth** — replace local bcrypt users with corporate **SSO (OIDC/SAML)**;
   issue signed, expiring session tokens.
2. **Secrets** — move `GROQ_API_KEY` and credentials from `.env` into a
   **vault**; enable rotation.
3. **Vector DB** — move from local ChromaDB to a **scalable** deployment
   (Chroma server, Pinecone, Weaviate, or pgvector).
4. **State** — externalize per-user state to **Redis** and run multiple
   stateless replicas behind a **load balancer**.
5. **Ops** — ship logs/metrics to **OpenTelemetry/Prometheus/Grafana** and add
   **alerting**, health checks, and cost budgets.
6. **Governance** — add **PII redaction** and retention/GDPR workflows. The
   admin **document-management** UI exists; extend it with content
   **versioning and an approval workflow**.
