# Interrupted capture recovery

The original recording is never repaired in place. The offline helper requires
an idle studio and a historical execution record whose exact worker PID/start
identity is no longer alive. Observation errors fail closed. It supports unified
0.2 captures marked `recording` or `saved_cleanup_error`, not legacy datasets.

Inspect, then explicitly create a new copy:

```sh
PYTHONPATH=src python3 tools/recover_capture.py CAPTURE_ID
PYTHONPATH=src python3 tools/recover_capture.py CAPTURE_ID --confirm-copy
```

Add `--install-replay` to publish the verified copy under a new `recovered-*`
dataset ID in the local playback catalog. Without that option, copies stay in
`.runtime/capture-recovery`. The original and failed attempts are retained.
The web data page also offers an explicitly confirmed recovery action for
interrupted datasets. It creates and audits a copy in a background job, then
offers a button to open it in playback. Request IDs prevent duplicate delivery
from repeating the same recovery. Reloading the same browser tab resumes status
lookup; interrupted bridge workers require inspection rather than automatic retry.

Recovery reconstructs a canonical index from committed frame metadata rather
than trusting the interrupted index or manifest count. Directories without
`frame.json` may be omitted only at the tail. Interior holes, malformed frame
identities, links, special files, overlarge sources and insufficient disk space
are rejected. Bounds: 20 GiB source, 10,000 sample directories, 300,000 files,
one GiB additional free-space reserve and a 300-second raw validation timeout.

All copied samples must pass the existing RGB/raw-input, metric-depth, XYZI,
BEV and calibration validator. Copy hashes must equal source hashes, and the
source inventory must remain unchanged through validation. The result records
the original identity/status, omitted tail and audit evidence. It does not
invent missing samples or make a crashed run successful. `saved_recovered`
is deliberately not accepted by automatic training-split admission.

This is not protection against concurrent adversarial filesystem replacement,
power loss or a full disk while writing the failure report. It does not repair
corrupt raw samples; failed copies remain pending and are not published.

## Real local evidence

Source `capture-20260910T165555-a6a12724` was retained from an earlier real worker
interruption. Recovery produced 5 valid synchronous samples with 14/14 verified
sensor extrinsics; uncommitted tail directory `0000241314` was omitted. All source
files remained byte-identical. Separate copy:
`recovered-9f17b788ef46482f9aadd1fdcc08b019`; independently recreated/published copy:
`recovered-e0f80435373d4fdba83aac8d8d06bcb2`.

Browser `63fbf33c-c7ad-4eaa-a6da-7bbff4eeb69a` loaded the published copy, displayed
the incomplete-recording warning and sought sample 3/5. Screenshot inspected:
six RGB views, point-cloud BEV, rendered top-down RGB and recorded trajectory.
No new native capture or scene mutation was performed for this recovery test.

Browser `06516971-cd34-48af-8d5a-01095d5b6f88` subsequently clicked the raw-data
audit button and observed a fresh passing report; screenshot inspected. Python
suite: 680 passing tests. Type checking and production build also passed.

## Browser recovery launch

`browser-models-1f2923b8-24ad-4f89-bbe1-8be96cc88c8f` confirmed recovery of the
original interrupted dataset, opened `recovered-d591b839253244fa8f0c830491dfbb4c`
and performed a fresh passing raw-data audit. Request
`5ccc6d4b71ae44d5ba8d8a9bf7ab2429` is recorded in `.runtime/dataset-recovery`.
Completion screenshot inspected. Full Python suite: 685 passed; types passed.

Initial browser testing exposed duplicate React keys between recovery, quality
and replay-event siblings: catalog polling duplicated panels and lost effective
confirmation state, without submitting a backend recovery. Keys now include the
component identity. Regression waits for catalog polling and checks that each
recovery/quality panel occurs exactly once before confirming.
The failed first run is retained as
`browser-models-732ad827-71ac-4927-98e6-aa0c3904c055` (recovery never started,
probe timed out); it is not counted as successful recovery.
