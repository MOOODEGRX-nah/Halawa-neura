# NEURA AI — SELF-CONTAINED REMAINING IMPLEMENTATION PLAN

Use the instructions below as the readable plan.
Do not block implementation on locating the previously mentioned attachment.

This plan covers 80 open tracking items across P1–P10.
Some items are partially implemented or require verification first.
Do not assume every listed feature is absent.

Start with P0, then deliver P1–P4 as the first integrated milestone.
Preserve the remaining phases as the subsequent implementation backlog.

## Mandatory user decisions

- Remove the permanent Projects and Skills tabs and their redundant forms.
- Keep conversation as the main entry point.
- Execute supported website, file, and application actions directly from chat.
- Keep skill permissions and availability management inside Settings.
- Access saved projects through one small folder button and a drawer.
- Open the coding workspace when creating or editing a project.
- Default layout: code LEFT, preview RIGHT.
- Provide pane swapping and full-page preview.
- Save each project separately with meaningful filenames.
- Maintain compact project metadata to reduce unnecessary source context.
- Preserve the existing Arabic visual identity and one-click desktop startup.

## Engineering constraints

1. Inspect the actual repository and its instructions before editing.
2. Reuse the existing backend, model manager, project service, and dispatcher.
3. Preserve sessions, projects, user settings, streaming, and cancellation.
4. Keep local inference and the existing single-large-model resource policy.
5. Do not silently introduce cloud inference.
6. Do not expose unrestricted shell execution.
7. Validate tool arguments and enforce permissions in the backend.
8. Generated content cannot authorize device actions.
9. Do not automatically execute generated programs or install their dependencies.
10. Store user data outside installed application files.
11. Preserve unsaved edits and the last good project revision.
12. Do not claim desktop, model, installer, or updater tests that were not run.
13. Do not publish, push, or perform administrative updates merely as a side
    effect of finishing implementation.
14. User-facing terminal examples must support fish or explicitly invoke the
    intended interpreter.

# P0 — Inspect and establish the baseline

Locate the actual:

- Chat API/controller.
- Router and skill dispatcher.
- Desktop application adapters.
- Project/Invoice implementation.
- Generation worker and event transport.
- Frontend renderer and Qt wrapper.
- Project/session storage.
- Launcher, installer, updater, and tests.

Identify the branch, commit, source checkout, and installed package being tested.

Run relevant existing checks and record actual results.

For partially implemented items, identify the missing behavior.
For uncertain items, reproduce the issue or demonstrate that it already passes.
Keep working implementations instead of rebuilding them.

Do not use historical test counts or old performance estimates as evidence for
the current version.

Continue implementation after the baseline report.

# P1 — Simplify navigation and connect chat actions

## N061 — Remove Projects and Skills tabs

Remove both permanent navigation entries and their redundant manual forms.
Preserve the backend functionality, saved projects, and coding workspace.
Repair references to removed views.

Acceptance:
Both tabs disappear without broken navigation or lost functionality.

## N062 — Repair composer actions

Group attachment, saved-session, and project-folder actions into one compact
toolbar aligned with the composer. Preserve existing IDs and handlers.
Rebuild bundled CSS when necessary.

Acceptance:
No full-window horizontal action bars remain. All actions still work.

## N063 — Correct Markdown rendering

Support paragraphs, lists, emphasis, links, inline code, and fenced code.
Escape code and sanitize rendered content. Handle unfinished streaming markup.
Never execute generated HTML in the privileged chat view.

Acceptance:
Completed Markdown renders correctly and malicious content remains harmless.

## N064 — Finish responsive RTL layout and accessibility

Fix clipped controls and inappropriate minimum widths.
Keep Arabic controls RTL and source code LTR.
Support keyboard navigation, visible focus, and narrow-window Code/Preview tabs.

Acceptance:
The supported desktop window sizes have usable, unclipped controls.

## N065 — Unify the skill registry

Register supported skills with validated input/output schemas, availability,
permissions, and appropriate timeouts.
Use one dispatcher for chat and any necessary settings controls.

Acceptance:
Unknown, disabled, or malformed skill calls fail clearly and safely.

## N066 — Execute skills from Arabic conversation

Connect clear action requests to the dispatcher before a generic conversational
reply can conceal the requested action.

