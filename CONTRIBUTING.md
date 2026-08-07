# Contributing to Ordivon Harness

Harness changes must preserve the separation between durable Task authority, Agent Run semantics and physical execution.

## Prepare

```bash
git status --short --branch
git rev-parse HEAD
uv --version
uv python install 3.12
uv sync --locked
uv lock --check
```

A local sibling checkout may be used for compatibility experiments only when exact Host and Protocol revisions are recorded.

## Required checks

```bash
uv run python -m compileall -q src tests scripts evals
uvx ruff==0.15.17 check src tests scripts
uv run python -W error::ResourceWarning -m unittest discover -s tests -v
uv run python scripts/check_dependencies.py
uv run python scripts/check_docs.py
uv run python scripts/check_evidence.py
uv run python scripts/demo_deterministic_run.py
uv lock --check
scripts/local-acceptance check
uv build --wheel --out-dir /tmp/ordivon-harness-wheel
uv run python scripts/check_wheel.py /tmp/ordivon-harness-wheel
```

Run live acceptance when changing Provider adapters, Runtime lowering, Tool recovery, cancellation, secret handling, compatibility or completion evidence.

## Change standard

A contribution must identify:

1. the observed failure or repeated missing operation;
2. whether Host, Harness, Runtime, Provider or Domain owns the fact;
3. durable identities and UNKNOWN states affected;
4. tests or receipts that can falsify the change;
5. compatibility, migration, recovery, security and privacy impact;
6. canonical documents whose claims change.

Do not add a Harness database, daemon, generic scheduler, automatic Provider router or remote Host protocol without a real workload failure that cannot be solved by the current owner.

Harness source must not import `ordivon_host`. New application-facing APIs belong in `ordivon_harness.api`; owner-local persistence types should remain in their defining modules.

## Releases

Update `CHANGELOG.md`, compatibility documentation and evidence index for user-visible changes. Exact Host and Protocol pins, `uv.lock`, wheel metadata and live receipts must agree. See [`docs/RELEASES.md`](docs/RELEASES.md).

Security reports follow [`SECURITY.md`](SECURITY.md) and must remain private.
