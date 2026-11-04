# Accuracy/execution repair handoff — 2026-11-04

Base HEAD: `233f7dc74fcb3152b3f41f000af619075718f9f4`, branch `fix/accuracy-context-preservation`, source VERSION 0.4.7. Installed 0.4.7-1 was not replaced. Use the supplied diff/hash manifest for working-tree identity. Per-run `identity.json` fingerprints runtime files at startup; earlier development runs are not evidence for identical source.

## Data and control flow

`web/chat.js` → authenticated `src/backend/chat_api.py` → `ChatDispatcher.dispatch` → `ProjectConversation` session association/proposal → existing `ProjectJobs` queue/coordinator → `InvoiceOrchestrator.stream_files` → candidate parsing/static/preservation/browser checks → `ProjectStore.commit` → durable receipt → `web/workspace.js` and chat status restore.

`IntentDecision` records validated dispatch outcomes; it is not a universal model-produced authorization object. Clear requests use deterministic paths; bounded semantic fallback yields a proposal/clarification, cannot select arbitrary tools or another project. The coordinator remains the single model owner.

SQLite additions in the existing store: `conversation_projects` and `project_proposals`. Proposal migration adds `details` when absent. Details bind UUID/digest, source turn, request, revision/hashes, requirements, permission scope. One pending proposal/session, 300-second lifetime, transactional consume; restart suspends pending records. No automatic action replay. Existing job storage/API remains.

Authenticated context endpoints: POST `/chat/context`, GET `/chat/context/{session}`, GET `/chat/status/{session}`. UI binds only after a successful project open/create; browser-global last project is not conversational authority.

`ProjectStore.commit` accepts optional `accepted_requirements` and `execution_receipt`; receipt is committed with metadata. It clears obsolete receipts on new saves. `rebuild` regenerates preservation facts and removes previous receipts after external edits. Crash recovery can recognize a matching committed receipt rather than replaying work.

## Validation and failure scope

`edit_preservation.py`: accepted source text/control identity/reference comparison, bounded metadata orientation, full supplied source comparison. Not semantic equivalence; may conservatively reject legitimate wording changes. Historical request context over the bound fails explicitly.

`candidate_browser.py`: independent Qt process/profile, capability-only manifest preview, no native bridge, isolated inspection JS world, bounded deadline/cancellation. Measures 480/1280 widths, sampled computed text contrast and known theme action. Complex backgrounds fail for visual review. Not full accessibility/interaction certification. Generated native programs are never executed.

`contrast_repair.py`: measured safe black/white CSS repairs only when all errors are eligible contrast failures; bounded selectors/rules, no fixture-specific names. Explicit color requests suppress repair. Candidate is fully rechecked. Otherwise `repair_candidate` permits bounded exact unique replacements in candidate files only. One repair attempt; default 4096 generation budget is split3072+1024; required planning has its own768 budget. Same job deadline applies. Native schema omits maxLength expansion; Pydantic retains string limits after decoding.

Execution outcomes distinguish saved/no_change/failure, with base/result hashes, revision, changed files, preservation scope, browser scope, preview checked revision. Candidate browser success precedes commit; the UI separately records loaded revision label. This is not a network page-loaded or native desktop claim.

## Evidence and commands

Evidence root: `../../outputs/accuracy-execution-20261104` from the source checkout. `real-exact-final`, `real-preserve-gpu-05`, `real-plan-final` contain composer captures, identity, source outputs, traces, screenshots and restart evidence. All failed development runs remain. `acceptance-current.json` is a mechanical audit of recorded artifacts, not a new inference run.

Fish-compatible commands (run from source checkout):

```sh
env NEURA_DATA_DIR=/tmp/neura-contract-data NEURA_SETTINGS_DIR=/tmp/neura-contract-settings PYTHONPATH=.:/opt/neura-ai/vendor python -m pytest tests -q
python tools/check_accuracy_evidence.py ../../outputs/accuracy-execution-20261104/real-exact-final ../../outputs/accuracy-execution-20261104/real-preserve-gpu-05 ../../outputs/accuracy-execution-20261104/real-plan-final
env QT_QPA_PLATFORM=offscreen QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu PYTHONPATH=.:/opt/neura-ai/vendor python tools/qa_accuracy_composer.py --real-model --workflow exact --gpu 'AMD Radeon RX 9060 XT (RADV GFX1200)' --output /tmp/neura-new-unique-run
```

The real runner refuses a foreign backend, uses a new QA profile and refuses overwriting existing composer evidence. `--workflow preserve` and `--workflow plan` select other scenarios. Engine token/raw output and actual device trace are separate from fake contract checks. Qt Chromium rendering is software/offscreen; Vulkan inference remains enabled in the backend. Runner exceptions now write `failure.json` even if the backend dies mid-turn.

No live update/install/publication was done. Vision, native KDE, broader accessibility and administrative update acceptance remain open. Phase B web skills are not implemented in this patch. Consult the Arabic report and matrix for bounded claims.
