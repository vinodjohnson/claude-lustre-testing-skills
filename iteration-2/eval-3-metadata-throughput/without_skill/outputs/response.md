# Lustre Environment Topology for Metadata Create Throughput Testing

I was unable to run the topology collection script (`scripts/collect_lustre_topology.py`) due to shell access restrictions, but I have analyzed the Vagrantfile and all provisioning scripts to give you a detailed picture of the environment. Below is what your cluster looks like, organized around the parameters most relevant to metadata create throughput on a multi-MDT setup.

---

## Cluster Overview

| Node    | VM Name        | IP             | CPUs | RAM    | Role                        |
|---------|----------------|----------------|------|--------|-----------------------------|
| MDS     | lustre-mds     | 192.168.56.11  | 2    | 2048MB | MGS + MDT0 + MDT1          |
| OSS     | lustre-oss     | 192.168.56.12  | 1    | 1024MB | OST0                        |
| Client  | lustre-client  | 192.168.56.13  | 4    | 4096MB | Lustre client + k3s + Go    |

- **Lustre version**: 2.15.5
- **OS**: Rocky Linux 8 (kernel 4.18.0-553.5.1.el8 variants)
- **LNet**: tcp over enp0s8 (private network)
- **Filesystem name**: `lustre`

---

## MDT Configuration (Multi-MDT / DNE)

Your environment uses the **smoke test setup** (`scripts/smoke_test_setup.sh`), which provisions **2 MDTs** on the single MDS node:

| Parameter     | Value                           | Notes                                                                 |
|---------------|---------------------------------|-----------------------------------------------------------------------|
| MDT count     | **2** (MDT0 + MDT1)            | Both on `lustre-mds`, backed by 200MB loopback files                  |
| MDT0          | `/tmp/mdt0_loop` on `/mnt/mdt0` | Combined MGS + MDT, index=0                                          |
| MDT1          | `/tmp/mdt1_loop` on `/mnt/mdt1` | Standalone MDT, index=1, mgsnode=192.168.56.11@tcp                   |
| HSM control   | `enabled` (set via `lctl set_param -P mdt.*.hsm_control=enabled`) | Persistent param across both MDTs |
| Directory striping | Default stripe set via `lfs setdirstripe -D -c 2 -H crush /mnt/lustre` | CRUSH hash, all 2 MDTs engaged |

The `smoke_test.sh` script sets a **default directory stripe of count=2 with CRUSH hash** on the filesystem root. This means new directories will automatically distribute across both MDTs -- which is exactly what you want for multi-MDT create throughput testing.

### DNE Feature Flags (need live collection to confirm)

These parameters control whether multi-MDT operations work. You should verify their values by running on the MDS:

```bash
lctl get_param mdt.*.enable_striped_dir
lctl get_param mdt.*.enable_remote_rename
lctl get_param mdt.*.enable_dir_auto_split
```

If `enable_striped_dir` is 0, creates in a single directory all hit one MDT even with multiple MDTs present. Enable with:
```bash
lctl set_param mdt.*.enable_striped_dir=1
```

---

## MDS Thread Pools (need live collection to confirm)

These are critical for metadata create throughput. Verify by running on the MDS:

```bash
lctl get_param mds.MDS.mdt.threads_started
lctl get_param mds.MDS.mdt.threads_min
lctl get_param mds.MDS.mdt.threads_max
lctl get_param mds.MDS.mdt_io.threads_started
```

With only 2 CPUs on the MDS VM, the thread pool will be limited. If `threads_started` equals `threads_max` under load, the MDS is at thread capacity and this will cap your create throughput.

---

## Client-Side MDC Tuning (need live collection to confirm)

The client-side MDC (Metadata Client) parameters are the **primary bottleneck knobs** for metadata create throughput:

| Parameter                      | What it controls                                                    | Check command |
|--------------------------------|---------------------------------------------------------------------|---------------|
| `mdc_max_rpcs_in_flight`       | Max concurrent metadata RPCs to the MDS                             | `lctl get_param mdc.*.max_rpcs_in_flight` |
| `mdc_max_mod_rpcs_in_flight`   | Max concurrent **modifying** RPCs (create, unlink, rename)          | `lctl get_param mdc.*.max_mod_rpcs_in_flight` |
| `llite_max_cached_mb`          | Client metadata cache size (large caches mask lock contention)      | `lctl get_param llite.*.max_cached_mb` |

**`mdc_max_mod_rpcs_in_flight` is the single most important parameter for your test.** If this value is below 8, your create throughput will be artificially bottlenecked regardless of how many MDTs you have. Tune with:
```bash
lctl set_param mdc.*.max_mod_rpcs_in_flight=16
```

---

## LDLM Lock Contention

Lock contention on metadata operations directly impacts create throughput. Check on the MDS:

```bash
lctl get_param ldlm.namespaces.mdt-*.contention_seconds
lctl get_param ldlm.namespaces.mdt-*.contended_locks
```

These are tuning knobs (thresholds), not live counters. If `contention_seconds` is high (>10), contention may go undetected in short test runs.

---

## Key Limitations for Your Test

1. **Single MDS node**: Both MDTs run on the same 2-CPU/2GB VM. In production multi-MDT setups, each MDT typically has its own server. Your throughput will be bounded by this single node's resources, which limits the value of multi-MDT scaling measurements.

2. **Loopback-backed MDTs**: The 200MB loopback files are small and share the same underlying disk. This means I/O contention between MDT0 and MDT1, which would not exist in a real multi-MDT deployment with dedicated storage.

3. **Single OST**: Only one OST exists (2GB, loopback). For pure metadata create tests (e.g., `touch` or `mkdir`) this is not a bottleneck, but if your creates involve writing data, the single OST becomes the constraint.

4. **Client resources**: The client has 4 CPUs and 4GB RAM, which is relatively generous compared to the servers. This is good -- it means the client is unlikely to be the bottleneck.

---

## Recommendations for Your Test

1. **Run the topology script** to get live parameter values: `python3 scripts/collect_lustre_topology.py` from the project root (requires VMs to be running).

2. **Verify DNE is active**: Confirm `enable_striped_dir=1` and that the default directory stripe count is 2 (`lfs getdirstripe -D /mnt/lustre`).

3. **Tune `mdc_max_mod_rpcs_in_flight`**: Set to at least 16 for meaningful throughput numbers.

4. **Use `lfs mkdir -c 2` explicitly** if the default striping is not set, to ensure creates distribute across both MDTs.

5. **Monitor with `md_stats`**: Watch create rates per MDT during the test:
   ```bash
   lctl get_param mdt.*.md_stats
   ```

---

## Follow-up

Would you like me to:
- Help design the specific metadata create throughput test (tool selection, measurement methodology)?
- Investigate any of the live parameters by running commands on the VMs?
- Help tune the MDC/MDS parameters for maximum create throughput?
