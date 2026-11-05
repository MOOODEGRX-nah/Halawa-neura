# Workspace API v1 — additive contract

All project/job/file/skill GET and mutation operations require X-Neura-Token and the application origin. IDs are opaque. Requests reject extra fields. Errors retain `{error:{message,type}}`; project conflicts use HTTP 409. Limits: 48 files, 300,000 bytes/file, 2,000,000 bytes/project, 1,000,000 bytes generated text.

## Projects

- POST /projects: existing synchronous request remains valid. With background=true: user_request, requirements, title?, project_type=auto|static_web|python|other, project_id?, expected_revision?, context_files=[], plan=false, max_tokens. Returns 202 `{project,job}` immediately. An existing project needs its revision and actual relevant source paths. No implicit source edits from a summary.
- GET /projects → `{projects:[metadata]}`; no model invocation.
- GET /projects/{id} → metadata + bounded derived summary + source_freshness.
- Catalog/event reads that skip hashing return `source_freshness: null` and a
  `not_checked` summary label; they never certify source freshness. The individual
  project endpoint hashes bounded source files even when size and mtime match.
- GET /projects/{id}/file?path=relative → content, sha256, project_revision, source_freshness.
- PUT /projects/{id}/file: path, content, expected_revision, expected_sha256 → updated metadata. 409 requires review/refresh; no silent overwrite.
- POST /projects/{id}/reindex: expected_revision → explicitly adopt statically valid external edits; keep previous snapshot.
- POST /projects/{id}/question: question → deterministic metadata answer, or source_required. No mandatory model pass.
- POST /projects/{id}/context: paths → bounded actual files and current hashes; refuses stale metadata until review.
- GET /projects/{id}/export → bounded zip of current files; excludes internal data.
- POST /projects/{id}/preview → revision-scoped capability URL, project/revision, isolated origin, restrictions.
- POST /projects/{id}/open-folder → controlled desktop action for that project only.

## Jobs

- GET /project-jobs/{id} → durable job status + ordered event cursor + draft files.
- POST /project-jobs/{id}/cancel → cancellation_requested=true. Status becomes cancelled only after native generation has ended and released its lock.
- GET /project-jobs/{id}/events?after=N, or Last-Event-ID → UTF-8 SSE. Event IDs are ordered integers; reconnect never creates work. Snapshot is available if earlier events were pruned.

Envelope: `{job_id,project_id,seq,type,revision,data}`. Types: job_started, stage_changed, file_started, file_delta, file_saved, validation_result, job_completed, job_failed, job_cancelled. States: queued, planning, generating, validating, completed, failed, cancelled. file_delta is actual model output, not a timing simulation; incomplete drafts are distinct from committed files. Bound event retention with a durable snapshot.

Interrupted nonterminal jobs become failed/interrupted on restart; their drafts persist. Failed/cancelled jobs do not advance the committed revision.

## Desktop skills

- GET /skills: existing tools plus explicit desktop skill schemas/capabilities.
- POST /skills/authorize: name,args,remember=false → scoped permission ID, issued only in response to explicit UI action.
- POST /skills/execute: name,args,permission_id → validated structured result.
- GET /skills/history → bounded Neura-only action history.
- POST /skills/revoke: permission_id → revoke grant.

Desktop content and model output cannot authorize actions. No shell, messages, installation, arbitrary executables, or dynamically imported skills.

## Additive job invoice/result contract (0.4.4, N041)

`ProjectRequest` accepts optional `constraints` (up to 28 user constraints; server safety constraints are appended). The shared TaskInvoice carries `task_id`, `project_id`, original `user_request`, requirements, constraints, `expected_files`, `required_python_symbols`, selected source context and target model. Both mandatory planning and generation receive the same identity/requirements.

`GET /project-jobs/{id}` adds `invoice`, `invoice_provenance`, `stage_results`, `saved_files`, and `validation`. Stage results record actual stage transitions, model/finish reasons where returned, and validated plan output. File references contain project ID, path, committed revision and SHA256 and do not change after later edits. Recorded invoices may contain selected actual source for an edit; this remains an authenticated private endpoint, not preview data or unrestricted logs.

Old records have `invoice: null`, `invoice_provenance: unavailable_legacy`, and empty unrecorded stage/file result lists. Their saved projects remain available. The additive `job_contracts` table does not replace the existing projects/jobs/catalog. No model grade bypasses deterministic file validation.

## Filename hints and current source facts (0.4.5)

`ProjectRequest.filename_hints` and `TaskInvoice.filename_hints` are optional
advisory relative paths, distinct from mandatory `required_files/expected_files`.
All are validated as safe paths. Named fences remain preferred. A legacy
language-only fence is accepted only when one filename is established by the
invoice, a completed HTML file's actual local asset references, or advisory hints
(for an edit, actual selected context files). Multiple candidates, duplicate
names, unsafe references or unresolved names fail. No `file_1` guessing occurs.
`file_started.data.filename_origin` and the generation result's
`filename_resolutions` record whether the name came from model/invoice/reference/hint.
Reference, syntax, required-file and revision checks still decide commit eligibility.

Freshness reads hash every bounded project file even if size/mtime are unchanged;
metadata answers refuse stale sources. A second inventory check detects changes
during the scan. Saves retain revision and content-hash guards.

Metadata adds bounded `features`, `features_provenance: static_source_observations`
and `limitations`. These describe saved source facts, not claimed behavioral tests.
Existing valid catalogs are enriched additively from current source without
changing source revision; stale catalogs require explicit reindex first. Summary
maintenance and basic metadata questions do not require a model pass.

## Mandatory planning policy — 2026-11-05

Every project creation and model-generated edit requires a validated EXPERT
steps/files plan before CODER, in both legacy and streaming orchestrators.
The compatibility `plan:false` input is normalized, and runtime execution does
not branch on that flag. A failed/truncated plan stops coding and retains the
last good revision. Planner output is capped at768 tokens within the shared
cancellation/deadline; coder and candidate-repair budgets remain bounded.
Grammar schema, semantic file validation, preservation, isolated preview,
revision guards and receipts still apply. Manual saves and ordinary explanations
do not invoke planning. This supersedes the prior optional planning policy.

`Message.project_job_id` is optional UI correlation stored with vault messages.
It never authorizes a job/tool and is removed from messages sent to inference.
Cards fetch authenticated durable job snapshots after terminal events, returning
to chat, reconnect and session restoration. Matching legacy request/start-card
pairs can be correlated with the session's latest durable job; unmatched text is
not attributed to arbitrary jobs.
