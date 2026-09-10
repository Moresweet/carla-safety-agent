# Batch ledger integrity

Both direct queue tools and the HTTP catalog validate the stored plan and its
ordered job list before dispatch, pause, retry or accounting. Queue files are
bounded to 32 MiB and duplicate JSON keys/special non-finite numbers are refused.
Linked queue directories, queue files and queue locks are rejected. Invalid
records stay on disk; catalog listings expose an error instead of repairing them.

The ownership ledger requires one active attempt at most, unique attempt and
execution IDs, correct bound/unbound states, finite timestamps and terminal
evidence. Old attempts before a retry must be failed or stopped. A pending job
cannot conceal an active or completed latest attempt. At most 20 attempts per
job are retained; a retry adds a new record, never overwrites the old outcome.
Outgoing updates are validated too, before a temporary file is written.

Publication flushes the unique temporary file, replaces queue.json and flushes
the queue directory. The new directory entry is flushed when creating a queue.
A post-replacement flush error requires inspecting actual state before retrying.
These checks are not a signature/authentication of externally edited data, a
transaction with CARLA, or comprehensive protection against hostile path races.

Compatibility: all 18 existing local batches passed the initial stricter read
check. Unit cases include invalid schema/pause, reordered jobs, pending live
attempts, duplicate identities, historical active attempts, missing bindings,
timestamps, count bounds, linked paths and unchanged corrupt files.

The 747-test suite passed. Native batch
`20e9df7cbee644d18bbae2fad8285634` repeated response-loss binding, explicit stop,
retry and continued dispatch with the strict ledger. Original execution
`88713075578b4e5295e37fe64f772fc4` remains recorded; replacement
`c044a2acd2bb4b74b6b1cf941261adbd` and second job
`abb6d31deebb469cbe27e0afa8ab14d1` each saved 20 verified samples, 14/14 spatial
calibrations and no residual sensors. Attempt counts are 2 and 1, not overwritten.
