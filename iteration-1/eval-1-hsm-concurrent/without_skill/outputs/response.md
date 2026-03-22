# Lustre Environment Topology for HSM Concurrent Copytool Testing

I was unable to run the `collect_lustre_topology.py` script directly (bash execution was denied), so the information below is derived from analyzing the Vagrantfile, provisioning scripts, and smoke test configuration.

## Cluster Overview

Your Lustre cluster is a 3-node Vagrant setup on VirtualBox, running Rocky Linux 8 with Lustre 2.15.5. All nodes communicate over a private network (`192.168.56.0/24`) using LNet TCP on interface `enp0s8`.

| VM Name  | Hostname       | IP Address      | Role              | vCPUs | RAM    |
|----------|----------------|-----------------|-------------------|-------|--------|
| mds      | lustre-mds     | 192.168.56.11   | MGS + MDS         | 2     | 2 GB   |
| oss      | lustre-oss     | 192.168.56.12   | OSS               | 1     | 1 GB   |
| client   | lustre-client  | 192.168.56.13   | Client + HSM Agent| 4     | 4 GB   |

## Filesystem Layout

- **Filesystem name:** `lustre`
- **MGS NID:** `192.168.56.11@tcp`
- **MDT0:** 200 MB loopback (`/tmp/mdt0_loop`), mounted at `/mnt/mdt0` on MDS -- combined MGS + MDT index 0
- **MDT1:** 200 MB loopback (`/tmp/mdt1_loop`), mounted at `/mnt/mdt1` on MDS -- MDT index 1
- **OST0:** 2000 MB (2 GB) loopback (`/tmp/ost_loop`), mounted at `/mnt/ost` on OSS -- single OST index 0
- **Client mount:** `/mnt/lustre` on both `client` and `mds` VMs

This is a DNE (Distributed Namespace) configuration with 2 MDTs. The smoke test uses `lfs setdirstripe -D -c 2 -H crush` for directory striping across both MDTs.

## HSM Configuration

- HSM control is enabled on all MDTs via `lctl set_param -P mdt.*.hsm_control=enabled` during setup.
- The `hsm_max_requests` parameter controls how many concurrent HSM requests the coordinator will dispatch. You will need to verify its current value by running `lctl get_param mdt.*.hsm.max_requests` on the MDS. For 4 concurrent copytools, you may need to increase this.

## Copytool Deployment

The smoke test currently runs `lhsm-oci` copytools on the following nodes:
- **localfs backend:** copytools on both `mds` and `client` (2 copytools)
- **ociincremental backend:** copytool on `client` only (1 copytool)

## Considerations for 4 Concurrent Copytools with Large Files

### Bottlenecks

1. **Single OST (2 GB):** All file data flows through one OST backed by a 2 GB loopback file. Large files will quickly exhaust this space. For meaningful large-file testing, you should increase the OST size (e.g., `count=10000` for 10 GB) or add additional OSTs.

2. **OSS resources:** The OSS VM has only 1 vCPU and 1 GB RAM. Under 4 concurrent copytools writing large files, this will be a severe bottleneck. Consider increasing to at least 2 vCPUs and 2 GB RAM.

3. **Client VM is the only copytool-capable node with 4 vCPUs / 4 GB RAM.** Running 4 copytool processes on a single client is feasible but they will compete for the same network link and memory. If you want true distribution, you could add additional client VMs.

4. **MDT sizes (200 MB each):** Metadata storage is small but should be sufficient for a moderate number of files. Not a concern unless you are creating tens of thousands of files.

5. **LNet configuration:** All nodes use `tcp(enp0s8)` over the VirtualBox host-only network. Bandwidth is limited by the virtual network adapter, not real hardware.

### What You Need to Do

1. **Verify VMs are running:**
   ```bash
   cd /Users/vinodjohnson/lustre-hsm-mover && vagrant status
   ```

2. **Collect live topology (if VMs are up):**
   ```bash
   python3 scripts/collect_lustre_topology.py
   ```
   This will show actual Lustre version, HSM state, tuning parameters, LDLM contention thresholds, thread pools, and annotated recommendations.

3. **Check/increase HSM max concurrent requests:**
   ```bash
   vagrant ssh mds -- sudo lctl get_param mdt.*.hsm.max_requests
   # If below 4, increase:
   vagrant ssh mds -- sudo lctl set_param mdt.*.hsm.max_requests=8
   ```

4. **Increase OST size for large file testing** -- edit `scripts/smoke_test_setup.sh` line 89, change `count=2000` to a larger value, then re-run setup.

5. **Optionally increase OSS VM resources** -- edit the Vagrantfile OSS block to set `vb.memory = "2048"` and `vb.cpus = 2`.

6. **Start 4 copytools on the client VM:**
   ```bash
   for i in 1 2 3 4; do
     vagrant ssh client -c "sudo systemd-run --unit=lhsm_oci_${i} \
       /tmp/lhsm_smoke/lhsm-oci --mount /mnt/lustre --backend localfs \
       --archive-dir /mnt/localfs_backend > /tmp/lhsm_smoke/lhsm-oci-${i}.log 2>&1"
   done
   ```

### Summary

Your environment is a small development/test Lustre cluster suitable for functional testing but constrained for concurrent large-file workloads. The single 2 GB OST and 1-vCPU OSS are the primary limits. Increase OST storage and OSS resources before running a 4-copytool large-file archive test.
