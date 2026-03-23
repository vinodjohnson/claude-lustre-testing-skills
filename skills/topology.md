---
name: discovering-lustre-topology
description: Discovers Lustre filesystem topology from Vagrant VMs, tailored to a planned test. Converses with the user to understand test intent, then collects and presents relevant Lustre parameters in layers. Produces a structured handoff block for downstream skills like create_lustre_test. Triggers on topology, filesystem config, infrastructure status, node status, test planning, or parameter sweeps. Also triggers proactively before proposing any test plan.
---

Iterative conversation to collect Lustre topology for test planning. Part of a workflow — output feeds into `create_lustre_test`.

## User Input

```text
$ARGUMENTS
```

## Background

Read `.claude/commands/lustre_background.md` for Lustre filesystem background knowledge before proceeding. If the file is not found, proceed without it.

## Workflow

```
Progress:
- [ ] Step 1: Understand test intent
- [ ] Step 2: Collect from VMs
- [ ] Step 3: Present Layer 1 (critical facts)
- [ ] Step 4: Iterate — deepen on request
- [ ] Step 5: Emit structured handoff
```

### Step 1: Understand test intent

If `$ARGUMENTS` describes a test, skip to Step 2. Otherwise ask 1-2 questions:
- What operation? (archive, restore, I/O, metadata, etc.)
- Correctness or performance? Concurrency involved?

Get enough to pick a collection filter. Refine later.

### Step 2: Collect from VMs

Run the collector. Do not substitute static file analysis.

```bash
python3 scripts/collect_lustre_topology.py $FILTER
```

Filters: `mds`, `oss`, `client`, `mds,client`, `mds,oss`, or omit for all.

| Test type | Filter |
|-----------|--------|
| HSM | `mds,client` |
| I/O throughput | `oss,client` |
| Metadata | `mds,client` |
| Full stack / unclear | omit |

If the script fails, stop — user needs to bring up VMs.

#### Role detection

The collector detects roles by probing live services, not VM names. A VM can hold multiple roles (MDS+client, MDS+MGS). The `role` field reflects primary role (priority: client > mds > oss); `is_mgs` is flagged separately.

MDT-0 holds the filesystem root directory — it receives disproportionate metadata load. Always note which node hosts MDT-0.

### Step 3: Present Layer 1 — critical facts only

From the collected JSON, present only the 2-4 most important facts for the user's test. Do not dump everything.

**What goes in Layer 1 by test type:**

| Test type | Layer 1 facts |
|-----------|---------------|
| HSM | hsm_control, max_requests vs requested parallelism, MDT count |
| I/O | OST count, osc_max_rpcs_in_flight, ost_io threads |
| Metadata | MDT count + which is index 0, mdc_max_mod_rpcs_in_flight, DNE enabled? |
| Concurrency | max_requests, LDLM contention_seconds, thread pool sizes |

Format as a short table with node overview. Example:

```
Topology: 3 nodes — Lustre 2.15.5
  mds (192.168.56.11) → MDS+MGS [MDT-0 root], detected via MDT
  oss (192.168.56.12) → OSS, detected via OST
  client (192.168.56.13) → Client, detected via mount

| Fact | Value | Why it matters for your test |
|------|-------|-----------------------------|
| hsm_control | enabled | Ready |
| max_requests | 3 | You want 4 copytools — 1 will queue |
| MDT count | 1 | All requests funnel through MDT-0 |
```

End with 1-2 follow-up questions max:
- "Want me to show thread pools and LDLM settings?"
- "Ready to move to test planning?"

### Step 4: Iterate — deepen on request

When the user asks for more detail, first check whether the data is already in the collected JSON. If it is, present it directly. If the user asks about a node or subsystem that wasn't in the original filter (e.g., started with `mds,client` but now wants OST data from `oss`), re-run the collector with a broader filter and merge the results.

**Layer 2 candidates** (present whichever the user asks about):
- Thread pools (mdt/ost threads started/min/max, io threads)
- LDLM contention (contention_seconds, contended_locks)
- Client tuning (osc/mdc rpcs, dirty_mb, llite cache)
- LNet NIDs and network path
- md_stats baseline
- DNE config (striped dirs, remote rename, auto-split)
- Mount options (flock, checksum, encrypt)

Keep each layer to one focused table. Ask before going deeper.

If the user pivots to a different test, loop back to Step 1.

### Step 5: Emit structured handoff

When the user is satisfied (or says "ready to plan"), emit this block for downstream skills:

```topology-handoff
test_intent: <what the user described>
lustre_version: <version>
nodes:
  - vm: <name>, ip: <ip>, roles: [<detected roles>], is_mgs: <bool>
mdts:
  - index: 0, node: <vm>, note: "root directory"
osts:
  - index: 0, node: <vm>
client_mounts:
  - node: <vm>, mountpoint: <path>
hsm:
  control: <enabled|disabled|stopped>
  max_requests: <n>
key_params:
  <only params surfaced during the conversation>
concerns:
  - <concerns raised during the conversation>
```

Only include fields that were discussed. This is the handoff to `plan_lustre_test`.
