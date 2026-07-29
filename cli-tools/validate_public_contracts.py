#!/usr/bin/env python3
"""Validate packaged nddev-mimocode-app artifacts without runtime side effects."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:[-+].*)?\Z")
SETUP_IDS = ["nddev-builder"]
PROFILE_IDS = ["full-auto", "safe"]
SETUP_LIFECYCLE = [
    "list",
    "status",
    "plan",
    "install",
    "update",
    "switch",
    "migrate",
    "restore",
    "remove",
]
FULL_LIFECYCLE = [
    *SETUP_LIFECYCLE,
    "software-status",
    "install-cli",
    "update-cli",
    "remove-cli",
    "launch",
]
SUPPORTED_HOSTS = ["macos-arm64", "macos-x64", "ubuntu-glibc-arm64", "ubuntu-glibc-x64"]
REJECTED_HOSTS = ["windows", "non-ubuntu-linux", "linux-musl", "unsupported-architecture"]
PRIVATE_PATH_MARKERS = {
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "__pycache__",
    "benchmarks",
    "tests",
    "validation",
}
PRIVATE_TEXT_MARKERS = ("validation/" + "nddev-mimocode-app", ".ser" + "ena")
SHARED_WORKFLOW_PIN = "2ccb80e96f5771b6a6b4eae63a4f47e232906dc7"


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def read_json(relative: str, errors: list[str]) -> dict[str, Any] | None:
    path = ROOT / relative
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"{relative}: unreadable or invalid JSON: {exc}")
        return None
    if not isinstance(value, dict):
        errors.append(f"{relative}: top-level value must be an object")
        return None
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_public_boundary(errors: list[str]) -> None:
    for path in ROOT.rglob("*"):
        if ".git" in path.parts:
            continue
        relative = path.relative_to(ROOT)
        require(
            not any(part in PRIVATE_PATH_MARKERS for part in relative.parts),
            f"{relative}: private path marker in public artifact",
            errors,
        )
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for marker in PRIVATE_TEXT_MARKERS:
            require(marker not in content, f"{relative}: private text marker {marker!r}", errors)


def validate_versions(errors: list[str]) -> None:
    version_text = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    build = read_json("build/version.json", errors)
    manifest = read_json("build/manifest.json", errors)
    contract = read_json("config/nddev-contract.json", errors)
    baseline = read_json("references/mimocode-baseline.json", errors)
    if None in (build, manifest, contract, baseline):
        return
    assert build is not None
    assert manifest is not None
    assert contract is not None
    assert baseline is not None

    require(SEMVER.fullmatch(version_text) is not None, "VERSION: invalid semantic version", errors)
    require(build.get("build_version") == version_text, "build version mismatch", errors)
    require(manifest.get("build_version") == version_text, "manifest version mismatch", errors)
    require(
        contract.get("builder_capability", {}).get("version")
        == build.get("nddev_builder_extension_version"),
        "builder extension version mismatch",
        errors,
    )
    runtime = build.get("mimocode_tested")
    require(
        manifest.get("runtime_compatibility", {}).get("tested_version") == runtime,
        "manifest runtime version mismatch",
        errors,
    )
    require(
        contract.get("runtime_compatibility", {}).get("tested_version") == runtime,
        "contract runtime version mismatch",
        errors,
    )
    require(
        baseline.get("release", {}).get("version") == runtime,
        "baseline runtime version mismatch",
        errors,
    )
    require(
        baseline.get("release", {}).get("tag") == build.get("mimocode_release_tag"),
        "baseline release tag mismatch",
        errors,
    )
    install = baseline.get("install", {})
    require(
        install.get("script") == build.get("official_installer"),
        "installer URL mismatch",
        errors,
    )
    require(
        install.get("script_size") == build.get("official_installer_size"),
        "installer size mismatch",
        errors,
    )
    require(
        install.get("script_sha256") == build.get("official_installer_sha256"),
        "installer digest mismatch",
        errors,
    )


def validate_catalog(errors: list[str]) -> None:
    contract = read_json("config/nddev-contract.json", errors)
    manifest = read_json("build/manifest.json", errors)
    baseline = read_json("references/mimocode-baseline.json", errors)
    if None in (contract, manifest, baseline):
        return
    assert contract is not None
    assert manifest is not None
    assert baseline is not None

    setup_dirs = sorted(path.name for path in (ROOT / "setups").iterdir() if path.is_dir())
    profile_dirs = sorted(path.name for path in (ROOT / "profiles").iterdir() if path.is_dir())
    require(setup_dirs == SETUP_IDS, "setups/: unexpected setup catalog", errors)
    require(profile_dirs == sorted(PROFILE_IDS), "profiles/: unexpected profile catalog", errors)
    setup_system = contract.get("setup_system", {})
    require(setup_system.get("setup_ids") == SETUP_IDS, "contract setup ids mismatch", errors)
    require(setup_system.get("profile_ids") == PROFILE_IDS, "contract profile ids mismatch", errors)
    require(
        setup_system.get("lifecycle") == FULL_LIFECYCLE,
        "contract lifecycle mismatch",
        errors,
    )
    require(
        manifest.get("setup_lifecycle") == SETUP_LIFECYCLE,
        "manifest setup lifecycle mismatch",
        errors,
    )

    setup = read_json("setups/nddev-builder/setup.json", errors)
    native = read_json("setups/nddev-builder/mimocode.json", errors)
    if setup is not None:
        require(setup.get("id") == "nddev-builder", "setup id mismatch", errors)
        require(setup.get("builder_default_on") is True, "builder must be default-on", errors)
    if native is not None:
        require(native.get("skills") == {"paths": ["./skills"]}, "native skills mismatch", errors)
        require(native.get("plugin") == [], "default plugins must be disabled", errors)
        require(native.get("mcp") == {}, "default MCP catalog must be empty", errors)

    defaults: list[str] = []
    for profile_id in PROFILE_IDS:
        profile = read_json(f"profiles/{profile_id}/profile.json", errors)
        if profile is None:
            continue
        require(profile.get("id") == profile_id, f"profiles/{profile_id}: id mismatch", errors)
        if profile.get("default") is True:
            defaults.append(profile_id)
    require(defaults == ["full-auto"], "full-auto must be the only default profile", errors)

    software = contract.get("software_install", {})
    hosts = baseline.get("supported_product_hosts", {})
    require(
        software.get("supported_product_host_ids") == SUPPORTED_HOSTS,
        "supported host ids mismatch",
        errors,
    )
    require(
        software.get("rejected_product_host_ids") == REJECTED_HOSTS,
        "rejected host ids mismatch",
        errors,
    )
    require(hosts.get("supported_ids") == SUPPORTED_HOSTS, "baseline host ids mismatch", errors)
    assets = baseline.get("release", {}).get("assets", {})
    require(
        sorted(assets) == sorted(software.get("observed_uploaded_runtime_asset_ids", [])),
        "runtime asset inventory mismatch",
        errors,
    )
    for asset_id, asset in assets.items():
        require(isinstance(asset, dict), f"asset {asset_id}: record must be an object", errors)
        if not isinstance(asset, dict):
            continue
        require(
            isinstance(asset.get("size"), int) and asset["size"] > 0,
            f"asset {asset_id}: invalid size",
            errors,
        )
        require(
            re.fullmatch(r"[0-9a-f]{64}", str(asset.get("sha256", ""))) is not None,
            f"asset {asset_id}: invalid sha256",
            errors,
        )


def validate_builder_projection(errors: list[str]) -> None:
    required = [
        "plugins/nddev-builder/agents/nddev-builder.md",
        "plugins/nddev-builder/instructions/nddev-builder.md",
        "plugins/nddev-builder/skills/nddev-builder/SKILL.md",
        "setups/nddev-builder/AGENTS.md",
    ]
    for relative in required:
        path = ROOT / relative
        require(path.is_file(), f"missing builder artifact: {relative}", errors)
        if path.is_file():
            require(path.stat().st_size > 0, f"empty builder artifact: {relative}", errors)


def validate_release_workflows_and_runtime_integrity(errors: list[str]) -> None:
    workflows = {
        "actionlint.yml", "codeql.yml", "dependency-review.yml", "release.yml",
        "scorecard.yml", "secret-scan.yml", "zizmor.yml",
    }
    for name in workflows:
        path = ROOT / ".github/workflows" / name
        require(path.is_file() and not path.is_symlink(), f"missing workflow: {name}", errors)
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if name != "release.yml":
            require(SHARED_WORKFLOW_PIN in text, f"{name}: shared workflow pin mismatch", errors)
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    for fragment in (
        "permissions: {}",
        'tags:\n      - "[0-9]+.[0-9]+.[0-9]+"',
        f"release-supply-chain.yml@{SHARED_WORKFLOW_PIN}",
        "version: ${{ github.ref_name }}",
        "package_name: nddev-mimocode-app",
        "archive_paths:",
        "runtime_paths:",
    ):
        require(fragment in release, f"release workflow omits {fragment}", errors)
    required_roots = {
        "AGENTS.md", ".claude/CLAUDE.md", "README.md", "LICENSE", "VERSION",
        "build", "cli-tools", "config", "plugins", "profiles", "references", "setups",
    }
    require(
        required_roots.issubset(set(release.split())),
        "release archive/runtime membership is incomplete",
        errors,
    )
    manager = (ROOT / "cli-tools/nddev_mimocode.py").read_text(encoding="utf-8")
    for fragment in (
        "detect_platform_selection",
        "O_NOFOLLOW",
        "cleanup_pending",
        "MIMOCODE_DISABLE_PROJECT_CONFIG",
        "MIMOCODE_DISABLE_EXTERNAL_SKILLS",
        "MIMOCODE_DISABLE_AUTOUPDATE",
        "validate_launch_managed_config_boundary",
        "validate_launch_project_boundary",
    ):
        require(fragment in manager, f"manager runtime-integrity fragment missing: {fragment}", errors)
    require("marketplace.json" not in manager, "manager must not synthesize a marketplace", errors)


def main() -> int:
    errors: list[str] = []
    validate_public_boundary(errors)
    validate_versions(errors)
    validate_catalog(errors)
    validate_builder_projection(errors)
    validate_release_workflows_and_runtime_integrity(errors)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("nddev-mimocode-app public contracts ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
