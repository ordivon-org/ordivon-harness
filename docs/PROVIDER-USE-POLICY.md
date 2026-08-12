# Provider Use Policy

Status: caller-owned Harness composition constraint.

Some exact inputs are lawful to process only on particular model/provider routes. Harness must not infer those rules from prose, classify providers as “safe”, or ask the model to remember them. The caller binds one immutable `HarnessProviderUsePolicy` into the Run Contract as a `provider-use-policy-v1` source reference.

The policy contains:
- exact restricted `HarnessBoundReference` values (ref, kind, digest);
- exact allowed `(providerId, adapterId, requestedModelId)` routes.

At `HarnessAgentRun.create/open`, Harness verifies the policy digest, confirms every restricted input is itself bound by the Run Contract, and checks the exact provider route **before provider construction and durable Run creation**. Mismatch is a composition error. A policy cannot be injected unless the Contract already commits to it, and a Contract that commits to a policy cannot run without the exact policy object.

This mechanism does not encode domain-specific rules. The first empirical requirement came from a data competition that permits local open-weight models while prohibiting competition data from being sent to hosted model APIs. The competition rule remains domain/source truth; Harness only enforces the caller-authored exact route constraint.

Unrestricted Runs remain unchanged. This is deliberately a thin admission invariant rather than a provider taxonomy or generalized data-governance engine.
