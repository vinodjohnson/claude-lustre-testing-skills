# lustre-topology Claude Skills

Two Claude Code skills for Lustre filesystem test planning, along with the
topology collector script they depend on.

## Skills

| Skill | Description |
|-------|-------------|
| `/topology` | Collects live Lustre topology from Vagrant VMs and surfaces the facts that matter for your test type |
| `/plan_lustre_test` | Plans a Lustre performance test; calls `/topology` automatically if no topology data is present |

## Requirements

- Python 3
- Vagrant + VirtualBox with Lustre VMs (`mds`, `oss`, `client`)
- Claude Code

## Install

```bash
# Into current directory
./install.sh

# Into a specific project
./install.sh /path/to/your/project
```

Then commit the installed files:

```bash
git add .claude/commands/lustre_background.md \
        .claude/commands/topology.md \
        .claude/commands/plan_lustre_test.md \
        scripts/collect_lustre_topology.py
git commit -m "chore: add lustre topology skills"
```

## Usage

```
/topology I want to benchmark rename performance
```

or jump straight to planning (topology runs automatically if needed):

```
/plan_lustre_test
```

## Files installed

```
.claude/commands/lustre_background.md     # shared Lustre background knowledge
.claude/commands/topology.md              # /topology skill
.claude/commands/plan_lustre_test.md      # /plan_lustre_test skill
scripts/collect_lustre_topology.py        # topology collector (requires Vagrant)
```
