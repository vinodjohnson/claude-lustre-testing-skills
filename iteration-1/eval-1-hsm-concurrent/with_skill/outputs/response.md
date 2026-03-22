# Topology Discovery for HSM Archive with 4 Concurrent Copytools

## Step 1: Test Intent (Skipped -- already clear)

Your test intent is well-defined: HSM archive with 4 concurrent copytools writing large files. This touches two Lustre subsystems:

- **HSM coordination** -- `hsm_control`, `max_requests` on the MDS govern how many copytool actions can run in parallel
- **Concurrency capacity** -- thread pools, LDLM contention thresholds, and client-side pipeline depth determine whether 4 writers can sustain throughput without serializing

No follow-up questions needed. Moving straight to collection.

## Step 2: Relevant Subsystems

For this test, I need data from:

| Subsystem | Why it matters |
|---|---|
| `hsm_control` | Must be `enabled` for archive to work |
| `max_requests` | Caps concurrent copytool actions -- you want at least 4 |
| MDT count | Archive requests route through MDTs; single MDT = single bottleneck |
| MDS thread pool | Thread saturation under 4 concurrent archives |
| LDLM contention | Lock contention thresholds affect concurrent file operations |
| Client mount | Where files are created before archive |
| Client OSC/MDC tuning | Pipeline depth for I/O and metadata RPCs |
| LNet NIDs | Network path between client and MDS |

**Filter chosen:** `mds,client` -- HSM state lives on the MDS, files are written on the client. The OSS data path is not the focus of this test.

## Step 3: Collection

Command executed:

```bash
cd /Users/vinodjohnson/lustre-hsm-mover && python3 scripts/collect_lustre_topology.py mds,client
```

**Result:** The collector script could not be executed because the Vagrant VMs are not currently running (or Bash execution was restricted in this session). Below is the topology derived from the Vagrantfile and provisioning configuration, which reflects the environment as designed.

## Step 4: Environment for HSM Archive Test (4 Concurrent Copytools)

**Topology:** 3 nodes (mds, oss, client) -- Rocky Linux 8, Lustre (version from VMs)

| Node | Hostname | IP | Role | vCPUs | RAM |
|------|----------|-----|------|-------|------|
| mds | lustre-mds | 192.168.56.11 | MDS + MGS | 2 | 2048 MB |
| oss | lustre-oss | 192.168.56.12 | OSS | 1 | 1024 MB |
| client | lustre-client | 192.168.56.13 | Client | 4 | 4096 MB |

### HSM Readiness

| Parameter | Expected Value | Implication for Your Test |
|---|---|---|
| `hsm_control` | `enabled` | Ready for archive/restore operations |
| `max_requests` | 3 (typical default) | **Bottleneck: you want 4 concurrent copytools but default allows only 3.** You will need to increase this. |
| MDT count | 1 | All archive requests funnel through a single MDT -- no parallelism across MDTs |

**Action required:** Before running with 4 copytools, increase `max_requests`:

```bash
# On the MDS VM:
sudo lctl set_param mdt.*.hsm.max_requests=4
```

If `max_requests` is already >= 4 when you run the collector against live VMs, no change is needed.

### Concurrency Capacity

| Parameter | Location | Expected Value | Implication |
|---|---|---|---|
| MDS thread pool | MDS | ~32 threads started | Should handle 4 concurrent HSM requests without thread exhaustion |
| LDLM contention_seconds | MDS | 2s (default) | Lock contention detected within 2s window -- appropriate for short test |
| LDLM contended_locks | MDS | 32 (default) | Lock considered contended after 32 waiters |
| `osc_max_rpcs_in_flight` | Client | 8 (default) | I/O pipeline to OSS -- adequate for large file writes |
| `osc_max_dirty_mb` | Client | 32 (default) | Client write-back buffer per OSC |
| `mdc_max_rpcs_in_flight` | Client | 8 (default) | Metadata RPC pipeline to MDS |
| `mdc_max_mod_rpcs_in_flight` | Client | 8 (default) | Concurrent metadata mutations (archive triggers these) |
| `llite_max_cached_mb` | Client | 128 (default) | Client metadata cache -- can mask contention in short runs |

### Data Path

| Parameter | Value |
|---|---|
| Client mount | `/mnt/lustre` |
| OST count | 1 (single OST on OSS) |
| Client LNet NID | `192.168.56.13@tcp` |
| MDS LNet NID | `192.168.56.11@tcp` |

### Potential Concerns for Your Test

1. **`max_requests` likely needs to be bumped to 4 or higher.** The default is typically 3, which would cause your 4th copytool to queue. Run the collector against live VMs to confirm the actual value.

2. **Single MDT** -- all 4 copytools' archive requests go through one MDT. This is fine for correctness testing but means the MDS is a serialization point. Thread pool size and LDLM settings will determine whether 4 concurrent archives cause contention.

3. **Single OST** -- archive I/O from all 4 copytools hits one backing device. For large files, this limits aggregate write throughput. Not a correctness issue, but performance numbers from this setup will not reflect multi-OST production environments.

4. **Client has 4 vCPUs / 4GB RAM** -- sufficient to run 4 copytools concurrently without CPU/memory contention on the client side.

5. **MDS has 2 vCPUs / 2GB RAM** -- under 4 concurrent HSM archive operations, monitor MDS thread utilization. If threads_started equals threads_max, the MDS is at capacity.

## Step 5: Next Steps

To get live values and confirm the above, start the VMs and run:

```bash
cd /Users/vinodjohnson/lustre-hsm-mover && python3 scripts/collect_lustre_topology.py mds,client
```

Once VMs are up, I can:
- Confirm the actual `max_requests` value and whether it needs bumping
- Check MDS thread pool utilization baseline
- Verify HSM is enabled and ready
- Dig into LDLM contention settings if you want to tune for the concurrency test

Want me to collect from the live VMs once they are running, or are you ready to plan the test parameters based on this layout?
