# Lustre Topology Discovery

## Step 1: Test Intent

Your test: **HSM archive with 4 concurrent copytools writing large files**

- Operation: HSM archive
- Concurrency: 4 copytools in parallel
- Workload: large files

This is an HSM concurrency test. I need MDS and client data to check whether the coordinator can handle 4 parallel requests. Collection filter: `mds,client`.

## Step 2: Collect from VMs

**Command attempted:**

```bash
cd /Users/vinodjohnson/lustre-hsm-mover && python3 scripts/collect_lustre_topology.py mds,client
```

**Result: FAILED -- Bash execution was denied.**

The collector script requires shell access to run `vagrant ssh` into each VM and execute `lctl get_param` commands. Without Bash permission, the live topology cannot be collected.

## Action Required

The topology collector could not run. To proceed, you need to:

1. **Grant Bash permission** to this session, then re-run this skill.
2. Or **run the collector manually** and paste the JSON output:
   ```bash
   cd /Users/vinodjohnson/lustre-hsm-mover
   python3 scripts/collect_lustre_topology.py mds,client
   ```

Per the skill's rules: "If the script fails, stop -- user needs to bring up VMs." In this case the failure is not VM-related but a permission issue with the current session.

---

**Key parameter to watch for your test (once topology is collected):**

| Fact | Why it matters |
|------|----------------|
| `hsm_control` | Must be `enabled` on all MDTs for archive to work |
| `max_requests` | If < 4, some of your 4 copytools will queue rather than run concurrently |
| MDT count | Single MDT means all HSM coordination funnels through one node |
| Client mount | Confirms the client can see the filesystem for copytool registration |

Once I have the live topology JSON, I can give you exact values and flag any bottlenecks for your 4-copytool concurrency test.
