#!/usr/bin/env python3
"""
collect_lustre_topology.py - Discovers Lustre topology from Vagrant VMs.

Usage: python3 scripts/collect_lustre_topology.py [filter]
  filter: mds, oss, client, or all (default). Comma-separated for multiple.

Output: JSON to stdout. All VMs are always probed for role detection;
        the filter controls which nodes appear in the output.
"""

import subprocess
import json
import sys
import re
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------------------------------------------------------------------
# Shell scripts run inside each VM via vagrant ssh
# ---------------------------------------------------------------------------

PROBE_SCRIPT = r"""
echo '===PROBE:hostname==='
hostname
echo '===PROBE:ip==='
hostname -I 2>/dev/null | tr ' ' '\n' | grep -v '^10\.0\.2' | head -1
echo '===PROBE:has_mdt==='
lctl get_param mdt.*.uuid 2>/dev/null | head -5
echo '===PROBE:has_ost==='
lctl get_param obdfilter.*.uuid 2>/dev/null | head -5
echo '===PROBE:has_client==='
lctl get_param llite.*.uuid 2>/dev/null
echo '===PROBE:has_mgs==='
lctl get_param mgs.MGS.uuid 2>/dev/null
"""

MDS_COLLECT = r"""
echo '===SECTION:version==='
lctl get_param version 2>/dev/null
echo '===SECTION:mdt_uuids==='
lctl get_param mdt.*.uuid 2>/dev/null
echo '===SECTION:md_stats==='
lctl get_param mdt.*.md_stats 2>/dev/null
echo '===SECTION:hsm_control==='
lctl get_param mdt.*.hsm_control 2>/dev/null
echo '===SECTION:hsm_max_requests==='
lctl get_param mdt.*.hsm.max_requests 2>/dev/null
echo '===SECTION:ldlm_contention==='
lctl get_param ldlm.namespaces.mdt-*.contention_seconds ldlm.namespaces.mdt-*.contended_locks 2>/dev/null
echo '===SECTION:mds_threads==='
lctl get_param mds.MDS.mdt.threads_started mds.MDS.mdt.threads_min mds.MDS.mdt.threads_max 2>/dev/null
echo '===SECTION:mds_io_threads==='
lctl get_param mds.MDS.mdt_io.threads_started 2>/dev/null
echo '===SECTION:lnet==='
lctl get_param nis 2>/dev/null
echo '===SECTION:enable_remote_rename==='
lctl get_param mdt.*.enable_remote_rename 2>/dev/null
echo '===SECTION:enable_striped_dir==='
lctl get_param mdt.*.enable_striped_dir 2>/dev/null
echo '===SECTION:enable_dir_auto_split==='
lctl get_param mdt.*.enable_dir_auto_split 2>/dev/null
"""

OSS_COLLECT = r"""
echo '===SECTION:version==='
lctl get_param version 2>/dev/null
echo '===SECTION:ost_uuids==='
lctl get_param obdfilter.*.uuid 2>/dev/null
echo '===SECTION:ldlm_contention==='
lctl get_param ldlm.namespaces.filter-*.contention_seconds ldlm.namespaces.filter-*.contended_locks 2>/dev/null
echo '===SECTION:lnet==='
lctl get_param nis 2>/dev/null
echo '===SECTION:ost_threads==='
lctl get_param ost.OSS.ost.threads_started ost.OSS.ost.threads_min ost.OSS.ost.threads_max 2>/dev/null
echo '===SECTION:ost_io_threads==='
lctl get_param ost.OSS.ost_io.threads_started 2>/dev/null
"""

