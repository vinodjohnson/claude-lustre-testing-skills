I can help you understand your Lustre test environment. Before I collect topology data from the VMs, a couple of quick questions so I pull the right information:

1. **What operation are you testing?** For example: HSM archive/restore workflows, I/O throughput, metadata operations, or something else?
2. **Are you focused on correctness or performance?** If concurrency or race conditions are part of the picture, that changes which parameters I prioritize.

Once I know the general direction, I will collect the relevant subset of the topology and present it organized around your test -- no raw config dumps.
