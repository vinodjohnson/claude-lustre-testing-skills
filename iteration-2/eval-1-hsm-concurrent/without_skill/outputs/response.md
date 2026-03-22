# Lustre Environment Topology

**Note:** I was unable to execute the topology collection script (`scripts/collect_lustre_topology.py`) because bash execution was denied in this session. The information below is derived from static analysis of the Vagrantfile and provisioning scripts. To get live runtime data (HSM control status, thread counts, LDLM contention thresholds, mount options, LNet NIDs), please run:

```bash
cd /Users/vinodjohnson/lustre-hsm-mover && python3 scripts/collect_lustre_topology.py
```

---

## Cluster Overview

Your Lustre cluster consists of **3 Vagrant VMs** running Rocky Linux 8 with Lustre 2.15.5:

| VM Name  | Hostname       | IP Address      | Role    | vCPUs | RAM    |
|----------|----------------|-----------------|---------|-------|--------|
| mds      | lustre-mds     | 192.168.56.11   | MDS/MGS | 2     | 2 GB   |
| oss      | lustre-oss     | 192.168.56.12   | OSS     | 1     | 1 GB   |
| client   | lustre-client  | 192.168.56.13   | Client  | 4     | 4 GB   |

- **Lustre version:** 2.15.5
- **Server kernel:** 4.18.0-553.5.1.el8_lustre
- **Client kernel:** 4.18.0-553.5.1.el8_10
- **LNet:** TCP over private network interface `enp0s8` (192.168.56.0/24 subnet)
- **Filesystem backend:** ldiskfs (on MDS and OSS)

---

## Assessment for 4 Concurrent Copytools with Large Files

### Concerns and Bottlenecks

1. **Single Client VM:** You have only 1 client node. All 4 copytools would run on the same VM (lustre-client). The client has 4 vCPUs and 4 GB RAM, which is reasonable for 4 concurrent copytool processes, but they will compete for the same network link and local resources.

2. **Single OSS with 1 OST:** The OSS VM has only 1 vCPU and 1 GB RAM. With large files and 4 concurrent archive operations, the single OST will be the I/O bottleneck. There is no striping benefit with a single OST -- all file data flows through one backing device. This is not representative of production striping behavior.

3. **MDS HSM Coordinator Capacity:** The MDS has 2 vCPUs and 2 GB RAM. The HSM coordinator's `max_requests` parameter controls how many concurrent HSM requests can be in flight. You need to verify this is set to at least 4 (run the topology script or check with `lctl get_param mdt.*.hsm.max_requests` on the MDS). If it is lower, increase it:
   ```bash
   vagrant ssh mds -- sudo lctl set_param mdt.*.hsm.max_requests=8
   ```

4. **HSM Control Must Be Enabled:** Before any archive operations work, HSM must be enabled on the MDT:
   ```bash
   vagrant ssh mds -- sudo lctl get_param mdt.*.hsm_control
   # If not "enabled":
   vagrant ssh mds -- sudo lctl set_param mdt.*.hsm_control=enabled
   ```

5. **Network:** All VMs communicate over a VirtualBox private network (TCP LNet). This is adequate for testing but bandwidth is limited compared to production InfiniBand or high-speed Ethernet.

### Recommendations Before Testing

1. **Verify HSM is enabled** -- run the topology script or manually check `hsm_control`.

2. **Increase `max_requests`** to at least 4 (ideally 8) so the coordinator does not serialize your concurrent copytool requests.

3. **Check client tuning parameters** -- `osc.*.max_rpcs_in_flight` and `mdc.*.max_mod_rpcs_in_flight` affect concurrency. Low values will throttle your copytools. The topology script reports these values with annotations.

4. **Monitor OSS resources** -- with 1 GB RAM and 1 vCPU, the OSS may become CPU or memory constrained during large file I/O. Watch for OOM kills or high iowait.

5. **Register copytool agents** -- each of your 4 copytools needs to register with the HSM coordinator via `llapi_hsm_copytool_register`. Ensure your copytool binary (lhsm-oci) supports running multiple instances concurrently on the same client mount.

### What the Topology Script Would Tell You

Running `python3 scripts/collect_lustre_topology.py` would provide live values for:
- Whether HSM control is currently enabled or disabled
- The current `max_requests` setting
- MDS/OSS thread pool sizes (started, min, max) and whether they are at capacity
- LDLM lock contention thresholds
- Client mount options (flock, checksum, encryption flags)
- Client tuning (max_rpcs_in_flight, max_dirty_mb, max_cached_mb)
- LNet NID configuration
- MDT/OST UUIDs and metadata operation statistics

This live data is essential for identifying runtime bottlenecks before starting your 4-copytool test.
