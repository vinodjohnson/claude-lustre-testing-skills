I can discover the Lustre topology from your Vagrant VMs, but I want to collect the right data for your needs. A couple of quick questions first:

1. **What operation are you planning to test?** For example: HSM archive/restore, I/O throughput, metadata operations, or something else?

2. **Are you focused on correctness or performance?** And will the test involve concurrency (e.g., multiple copytools, parallel I/O)?

This helps me filter the collection to the relevant nodes and surface the parameters that actually matter for your test.