Support:
- "افتح يوتيوب"
- "افتح لي موقع يوتيوب"
- "هل يمكنك ان تفتح لي موقع youtube"
- "افتح Brave"
- "افتح مجلد مشروع السيرة الذاتية"

Distinguish action requests from explanation, negation, quotations, and code.
Ask only when the intended action or target is ambiguous.

Acceptance:
The exact YouTube request invokes the real website skill.
"لا تفتح يوتيوب" and quoted examples cause no launch.

## N067 — Open websites in Brave

Validate HTTP/HTTPS destinations and common configured website names.
Launch Brave through a trusted adapter using structured arguments.
Report missing Brave and real launch failures.

Acceptance:
A real supported desktop test opens YouTube.
Do not claim the remote page loaded merely because launch succeeded.

## N068 — Separate browser search from retrieved research

Implement encoded search-result URLs for Brave.
Keep server-side source retrieval, when available, as a distinct capability.

Acceptance:
Arabic searches open correct results.
Opening a results page is not reported as reading or verifying it.

## N069 — Search YouTube

Encode the user's query and open the corresponding YouTube results URL through
the website adapter.

Acceptance:
Arabic and mixed-language queries produce the correct search URL.
Empty or invalid requests receive useful errors.

## N070 — Open approved files and folders

Resolve selected files, project IDs, or matches inside approved roots.
Ask about ambiguous matches and validate paths.
Separate document viewing from executable launching.

Acceptance:
An approved target opens.
Missing files, ambiguity, traversal, and executable bypass attempts are handled.

## N071 — Open installed applications

Use trusted installed desktop entries or a reviewed application catalog.
Handle desktop entry semantics correctly.
Do not construct arbitrary shell commands from model text.

Acceptance:
A supported installed application launches.
Unknown apps and injected arguments cannot trigger arbitrary commands.

## N072 — Record recent applications

Persist a bounded history of applications launched through Neura.
Label that scope honestly.
Resolve the intended list before an ambiguous batch launch.

Acceptance:
The history survives restart and contains actual Neura launches.
Do not claim access to the complete KDE or Brave history.

## N073 — Permissions and duplicate-action prevention

Enforce scoped permissions server-side with revocation and expiry where used.
Clear supported low-risk user requests should not trigger repetitive dialogs.
Deduplicate retried or reconnected requests.

Acceptance:
Retries do not launch twice.
Forged input and model-generated text cannot grant permissions.

## N098 — Protect local APIs and resist injected instructions

Inspect authentication, Host/Origin handling, state-changing requests, and native
bridges. Protect privileged operations server-side.
Treat project files and retrieved pages as data.

Acceptance:
A preview or third-party page cannot launch tools or change private app data.
Injection fixtures cannot bypass permissions.

# P2 — Complete durable project generation

## N041 — Complete the Task Invoice contract

Extend the current project/job contract with project ID, original request,
constraints, expected files, stage results, and validation.
Do not create a duplicate orchestrator.

Acceptance:
One request creates one job and returns saved project/file references.

## N042 — Use planning only when useful

Distinguish explanations, edits, simple projects, and complex projects.
Avoid a mandatory four-model cycle for every task.
Preserve explicit requirements between stages.

Acceptance:
Explanations create no project.
Simple work avoids unnecessary model swaps.

## N043 — Preserve filenames and references

Prefer structured filename/content generation.
Handle fragmented fences, duplicate filenames, incomplete output, and conflicts
with planned names when legacy extraction remains.

Acceptance:
index.html, style.css, and script.js are saved with matching references.
Do not silently substitute broken file_1 names.

## N044 — Validate output deterministically

Reject zero files, unsafe paths, missing required files, duplicate names,
oversized output, and invalid Python/JSON syntax.
Use static parsing without running generated code.

Acceptance:
Invalid output cannot be reported as successful.
Static validation is clearly distinguished from behavioral testing.

## N045 — Correct reviewer and repair logic

Reproduce reported review bugs first.
Approval must satisfy deterministic checks as well as the explicit verdict.
Bound repair attempts.

Acceptance:
Grade B with NEEDS_FIX is not accepted.
Zero-file output never passes.
Failed repairs end honestly.

## N049 — Create projects directly from chat

Reuse the chat request and project context to create a project and open its
workspace. Do not make the user retype the request in another form.

Acceptance:
The Arabic CV-site request creates one project and opens its workspace.

## N050 — Store separate named projects

