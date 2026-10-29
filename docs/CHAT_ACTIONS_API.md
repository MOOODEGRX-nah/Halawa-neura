# Chat actions and project entry points (0.4.1)

All routes require the existing app token and same-origin policy, including reads.
Only newly submitted user text is sent here. Assistant output, restored history,
project/preview content and model-proposed tools are never dispatched automatically.
The OpenAI-compatible completion endpoint retains its text/inference contract.

`POST /chat/dispatch` accepts exactly:

```json
{"text":"هل يمكنك ان تفتح لي موقع youtube","request_id":"r_<13-digit UTC milliseconds>_<32 lowercase hex UUID>","active_project_id":null}
```

The backend resolves supported intent, checks actual capability availability,
validates arguments, grants the one specifically requested action and invokes the
existing skill registry/desktop adapter. No model is used for known actions.
`kind` is `chat` (continue ordinary inference), `action` (real `result.status` and
message), `clarification` (server-bound choices), `project` (existing durable
project/job), `metadata` (active-project index), or `pending` (same execution).
Desktop errors remain structured results; they never fall back to model prose.

`POST /chat/choose` accepts only `request_id` and opaque `choice_id`. No skill
arguments can be substituted; the selected target is stored server-side. A second
choice for an already selected request conflicts. Choices render inside chat.

`GET /chat/requests/{request_id}` restores the truthful durable result/snapshot
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
