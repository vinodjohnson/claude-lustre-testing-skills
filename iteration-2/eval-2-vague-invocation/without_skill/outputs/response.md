# Lustre Test Environment -- What's Available

I was unable to run the live topology collection script (`scripts/collect_lustre_topology.py`) because bash execution was denied. Below is what I can tell you from the static configuration files (Vagrantfile and provisioning scripts).

## Cluster Layout (from Vagrantfile)

Your Lustre test environment is a 3-node Vagrant cluster running **Rocky Linux 8** (`bento/rockylinux-8`) with **Lustre 2.15.5**.

| VM | Hostname | IP | RAM | CPUs | Role |
|----|----------|-----|-----|------|------|
| mds | lustre-mds | 192.168.56.11 | 2 GB | 2 | MGS + MDS (metadata server) |
| oss | lustre-oss | 192.168.56.12 | 1 GB | 1 | OSS (object storage server) |
| client | lustre-client | 192.168.56.13 | 4 GB | 4 | Lustre client + HSM agent + k3s/Argo |

### MDS (lustre-mds)

- Combined MGS (Management Server) and MDS.
- Hosts the MDT (Metadata Target) and coordinates HSM operations.
- Lustre server kernel: `4.18.0-553.5.1.el8_lustre`.
- Packages: `lustre`, `kmod-lustre`, `kmod-lustre-osd-ldiskfs`, `lustre-osd-ldiskfs-mount`, `lustre-iokit`, `lustre-tests`.
- LNet configured on `enp0s8` (private network), using TCP.

### OSS (lustre-oss)

- Hosts OST(s) for file data storage.
- Single OST configuration (typical for dev/test -- not representative of production striping).
- Same Lustre server kernel and packages as MDS.
- LNet configured on `enp0s8` (private network), using TCP.

### Client (lustre-client)

- Mounts the Lustre filesystem and runs the HSM copytool (`lhsm-oci`).
- Lustre client kernel: `4.18.0-553.5.1.el8_10`.
- Packages: `lustre-client`, `kmod-lustre-client`.
- Also runs **k3s** and **Argo Workflows** (guest port 32746 forwarded to host port 2746 for the Argo UI).
- Has the most resources (4 GB RAM, 4 CPUs) since it runs the copytool and k3s.

## How to Get Live Data

To see the actual runtime state (HSM readiness, tuning parameters, thread counts, LDLM contention thresholds, LNet NIDs, mount options, etc.), run the topology collection script:

```bash
# Check if VMs are running first
cd /Users/vinodjohnson/lustre-hsm-mover && vagrant status

# If not running, start them
vagrant up

# Collect full topology (outputs JSON to stdout)
python3 scripts/collect_lustre_topology.py

# Or filter by role
python3 scripts/collect_lustre_topology.py mds
python3 scripts/collect_lustre_topology.py client
python3 scripts/collect_lustre_topology.py mds,oss
```

The script probes all running VMs via `vagrant ssh`, detects roles automatically, and returns structured JSON including:

- **MDS:** MDT UUIDs, MD stats, HSM control state and max requests, LDLM contention thresholds, MDS thread pool sizes, DNE settings (remote rename, striped directories), LNet NIDs.
- **OSS:** OST UUIDs, LDLM contention thresholds, OST thread pool sizes, LNet NIDs.
- **Client:** Mount points and options (flock, checksum, encrypt), OSC tuning (max RPCs in flight, max dirty MB), MDC tuning (max RPCs, max mod RPCs), LLite cache size, LNet NIDs.
- **Summary:** Total MDT count, OST count, client count, and whether HSM is ready (enabled on all MDS nodes).

The script also provides automated annotations -- for example, it will warn if HSM is not enabled, if RPC limits are low, or if the single-OST configuration limits I/O bandwidth testing.