Use stable project IDs and separate display names.
Store files under writable user data with safe path validation, atomic commits,
and recoverable revisions.

Acceptance:
Duplicate titles do not collide.
Restart preserves projects.
Failure cannot overwrite the last good revision or escape the project root.

## N052 — Stream actual project/file events

Connect the real worker to ordered job/file events.
Include project/job identity, sequence, state, and relevant file/revision.
Bound queues and support UTF-8 fragmentation and snapshot recovery.

Acceptance:
Visible code corresponds to actual generation.
Reconnects do not create duplicate jobs.
Cancellation preserves resource safety.

# P3 — Deliver the coding workspace

## N051 — Code left, preview right

Reuse any existing workspace.
Provide project status, file navigation, code, preview, and return-to-chat.
Set physical pane positions explicitly despite RTL.

Acceptance:
A website opens with code LEFT and preview RIGHT.
Non-web projects show files and useful instructions.

## N053 — Swap panes

Implement pane swapping and persist the preference.
Keep selected files and unsaved editor state.

Acceptance:
Swapping and restarting preserve the selected arrangement without losing edits.

## N054 — Safe editing and saving

Add dirty indicators, atomic saves, revision/hash guards, external-change
detection, and unsaved-change handling.

Acceptance:
Conflicting edits produce a reviewable conflict instead of silent overwrite.

## N055 — Static web preview

Support actual HTML/CSS/JavaScript and eligible assets.
Refresh completed or valid saved snapshots rather than every token.
Identify projects requiring a build or backend.

Acceptance:
A small interactive static website renders correctly.
Unsupported React/TSX/server projects are not falsely labelled ready.

## N056 — Full-page preview

Enable the corner button when the supported entry point and required files
are ready. Open the same project in a dedicated isolated preview view.

Acceptance:
Embedded and full-page views show the same project/revision.
Full-page mode does not bypass isolation.

## N057 — Preview isolation

Separate generated content from the privileged app origin and native bridge.
Apply appropriate sandbox/CSP, navigation/request controls, authorization, and
asset confinement.

Exclude secrets, internal metadata, unrelated files/projects, and unrelated
local services. Restrict external resources by default.

Acceptance:
Generated JavaScript cannot access privileged actions, WebChannel methods,
secrets, or other projects. Test browser and Qt paths separately.

## N060 — Saved-project drawer

Use one small folder button near the composer.
List saved projects and reopen them.
Resolve ambiguous project references from chat.

Acceptance:
Projects reopen after restart without restoring the removed permanent tabs.
View switching preserves active work.

# P4 — Compact project metadata

## N058 — Create the compact project index

Maintain one canonical metadata representation and derive a readable summary.
Include purpose, actual languages, files/roles, entry point, preview capability,
validation provenance, and revisions.

Use actual saved files for factual fields.
Avoid an extra model pass solely for routine metadata.

Acceptance:
Basic language/purpose questions use metadata.
Keep the model-facing summary bounded, roughly 600–1,000 tokens when suitable.

## N059 — Maintain freshness and selective source access

Refresh metadata after committed changes.
Detect external changes using file statistics/watchers and relevant hashes.
Answer deterministic metadata questions directly.
Read relevant actual files before behavioral answers or code edits.

Acceptance:
Stale metadata is detected.
Editing never relies on a summary alone.
Context savings are measured using representative queries.

# FIRST DELIVERY GATE

Deliver P1–P4 as one usable workflow:

- No permanent Projects or Skills tabs.
- Chat can execute supported desktop actions.
- Chat can create a named project.
- Real generated code appears in the workspace.
- Files are saved correctly.
- Editing, preview, pane swapping, and reopening work.
- Compact metadata stays current.

This is the first milestone, not completion of all 80 items.

# P5 — Runtime, monitoring, and quality

## N002 — Import and shared-state boundaries

Inspect the import graph and remove confirmed cycles.
Keep shared state dependency-safe and optional modules from breaking startup.

Acceptance:
Supported entry points import successfully without confirmed circular imports.

## N006 — Empty replies, reasoning tags, repetition, and limits

Reproduce each issue independently.
Inspect actual templates, roles, stop conditions, finish reasons, token-budget
propagation, and output filtering.

Acceptance:
Representative Arabic, English, and coding requests return valid output or an
explicit error. Filtering cannot erase valid final answers.

