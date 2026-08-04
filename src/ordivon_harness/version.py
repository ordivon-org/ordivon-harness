"""Single runtime accessor for the installed Harness package version."""

from importlib.metadata import PackageNotFoundError, version

_FALLBACK_VERSION = "0.6.0"


def package_version() -> str:
    try:
        return version("ordivon-harness")
    except PackageNotFoundError:
        return _FALLBACK_VERSION


__all__ = ["package_version"]
