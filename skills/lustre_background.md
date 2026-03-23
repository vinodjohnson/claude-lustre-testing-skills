# Lustre Filesystem Background

Concise reference for Claude when running lustre-topology skills.
Not a slash command — loaded by `/topology` and `/plan_lustre_test`.

## Architecture

Lustre is a POSIX-compliant parallel filesystem for HPC. Data and metadata travel separate paths:

| Component | Role | Key daemon |
|-----------|------|------------|
| **MGS** (Management Server) | Stores cluster config. Usually co-located with MDS. | `mgs` |
| **MDS** (Metadata Server) | Handles namespace ops (open, stat, rename, unlink). Hosts one or more **MDTs**. | `mdt` |
| **OSS** (Object Storage Server) | Handles file data I/O. Hosts one or more **OSTs**. | `obdfilter` |
| **Client** | Mounts the filesystem, talks to MDS for metadata and OSS for data in parallel. | `llite` |
| **LNet** | Network transport layer underneath all Lustre traffic. NIDs identify endpoints (e.g. `192.168.56.11@tcp`). | `lnet` |

**MDT-0** is special: it holds the root directory and receives disproportionate metadata load in single-MDT setups.

## Key Subsystems

### LDLM (Lustre Distributed Lock Manager)
All metadata and data operations acquire LDLM locks. Lock contention is the most common performance bottleneck:
- `contention_seconds` — time window for detecting contention (tuning knob, not a live counter)
- `contended_locks` — number of waiters before a lock is flagged as contended
- Extent locks (on OSTs) protect byte ranges; ibits locks (on MDTs) protect metadata attributes

### HSM (Hierarchical Storage Management)
Moves data between Lustre and external storage (tape, S3, etc.):
- **Coordinator** runs on the MDS; controlled by `hsm_control` (enabled/disabled/stopped)
- **Copytools** run on clients and do the actual data movement
- `max_requests` limits concurrent archive/restore operations per MDT — if you run more copytools than this, extras queue

### DNE (Distributed Namespace)
Spreads metadata across multiple MDTs:
- `enable_remote_rename` — allows renames across MDTs (cross-MDT rename is slower than local)
- `enable_striped_dir` — allows directories to span multiple MDTs
- `enable_dir_auto_split` — automatically splits large directories across MDTs

### Thread Pools
MDS and OSS have auto-scaling thread pools:
- `threads_started` / `threads_min` / `threads_max` — if `started == max` under load, the server is at thread capacity
- `ost_io` threads handle bulk data I/O on OSSes
- `mdt_io` threads handle data-on-MDT operations

### Caches and Sync
Multiple cache layers affect performance and test repeatability:
- **Client data cache** (`llite_max_cached_mb`): cached reads/writes avoid network round-trips but can mask I/O bottlenecks in short tests
- **Client metadata cache**: directory entries and attributes cached locally; large caches reduce MDS load but delay visibility of lock contention
- **Lock cache (LDLM)**: clients hold granted locks until the server revokes (callbacks). A large lock cache reduces lock traffic but increases revocation storms under contention
- **Server-side caches**: MDS and OSS cache data in memory before flushing to backing storage

Sync frequency to durable storage matters for both correctness and performance:
- `sync_on_lock_cancel` — controls whether dirty data is flushed when a lock is revoked; affects write latency under contention
- Journal commit intervals on backing ldiskfs/ZFS determine how often metadata hits disk — longer intervals improve throughput but increase data-at-risk window
- Client `sync` mount option forces synchronous writes; useful for correctness tests but kills throughput

## Common Tuning Parameters (Client-Side)

| Parameter | Controls | Impact |
|-----------|----------|--------|
| `osc_max_rpcs_in_flight` | Max concurrent data RPCs per OST | Low values (< 8) throttle I/O throughput |
| `osc_max_dirty_mb` | Client write cache before flush | Affects write burst size |
| `mdc_max_rpcs_in_flight` | Max concurrent metadata RPCs | Limits metadata parallelism |
| `mdc_max_mod_rpcs_in_flight` | Max concurrent metadata *mutation* RPCs (create, rename, unlink) | Most impactful for metadata benchmarks |
| `llite_max_cached_mb` | Client-side metadata cache | Large caches reduce MDS load but can mask lock contention in short tests |

## Performance Bottleneck Patterns

- **Single MDT saturation**: all metadata funnels through MDT-0; symptoms are high `mdt_threads_started` and increasing LDLM contention
- **Low RPC concurrency**: client-side `max_rpcs_in_flight` too low; throughput plateaus well below hardware capability
- **HSM queueing**: `max_requests` lower than copytool count; archive/restore ops queue instead of running
- **Lock contention on shared directories**: many clients creating/renaming files in the same directory triggers LDLM hotspots
- **OST imbalance**: uneven file distribution across OSTs leads to I/O hotspots on individual OSSes
- **Cache masking**: large client caches (data or metadata) can hide real bottlenecks in short test runs; drop caches or use cold-start methodology to get representative numbers
- **Lock cache thrashing**: too many clients holding locks on the same resources triggers callback storms; symptoms are high lock revocation rates and latency spikes
- **Infrequent sync**: long intervals between durable flushes inflate throughput numbers but don't reflect crash-safe performance; watch journal commit settings when benchmarking write-heavy workloads