## N008 — Verify Qwen2.5-Coder availability

Inspect configured files, incomplete downloads, metadata, compatibility, and
provenance information. Test actual loading/generation when available.

Acceptance:
Missing or incomplete models remain unavailable.
Any claimed Coder trial contains real output.

## N011 — Reduce unnecessary swaps

Measure cold load, warm reuse, queueing, and generation separately.
Reuse resident weights shared by tiers and avoid unnecessary unloading.

Acceptance:
Repeated requests to the same weights avoid redundant loads.
Any improvement is measured.

## N013 — Timeouts and failure handling

Audit network, tool, and generation deadlines.
Bound retries and distinguish client timeout from native work still running.

Acceptance:
Stalled operations do not hang forever or release native resources prematurely.

## N015 — Real system readings

Use available OS/vendor sensors with nonblocking sampling.
Keep missing readings unknown and estimates explicitly labelled.

Acceptance:
CPU/RAM/VRAM/temperature displays match supported samples without fabricated
fallback values.

## N016 — Safe Gaming mode

Connect configured game detection to residency and job scheduling.
Define treatment of pending and running inference before freeing memory.

Acceptance:
Mode changes cannot unload an active model and recovery is tested.

## N017 — Profiling and tracing

Track queue/load/generation/tool phases by request/job ID.
Use actual token counters and measured timings. Redact and rotate logs.

Acceptance:
Requests are traceable without invented token speeds or sensitive logging.

## N018 — Safe hardware defaults

Account for free memory, context/KV cache, runtime buffers, and selected device.
Provide conservative defaults and graceful OOM behavior.

Acceptance:
Limited-memory configurations remain usable or fail clearly.

## N022 — Startup performance

Measure UI startup, backend liveness, model readiness, and first generation
separately. Warm only necessary resources.

Acceptance:
Readiness labels match reality and cold/warm timings are recorded.

## N031 — Cloud-folder warning

Inspect existing diagnostics and detect relevant synced-folder risks without
blocking ordinary paths based on loose name matching.

Acceptance:
Controlled fixtures warn appropriately without false-positive blocking.

## N032 — Scoped lint and style cleanup

Run actual repository lint/import/compile checks.
Fix relevant issues without renaming working public contracts.

Acceptance:
Required checks pass or remaining baseline failures are documented.

## N097 — Repeatable evaluations

Create versioned Arabic chat, coding, skills, failure, and injection fixtures.
Separate deterministic tests from model, desktop, and performance trials.

Acceptance:
Results record environment, input, expectation, and actual outcome.

## N108 — Live status transport

Reuse working polling/SSE/WebSocket infrastructure.
Bound producers and handle disconnects/backpressure.

Acceptance:
Monitoring stays responsive during generation without duplicate workers.

# P6 — Local voice, vision, and visual states

## N085 — Local speech recognition

Inspect the existing Whisper adapter and pair the actual engine with compatible
weights. Validate audio input and supported decoding.

Acceptance:
A real Arabic recording is transcribed offline.
Missing or incompatible weights produce a clear error.

## N086 — VAD and hallucination filters

Integrate supported local voice detection and engine-specific no-speech/
confidence signals. Tune against actual fixtures.

Acceptance:
Silence, noise, short speech, and end-of-speech behavior are tested.

## N087 — Piper speech output

Verify the runtime and compatible voice/configuration.
Generate and play real audio with interruption support.

Acceptance:
A supported Arabic-capable voice produces audible local output.

## N088 — Optional Kokoro suitability

Inspect runtime, trusted loading, model format, and actual language support.
Integrate only if suitable; otherwise keep its limitation explicit.

Acceptance:
Readiness requires real supported audio output, not merely existing weights.

## N089 — Arabic voice evaluation

Compare available voices using the same Arabic phrases, names, and numbers.
Save samples and measure startup/synthesis latency.

Acceptance:
Voice selection has reproducible evidence and documented limitations.

## N090 — Sentence streaming and isolated audio worker

Queue complete sentences from real generation.
Handle Arabic punctuation and code/Markdown.
Bound queues, isolate audio failures, and cancel stale playback.

Acceptance:
Stopping a reply clears queued speech.
An audio crash does not crash chat.
First-audio latency is measured.

## N091 — Dictation

Use a supported KDE/Wayland input, clipboard, or portal workflow.
Provide visible controls and a deliberate destination/insert action.

