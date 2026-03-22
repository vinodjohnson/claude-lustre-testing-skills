# Lustre Test Environment Overview

## What I Found

I was unable to run the live topology collection script (`scripts/collect_lustre_topology.py`) because Bash execution was denied. However, I can describe the environment based on the Vagrantfile and the topology collection script.

## Environment Configuration (from Vagrantfile)

Your Lustre test cluster consists of **3 Vagrant VMs** running on **Rocky Linux 8** (`bento/rockylinux-8`):

### 1. MDS (Metadata Server)
- **Hostname:** `lustre-mds`
- **IP:** `192.168.56.11`
- **Resources:** 2 GB RAM, 2 CPUs
- **Role:** Combined MGS (Management Server) and MDS. Hosts the MDT (Metadata Target) and manages HSM coordination.

### 2. OSS (Object Storage Server)
- **Hostname:** `lustre-oss`
- **IP:** `192.168.56.12`
- **Resources:** 1 GB RAM, 1 CPU
- **Role:** Hosts OST(s) (Object Storage Targets) that store actual file data.

### 3. Client (HSM Agent / Dev Machine)
- **Hostname:** `lustre-client`
- **IP:** `192.168.56.13`
- **Resources:** 4 GB RAM, 4 CPUs
- **Role:** Mounts the Lustre filesystem and runs the HSM copytool agent. Also runs k3s + Argo Workflows (port 2746 forwarded to host).
- **Port forwarding:** Guest port 32746 mapped to host port 2746 (Argo Workflows UI).

## Available Topology Collection Tool

The script `scripts/collect_lustre_topology.py` can collect live topology data. It:

- Probes all running VMs in parallel via `vagrant ssh`
- Detects each VM's role (MDS, OSS, client) by checking for MDTs, OSTs, and Lustre mounts
- Collects role-specific data including:
  - **MDS:** Lustre version, MDT UUIDs, MD stats, HSM control state, HSM max requests, LDLM contention, thread counts, DNE settings (remote rename, striped dirs), LNet NIDs
  - **OSS:** Lustre version, OST UUIDs, LDLM contention, thread counts, LNet NIDs
  - **Client:** Lustre version, mount points and options, OSC/MDC tuning (max RPCs, dirty MB), LLite cache size, LNet NIDs
- Provides annotations and tuning notes (e.g., warnings about low RPC limits, HSM not enabled, single-OST limitations)

### Usage

```bash
# Collect all roles
cd /Users/vinodjohnson/lustre-hsm-mover && python3 scripts/collect_lustre_topology.py

# Filter by role
python3 scripts/collect_lustre_topology.py mds
python3 scripts/collect_lustre_topology.py client
python3 scripts/collect_lustre_topology.py mds,oss
```

## To Get Live Data

To see the actual live state of your environment, run:

```bash
# First check if VMs are running
cd /Users/vinodjohnson/lustre-hsm-mover && vagrant status

# If VMs are not running, start them
vagrant up

# Then collect topology
python3 scripts/collect_lustre_topology.py
```

The script outputs JSON to stdout with a summary including MDT count, OST count, client count, and whether HSM is ready (enabled on all MDS nodes).
