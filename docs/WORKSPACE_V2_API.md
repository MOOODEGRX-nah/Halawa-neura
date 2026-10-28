# Workspace API v1 — additive contract

All project/job/file/skill GET and mutation operations require X-Neura-Token and the application origin. IDs are opaque. Requests reject extra fields. Errors retain `{error:{message,type}}`; project conflicts use HTTP 409. Limits: 48 files, 300,000 bytes/file, 2,000,000 bytes/project, 1,000,000 bytes generated text.

## Projects

- POST /projects: existing synchronous request remains valid. With background=true: user_request, requirements, title?, project_type=auto|static_web|python|other, project_id?, expected_revision?, context_files=[], plan=false, max_tokens. Returns 202 `{project,job}` immediately. An existing project needs its revision and actual relevant source paths. No implicit source edits from a summary.
- GET /projects → `{projects:[metadata]}`; no model invocation.
- GET /projects/{id} → metadata + bounded derived summary + source_freshness.
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
