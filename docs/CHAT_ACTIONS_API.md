# Chat actions and project entry points (0.4.2)

All routes require the existing app token and same-origin policy, including reads.
Only newly submitted user text is sent here. Assistant output, restored history,
project/preview content and model-proposed tools are never dispatched automatically.
The OpenAI-compatible completion endpoint retains its text/inference contract.

`POST /chat/dispatch` accepts exactly:

```json
{"text":"هل يمكنك ان تفتح لي موقع youtube","request_id":"r_<13-digit UTC milliseconds>_<32 lowercase hex UUID>","session_id":"s_<UUID hex>","active_project_id":null,"workspace_dirty":false}
```

The backend resolves supported intent, checks actual capability availability,
validates arguments, grants the one specifically requested action and invokes the
existing skill registry/desktop adapter. No model is used for known actions.
`kind` is `chat` (continue ordinary inference), `action` (real `result.status` and
message), `clarification` (server-bound choices), `project` (existing durable
project/job), `metadata` (active-project index), or `pending` (same execution).
Desktop errors remain structured results; they never fall back to model prose.

`POST /chat/choose` accepts `request_id`, opaque `choice_id`, and the originating `session_id`. No skill
arguments can be substituted; the selected target is stored server-side. A second
choice for an already selected request conflicts. Choices render inside chat.

`GET /chat/requests/{request_id}?session_id=...` restores the truthful durable result/snapshot
without executing. Retrying a POST with the same ID and fingerprint is also safe;
changing its text/context conflicts. A running request returns pending. Interrupted
desktop execution becomes unknown rather than being repeated after restart.
Exact execution across a process crash cannot be guaranteed; uncertain results ask
the user to check the desktop before making a new explicit request.

IDs must be fresh within 24 hours (at most 120 seconds ahead). Results are retained
48 hours; expired IDs cannot initiate execution after eviction. At most 4096 recent
records are retained. One-time/revocable skill grants and the bounded action history
remain separate from this retry ledger. Text hashes are stored for the action
fingerprint; search queries are not copied into its execution result.

Manual `/skills/authorize` remains compatible. New manual `/skills/execute` adds
the same `request_id`; it calls the same capability/validation/permission/execution
path as chat. Legacy execution without an ID retains the old grant behavior.
Disabled skills are enforced in the registry for both authorization and execution.
The client cannot submit `source`, skill names, arguments or grants to chat dispatch.

Project creation uses ProjectJobs/Invoice/NeuraLoop, with the same events, queue,
model lock, cancellation, validation, revision guards, metadata and isolated preview.
The UI opens the returned project/job without submitting another create request.

## Application target context and short project edits (0.4.5)

`session_id` is an optional additive field for older API clients. The current UI
always sends its conversation UUID. Requests/choices/snapshots with a recorded
session binding reject a different session; a session ID is context scope, not a
replacement for API authentication. Manual UI execution also supplies session_id.

Arabic/English Discord and Brave aliases resolve only against validated installed
desktop IDs and available localized names. Zero matches return an unavailable
result; multiple relevant matches alone become choices. No fuzzy executable
construction, installation, or unrelated first-page catalog fallback is used.

A user knowledge question can return `kind: knowledge` without inference or launch.
The backend stores at most eight trusted target IDs per session, 128 sessions and
five minutes of validity. Explicit follow-ups such as `هذا هوا افتحه` use only
that session's still-installed targets. Assistant prose, restored messages,
negation, quotations and code cannot establish permission or launch an action.
New topics clear/replace context. Legacy clients omitting session_id do not gain
implicit follow-up context.

`برمج لي موقع للcv` enters project creation before ordinary chat inference. For a
clean active project, `غيّر لون الخلفية إلى الأزرق` returns `kind: project` plus
`operation: edit`, the same project ID, a new job and actual selected source paths.
Dirty/saving editors do not silently discard changes or create another project.
Named-project navigation remains reviewable through `kind: workspace`.

Handled actions/errors/knowledge never continue into generic completion. The
completion endpoint prepends a bounded server capability description while
preserving client messages; a textual model response is never an execution result.

## Saved workspace routing (0.4.2)

Explicit requests such as `عدل هذا المشروع` and `افتح مشروع السيرة الذاتية` return `kind: workspace`, `project_id`, `display_name`, `edit_request` and `message`. They read the existing project without creating another job or executing a desktop action. The UI opens that workspace, preserves its active editor and prepares an edit request for source review. Ambiguous projects use the same server-bound opaque choices. Ordinary explanations stay chat. No existing skill/project endpoints were removed.