CLIENT_COLLECT = r"""
echo '===SECTION:version==='
lctl get_param version 2>/dev/null
echo '===SECTION:mount==='
mount | grep 'type lustre'
echo '===SECTION:llite_uuid==='
lctl get_param llite.*.uuid 2>/dev/null
echo '===SECTION:osc_tuning==='
lctl get_param osc.*.max_rpcs_in_flight osc.*.max_dirty_mb 2>/dev/null
echo '===SECTION:mdc_tuning==='
lctl get_param mdc.*.max_rpcs_in_flight mdc.*.max_mod_rpcs_in_flight 2>/dev/null
echo '===SECTION:llite_cache==='
lctl get_param llite.*.max_cached_mb 2>/dev/null
echo '===SECTION:lnet==='
lctl get_param nis 2>/dev/null
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Vagrant SSH adds ~5s overhead (connection setup, sudo). The lctl commands
# themselves complete in <1s, but under heavy load or with many MDTs/OSTs the
# collection script can take 10-20s. 45s gives ample headroom without hanging
# indefinitely if a VM is unresponsive.
SSH_TIMEOUT_SECONDS = 45


def vagrant_ssh(vm, script, timeout=SSH_TIMEOUT_SECONDS):
    """Run a bash script inside a VM via vagrant ssh. Returns (stdout, returncode)."""
    cmd = ['vagrant', 'ssh', vm, '--', 'sudo bash -s']
    try:
        r = subprocess.run(cmd, input=script, capture_output=True, text=True, timeout=timeout)
        return r.stdout, r.returncode
    except subprocess.TimeoutExpired:
        return '', -1


def running_vms():
    """Return list of running Vagrant VM names."""
    r = subprocess.run(['vagrant', 'status', '--machine-readable'],
                       capture_output=True, text=True)
    vms = []
    for line in r.stdout.splitlines():
        parts = line.split(',')
        if len(parts) >= 4 and parts[2] == 'state' and parts[3] == 'running':
            vms.append(parts[1])
    return vms


def parse_sections(output):
    """Split output by ===PROBE:key=== or ===SECTION:key=== markers into a dict."""
    sections = {}
    current = None
    buf = []
    for line in output.splitlines():
        m = re.match(r'===(?:PROBE|SECTION):(\w+)===', line)
        if m:
            if current is not None:
                sections[current] = '\n'.join(buf).strip()
            current = m.group(1)
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = '\n'.join(buf).strip()
    return sections


def parse_kv(text):
    """Parse lctl 'param.name=value' lines into {param_name: value} dict.
    The key returned is just the last component after the final dot."""
    result = {}
    for line in (text or '').splitlines():
        if '=' not in line:
            continue
        full_key, _, val = line.strip().partition('=')
        short_key = full_key.strip().rsplit('.', 1)[-1]
        val = val.strip()
        try:
            result[short_key] = int(val)
        except ValueError:
            result[short_key] = val
    return result


def first_val(kv, *keys):
    """Return the first matching value from a kv dict, or None."""
    for k in keys:
        if k in kv:
            return kv[k]
    return None


def parse_lustre_version(text):
    """Extract Lustre version string from `lctl get_param version` output."""
    for line in (text or '').splitlines():
        m = re.search(r'lustre:\s*(\S+)', line)
        if m:
            return m.group(1)
    return None


def parse_uuids(text, prefix):
    """Extract [{name, uuid}] from 'prefix.name.uuid=...' lctl lines."""
    items = []
    pattern = re.compile(rf'{re.escape(prefix)}\.([^.]+)\.uuid=(.+)')
    for line in (text or '').splitlines():
        m = pattern.match(line.strip())
        if m:
            items.append({'name': m.group(1), 'uuid': m.group(2).strip()})
    return items


def parse_md_stats(text):
    """Parse mdt.*.md_stats into a flat op->count dict (summed across MDTs)."""
    ops = {}
    in_stats = False
    for line in (text or '').splitlines():
        if 'md_stats=' in line:
            in_stats = True
            continue
        if in_stats:
            parts = line.split()
            if len(parts) >= 2 and parts[0] not in ('snapshot_time',):
                try:
                    ops[parts[0]] = ops.get(parts[0], 0) + int(parts[1])
                except ValueError:
                    pass
    return ops


def parse_lnet_nids(text):
    """Extract NID strings (e.g. 192.168.56.11@tcp) from lctl get_param nis."""
    nids = []
    for line in (text or '').splitlines():
        # Format: "nid: 192.168.56.11@tcp" or bare "192.168.56.11@tcp"
        m = re.search(r'(\d+\.\d+\.\d+\.\d+@\w+)', line)
        if m:
            nid = m.group(1)
            if nid not in nids:
                nids.append(nid)
    return nids


def parse_mount(text):
    """Parse mount lines into [{device, mountpoint, fstype, options}]."""
    mounts = []
    for line in (text or '').splitlines():
        m = re.match(r'(\S+) on (\S+) type (\S+) \((.+)\)', line.strip())
        if m:
            mounts.append({
                'device': m.group(1),
                'mountpoint': m.group(2),
                'fstype': m.group(3),
                'options': m.group(4),
            })
    return mounts

# ---------------------------------------------------------------------------
# Annotation heuristics (domain knowledge baked in — no LLM reasoning needed)
# ---------------------------------------------------------------------------

def annotate_mds(node):
    notes = []
    t = node.get('tuning', {})
    ldlm = node.get('ldlm', {})
    hsm = node.get('hsm', {})

    started = t.get('mdt_threads_started')
    tmin = t.get('mdt_threads_min')
    tmax = t.get('mdt_threads_max')
    if started is not None:
        notes.append(
            f"MDS thread pool: {started} threads started"
            + (f" (min={tmin}, max={tmax})" if tmin and tmax else "")
            + ". Pool auto-scales — if started equals max under load, MDS is at thread capacity."
        )

    if hsm.get('control') != 'enabled':
        ctrl = hsm.get('control', 'unknown')
        notes.append(
            f"HSM is '{ctrl}' on this MDT. Run: "
            f"lctl set_param mdt.*.hsm_control=enabled  before archive/restore tests."
        )

    cs = ldlm.get('contention_seconds')
    cl = ldlm.get('contended_locks')
    if cs is not None and cl is not None:
        msg = (f"LDLM contention thresholds: a lock is considered contended after {cl} waiters, "
               f"detection window is {cs}s. These are tuning knobs, not live counters.")
        if cs > 10:
            msg += " Window is relaxed — contention may go undetected in short test runs."
        elif cs < 2:
            msg += " Window is aggressive — ops will be flagged as contended quickly."
        notes.append(msg)

    if t.get('enable_remote_rename') == 1:
        notes.append("Remote (cross-MDT) rename is enabled. Relevant for DNE rename tests.")
    if t.get('enable_striped_dir') == 1:
        notes.append("Striped directories are enabled. Can create directories spanning multiple MDTs.")

    node['notes'] = notes


def annotate_oss(node):
    notes = []
    ldlm = node.get('ldlm', {})
    osts = node.get('osts', [])

    if len(osts) == 1:
        notes.append(
            "Single OST configuration. I/O bandwidth is limited to one backing device "
            "— not representative of production striping."
        )

    cs = ldlm.get('contention_seconds')
    cl = ldlm.get('contended_locks')
    if cs is not None and cl is not None:
        notes.append(
            f"LDLM extent lock contention threshold: {cl} waiters, {cs}s window."
        )

    node['notes'] = notes


def annotate_client(node):
    notes = []
    t = node.get('tuning', {})

    osc_rpcs = t.get('osc_max_rpcs_in_flight')
    if osc_rpcs is not None and osc_rpcs < 8:
        notes.append(
            f"osc_max_rpcs_in_flight={osc_rpcs} is below typical production values (8–256). "
            "I/O throughput will be artificially limited."
        )

    mdc_mod = t.get('mdc_max_mod_rpcs_in_flight')
    if mdc_mod is not None and mdc_mod < 8:
        notes.append(
            f"mdc_max_mod_rpcs_in_flight={mdc_mod} limits concurrent metadata mutations "
            "(rename, create, unlink) to the MDS. Values below 8 can bottleneck metadata-heavy tests. "
            "Tune via: lctl set_param mdc.*.max_mod_rpcs_in_flight=16"
        )

    llite_mb = t.get('llite_max_cached_mb')
    if llite_mb is not None:
        notes.append(
            f"Client metadata cache: {llite_mb}MB. "
            "Large caches reduce MDS load but can mask lock contention in short tests."
        )

    for mount in node.get('mounts', []):
        opts = mount.get('options', '')
        flock = 'yes' if 'flock' in opts else 'no'
        checksum = 'no' if 'nochecksum' in opts else 'yes'
        encrypt = 'yes' if 'encrypt' in opts else 'no'
        notes.append(
            f"Mount options: {opts}. "
            f"Key flags: flock={flock}, checksum={checksum}, encrypt={encrypt}."
        )

    node['notes'] = notes

# ---------------------------------------------------------------------------
# Role probing
# ---------------------------------------------------------------------------

def probe_vm(vm):
    stdout, _ = vagrant_ssh(vm, PROBE_SCRIPT)
    s = parse_sections(stdout)

    has_client = bool(s.get('has_client', '').strip())
    has_mdt = bool(s.get('has_mdt', '').strip())
    has_ost = bool(s.get('has_ost', '').strip())
    has_mgs = bool(s.get('has_mgs', '').strip())

    if has_client:
        role = 'client'
    elif has_mdt:
        role = 'mds'
    elif has_ost:
        role = 'oss'
    else:
        role = 'unknown'

    return {
        'vm_name': vm,
        'hostname': s.get('hostname', '').strip(),
        'ip': s.get('ip', '').strip(),
        'role': role,
        'is_mgs': has_mgs,
    }

# ---------------------------------------------------------------------------
# Role-specific data collection
# ---------------------------------------------------------------------------

def collect_mds(vm, meta):
    stdout, _ = vagrant_ssh(vm, MDS_COLLECT)
    s = parse_sections(stdout)

    mdts = parse_uuids(s.get('mdt_uuids', ''), 'mdt')
    md_stats = parse_md_stats(s.get('md_stats', ''))

    hsm_kv = parse_kv(s.get('hsm_control', ''))
    hsm_max_kv = parse_kv(s.get('hsm_max_requests', ''))

    ldlm_kv = parse_kv(s.get('ldlm_contention', ''))
    threads_kv = parse_kv(s.get('mds_threads', ''))
    io_kv = parse_kv(s.get('mds_io_threads', ''))
    dne_kv = {
        **parse_kv(s.get('enable_remote_rename', '')),
        **parse_kv(s.get('enable_striped_dir', '')),
        **parse_kv(s.get('enable_dir_auto_split', '')),
    }

    node = {
        **meta,
        'lustre_version': parse_lustre_version(s.get('version', '')),
        'mdts': mdts,
        'md_stats': md_stats,
        'hsm': {
            'control': first_val(hsm_kv, 'hsm_control'),
            'max_requests': first_val(hsm_max_kv, 'max_requests'),
        },
        'tuning': {
            'mdt_threads_started': first_val(threads_kv, 'threads_started'),
            'mdt_threads_min': first_val(threads_kv, 'threads_min'),
            'mdt_threads_max': first_val(threads_kv, 'threads_max'),
            'mdt_io_threads_started': first_val(io_kv, 'threads_started'),
            'enable_remote_rename': dne_kv.get('enable_remote_rename'),
            'enable_striped_dir': dne_kv.get('enable_striped_dir'),
            'enable_dir_auto_split': dne_kv.get('enable_dir_auto_split'),
        },
        'ldlm': {
            'contention_seconds': first_val(ldlm_kv, 'contention_seconds'),
            'contended_locks': first_val(ldlm_kv, 'contended_locks'),
        },
        'lnet': {'nids': parse_lnet_nids(s.get('lnet', ''))},
        'notes': [],
    }
    annotate_mds(node)
    return node


def collect_oss(vm, meta):
    stdout, _ = vagrant_ssh(vm, OSS_COLLECT)
    s = parse_sections(stdout)

    osts = parse_uuids(s.get('ost_uuids', ''), 'obdfilter')
    ldlm_kv = parse_kv(s.get('ldlm_contention', ''))
    threads_kv = parse_kv(s.get('ost_threads', ''))
    io_kv = parse_kv(s.get('ost_io_threads', ''))

    node = {
        **meta,
        'lustre_version': parse_lustre_version(s.get('version', '')),
        'osts': osts,
        'tuning': {
            'ost_threads_started': first_val(threads_kv, 'threads_started'),
            'ost_threads_min': first_val(threads_kv, 'threads_min'),
            'ost_threads_max': first_val(threads_kv, 'threads_max'),
            'ost_io_threads_started': first_val(io_kv, 'threads_started'),
        },
        'ldlm': {
            'contention_seconds': first_val(ldlm_kv, 'contention_seconds'),
            'contended_locks': first_val(ldlm_kv, 'contended_locks'),
        },
        'lnet': {'nids': parse_lnet_nids(s.get('lnet', ''))},
        'notes': [],
    }
    annotate_oss(node)
    return node


def collect_client(vm, meta):
    stdout, _ = vagrant_ssh(vm, CLIENT_COLLECT)
    s = parse_sections(stdout)

    osc_kv = parse_kv(s.get('osc_tuning', ''))
    mdc_kv = parse_kv(s.get('mdc_tuning', ''))
    llite_kv = parse_kv(s.get('llite_cache', ''))

    node = {
        **meta,
        'lustre_version': parse_lustre_version(s.get('version', '')),
        'mounts': parse_mount(s.get('mount', '')),
        'tuning': {
            'osc_max_rpcs_in_flight': first_val(osc_kv, 'max_rpcs_in_flight'),
            'osc_max_dirty_mb': first_val(osc_kv, 'max_dirty_mb'),
            'mdc_max_rpcs_in_flight': first_val(mdc_kv, 'max_rpcs_in_flight'),
            'mdc_max_mod_rpcs_in_flight': first_val(mdc_kv, 'max_mod_rpcs_in_flight'),
            'llite_max_cached_mb': first_val(llite_kv, 'max_cached_mb'),
        },
        'lnet': {'nids': parse_lnet_nids(s.get('lnet', ''))},
        'notes': [],
    }
    annotate_client(node)
    return node

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

ROLE_ORDER = {'client': 0, 'mds': 1, 'oss': 2, 'unknown': 3}


def main():
    filter_arg = (sys.argv[1] if len(sys.argv) > 1 else 'all').strip().lower()
    if filter_arg == 'all':
        requested = {'mds', 'oss', 'client'}
    else:
        requested = {r.strip() for r in filter_arg.split(',')}

    vms = running_vms()
    if not vms:
        print(json.dumps({'error': 'No running Vagrant VMs found'}), file=sys.stderr)
        sys.exit(1)

    # Step 1: probe all VMs in parallel
    probed = {}
    with ThreadPoolExecutor(max_workers=len(vms)) as ex:
        futures = {ex.submit(probe_vm, vm): vm for vm in vms}
        for f in as_completed(futures):
            meta = f.result()
            probed[meta['vm_name']] = meta

    # Step 2: collect role-specific data in parallel, filtered by requested roles
    collect_futures = {}
    with ThreadPoolExecutor(max_workers=len(vms)) as ex:
        for vm, meta in probed.items():
            role = meta['role']
            if role == 'unknown' or role not in requested:
                continue
            if role == 'mds':
                collect_futures[ex.submit(collect_mds, vm, meta)] = vm
            elif role == 'oss':
                collect_futures[ex.submit(collect_oss, vm, meta)] = vm
            elif role == 'client':
                collect_futures[ex.submit(collect_client, vm, meta)] = vm

        nodes = []
        for f in as_completed(collect_futures):
            nodes.append(f.result())

    nodes.sort(key=lambda n: ROLE_ORDER.get(n['role'], 3))

    mdt_count = sum(len(n.get('mdts', [])) for n in nodes if n['role'] == 'mds')
    ost_count = sum(len(n.get('osts', [])) for n in nodes if n['role'] == 'oss')
    client_count = sum(1 for n in nodes if n['role'] == 'client')
    mds_nodes = [n for n in nodes if n['role'] == 'mds']
    hsm_ready = bool(mds_nodes) and all(
        n.get('hsm', {}).get('control') == 'enabled' for n in mds_nodes
    )

    output = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'nodes': nodes,
        'summary': {
            'mdt_count': mdt_count,
            'ost_count': ost_count,
            'client_count': client_count,
            'hsm_ready': hsm_ready,
        },
    }

    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
