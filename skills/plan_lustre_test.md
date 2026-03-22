---
name: plan-lustre-test
description: Plans a Lustre performance test from a topology handoff. Produces a structured test plan artifact covering setup, parameterization, measurement points, and expected outcomes. First step in the lustre test workflow — requires topology data; invokes /topology automatically if none is present.
---

Plan a Lustre performance test from topology data. Part of a workflow — consumes a `topology-handoff` block and produces a test plan artifact.

## User Input

```text
$ARGUMENTS
```

## Workflow

```
Progress:
- [ ] Step 1: Check for topology handoff
- [ ] Step 2: Enter worktree
- [ ] Step 3: Confirm test intent with user
- [ ] Step 4: Draft test plan
- [ ] Step 5: Resolve concerns from topology
- [ ] Step 6: Emit artifact (TBD: storage location)
- [ ] Step 7: Exit worktree
```

---

### Step 1: Check for topology handoff

Scan the current conversation for a fenced block labelled `topology-handoff`.

- **Found:** extract all fields and proceed to Step 2.
- **Not found:** invoke the `topology` skill now. Do not proceed until the user
  has confirmed the handoff (i.e., a `topology-handoff` block appears in the
  conversation). Then continue from Step 2.

---

### Step 2: Enter worktree

Use the `EnterWorktree` tool to create an isolated working copy before writing
any files. All file writes happen inside the worktree.

---

### Step 3: Confirm test intent with user

From `topology-handoff.test_intent`, state back what test you are planning in
one sentence and ask for confirmation or corrections before proceeding. Keep
this to a single exchange — do not ask multiple questions.

---

### Step 4: Draft test plan

Produce a test plan document. Structure it as follows:

#### 4.1 — Overview

| Field | Value |
|-------|-------|
| Test intent | (from handoff) |
| Lustre version | (from handoff) |
| Target node(s) | (client mount points, MDT node) |

#### 4.2 — Environment setup

List every prerequisite command that must run before the test, derived from
`concerns` and `key_params` in the handoff. For each:

```
# <what it does>
<command>
```

Common setup items by test type:

| Test type | Setup needed |
|-----------|-------------|
| Metadata/rename | Tune `mdc_max_mod_rpcs_in_flight`, create test directory tree |
| I/O throughput | Tune `osc_max_rpcs_in_flight`, pre-create files if needed |
| HSM | Enable `hsm_control`, start copytool |

#### 4.3 — Parameterization

Define the variables the test sweeps over. For each parameter:

```
name: <param>
values: [<low>, <mid>, <high>]
rationale: <why this range, grounded in topology data>
```

Ground ranges in topology facts (e.g., `max_requests=3` → sweep 1–6 to
show queueing behaviour; `mdt_threads_max=80` → don't exceed it without noting
saturation risk).

#### 4.4 — Test procedure

Step-by-step commands to run the test on the client VM, written as a bash
script block. Must be runnable via `vagrant ssh client -- sudo bash -s`.

Include:
- Directory/file setup
- The measurement command (e.g., `mdtest`, `fio`, custom Go benchmark)
- How to capture output

#### 4.5 — Measurement points

| Metric | How to collect | Tool/command |
|--------|---------------|--------------|
| (e.g., renames/sec) | (e.g., mdtest -I output) | ... |
| MDS thread saturation | `lctl get_param mds.MDS.mdt.threads_started` | lctl |
| LDLM contention | `lctl get_param ldlm.namespaces.mdt-*.contended_locks` | lctl |

Always include at least one MDS-side counter alongside the client-side metric.

#### 4.6 — Expected outcomes and red flags

For each concern in `topology-handoff.concerns`, describe:
- What you expect to see if the concern is irrelevant
- What signal indicates the concern is actively limiting performance

---

### Step 5: Resolve concerns

For every entry in `topology-handoff.concerns`, add a note to the plan
explaining whether it is:
- **Mitigated** — handled by a setup step in 4.2
- **Accepted** — acknowledged, won't affect this test
- **Blocking** — must be resolved before the test can run; tell the user

If any concern is **Blocking**, stop here and surface it to the user.

---

### Step 6: Emit artifact

Write the completed test plan to `lustre-test-plan.md` inside the worktree.

**Artifact storage: TBD** — ask the user where the final plan should be
committed or copied once the worktree work is done. Options to offer:

1. Committed to the current branch under `tests/plans/`
2. Saved to a new branch `test-plan/<test-name>`
3. Left in the worktree for the user to move manually

Do not commit or copy until the user decides.

---

### Step 7: Exit worktree

Use the `ExitWorktree` tool. If files were written, report the worktree path
so the user can review before the artifact is moved to its final location.
