# Change contract

## Boundary

- [ ] The change names the observed failure or missing operation.
- [ ] Host, Harness, Runtime, Provider and Domain ownership remains explicit.
- [ ] No new database, daemon, scheduler, retry authority or hidden-state dependency was added without a demonstrated workload requirement.

## Evidence

- [ ] Deterministic tests cover the changed invariant or failure path.
- [ ] UNKNOWN, cancellation, replay and recovery consequences were considered.
- [ ] A live receipt is attached or referenced when Provider, Runtime, Tool, cancellation or completion semantics changed.

## Compatibility

- [ ] Public API impact is stated.
- [ ] Durable object/schema and retained-state impact is stated.
- [ ] Host, Protocol and Runtime catalog compatibility is stated.
- [ ] Changelog and canonical documents were updated when their claims changed.

## Security and data

- [ ] Credentials, prompts, private source and sensitive Artifact content are absent from the pull request.
- [ ] ToolGrant, Provider disclosure, persistence, export and deletion impact was reviewed.
- [ ] Suspected vulnerabilities are reported privately rather than described here.