Acceptance:
Text reaches the intended supported application without covert input capture
or disabling desktop security.

## N092 — Mute and activation

Implement visible recording state, reliable mute, and configurable activation.
Passive wake behavior must be explicitly enabled and supported.

Acceptance:
Mute actually stops capture and false-trigger behavior is tested.

## N093 — Current vision integration

Verify model/projector compatibility, message schema, installed runtime support,
and resource coordination.

Acceptance:
An actual uploaded image is interpreted through the packaged application.
Text-only fallback is not claimed as vision success.

## N094 — Mascot/Orb states

Preserve the current design and connect visual states to real idle/listening/
generating/speaking/error events.

Acceptance:
Visual state follows actual activity and recovers after cancellation/errors.

## N095 — Audio animation and HUD

Use real playback/audio levels and real sensor samples.
Bound refresh rates and support reduced motion.

Acceptance:
Animation stops with playback and monitoring values agree with samples.

# P7 — Persistent personal memory and retrieval

## N034 — Preference/directive vault

Store approved facts with provenance and update/delete rules.
Inject a bounded relevant profile rather than full history.

Acceptance:
Approved preferences persist across sessions and deletion updates retrieval
and cached profile content.

## N035 — Memory extraction

Support explicit remember requests first.
Keep inferred facts as reviewable suggestions with sources.

Acceptance:
Approved facts are stored once and rejected suggestions are not injected.

## N036 — Long-conversation summaries

Summarize when context pressure justifies it.
Preserve requirements and keep original history recoverable.

Acceptance:
Long-session fixtures retain important constraints within the context budget.

## N037 — Memory management and transfer

Provide view/edit/delete and validated import/export with conflict handling.

Acceptance:
Round-trip transfer works and deleted facts do not return through stale indexes.

## N038 — Local RAG

Index approved sources into versioned chunks with stable source IDs.
Retrieve a bounded relevant set and invalidate stale/deleted content.

Acceptance:
Answers cite the correct allowed source passages and acknowledge missing or
irrelevant evidence.

## N039 — Reviewable preference learning

Propose persistent preference rules with review and rollback.
Keep application permissions and core policies outside learned text.

Acceptance:
Accepted/rejected suggestions behave correctly without autonomous policy changes.

## N040 — Personas and prompt caching

Separate persona style from permissions.
Use supported caching and invalidate it after model/template/profile changes.

Acceptance:
Personas change style without expanding privileges.
Any cache benefit is measured.

## N109 — Vault Harvest

Inspect the endpoint for placeholders.
Generate a real article from selected saved notes and retain source references.

Acceptance:
The result is actually generated and stored.
Missing notes or unavailable generation return truthful errors.

# P8 — Reminders and continuation

## N080 — Persistent reminders

Implement create/list/edit/complete/delete with stable IDs, UTC due times,
IANA timezones, and optional project/URL references.

Acceptance:
Reminders persist across restart, resolve ambiguous times, and avoid duplicates.
Default this user's timezone preference to Asia/Riyadh.

## N081 — Notification delivery

Define due-time scheduling and missed-reminder behavior.
Closed-app delivery requires an intentional supported per-user service.

Acceptance:
Due-time, restart, missed schedules, and duplicate delivery are tested.
Do not claim closed-app delivery without a real service test.

## N082 — Video continuation

Store validated video URLs and optional user-provided timestamps.
Construct correct resume links without claiming account watch-history access.

Acceptance:
The stored video and timestamp reopen correctly where supported.

# P9 — Additional skills and bounded agent workflows

## N074 — Calculator, time, and weather

Use a restricted arithmetic parser and real timezone-aware time.
Weather needs a chosen source, location, freshness, and timeout behavior.

Acceptance:
Arithmetic/time fixtures pass and weather is sourced, dated, or explicitly
unavailable.

## N075 — YouTube summaries

Retrieve available transcript/caption text through a supported integration.
Summarize retrieved content with a source URL.

Acceptance:
Missing transcripts are acknowledged.
Search results alone are not presented as video understanding.

## N076 — File organization

Preview proposed moves inside permitted roots.
Handle collisions and keep a reversible journal or recoverable staging.

Acceptance:
Approved moves, cancellation, and recovery work without touching unrelated files.

## N077 — Code explanation

Reuse normal chat plus approved relevant-file reading when sufficient.
Add a wrapper only if it provides a meaningful workflow.

