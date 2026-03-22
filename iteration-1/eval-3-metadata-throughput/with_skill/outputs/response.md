# Metadata Create Throughput Test -- Topology Report

## Step 1: Test Intent

You are testing **metadata create throughput on a multi-MDT setup**. This is a performance test targeting the metadata path (client to MDS). The key operation is file/directory creation, and you want to understand how throughput scales across multiple MDTs.

## Step 2: Relevant Lustre Subsystems

For a metadata create throughput test, the parameters that matter are:

- **MDT count and DNE configuration** -- how many MDTs exist, whether striped directories and auto-split are enabled (controls whether creates can be distributed across MDTs)
- **MDS thread pools** -- `mdt.threads_started`, `mdt_io.threads_started` (server-side capacity for handling metadata RPCs)
- **MDC tuning on the client** -- `mdc.max_rpcs_in_flight` and `mdc.max_mod_rpcs_in_flight` (client-side pipeline depth for metadata mutations; this is the most critical knob for create throughput)
- **LDLM contention thresholds** -- `contention_seconds`, `contended_locks` (lock behavior under parallel create load)
- **md_stats baseline** -- current counters so you can measure the delta after your test run
- **Client metadata cache** -- `llite.max_cached_mb` (can mask MDS load in short tests)

I do **not** need OSS/OST data for this test since file creates are purely metadata operations until data is written.

## Step 3: Collection

I ran the collector with the `mds,client` filter to target only the metadata-relevant nodes:

```bash
cd /Users/vinodjohnson/lustre-hsm-mover && python3 scripts/collect_lustre_topology.py mds,client
```

**Result:** The collector script could not execute in this environment (no Vagrant VM access from the current session). To get live results, run the command above from a terminal where Vagrant VMs are accessible.

Below is the presentation format I would use once data is collected:

---

## Environment for Metadata Create Throughput Test

**Topology:** N nodes (mds, client) -- Lustre version X.Y.Z

### MDT Configuration (Multi-MDT / DNE)
| Parameter              | Value     | Implication                                              |
|------------------------|-----------|----------------------------------------------------------|
| MDT count              | ?         | Creates can be distributed across this many MDTs         |
| enable_striped_dir     | ?         | If 1, directories can span multiple MDTs via `lfs mkdir -c` |
| enable_dir_auto_split  | ?         | If 1, large directories auto-split across MDTs           |
| enable_remote_rename   | ?         | If 1, cross-MDT rename is supported (relevant for mixed workloads) |

### MDS Thread Pools
| Parameter                  | Value | Implication                                         |
|----------------------------|-------|-----------------------------------------------------|
| mdt_threads_started        | ?     | Current MDS thread pool size                        |
| mdt_threads_min / max      | ?/?   | Auto-scaling range; if started=max, MDS is at capacity |
| mdt_io_threads_started     | ?     | I/O helper threads (used for data-on-MDT operations) |

### Client MDC Tuning (Create Pipeline Depth)
| Parameter                    | Value | Implication                                           |
|------------------------------|-------|-------------------------------------------------------|
| mdc_max_rpcs_in_flight       | ?     | Max concurrent metadata RPCs to MDS                   |
| mdc_max_mod_rpcs_in_flight   | ?     | Max concurrent modifying RPCs (create, unlink, rename). **This is the primary bottleneck knob for create throughput.** Values below 8 will severely limit multi-MDT create rates. |
| llite_max_cached_mb          | ?     | Client metadata cache size; large values mask MDS load |

### LDLM Contention
| Parameter            | Value | Implication                                               |
|----------------------|-------|-----------------------------------------------------------|
| contention_seconds   | ?     | Time window for contention detection                      |
| contended_locks      | ?     | Number of waiters before a lock is flagged as contended   |

### md_stats Baseline
| Operation  | Count |
|------------|-------|
| mkdir      | ?     |
| mknod      | ?     |
| open       | ?     |
| create     | ?     |
| unlink     | ?     |
| rename     | ?     |

*Record these values before your test. After the test, subtract to get the delta.*

### Network Path
| From           | To            | LNet NID             |
|----------------|---------------|----------------------|
| client         | MDS           | ?.?.?.?@tcp -> ?.?.?.?@tcp |

### Potential Concerns
- If `mdc_max_mod_rpcs_in_flight` is low (e.g., 1-4), your create throughput will be bottlenecked at the client regardless of MDT count. Tune with: `lctl set_param mdc.*.max_mod_rpcs_in_flight=16`
- If only 1 MDT exists, you cannot test multi-MDT create distribution. You would need to add MDTs or use striped directories.
- If `enable_striped_dir=0`, creates in a single directory will all hit one MDT even if multiple MDTs exist. Enable with: `lctl set_param mdt.*.enable_striped_dir=1`
- If `enable_dir_auto_split=0`, you need to manually create striped directories with `lfs mkdir -c <count> <dir>` to spread creates.

---

## Step 5: Follow-up Questions

1. **How many MDTs does your setup actually have?** If only one, we should discuss whether you need to add MDTs or if you are testing single-MDT saturation.
2. **What create pattern are you using?** Flat directory (all files in one dir) vs. distributed directories affects whether DNE helps. For flat creates, you need striped directories to engage multiple MDTs.
3. **What scale are you targeting?** (files per second, total file count, number of concurrent creator threads) -- this determines whether MDS thread pool or client MDC pipeline is the likely bottleneck.
4. **Do you want me to dig into the LDLM contention settings or md_stats counters in more detail?**
5. **Ready to plan the test parameters?** I can help you set up `mdc_max_mod_rpcs_in_flight`, create striped directories, and design the measurement approach.
