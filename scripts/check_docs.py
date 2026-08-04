#!/usr/bin/env python3
"""Validate canonical Harness documents and public repository contracts."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / ".ordivon/project.yaml"
REQUIRED_FRONTMATTER = {
    "schema_version",
    "id",
    "title",
    "type",
    "profile",
    "lifecycle",
    "source_role",
    "visibility",
    "owners",
    "audience",
    "updated",
    "summary",
    "evidence_status",
    "readiness",
    "applies_to",
}
REQUIRED_README_HEADINGS = {
    "Responsibility boundary",
    "Status",
    "What works",
    "What it does not do",
    "Requirements",
    "Quick start",
    "Public API",
    "Operator interface",
    "Documentation map",
    "Security and data",
    "License",
}
STABLE_API = {
    "CompletionMode",
    "DomainToolBridge",
    "DomainToolCatalog",
    "DomainToolLoopPlan",
    "DomainToolLoopRunner",
    "HarnessCancellationResult",
    "HarnessExecutionResult",
    "HarnessRunner",
    "HarnessRunPlan",
    "HarnessStatus",
    "RunHandle",
    "TaskContract",
    "ToolGrant",
}
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class DocumentError(ValueError):
    pass


def parse_frontmatter(path: Path) -> dict[str, object] | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        raise DocumentError(f"{path.relative_to(ROOT)} has unterminated frontmatter")
    values: dict[str, object] = {}
    active: str | None = None
    for line_number, raw in enumerate(text[4:end].splitlines(), start=2):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith("  - "):
            if active is None:
                raise DocumentError(
                    f"{path.relative_to(ROOT)}:{line_number} list item has no key"
                )
            value = values.setdefault(active, [])
            if not isinstance(value, list):
                raise DocumentError(
                    f"{path.relative_to(ROOT)}:{line_number} mixes list and scalar"
                )
            value.append(raw[4:].strip())
            continue
        match = re.fullmatch(r"([a-z][a-z0-9_]*)\s*:\s*(.*)", raw)
        if match is None:
            raise DocumentError(
                f"{path.relative_to(ROOT)}:{line_number} unsupported frontmatter"
            )
        key, scalar = match.groups()
        if key in values:
            raise DocumentError(f"{path.relative_to(ROOT)} repeats {key}")
        active = key if not scalar else None
        values[key] = scalar if scalar else []
    return values


def managed_paths() -> list[Path]:
    active = False
    paths: list[Path] = []
    for line in PROJECT.read_text(encoding="utf-8").splitlines():
        if line == "managed_paths:":
            active = True
            continue
        if active and re.match(r"^[a-zA-Z_]", line):
            break
        if active and line.startswith("  - "):
            paths.append(ROOT / line[4:].strip())
    if not paths:
        raise DocumentError("project manifest has no managed_paths")
    return paths


def validate_frontmatter() -> list[str]:
    errors: list[str] = []
    ids: dict[str, Path] = {}
    for path in managed_paths():
        if not path.is_file():
            errors.append(f"managed path is missing: {path.relative_to(ROOT)}")
            continue
        values = parse_frontmatter(path)
        if values is None:
            errors.append(f"managed document lacks frontmatter: {path.relative_to(ROOT)}")
            continue
        missing = sorted(REQUIRED_FRONTMATTER - values.keys())
        if missing:
            errors.append(
                f"{path.relative_to(ROOT)} lacks keys: {', '.join(missing)}"
            )
        identifier = values.get("id")
        if not isinstance(identifier, str) or not identifier:
            errors.append(f"{path.relative_to(ROOT)} has no scalar id")
        elif identifier in ids:
            errors.append(
                f"duplicate id {identifier}: {ids[identifier].relative_to(ROOT)} and {path.relative_to(ROOT)}"
            )
        else:
            ids[identifier] = path
        updated = values.get("updated")
        if not isinstance(updated, str) or DATE_PATTERN.fullmatch(updated) is None:
            errors.append(f"{path.relative_to(ROOT)} has invalid updated date")
        if values.get("source_role") != "canonical":
            errors.append(f"managed document is not canonical: {path.relative_to(ROOT)}")
    return errors


def validate_links() -> list[str]:
    errors: list[str] = []
    for path in ROOT.rglob("*.md"):
        if any(part in {".git", ".venv", "build", "dist"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        for match in LINK_PATTERN.finditer(text):
            target = match.group(1).strip().strip("<>").split(maxsplit=1)[0]
            if not target or target.startswith(("#", "https://", "http://", "mailto:")):
                continue
            relative = target.split("#", 1)[0].split("?", 1)[0]
            resolved = (path.parent / relative).resolve()
            try:
                resolved.relative_to(ROOT)
            except ValueError:
                errors.append(f"{path.relative_to(ROOT)} links outside repository: {target}")
                continue
            if not resolved.exists():
                errors.append(f"{path.relative_to(ROOT)} has broken link: {target}")
    return errors


def public_api_exports() -> set[str]:
    tree = ast.parse((ROOT / "src/ordivon_harness/api.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in node.targets
        ):
            return {
                item.value
                for item in node.value.elts
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            }
    return set()


def validate_public_contracts() -> list[str]:
    errors: list[str] = []
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    headings = set(re.findall(r"^## (.+)$", readme, re.MULTILINE))
    missing = sorted(REQUIRED_README_HEADINGS - headings)
    if missing:
        errors.append("README lacks headings: " + ", ".join(missing))
    if "/security/advisories/new" not in (ROOT / "SECURITY.md").read_text():
        errors.append("SECURITY.md lacks private reporting route")
    if "## Unreleased" not in (ROOT / "CHANGELOG.md").read_text():
        errors.append("CHANGELOG.md lacks Unreleased")
    if "enforcement: strict" not in PROJECT.read_text():
        errors.append("project documentation enforcement is not strict")

    required_repository_files = (
        ROOT / ".github/pull_request_template.md",
        ROOT / "scripts/check_wheel.py",
    )
    for path in required_repository_files:
        if not path.is_file():
            errors.append(f"required repository contract is missing: {path.relative_to(ROOT)}")

    canonical_guides = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in ("README.md", "CONTRIBUTING.md", "docs/QUICKSTART.md")
    )
    if "python -m ruff" in canonical_guides:
        errors.append("canonical setup still assumes Ruff is installed in the project environment")
    if canonical_guides.count("uvx ruff==0.15.17") < 3:
        errors.append("canonical setup does not pin the isolated Ruff invocation")
    if canonical_guides.count("scripts/check_wheel.py") < 3:
        errors.append("canonical setup omits isolated wheel verification")

    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github/workflows/release-acceptance.yml").read_text(
        encoding="utf-8"
    )
    for label, workflow in (("CI", ci), ("release acceptance", release)):
        if "scripts/check_wheel.py" not in workflow:
            errors.append(f"{label} does not verify the built wheel")
    if 'tags:\n      - "v*"' not in release:
        errors.append("release acceptance is not triggered by version tags")
    if "actions/upload-artifact@" not in release:
        errors.append("release acceptance does not retain the verified wheel")

    pull_request = (ROOT / ".github/pull_request_template.md").read_text(
        encoding="utf-8"
    )
    for heading in ("## Boundary", "## Evidence", "## Compatibility", "## Security and data"):
        if heading not in pull_request:
            errors.append(f"pull-request contract lacks heading: {heading}")

    if public_api_exports() != STABLE_API:
        errors.append(
            f"stable API differs: expected={sorted(STABLE_API)} observed={sorted(public_api_exports())}"
        )

    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    for stale in (
        "thin generic extension port",
        "They are not exported from the package root",
    ):
        if stale in architecture:
            errors.append(f"ARCHITECTURE.md retains stale claim: {stale}")
    if "Host-native source compatibility boundary" not in architecture:
        errors.append("ARCHITECTURE.md lacks the Host-native boundary")

    source_root = ROOT / "src/ordivon_harness"
    for path in source_root.rglob("*.py"):
        relative = path.relative_to(source_root)
        if relative.parts and relative.parts[0] == "_host_compat":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            elif isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            for module in modules:
                if module == "ordivon_host" or module.startswith("ordivon_host."):
                    errors.append(
                        f"raw Host import outside _host_compat: {relative}:{node.lineno}:{module}"
                    )
    return errors


def main() -> int:
    errors: list[str] = []
    for validator in (validate_frontmatter, validate_links, validate_public_contracts):
        try:
            errors.extend(validator())
        except (DocumentError, OSError, SyntaxError, UnicodeError) as error:
            errors.append(str(error))
    if errors:
        for error in sorted(set(errors)):
            print(f"docs: {error}", file=sys.stderr)
        return 1
    print("documentation contract: valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