Acceptance:
Selected real source is explained without running it or creating an unwanted
project. Verified reuse may satisfy this item.

## N078 — Deep research

Use bounded search/fetch/retrieve stages with source IDs, safe URL fetching,
deduplication, and supporting citations.

Acceptance:
Reports cite actual retrieved evidence and respect request/step budgets.

## N079 — Optional MCP adapter

Integrate a deliberately configured trusted server through existing validation,
permissions, timeouts, and result handling.

Acceptance:
One selected server works and unauthorized/disconnected calls fail safely.
Do not auto-install servers suggested by generated or retrieved content.

## N047 — Bounded multi-step actions

Represent plan/actions/results as typed state with step/retry limits,
cancellation, progress summaries, and controlled fallback.

Acceptance:
A supported multi-step task completes and loop/failure cases terminate.

## N048 — Sequential researcher/writer/reviewer

Reuse the inference scheduler for logical roles and shared artifact contracts.
Do not require three resident models.

Acceptance:
Outputs are traceable to sources and requirements.
Added calls/latency and resource behavior are measured.

## N046 — Isolated testing of generated programs

Offer an explicit bounded sandbox-test action.
Restrict host filesystem, secrets, devices, network, memory, CPU, and duration.

Acceptance:
Selected tests run only within the documented boundary.
If isolation is unavailable, report not tested rather than running on the host.

# P10 — Distribution and channel verification

Apply packaging checks to each candidate delivery.
Do not wait until every later feature exists.

## N025 — Installed package and installer

Identify the actual tested package/version.
Test appropriate clean/disposable installation, retry/cache behavior,
launcher/assets, and user-data preservation.

Acceptance:
Installed-app evidence is distinguished from source-checkout tests.

## N026 — Updater verification

Audit release identity, version/architecture/size/hash checks, root-owned
staging, helper scope, and failures.

Acceptance:
Tampered/wrong packages are rejected.
Actual authorized update testing preserves data.
Untested administrative paths remain explicitly open.

## N030 — Documentation and Doctor

Update documentation to match real feature availability and UI paths.
Count only diagnostics that actually run and give actionable results.

Acceptance:
Docs match the shipped app.
No invented diagnostic totals or success claims.

## N103 — Telegram/backend integration

Replace fixed-port assumptions with protected local discovery/configuration.
Verify backend identity and stale state.
Keep Telegram as an API client rather than a second model process.

Acceptance:
Discovery/failure contract tests pass.
Real channel tests are reported separately, without unsolicited live messages.

# DEFERRED EXTENSIONS — NOT PART OF THE FIRST DELIVERY

Preserve these separately:

- N009: Optional larger model after availability and memory benchmarking.
- N027: AUR publication when explicitly selected and account access exists.
- N028: Windows distribution with native Windows verification.
- N083: Opt-in unfinished-work/browser tracking with retention controls.
- N084: Calendar integration with scoped provider authorization.
- N096: Optional cinematic boot, display modes, and portrait layout.
- N100: Docker/public-server deployment only for a real deployment requirement.
- N101: Self-authored skills with draft/review/test/activation/rollback controls.
- N102: Advanced KDE window/mouse/keyboard control through supported interfaces.
- N105: Alternative inference server only after a measured compatibility study.

Do not silently activate these extensions or claim them complete.

# SUPERSEDED ITEMS

- N106: Do not add another pywebview wrapper solely to duplicate Qt.
- N107: Do not perform historical Windows F: maintenance as a Neura feature.

# TRACKING AND DELIVERY

Maintain current evidence by N ID:

- Current status.
- Changed or verified code paths.
- Acceptance command/scenario.
- Actual outcome.
- Environment: fake adapter, local model, browser, desktop, or packaged app.
- Remaining limitation and next action.

Preserve historical reports rather than replacing them with unsupported success.

At each milestone:
1. Implement the smallest complete behavior.
2. Run relevant checks.
3. Verify the actual UI where available.
4. Record evidence.
5. Continue with independent authorized work when another item is blocked.

Do not stop after producing another plan or adding buttons.

Return milestone reports in Arabic with:
- Verified/completed N IDs.
- What the user can now request through chat.
- Actual tests performed.
- Project/data locations.
- Blocked, deferred, and untested items.

Do not claim the whole plan is complete after delivering only P1–P4.
