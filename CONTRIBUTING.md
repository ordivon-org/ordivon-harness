# Contributing to Ordivon Harness

Harness changes must preserve the separation between durable Task authority, Agent Run semantics and physical execution.

## Prepare

```bash
git status --short --branch
git rev-parse HEAD
python3.12 --version
uv lock --check
```

Install the exact graph:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m pip check
```

A local sibling checkout may be used for compatibility experiments only when exact Host and Protocol revisions are recorded.

## Required checks

```bash
python -m compileall -q src tests scripts evals
python -m ruff check src tests scripts
python -W error::ResourceWarning -m unittest discover -s tests -v
python scripts/check_dependencies.py
python scripts/check_docs.py
python scripts/check_evidence.py
uv lock --check
scripts/local-acceptance check
python -m pip wheel --no-deps --wheel-dir /tmp/ordivon-harness-wheel .
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

Only `src/ordivon_harness/_host_compat/` may import `ordivon_host` directly. New application-facing APIs belong in `ordivon_harness.api`; owner-local persistence types should remain in their defining modules.

## Releases

Update `CHANGELOG.md`, compatibility documentation and evidence index for user-visible changes. Exact Host and Protocol pins, `uv.lock`, wheel metadata and live receipts must agree. See [`docs/RELEASES.md`](docs/RELEASES.md).

Security reports follow [`SECURITY.md`](SECURITY.md) and must remain private.
