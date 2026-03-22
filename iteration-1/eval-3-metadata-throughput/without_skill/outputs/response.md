# Lustre Environment Topology

I was unable to run the topology collection script (`scripts/collect_lustre_topology.py`) directly because bash execution is currently restricted. However, I have analyzed all the configuration files (Vagrantfile, provisioning scripts, and filesystem setup scripts) to give you a complete picture of your environment.

## Cluster Overview

Your Lustre cluster consists of **3 Vagrant VMs** running Rocky Linux 8 with Lustre 2.15.5:

| VM       | Hostname       | IP              | Role                    | CPUs | RAM    |
|----------|----------------|-----------------|-------------------------|------|--------|
| mds      | lustre-mds     | 192.168.56.11   | MGS + MDS (combined)    | 2    | 2048MB |
| oss      | lustre-oss     | 192.168.56.12   | OSS                     | 1    | 1024MB |
| client   | lustre-client  | 192.168.56.13   | Client + HSM Agent      | 4    | 4096MB |

## MDT Configuration (Critical for Metadata Throughput Testing)

**You have a single-MDT setup, not a multi-MDT setup.** The setup script (`scripts/setup_fs.sh`) creates only one MDT:

- **MDT-0**: Loopback device (`/tmp/mdt_loop`), 200MB, formatted with `--mgs --mdt --index=0`, mounted at `/mnt/mdt`
- No additional MDTs (MDT-1, MDT-2, etc.) are configured anywhere in the provisioning scripts
- The MGS and MDS are combined on the same node

This means **you cannot test multi-MDT metadata create throughput with the current configuration**. DNE (Distributed Namespace) features like striped directories and remote operations require at least 2 MDTs.

## OST Configuration

- **OST-0**: Single OST, loopback device (`/tmp/ost_loop`), 500MB, mounted at `/mnt/ost` on the OSS node
- MGS NID: `192.168.56.11@tcp`
- Filesystem name: `lustre`

## Client Configuration

- Mount point: `/mnt/lustre` (mounted via `192.168.56.11@tcp:/lustre`)
- HSM directory: `/mnt/lustre/hsm` (pinned to MDT-0 via `lfs mkdir -i 0`)
- LNet: TCP over `enp0s8` (private network)

## Implications for Metadata Create Throughput Testing

1. **Single MDT bottleneck**: All metadata operations (creates, lookups, unlinks) go to a single MDT on the `mds` VM. You are measuring single-MDT throughput only.

2. **Loopback storage**: The MDT uses a 200MB loopback file, not a real block device. This means:
   - I/O performance is limited by the host filesystem layer on top of VirtualBox's virtual disk
   - The small size (200MB) will fill up quickly during create-heavy tests
   - Journal commit latency will not be representative of production hardware

3. **Resource constraints**: The MDS VM has only 2 CPUs and 2GB RAM. MDS thread pool auto-scaling will be limited by these resources.

4. **No DNE features available**: With a single MDT, you cannot test:
   - Striped directories (`lfs mkdir -c 2 /mnt/lustre/dir`)
   - Remote directories on alternate MDTs (`lfs mkdir -i 1 /mnt/lustre/dir`)
   - Cross-MDT rename performance

## What You Need for Multi-MDT Testing

To test metadata create throughput on a multi-MDT setup, you would need to:

1. **Add a second MDT** on the MDS node (or add a second MDS VM):
   ```bash
   # On the MDS node:
   dd if=/dev/zero of=/tmp/mdt1_loop bs=1M count=200
   mkfs.lustre --reformat --fsname=lustre --mdt --mgsnode=192.168.56.11@tcp --index=1 --device-size=200000 /tmp/mdt1_loop
   mkdir -p /mnt/mdt1
   mount -t lustre -o loop /tmp/mdt1_loop /mnt/mdt1
   ```

2. **Create striped or distributed directories** on the client:
   ```bash
   # Stripe a directory across both MDTs
   lfs mkdir -c 2 /mnt/lustre/multi_mdt_test
   # Or place a directory on a specific MDT
   lfs mkdir -i 1 /mnt/lustre/mdt1_test
   ```

3. **Verify MDT count** after setup:
   ```bash
   lctl get_param mdt.*.uuid   # on MDS
   lfs df -i                    # on client, shows inode usage per MDT
   ```

## Running the Topology Script

To get live runtime data (thread counts, LDLM contention settings, HSM status, client tuning parameters), run:

```bash
cd /Users/vinodjohnson/lustre-hsm-mover && python3 scripts/collect_lustre_topology.py
```

This will SSH into each VM and collect detailed parameters including `mdc_max_mod_rpcs_in_flight` (which directly limits concurrent metadata mutations from the client) and MDS thread pool sizing.
