#!/usr/bin/env python3
"""Validate nddev-mimocode-app public contracts without live side effects."""
# ruff: noqa: E402

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import contextlib
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import tempfile
from io import StringIO
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANAGER_PATH = ROOT / "cli-tools" / "nddev_mimocode.py"
MANAGER_SPEC = importlib.util.spec_from_file_location("nddev_mimocode", MANAGER_PATH)
if MANAGER_SPEC is None or MANAGER_SPEC.loader is None:
    raise RuntimeError(f"cannot load {MANAGER_PATH}")
nddev_mimocode = importlib.util.module_from_spec(MANAGER_SPEC)
sys.modules[MANAGER_SPEC.name] = nddev_mimocode
MANAGER_SPEC.loader.exec_module(nddev_mimocode)

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
JSON_COMMANDS = [command for command in FULL_LIFECYCLE if command != "launch"]
TARGET_COMMANDS = [command for command in FULL_LIFECYCLE if command != "list"]
SHARED_CI_COMMIT = "2ccb80e96f5771b6a6b4eae63a4f47e232906dc7"
SHARED_CI_VERSION = "0.12.0"
SHARED_CALLERS = {
    "actionlint.yml": ".github/workflows/actionlint.yml",
    "codeql.yml": ".github/workflows/public-codeql.yml",
    "dependency-review.yml": ".github/workflows/public-dependency-review.yml",
    "release.yml": ".github/workflows/release-supply-chain.yml",
    "scorecard.yml": ".github/workflows/public-scorecard-json.yml",
    "secret-scan.yml": ".github/workflows/secret-scan.yml",
    "zizmor.yml": ".github/workflows/zizmor-sarif.yml",
}
RELEASE_ARCHIVE_PATHS = [
    "AGENTS.md",
    ".claude/CLAUDE.md",
    "README.md",
    "LICENSE",
    "VERSION",
    "CHANGELOG.md",
    "SECURITY.md",
    ".gds/repository.yaml",
    ".github",
    "build",
    "cli-tools",
    "config",
    "plugins",
    "profiles",
    "references",
    "setups",
]
RELEASE_RUNTIME_PATHS = [
    "AGENTS.md",
    ".claude/CLAUDE.md",
    "README.md",
    "LICENSE",
    "VERSION",
    "build",
    "cli-tools",
    "config",
    "plugins",
    "profiles",
    "references",
    "setups",
]
REQUIRED_RELEASE_PERMISSIONS = {
    "contents": "write",
    "id-token": "write",
    "attestations": "write",
    "artifact-metadata": "write",
}
REQUIRED_RELEASE_INPUTS = {"version", "package_name", "archive_paths", "runtime_paths"}
REQUIRED_CONTRACT_ROOTS = {
    "build",
    "cli-tools",
    "config",
    "plugins",
    "profiles",
    "references",
    "setups",
}
PRIVATE_PATH_MARKERS = {
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "__pycache__",
    "benchmarks",
    "tests",
    "validation",
}
PRIVATE_TEXT_MARKERS = (
    "validation/" + "nddev-mimocode-app",
    ".ser" + "ena",
)
OBSERVED_UPLOADED_RUNTIME_ASSET_IDS = [
    "darwin-arm64",
    "darwin-x64-baseline",
    "darwin-x64",
    "linux-arm64-musl",
    "linux-arm64",
    "linux-x64-baseline-musl",
    "linux-x64-baseline",
    "linux-x64-musl",
    "linux-x64",
    "windows-arm64",
    "windows-x64-baseline",
    "windows-x64",
]
RELEASE_PAGE_ASSET_COUNT = 14
GENERATED_SOURCE_DOWNLOADS = [
    {
        "name": "Source code (zip)",
        "url": "https://github.com/XiaomiMiMo/MiMo-Code/archive/refs/tags/v0.1.9.zip",
    },
    {
        "name": "Source code (tar.gz)",
        "url": "https://github.com/XiaomiMiMo/MiMo-Code/archive/refs/tags/v0.1.9.tar.gz",
    },
]
SUPPORTED_PRODUCT_HOST_IDS = [
    "macos-arm64",
    "macos-x64",
    "ubuntu-glibc-arm64",
    "ubuntu-glibc-x64",
]
REJECTED_PRODUCT_HOST_IDS = [
    "windows",
    "non-ubuntu-linux",
    "linux-musl",
    "unsupported-architecture",
]
PRODUCT_HOST_ASSET_SELECTION = {
    "macos-arm64": {"default": "darwin-arm64"},
    "macos-x64": {"avx2": "darwin-x64", "baseline": "darwin-x64-baseline"},
    "ubuntu-glibc-arm64": {"default": "linux-arm64"},
    "ubuntu-glibc-x64": {"avx2": "linux-x64", "baseline": "linux-x64-baseline"},
}
FORBIDDEN_BOOTSTRAP_OVERRIDE_NAMES = (
    "NDDEV_MIMOCODE_BOOTSTRAP_ROOT",
    "NDDEV_MIMOCODE_LOCK_ROOT",
    "MIMOCODE_BOOTSTRAP_LOCK_ROOT",
    "MIMOCODE_LOCK_ROOT",
)
PLACEHOLDER_MARKER = "skele" + "ton"
EXPECTED_FIXED_RUNTIME_ENV = {
    "MIMOCODE_DISABLE_AUTOUPDATE": "1",
    "MIMOCODE_DISABLE_CLAUDE_CODE": "1",
    "MIMOCODE_DISABLE_CLAUDE_CODE_COMMANDS": "1",
    "MIMOCODE_DISABLE_CLAUDE_CODE_MCP": "1",
    "MIMOCODE_DISABLE_CLAUDE_IMPORT": "1",
    "MIMOCODE_DISABLE_EXTERNAL_SKILLS": "1",
    "MIMOCODE_DISABLE_LSP_DOWNLOAD": "1",
    "MIMOCODE_DISABLE_MODELS_FETCH": "1",
    "MIMOCODE_DISABLE_PROJECT_CONFIG": "1",
    "MIMOCODE_DISABLE_PROVIDER_ENV": "1",
    "MIMOCODE_ENABLE_ANALYSIS": "0",
    "MIMOCODE_PURE": "1",
}
EXPECTED_PROJECT_BOUNDARY_PATHS = [
    ".mimocode/mimocode.json",
    ".mimocode/mimocode.jsonc",
    ".mimocode/plugin",
    ".mimocode/plugins",
    ".mimocode/tools",
    ".mimocode/tui",
    ".agents/skills",
    ".claude",
    ".claude.json",
    ".codex/skills",
    ".opencode/skills",
]


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def require_manager_failure(callable_obj: Any, message: str, errors: list[str]) -> None:
    try:
        callable_obj()
    except nddev_mimocode.MiMoCodeSetupError:
        return
    errors.append(message)


def require_exception(
    callable_obj: Any, exception_type: type[BaseException], message: str, errors: list[str]
) -> None:
    try:
        callable_obj()
    except exception_type:
        return
    errors.append(message)


def read_json(relative: str) -> dict[str, Any]:
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"{relative} must contain a JSON object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_uid() -> int | str:
    if hasattr(os, "geteuid"):
        return os.geteuid()
    if hasattr(os, "getuid"):
        return os.getuid()
    return "unknown"


def bootstrap_product_root(system_root: Path) -> Path:
    return system_root / f".{nddev_mimocode.PRODUCT_NAME}-{current_uid()}-lifecycle-locks"


def is_product_lifecycle_lock_path(path: Path) -> bool:
    try:
        return (
            path.resolve()
            == (
                bootstrap_product_root(nddev_mimocode.fixed_system_temp_root())
                / nddev_mimocode.BOOTSTRAP_GLOBAL_LOCK_NAME
            ).resolve()
        )
    except OSError:
        return False


def is_bootstrap_lifecycle_lock_path(path: Path) -> bool:
    if path.name == nddev_mimocode.BOOTSTRAP_GLOBAL_LOCK_NAME:
        return False
    return path.name.endswith(nddev_mimocode.BOOTSTRAP_LOCK_SUFFIX) or (
        nddev_mimocode.BOOTSTRAP_LOCK_SUFFIX in path.name and ".nddev.tmp." in path.name
    )


def path_identity(path: Path) -> tuple[int, int, int, int, int, int] | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid, info.st_size)


def real_bootstrap_snapshot(path: Path) -> dict[str, Any]:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {"exists": False}
    snapshot: dict[str, Any] = {"exists": True, "root": path_identity(path), "entries": []}
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        return snapshot
    entries = sorted(path.iterdir(), key=lambda item: item.name)
    if len(entries) > 1000:
        snapshot["too_many_entries"] = len(entries)
        return snapshot
    for child in entries:
        child_info = child.lstat()
        record: dict[str, Any] = {
            "name": child.name,
            "identity": path_identity(child),
            "type": "other",
        }
        if (
            stat.S_ISREG(child_info.st_mode)
            and child_info.st_size <= nddev_mimocode.METADATA_MAX_BYTES
        ):
            record["type"] = "file"
            record["sha256"] = sha256_file(child)
        elif stat.S_ISDIR(child_info.st_mode):
            record["type"] = "directory"
        elif stat.S_ISLNK(child_info.st_mode):
            record["type"] = "symlink"
            record["target"] = os.readlink(child)
        snapshot["entries"].append(record)
    return snapshot


@contextlib.contextmanager
def isolated_bootstrap_root(errors: list[str]) -> Any:
    original = nddev_mimocode.fixed_system_temp_root
    real_root = original()
    real_product_root = bootstrap_product_root(real_root)
    before = real_bootstrap_snapshot(real_product_root)
    with tempfile.TemporaryDirectory(prefix="nddev-mimocode-bootstrap-root-") as raw:
        injected = Path(raw)
        injected.chmod(0o1777)

        def injected_fixed_system_temp_root() -> Path:
            return injected

        nddev_mimocode.fixed_system_temp_root = injected_fixed_system_temp_root
        try:
            yield injected
        finally:
            nddev_mimocode.fixed_system_temp_root = original
    after = real_bootstrap_snapshot(real_product_root)
    require(before == after, "public validator touched the real system bootstrap lock root", errors)


def relative_files() -> list[str]:
    result: list[str] = []
    for path in sorted(ROOT.rglob("*"), key=lambda item: str(item.relative_to(ROOT))):
        relative = path.relative_to(ROOT)
        if ".git" in relative.parts:
            continue
        if path.is_symlink():
            raise AssertionError(f"symlink is not allowed: {relative}")
        if any(part in PRIVATE_PATH_MARKERS for part in relative.parts):
            raise AssertionError(f"private/cache path is not allowed: {relative}")
        if path.is_file():
            result.append(str(relative))
    return result


def validate_no_private_markers(errors: list[str]) -> None:
    try:
        files = relative_files()
    except AssertionError as exc:
        errors.append(str(exc))
        return
    for raw in files:
        path = ROOT / raw
        text = path.read_text(encoding="utf-8", errors="ignore")
        require(
            PLACEHOLDER_MARKER not in text.lower(), f"placeholder marker remains in {raw}", errors
        )
        for marker in PRIVATE_TEXT_MARKERS:
            require(marker not in text, f"private marker {marker!r} appears in {raw}", errors)


def validate_claude_bridge(errors: list[str]) -> None:
    agents = ROOT / "AGENTS.md"
    claude_dir = ROOT / ".claude"
    bridge = claude_dir / "CLAUDE.md"
    for path, label in (
        (agents, "AGENTS.md"),
        (claude_dir, ".claude"),
        (bridge, ".claude/CLAUDE.md"),
    ):
        try:
            info = path.lstat()
        except FileNotFoundError:
            errors.append(f"{label} is missing")
            return
        require(not stat.S_ISLNK(info.st_mode), f"{label} must not be a symlink", errors)
    require(agents.is_file(), "AGENTS.md must be a regular file", errors)
    require(claude_dir.is_dir(), ".claude must be a real directory", errors)
    require(
        sorted(item.name for item in claude_dir.iterdir()) == ["CLAUDE.md"],
        ".claude must contain only CLAUDE.md",
        errors,
    )
    require(bridge.is_file(), ".claude/CLAUDE.md must be a regular file", errors)
    require(bridge.read_bytes() == b"@../AGENTS.md\n", ".claude/CLAUDE.md bytes mismatch", errors)


def validate_versions(errors: list[str]) -> None:
    version = (ROOT / "VERSION").read_text(encoding="ascii").strip()
    build = read_json("build/version.json")
    manifest = read_json("build/manifest.json")
    contract = read_json("config/nddev-contract.json")
    baseline = read_json("references/mimocode-baseline.json")
    require(SEMVER.fullmatch(version) is not None, "VERSION is not SemVer", errors)
    require(version == nddev_mimocode.VERSION, "manager VERSION mismatch", errors)
    require(build.get("schema_version") == 2, "build schema mismatch", errors)
    require(manifest.get("schema_version") == 2, "manifest schema mismatch", errors)
    require(contract.get("contract_version") == 2, "contract version mismatch", errors)
    require(build.get("build_version") == version, "build version mismatch", errors)
    require(manifest.get("build_version") == version, "manifest version mismatch", errors)
    require(
        contract.get("builder_capability", {}).get("version") == version,
        "builder version mismatch",
        errors,
    )
    require(
        build.get("nddev_builder_extension_version") == version,
        "builder extension version mismatch",
        errors,
    )
    require(build.get("python_requires") == ">=3.9", "build python_requires mismatch", errors)
    require(
        build.get("mimocode_tested") == nddev_mimocode.TESTED_VERSION,
        "tested version mismatch",
        errors,
    )
    require(build.get("command") == nddev_mimocode.COMMAND_NAME, "command mismatch", errors)
    require(
        build.get("official_installer") == nddev_mimocode.INSTALLER_URL,
        "installer URL mismatch",
        errors,
    )
    require(
        build.get("official_installer_size") == nddev_mimocode.INSTALLER_SIZE,
        "installer size mismatch",
        errors,
    )
    require(
        build.get("official_installer_sha256") == nddev_mimocode.INSTALLER_SHA256,
        "installer SHA mismatch",
        errors,
    )
    runtime = manifest.get("runtime_compatibility")
    require(isinstance(runtime, dict), "manifest runtime_compatibility missing", errors)
    if isinstance(runtime, dict):
        require(
            runtime.get("github_release_page_asset_count") == RELEASE_PAGE_ASSET_COUNT,
            "manifest release page asset count mismatch",
            errors,
        )
        require(
            runtime.get("generated_source_downloads") == GENERATED_SOURCE_DOWNLOADS,
            "manifest generated source downloads mismatch",
            errors,
        )
        require(
            runtime.get("observed_uploaded_runtime_asset_ids")
            == OBSERVED_UPLOADED_RUNTIME_ASSET_IDS,
            "manifest observed runtime asset ids mismatch",
            errors,
        )
        require(
            runtime.get("supported_product_host_ids") == SUPPORTED_PRODUCT_HOST_IDS,
            "manifest product host ids mismatch",
            errors,
        )
        require(
            runtime.get("rejected_product_host_ids") == REJECTED_PRODUCT_HOST_IDS,
            "manifest rejected host ids mismatch",
            errors,
        )
        require(
            runtime.get("product_host_asset_selection") == PRODUCT_HOST_ASSET_SELECTION,
            "manifest product host asset selection mismatch",
            errors,
        )
        require(
            runtime.get("platform_selection_source")
            == "cli-tools/nddev_mimocode.py:detect_platform_selection",
            "manifest platform source mismatch",
            errors,
        )
        require(
            runtime.get("target_preflight_order_source") == "cli-tools/nddev_mimocode.py:run",
            "manifest preflight source mismatch",
            errors,
        )
    release = baseline.get("release")
    install = baseline.get("install")
    product_hosts = baseline.get("supported_product_hosts")
    require(isinstance(release, dict), "baseline release missing", errors)
    require(isinstance(install, dict), "baseline install missing", errors)
    require(isinstance(product_hosts, dict), "baseline supported_product_hosts missing", errors)
    if isinstance(release, dict):
        require(
            release.get("version") == build.get("mimocode_tested"),
            "baseline release mismatch",
            errors,
        )
        require(
            release.get("tag") == build.get("mimocode_release_tag"), "baseline tag mismatch", errors
        )
        require(
            release.get("published_at") == build.get("mimocode_published_at"),
            "baseline published_at mismatch",
            errors,
        )
        require(
            release.get("github_release_page_asset_count") == RELEASE_PAGE_ASSET_COUNT,
            "baseline release page asset count mismatch",
            errors,
        )
        require(
            release.get("generated_source_downloads") == GENERATED_SOURCE_DOWNLOADS,
            "baseline generated source downloads mismatch",
            errors,
        )
        require(
            release.get("observed_uploaded_runtime_asset_ids")
            == OBSERVED_UPLOADED_RUNTIME_ASSET_IDS,
            "baseline observed runtime asset ids mismatch",
            errors,
        )
        require(
            set(release.get("assets", {})) == set(OBSERVED_UPLOADED_RUNTIME_ASSET_IDS),
            "observed runtime asset key mismatch",
            errors,
        )
    if isinstance(product_hosts, dict):
        require(
            product_hosts.get("supported_ids") == SUPPORTED_PRODUCT_HOST_IDS,
            "baseline product host ids mismatch",
            errors,
        )
        require(
            product_hosts.get("rejected_ids") == REJECTED_PRODUCT_HOST_IDS,
            "baseline rejected host ids mismatch",
            errors,
        )
        require(
            product_hosts.get("linux_distro_gate") == "ID=ubuntu",
            "baseline Ubuntu gate mismatch",
            errors,
        )
        require(
            product_hosts.get("linux_libc_gate") == "glibc", "baseline libc gate mismatch", errors
        )
        require(
            product_hosts.get("ubuntu_version_floor") is None,
            "baseline must not invent an Ubuntu version floor",
            errors,
        )
        require(
            product_hosts.get("ubuntu_version_floor_semantics") == "no-official-floor",
            "baseline Ubuntu floor semantics mismatch",
            errors,
        )
        require(
            product_hosts.get("product_host_asset_selection") == PRODUCT_HOST_ASSET_SELECTION,
            "baseline product host asset selection mismatch",
            errors,
        )
        require(
            product_hosts.get("selection_source")
            == "cli-tools/nddev_mimocode.py:detect_platform_selection",
            "baseline platform selection source mismatch",
            errors,
        )
    if isinstance(install, dict):
        require(
            install.get("script") == nddev_mimocode.INSTALLER_URL,
            "baseline installer URL mismatch",
            errors,
        )
        require(
            install.get("script_size") == nddev_mimocode.INSTALLER_SIZE,
            "baseline installer size mismatch",
            errors,
        )
        require(
            install.get("script_sha256") == nddev_mimocode.INSTALLER_SHA256,
            "baseline installer SHA mismatch",
            errors,
        )
        require(
            install.get("package_manager_install") is None,
            "package manager install must be null",
            errors,
        )
    native = baseline.get("native_surfaces")
    require(isinstance(native, dict), "baseline native_surfaces missing", errors)
    if isinstance(native, dict):
        flags = native.get("manager_owned_runtime_flags")
        require(isinstance(flags, dict), "baseline runtime flag semantics missing", errors)
        if isinstance(flags, dict):
            require(
                set(flags) == set(EXPECTED_FIXED_RUNTIME_ENV),
                "baseline runtime flag key set mismatch",
                errors,
            )
            require(
                "MIMOCODE_CONFIG_DIR" in flags.get("MIMOCODE_DISABLE_EXTERNAL_SKILLS", ""),
                "external skill flag semantics must mention MIMOCODE_CONFIG_DIR",
                errors,
            )
            require(
                "Defaults to enabled" in flags.get("MIMOCODE_ENABLE_ANALYSIS", ""),
                "analysis flag semantics must record default-on behavior",
                errors,
            )
            require(
                "manager sets 0" in flags.get("MIMOCODE_ENABLE_ANALYSIS", ""),
                "analysis flag semantics must record value 0",
                errors,
            )
        require(
            native.get("project_boundary_rejected_paths") == EXPECTED_PROJECT_BOUNDARY_PATHS,
            "baseline project boundary paths mismatch",
            errors,
        )
        require(
            "unknown files under MIMOCODE_CONFIG_DIR"
            in native.get("managed_config_dir_launch_closure", ""),
            "baseline managed config closure missing",
            errors,
        )
    runtime_launch = contract.get("runtime_launch")
    require(isinstance(runtime_launch, dict), "contract runtime_launch missing", errors)
    if isinstance(runtime_launch, dict):
        require(
            runtime_launch.get("manager_owned_runtime_env_source")
            == "cli-tools/nddev_mimocode.py:MIMOCODE_FIXED_RUNTIME_ENV",
            "runtime env source mismatch",
            errors,
        )
        require(
            runtime_launch.get("manager_owned_runtime_env") == EXPECTED_FIXED_RUNTIME_ENV,
            "runtime env values mismatch",
            errors,
        )
        require(
            "MIMOCODE_DISABLE_PROJECT_CONFIG=1"
            in runtime_launch.get("project_config_discovery", ""),
            "project config disable contract missing",
            errors,
        )
        require(
            "MIMOCODE_ENABLE_ANALYSIS=0" in runtime_launch.get("external_telemetry", ""),
            "analysis disable contract missing",
            errors,
        )
        require(
            runtime_launch.get("project_boundary_rejected_paths_source")
            == "cli-tools/nddev_mimocode.py:PROJECT_BOUNDARY_PATHS",
            "project boundary source mismatch",
            errors,
        )
        require(
            runtime_launch.get("managed_config_dir_launch_closure_source")
            == "cli-tools/nddev_mimocode.py:validate_launch_managed_config_boundary",
            "managed config closure source mismatch",
            errors,
        )
        require(
            "unknown files under MIMOCODE_CONFIG_DIR"
            in runtime_launch.get("managed_config_dir_launch_closure", ""),
            "managed config closure contract missing",
            errors,
        )
    transaction = contract.get("transaction_policy")
    require(isinstance(transaction, dict), "contract transaction_policy missing", errors)
    if isinstance(transaction, dict):
        require(
            transaction.get("legacy_migrate_preserves_unmanaged_config_keys") is True,
            "legacy migrate preservation contract missing",
            errors,
        )
        require(
            transaction.get("durable_write_order")
            == ["stage", "fchmod", "file-fsync", "replace", "parent-fsync"],
            "durable write order contract mismatch",
            errors,
        )
        require(
            transaction.get("exact_postconditions") is True,
            "exact postcondition contract missing",
            errors,
        )
        require(
            "lexical absolute-target validation"
            in transaction.get("pre_lock_target_observation", ""),
            "pre-lock target observation contract missing",
            errors,
        )
        require(
            "global.lock" in transaction.get("lock", ""),
            "product global lock contract missing",
            errors,
        )
        require(
            "read-only inspection uses existing canonical bootstrap" in transaction.get("lock", ""),
            "read-only external lock contract missing",
            errors,
        )
        require(
            "mutating commands atomically publish" in transaction.get("lock", ""),
            "mutating external lock contract missing",
            errors,
        )
        require(
            "no-replace" in transaction.get("lock", ""),
            "anchor no-replace publication contract missing",
            errors,
        )
        require(
            transaction.get("product_coordination_lock") == "persistent-product-global-lock-file",
            "product coordination lock contract mismatch",
            errors,
        )
        require(
            "cold no-anchor read" in transaction.get("read_only_cold_exception", ""),
            "cold read exception contract missing",
            errors,
        )
        require(
            "final-path publication commit point"
            in transaction.get("published_anchor_rollback_exception", ""),
            "published anchor commit point missing",
            errors,
        )
        require(
            "monotonic rendezvous" in transaction.get("published_anchor_rollback_exception", ""),
            "published anchor rollback exception missing",
            errors,
        )
        require(
            "same-dev-inode" in transaction.get("hardlink_publication_alias_recovery", ""),
            "hardlink alias recovery contract missing",
            errors,
        )
        require(
            "mutating openers" in transaction.get("hardlink_publication_alias_recovery", ""),
            "hardlink alias mutator-only recovery contract missing",
            errors,
        )
        require(
            "read-only shared openers fail closed without recovery"
            in transaction.get("hardlink_publication_alias_recovery", ""),
            "read-only alias fail-closed contract missing",
            errors,
        )
        require(
            "unknown or multiple hardlinks fail closed"
            in transaction.get("hardlink_publication_alias_recovery", ""),
            "hardlink alias fail-closed contract missing",
            errors,
        )
        require(
            "absent targets do not create target-specific"
            in str(transaction.get("external_lock_persistent", "")),
            "command-accurate external lock persistence contract missing",
            errors,
        )
        require(
            "read-only inspection commands do not create"
            in str(transaction.get("internal_lock_persistent", "")),
            "read-only internal lock contract missing",
            errors,
        )
        require(
            transaction.get("lock_order")
            == [
                "product-wide-external-coordination",
                "target-filesystem-resolution",
                "canonical-target-external-lock-if-present-or-mutating",
                "target-internal-mutating-only",
            ],
            "transaction lock order contract mismatch",
            errors,
        )
        require(
            "inode identity" in transaction.get("rollback_exact_object_graph", ""),
            "exact object graph contract missing inode identity",
            errors,
        )
        require(
            "rename-held undo" in transaction.get("rollback_strategy", ""),
            "rollback strategy contract mismatch",
            errors,
        )
        require(
            "final-path no-replace publication" in transaction.get("rollback_strategy", ""),
            "cleanup journal commit boundary missing",
            errors,
        )
        require(
            ".nddev-mimocode-recovery/NDDEV-MIMOCODE-RECOVERY."
            in transaction.get("precommit_recovery_intent", ""),
            "precommit recovery intent path contract missing",
            errors,
        )
        require(
            "before every visible" in transaction.get("precommit_recovery_intent", ""),
            "precommit recovery ordering contract missing",
            errors,
        )
        require(
            "exact object graph records" in transaction.get("precommit_recovery_intent", ""),
            "precommit recovery graph contract missing",
            errors,
        )
        require(
            transaction.get("precommit_recovery_publish_order")
            == [
                "complete intent file-fsync",
                "atomic no-replace final-path publication",
                "recovery parent-fsync",
                "visible source move",
            ],
            "precommit recovery publish order mismatch",
            errors,
        )
        require(
            "read-only commands fail closed without recovery"
            in transaction.get("precommit_recovery_read_only", ""),
            "precommit recovery read-only contract missing",
            errors,
        )
        require(
            "exclusive target coordination" in transaction.get("precommit_recovery_read_only", ""),
            "precommit recovery mutator contract missing",
            errors,
        )
        require(
            transaction.get("precommit_recovery_intent_max_bytes")
            == nddev_mimocode.PRECOMMIT_RECOVERY_INTENT_MAX_BYTES,
            "precommit recovery intent byte bound mismatch",
            errors,
        )
        require(
            ".nddev-mimocode-cleanup/NDDEV-MIMOCODE-CLEANUP.json"
            in transaction.get("postcommit_cleanup_journal", ""),
            "postcommit cleanup journal path contract missing",
            errors,
        )
        require(
            transaction.get("postcommit_cleanup_journal_max_bytes")
            == nddev_mimocode.POSTCOMMIT_CLEANUP_JOURNAL_MAX_BYTES,
            "postcommit cleanup journal byte bound mismatch",
            errors,
        )
        require(
            "no-replace journal" in transaction.get("postcommit_cleanup_journal", ""),
            "postcommit cleanup no-replace contract missing",
            errors,
        )
        require(
            "bounded relative tombstones" in transaction.get("postcommit_cleanup_journal", ""),
            "postcommit cleanup tombstone bounds missing",
            errors,
        )
        require(
            "read-only commands validate and report only"
            in transaction.get("postcommit_cleanup_journal", ""),
            "read-only cleanup contract missing",
            errors,
        )
        require(
            transaction.get("postcommit_cleanup_publish_order")
            == [
                "verified desired active state",
                "rename preserve roots to final tombstones",
                "validate tombstone identities",
                "complete journal file-fsync",
                "atomic no-replace final-path publication",
                "cleanup parent-fsync",
            ],
            "postcommit cleanup publish order mismatch",
            errors,
        )
        require(
            "top-level cleanup_pending true" in transaction.get("cleanup_pending_result", ""),
            "cleanup_pending result contract missing",
            errors,
        )
        require(
            "bounded non-path cleanup_pending_entries"
            in transaction.get("cleanup_pending_result", ""),
            "cleanup_pending metadata bound missing",
            errors,
        )
        require(
            "exits rc 2 without mutation" in transaction.get("cleanup_pending_result", ""),
            "malformed cleanup fail-closed contract missing",
            errors,
        )
        require(
            transaction.get("restore_removes_known_managed_paths_absent_from_backup") is True,
            "restore deletion contract missing",
            errors,
        )
        require(
            transaction.get("restore_unknown_backup_paths") == "fail-closed",
            "restore unknown-path contract mismatch",
            errors,
        )
        require(
            transaction.get("backup_file_records") == "path-size-sha256",
            "backup file record contract mismatch",
            errors,
        )
        require(
            "empty extra directories" in transaction.get("backup_physical_topology", ""),
            "backup topology contract missing",
            errors,
        )
        require(
            "immutable postcommit cleanup journal"
            in transaction.get("backup_cleanup_postcondition", ""),
            "backup cleanup journal contract missing",
            errors,
        )
        require(
            "cleanup_pending" in transaction.get("backup_cleanup_postcondition", ""),
            "backup cleanup pending contract missing",
            errors,
        )
        require(
            transaction.get("same_uid_recomputed_payload_digest_tamper_machine_capability")
            is False,
            "same-UID tamper capability must be false",
            errors,
        )
        require(
            transaction.get("setup_update_command") == "update",
            "setup update command contract missing",
            errors,
        )
        require(
            "update-cli" in transaction.get("setup_update_scope", ""),
            "setup update/software update separation missing",
            errors,
        )
        require(
            "true no-op" in transaction.get("setup_update_noop", ""),
            "setup update no-op contract missing",
            errors,
        )
        require(
            "no cleanup_pending" in transaction.get("setup_update_noop", ""),
            "setup update cleanup-pending no-op boundary missing",
            errors,
        )
        require(
            "only when update changes" in transaction.get("setup_update_backup", ""),
            "setup update backup contract missing",
            errors,
        )
        require(
            "exact desired managed bytes" in transaction.get("setup_update_postcondition", ""),
            "setup update postcondition contract missing",
            errors,
        )
    software = contract.get("software_install")
    require(isinstance(software, dict), "contract software_install missing", errors)
    if isinstance(software, dict):
        require(
            software.get("github_release_page_asset_count") == RELEASE_PAGE_ASSET_COUNT,
            "contract release page asset count mismatch",
            errors,
        )
        require(
            software.get("generated_source_downloads") == GENERATED_SOURCE_DOWNLOADS,
            "contract generated source downloads mismatch",
            errors,
        )
        require(
            software.get("observed_uploaded_runtime_asset_ids")
            == OBSERVED_UPLOADED_RUNTIME_ASSET_IDS,
            "contract observed runtime asset ids mismatch",
            errors,
        )
        require(
            software.get("supported_product_host_ids") == SUPPORTED_PRODUCT_HOST_IDS,
            "contract product host ids mismatch",
            errors,
        )
        require(
            software.get("rejected_product_host_ids") == REJECTED_PRODUCT_HOST_IDS,
            "contract rejected host ids mismatch",
            errors,
        )
        require(
            software.get("product_host_asset_selection") == PRODUCT_HOST_ASSET_SELECTION,
            "contract product host asset selection mismatch",
            errors,
        )
        require(
            software.get("platform_selection_source")
            == "cli-tools/nddev_mimocode.py:detect_platform_selection",
            "contract platform source mismatch",
            errors,
        )
        require(
            software.get("ubuntu_version_floor") is None,
            "contract must not invent an Ubuntu version floor",
            errors,
        )
        require(
            "upstream publishes no official floor" in software.get("linux_product_scope", ""),
            "contract must describe no official Ubuntu floor",
            errors,
        )
        require(
            software.get("staged_probe_environment_source")
            == "cli-tools/nddev_mimocode.py:minimal_process_env",
            "staged probe env source mismatch",
            errors,
        )
        require(
            "MIMOCODE_ENABLE_ANALYSIS=0" in software.get("staged_probe_telemetry", ""),
            "staged probe telemetry contract missing",
            errors,
        )
    require(
        nddev_mimocode.MIMOCODE_FIXED_RUNTIME_ENV == EXPECTED_FIXED_RUNTIME_ENV,
        "manager fixed runtime env mismatch",
        errors,
    )
    require(
        nddev_mimocode.POSTCOMMIT_CLEANUP_DIRECTORY_NAME == ".nddev-mimocode-cleanup",
        "manager cleanup directory constant mismatch",
        errors,
    )
    require(
        nddev_mimocode.POSTCOMMIT_CLEANUP_JOURNAL_NAME == "NDDEV-MIMOCODE-CLEANUP.json",
        "manager cleanup journal constant mismatch",
        errors,
    )
    require(
        nddev_mimocode.POSTCOMMIT_CLEANUP_MAX_ENTRIES == 8,
        "manager cleanup entry bound mismatch",
        errors,
    )
    require(
        nddev_mimocode.POSTCOMMIT_CLEANUP_MAX_TREE_RECORDS <= 4096,
        "manager cleanup tree bound mismatch",
        errors,
    )
    require(
        nddev_mimocode.POSTCOMMIT_CLEANUP_JOURNAL_MAX_BYTES == 4 * 1024 * 1024,
        "manager cleanup journal byte bound mismatch",
        errors,
    )
    require(
        nddev_mimocode.PRECOMMIT_RECOVERY_DIRECTORY_NAME == ".nddev-mimocode-recovery",
        "manager recovery directory constant mismatch",
        errors,
    )
    require(
        nddev_mimocode.PRECOMMIT_RECOVERY_INTENT_MAX_BYTES == 4 * 1024 * 1024,
        "manager recovery intent byte bound mismatch",
        errors,
    )
    require(
        [str(path) for path in nddev_mimocode.PROJECT_BOUNDARY_PATHS]
        == EXPECTED_PROJECT_BOUNDARY_PATHS,
        "manager project boundary paths mismatch",
        errors,
    )
    require(
        list(nddev_mimocode.OBSERVED_UPLOADED_RUNTIME_ASSET_IDS)
        == OBSERVED_UPLOADED_RUNTIME_ASSET_IDS,
        "manager observed runtime asset ids mismatch",
        errors,
    )
    require(
        nddev_mimocode.RELEASE_PAGE_ASSET_COUNT == RELEASE_PAGE_ASSET_COUNT,
        "manager release page asset count mismatch",
        errors,
    )
    require(
        list(nddev_mimocode.GENERATED_SOURCE_DOWNLOADS) == GENERATED_SOURCE_DOWNLOADS,
        "manager generated source downloads mismatch",
        errors,
    )
    require(
        list(nddev_mimocode.SUPPORTED_PRODUCT_HOST_IDS) == SUPPORTED_PRODUCT_HOST_IDS,
        "manager product host ids mismatch",
        errors,
    )
    require(
        list(nddev_mimocode.REJECTED_PRODUCT_HOST_IDS) == REJECTED_PRODUCT_HOST_IDS,
        "manager rejected host ids mismatch",
        errors,
    )
    for name in EXPECTED_FIXED_RUNTIME_ENV:
        require(
            name in nddev_mimocode.BLOCKED_MANAGER_ENV_NAMES,
            f"manager env override not blocked: {name}",
            errors,
        )
    command_policy = contract.get("command_policy")
    require(isinstance(command_policy, dict), "contract command_policy missing", errors)
    if isinstance(command_policy, dict):
        require(
            command_policy.get("target_preflight_order")
            == [
                "supported-host",
                "lexical-absolute-target",
                "product-wide-external-coordination",
                "target-filesystem-resolution",
                "canonical-target-external-lock-if-present-or-mutating",
            ],
            "target preflight order contract mismatch",
            errors,
        )
        require(
            "JSON stdout" in command_policy.get("json_argparse_errors", ""),
            "JSON argparse boundary contract missing",
            errors,
        )


def validate_assets(errors: list[str]) -> None:
    baseline = read_json("references/mimocode-baseline.json")
    build = read_json("build/version.json")
    assets = baseline.get("release", {}).get("assets")
    require(isinstance(assets, dict), "baseline assets missing", errors)
    if not isinstance(assets, dict):
        return
    prefix = f"https://github.com/XiaomiMiMo/MiMo-Code/releases/download/{build['mimocode_release_tag']}/"
    for key in OBSERVED_UPLOADED_RUNTIME_ASSET_IDS:
        asset = assets.get(key)
        require(isinstance(asset, dict), f"asset missing: {key}", errors)
        if not isinstance(asset, dict):
            continue
        require(isinstance(asset.get("name"), str), f"asset name missing: {key}", errors)
        require(
            isinstance(asset.get("size"), int) and asset["size"] > 0,
            f"asset size invalid: {key}",
            errors,
        )
        require(
            re.fullmatch(r"[0-9a-f]{64}", str(asset.get("sha256", ""))) is not None,
            f"asset SHA invalid: {key}",
            errors,
        )
        require(str(asset.get("url", "")).startswith(prefix), f"asset URL mismatch: {key}", errors)
        if key in {"linux-arm64", "linux-x64", "linux-x64-baseline"}:
            require(
                "-musl" not in asset["name"],
                f"Ubuntu-selected asset must not use musl archive: {key}",
                errors,
            )
        if "musl" in key:
            require("-musl" in asset["name"], f"musl observation name mismatch: {key}", errors)
        if key.startswith("windows-"):
            require(
                asset["name"].startswith("mimocode-windows-"),
                f"Windows observation name mismatch: {key}",
                errors,
            )
        if key == "darwin-arm64":
            executable = asset.get("executable")
            require(
                isinstance(executable, dict), "darwin-arm64 executable metadata missing", errors
            )
            if isinstance(executable, dict):
                require(
                    executable.get("path") == nddev_mimocode.COMMAND_NAME,
                    "executable path mismatch",
                    errors,
                )
                require(
                    executable.get("installer_mode") == "0755", "installer mode mismatch", errors
                )
                require(
                    re.fullmatch(r"[0-9a-f]{64}", str(executable.get("sha256", ""))) is not None,
                    "executable SHA invalid",
                    errors,
                )


def injected_host(
    sys_platform: str,
    machine: str,
    *,
    libc: str = "",
    os_id: str | None = None,
    variant_id: str | None = None,
    avx2: bool = True,
    darwin_translated: bool = False,
) -> dict[str, Any]:
    os_release: dict[str, str] = {}
    if os_id is not None:
        os_release["ID"] = os_id
    if variant_id is not None:
        os_release["VARIANT_ID"] = variant_id
    return {
        "sys_platform": sys_platform,
        "machine": machine,
        "libc": libc,
        "libc_version": "",
        "os_release": os_release,
        "avx2": avx2,
        "darwin_translated": darwin_translated,
    }


def validate_platform_selection(errors: list[str]) -> None:
    success_cases = [
        ("macos arm64", injected_host("darwin", "arm64"), "darwin-arm64", "macos-arm64"),
        ("macos x64 avx2", injected_host("darwin", "x86_64", avx2=True), "darwin-x64", "macos-x64"),
        (
            "macos x64 baseline",
            injected_host("darwin", "x86_64", avx2=False),
            "darwin-x64-baseline",
            "macos-x64",
        ),
        (
            "macos translated arm64",
            injected_host("darwin", "x86_64", avx2=True, darwin_translated=True),
            "darwin-arm64",
            "macos-arm64",
        ),
        (
            "ubuntu desktop arm64",
            injected_host("linux", "aarch64", libc="glibc", os_id="ubuntu"),
            "linux-arm64",
            "ubuntu-glibc-arm64",
        ),
        (
            "ubuntu desktop x64 avx2",
            injected_host("linux", "x86_64", libc="glibc", os_id="ubuntu", avx2=True),
            "linux-x64",
            "ubuntu-glibc-x64",
        ),
        (
            "ubuntu server x64 baseline",
            injected_host(
                "linux", "x86_64", libc="glibc", os_id="ubuntu", variant_id="server", avx2=False
            ),
            "linux-x64-baseline",
            "ubuntu-glibc-x64",
        ),
        (
            "ubuntu server arm64",
            injected_host("linux", "arm64", libc="glibc", os_id="ubuntu", variant_id="server"),
            "linux-arm64",
            "ubuntu-glibc-arm64",
        ),
    ]
    for label, host, expected_asset, expected_product_host in success_cases:
        selection = nddev_mimocode.detect_platform_selection(host)
        require(
            selection.get("asset_key") == expected_asset, f"{label} selected wrong asset", errors
        )
        require(
            selection.get("product_host_id") == expected_product_host,
            f"{label} selected wrong product host",
            errors,
        )
        asset_key, asset = nddev_mimocode.detect_platform_asset(host)
        require(
            asset_key == expected_asset and isinstance(asset, dict),
            f"{label} asset lookup failed",
            errors,
        )

    reject_cases = [
        ("debian glibc", injected_host("linux", "x86_64", libc="glibc", os_id="debian", avx2=True)),
        ("alpine musl", injected_host("linux", "x86_64", libc="musl", os_id="alpine", avx2=True)),
        ("unknown linux", injected_host("linux", "x86_64", libc="glibc", avx2=True)),
        ("ubuntu musl", injected_host("linux", "x86_64", libc="musl", os_id="ubuntu", avx2=True)),
        ("windows", injected_host("win32", "x86_64", avx2=True)),
        ("unsupported arch", injected_host("darwin", "ppc64")),
    ]
    for label, host in reject_cases:
        require_manager_failure(
            lambda host=host: nddev_mimocode.require_supported_product_host(host),
            f"{label} host must be rejected before platform selection proceeds",
            errors,
        )


def command_argv(command: str, target: str = "/tmp/nddev-mimocode-public-target") -> list[str]:
    if command == "status":
        return ["status", "--target", target, "--json"]
    if command == "software-status":
        return ["software-status", "--target", target, "--json"]
    if command == "plan":
        return ["plan", "--target", target, "--json"]
    if command in {"install", "switch"}:
        return [command, "--target", target, "--json"]
    if command == "update":
        return ["update", "--target", target, "--json"]
    if command == "migrate":
        return ["migrate", "--target", target, "--json"]
    if command == "restore":
        return ["restore", "--backup", "0", "--target", target, "--json"]
    if command == "remove":
        return ["remove", "--target", target, "--json"]
    if command in {"install-cli", "update-cli", "remove-cli"}:
        return [command, "--target", target, "--json"]
    if command == "launch":
        return ["launch", "--target", target, "--json", "--", "--version"]
    raise AssertionError(f"unsupported command fixture: {command}")


def run_main_captured(argv: list[str]) -> tuple[int, str, str]:
    stdout = StringIO()
    stderr = StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        rc = nddev_mimocode.main(argv)
    return rc, stdout.getvalue(), stderr.getvalue()


def validate_cli_json_and_preflight_boundary(errors: list[str]) -> None:
    for argv in (
        ["status", "--json"],
        ["restore", "--backup", "not-an-int", "--target", "/tmp/target", "--json"],
        ["unknown-command", "--json"],
    ):
        rc, stdout, stderr = run_main_captured(list(argv))
        require(rc == 2, f"argparse JSON boundary rc mismatch: {argv}", errors)
        require(stderr == "", f"argparse JSON boundary wrote stderr: {argv}", errors)
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            errors.append(f"argparse JSON boundary wrote invalid JSON: {argv}")
            continue
        require(
            payload.get("ok") is False and isinstance(payload.get("error"), str),
            f"argparse JSON error payload mismatch: {argv}",
            errors,
        )

    original_host = nddev_mimocode.require_supported_product_host
    original_target = nddev_mimocode.require_absolute_target_argument
    original_bootstrap = nddev_mimocode.bootstrap_lifecycle_lock

    def unsupported_host(_host: Any = None) -> None:
        raise nddev_mimocode.MiMoCodeSetupError("forced unsupported host")

    def target_must_not_run(_raw_target: str | None) -> Path:
        raise AssertionError("target validation ran before host preflight")

    @contextlib.contextmanager
    def lock_must_not_run(_target: Path) -> Any:
        raise AssertionError("lifecycle lock ran before host preflight")
        yield

    nddev_mimocode.require_supported_product_host = unsupported_host
    nddev_mimocode.require_absolute_target_argument = target_must_not_run
    nddev_mimocode.bootstrap_lifecycle_lock = lock_must_not_run
    try:
        for command in sorted(nddev_mimocode.TARGET_BOUND_COMMANDS):
            rc, stdout, stderr = run_main_captured(command_argv(command, target="relative-target"))
            require(rc == 2, f"{command} unsupported host rc mismatch", errors)
            require(stderr == "", f"{command} unsupported host JSON wrote stderr", errors)
            payload = json.loads(stdout)
            require(
                payload.get("error") == "forced unsupported host",
                f"{command} did not fail at host preflight",
                errors,
            )
    finally:
        nddev_mimocode.require_supported_product_host = original_host
        nddev_mimocode.require_absolute_target_argument = original_target
        nddev_mimocode.bootstrap_lifecycle_lock = original_bootstrap

    trace: list[str] = []
    original_canonical = nddev_mimocode.canonical_target_for_bootstrap_lock
    original_acquire = nddev_mimocode.acquire_file_lock
    original_inspect = nddev_mimocode.inspect_target
    original_host = nddev_mimocode.require_supported_product_host
    original_target = nddev_mimocode.require_absolute_target_argument
    original_path_present = nddev_mimocode.path_present
    original_selected_asset = nddev_mimocode.selected_asset

    def traced_host(_host: Any = None) -> None:
        trace.append("host")

    def traced_target(raw_target: str | None) -> Path:
        trace.append("lexical-target")
        return original_target(raw_target)

    def traced_acquire(descriptor: int, path: Path, *, shared: bool = False) -> None:
        if is_product_lifecycle_lock_path(path):
            trace.append("product-lock-acquire")
        elif is_bootstrap_lifecycle_lock_path(path):
            trace.append("external-lock-acquire")
        else:
            trace.append("target-lock-acquire")
        return original_acquire(descriptor, path, shared=shared)

    def traced_canonical(target: Path) -> Path:
        trace.append("target-fs-canonicalization")
        return original_canonical(target)

    def traced_inspect(target: Path) -> dict[str, Any]:
        trace.append("status-read")
        return original_inspect(target)

    traced_target_path = {"value": ""}

    def traced_path_present(path: Path) -> bool:
        if str(path) == traced_target_path["value"]:
            trace.append("target-path-present")
        return original_path_present(path)

    def stop_before_network() -> tuple[str, dict[str, Any]]:
        trace.append("selected-asset")
        raise nddev_mimocode.MiMoCodeSetupError("forced stop before network")

    nddev_mimocode.require_supported_product_host = traced_host
    nddev_mimocode.require_absolute_target_argument = traced_target
    nddev_mimocode.acquire_file_lock = traced_acquire
    nddev_mimocode.canonical_target_for_bootstrap_lock = traced_canonical
    nddev_mimocode.inspect_target = traced_inspect
    nddev_mimocode.path_present = traced_path_present
    nddev_mimocode.selected_asset = stop_before_network
    try:
        with isolated_bootstrap_root(errors):
            with tempfile.TemporaryDirectory(prefix="nddev-mimocode-preflight.") as raw:
                target = Path(raw) / "target"
                target.mkdir(mode=0o700)
                target.chmod(0o700)
                traced_target_path["value"] = str(target.parent.resolve() / target.name)
                rc, stdout, stderr = run_main_captured(
                    ["status", "--target", str(target), "--json"]
                )
                require(rc == 0, "status preflight trace command failed", errors)
                require(stderr == "", "status preflight trace wrote stderr", errors)
                require(
                    json.loads(stdout).get("state") == "unmanaged",
                    "status preflight trace payload mismatch",
                    errors,
                )
                status_trace = list(trace)
                require(
                    status_trace[:3] == ["host", "lexical-target", "target-fs-canonicalization"]
                    and "product-lock-acquire" not in status_trace
                    and "external-lock-acquire" not in status_trace,
                    f"cold read-only preflight exception trace mismatch: {status_trace}",
                    errors,
                )
                for command in ("install-cli", "update-cli"):
                    trace.clear()
                    command_target = Path(raw) / command
                    traced_target_path["value"] = str(
                        command_target.parent.resolve() / command_target.name
                    )
                    rc, stdout, stderr = run_main_captured(
                        [command, "--target", str(command_target), "--json"]
                    )
                    require(
                        rc == 2,
                        f"{command} preflight trace command should fail before live work",
                        errors,
                    )
                    require(stderr == "", f"{command} preflight trace wrote stderr", errors)
                    payload = json.loads(stdout)
                    if command == "install-cli":
                        require(
                            payload.get("error") == "forced stop before network",
                            "install-cli did not stop at stubbed network boundary",
                            errors,
                        )
                    else:
                        require(
                            "requires existing" in payload.get("error", ""),
                            "update-cli absent target error mismatch",
                            errors,
                        )
                    require(
                        not original_path_present(command_target),
                        f"{command} left a newly created target after failure",
                        errors,
                    )
                    require(
                        trace[:2] == ["host", "lexical-target"],
                        f"{command} preflight order mismatch: {trace}",
                        errors,
                    )
                    require(
                        "product-lock-acquire" in trace
                        and trace.index("product-lock-acquire")
                        < trace.index("target-fs-canonicalization"),
                        f"{command} did not coordinate before canonicalization: {trace}",
                        errors,
                    )
                    external_index = (
                        trace.index("external-lock-acquire")
                        if "external-lock-acquire" in trace
                        else trace.index("product-lock-acquire")
                    )
                    require(
                        "target-path-present" in trace
                        and trace.index("target-path-present") > external_index,
                        f"{command} observed target before external lifecycle coordination: {trace}",
                        errors,
                    )
                    require(
                        trace.index("target-path-present")
                        > trace.index("target-fs-canonicalization"),
                        f"{command} observed target before coordinated canonicalization: {trace}",
                        errors,
                    )
                trace[:] = status_trace
    finally:
        nddev_mimocode.require_supported_product_host = original_host
        nddev_mimocode.require_absolute_target_argument = original_target
        nddev_mimocode.acquire_file_lock = original_acquire
        nddev_mimocode.canonical_target_for_bootstrap_lock = original_canonical
        nddev_mimocode.inspect_target = original_inspect
        nddev_mimocode.path_present = original_path_present
        nddev_mimocode.selected_asset = original_selected_asset
    require(
        trace[:3] == ["host", "lexical-target", "target-fs-canonicalization"],
        f"cold read-only preflight order mismatch: {trace}",
        errors,
    )
    require(
        "status-read" in trace
        and trace.index("status-read") > trace.index("target-fs-canonicalization"),
        "status read occurred before external lock canonicalization",
        errors,
    )


def validate_setup_profiles(errors: list[str]) -> None:
    manifest = read_json("build/manifest.json")
    contract = read_json("config/nddev-contract.json")
    require(manifest.get("setup_ids") == SETUP_IDS, "manifest setup ids mismatch", errors)
    require(manifest.get("profile_ids") == PROFILE_IDS, "manifest profile ids mismatch", errors)
    require(
        manifest.get("setup_lifecycle") == SETUP_LIFECYCLE,
        "manifest setup lifecycle mismatch",
        errors,
    )
    setup_system = contract.get("setup_system")
    require(isinstance(setup_system, dict), "contract setup_system missing", errors)
    if isinstance(setup_system, dict):
        require(setup_system.get("setup_ids") == SETUP_IDS, "contract setup ids mismatch", errors)
        require(
            setup_system.get("profile_ids") == PROFILE_IDS, "contract profile ids mismatch", errors
        )
        require(
            setup_system.get("default_profile_id") == nddev_mimocode.DEFAULT_PROFILE_ID,
            "default profile mismatch",
            errors,
        )
        require(
            setup_system.get("lifecycle") == FULL_LIFECYCLE,
            "contract setup lifecycle mismatch",
            errors,
        )
    command_policy = contract.get("command_policy")
    require(isinstance(command_policy, dict), "contract command_policy missing", errors)
    if isinstance(command_policy, dict):
        require(
            command_policy.get("json_supported") == JSON_COMMANDS,
            "command JSON support mismatch",
            errors,
        )
        require(
            command_policy.get("target_required") == TARGET_COMMANDS,
            "target command list mismatch",
            errors,
        )
    update_args = nddev_mimocode.parse_args(
        ["update", "--target", "/tmp/nddev-mimocode-target", "--json"]
    )
    require(update_args.command == "update", "update parser command mismatch", errors)
    require(
        not hasattr(update_args, "setup") and not hasattr(update_args, "profile"),
        "setup update must not accept setup/profile arguments",
        errors,
    )
    listed = nddev_mimocode.list_setups()
    profiles = nddev_mimocode.list_profiles()
    require([item["id"] for item in listed] == SETUP_IDS, "manager setup list mismatch", errors)
    require(
        [item["id"] for item in profiles] == PROFILE_IDS, "manager profile list mismatch", errors
    )
    for profile_id in PROFILE_IDS:
        _metadata, desired = nddev_mimocode.render_setup("nddev-builder", profile_id)
        config = json.loads(desired[nddev_mimocode.MIMOCODE_CONFIG_RELATIVE].decode("utf-8"))
        require(
            config.get("$schema") == "https://mimo.xiaomi.com/mimocode/config.json",
            f"{profile_id} schema mismatch",
            errors,
        )
        require(
            config.get("mcp") == {}, f"{profile_id} must not configure live MCP servers", errors
        )
        require(config.get("plugin") == [], f"{profile_id} must not load default plugins", errors)
        require("tools" not in config, f"{profile_id} must not use deprecated tools config", errors)
        if profile_id == "full-auto":
            require(
                config.get("permission") == "allow", "full-auto must use native allow-all", errors
            )
            stamp = json.loads(desired[Path(nddev_mimocode.STAMP_NAME)].decode("utf-8"))
            require(
                set(stamp["launch_env"]).isdisjoint(EXPECTED_FIXED_RUNTIME_ENV),
                "full-auto launch_env must not override manager-owned runtime env",
                errors,
            )
            require(
                "MIMOCODE_MIMO_ONLY" not in stamp["launch_env"],
                "full-auto must not force MiMo-only",
                errors,
            )
            require(
                stamp["launch_env"].get("MIMOCODE_DANGEROUSLY_SKIP_PERMISSIONS") == "1",
                "full-auto bypass env missing",
                errors,
            )
        else:
            require(
                config.get("default_agent") == "plan", "safe profile must use plan agent", errors
            )
            require(
                isinstance(config.get("permission"), dict), "safe permission must be object", errors
            )
            stamp = json.loads(desired[Path(nddev_mimocode.STAMP_NAME)].decode("utf-8"))
            require(stamp["launch_env"] == {}, "safe launch_env must be empty", errors)


def validate_read_only_alias_and_lock_noop(errors: list[str]) -> None:
    with isolated_bootstrap_root(errors) as injected:
        with tempfile.TemporaryDirectory(prefix="nddev-mimocode-readonly-locks.") as raw:
            root = Path(raw)
            root.chmod(0o700)
            real_parent = root / "real-parent"
            real_parent.mkdir(mode=0o700)
            real_parent.chmod(0o700)
            alias_parent = root / "alias-parent"
            alias_parent.symlink_to(real_parent, target_is_directory=True)
            missing_real = real_parent / "missing-target"
            missing_alias = alias_parent / "missing-target"
            canonical_missing = real_parent.resolve() / "missing-target"
            lock_events: list[tuple[str, str]] = []
            original_acquire = nddev_mimocode.acquire_file_lock

            def traced_acquire(descriptor: int, path: Path, *, shared: bool = False) -> None:
                if is_product_lifecycle_lock_path(path):
                    lock_events.append(("product", str(path)))
                elif is_bootstrap_lifecycle_lock_path(path):
                    lock_events.append(("external", str(path)))
                else:
                    lock_events.append(("internal", str(path)))
                return original_acquire(descriptor, path, shared=shared)

            nddev_mimocode.acquire_file_lock = traced_acquire
            try:
                before_pool = real_bootstrap_snapshot(bootstrap_product_root(injected))
                for command in ("status", "plan", "software-status"):
                    for label, target in (("real", missing_real), ("alias", missing_alias)):
                        before = len(lock_events)
                        rc, stdout, stderr = run_main_captured(
                            command_argv(command, target=str(target))
                        )
                        require(
                            rc == 0,
                            f"{command} {label} missing target failed through symlink parent",
                            errors,
                        )
                        require(
                            stderr == "", f"{command} {label} missing target wrote stderr", errors
                        )
                        payload = json.loads(stdout)
                        if command == "status":
                            require(
                                payload.get("state") == "missing",
                                "missing status state mismatch",
                                errors,
                            )
                        elif command == "plan":
                            require(
                                payload.get("operation") == "install",
                                "missing plan operation mismatch",
                                errors,
                            )
                            require(
                                payload.get("mutates") is False,
                                "missing plan must declare mutates false",
                                errors,
                            )
                        else:
                            require(
                                payload.get("present") is False
                                and payload.get("installed") is False,
                                "missing software-status payload mismatch",
                                errors,
                            )
                        require(
                            payload.get("target") == str(canonical_missing),
                            f"{command} {label} did not report canonical missing target",
                            errors,
                        )
                        require(
                            not missing_real.exists(),
                            f"{command} {label} created the canonical missing target",
                            errors,
                        )
                        require(
                            not missing_alias.exists(),
                            f"{command} {label} created the alias missing target",
                            errors,
                        )
                        events = lock_events[before:]
                        kinds = [kind for kind, _path in events]
                        require(
                            kinds.count("product") == 0,
                            f"{command} {label} cold read created/acquired product anchor: {events}",
                            errors,
                        )
                        require(
                            kinds.count("external") == 0,
                            f"{command} {label} created target-specific external lock for absent read: {events}",
                            errors,
                        )
                        require(
                            "internal" not in kinds,
                            f"{command} {label} created an internal target lock for an absent read",
                            errors,
                        )
                    require(
                        real_bootstrap_snapshot(bootstrap_product_root(injected)) == before_pool,
                        f"{command} absent read mutated bootstrap lock pool",
                        errors,
                    )
            finally:
                nddev_mimocode.acquire_file_lock = original_acquire

            with nddev_mimocode.bootstrap_lifecycle_lock(missing_alias) as canonical_target:
                require(
                    canonical_target == canonical_missing,
                    "held alias lock canonical target mismatch",
                    errors,
                )
                child = (
                    "from __future__ import annotations\n"
                    "import importlib.util, pathlib, sys\n"
                    "sys.dont_write_bytecode = True\n"
                    "manager_path = pathlib.Path(sys.argv[1])\n"
                    "bootstrap_root = pathlib.Path(sys.argv[2])\n"
                    "target = sys.argv[3]\n"
                    "spec = importlib.util.spec_from_file_location('nddev_mimocode_child', manager_path)\n"
                    "module = importlib.util.module_from_spec(spec)\n"
                    "assert spec.loader is not None\n"
                    "spec.loader.exec_module(module)\n"
                    "module.fixed_system_temp_root = lambda: bootstrap_root\n"
                    "raise SystemExit(module.main(['status', '--target', target, '--json']))\n"
                )
                child_env = {"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"}
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        "-c",
                        child,
                        str(MANAGER_PATH),
                        str(injected),
                        str(canonical_missing),
                    ],
                    env=child_env,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=10,
                )
                require(
                    completed.returncode == 2,
                    "held alias canonical lock did not block real target status",
                    errors,
                )
                require(
                    completed.stderr == "", "held alias canonical lock child wrote stderr", errors
                )
                try:
                    payload = json.loads(completed.stdout)
                except json.JSONDecodeError:
                    errors.append("held alias canonical lock child did not emit JSON")
                else:
                    require(
                        "target is locked" in payload.get("error", ""),
                        "held alias canonical lock error mismatch",
                        errors,
                    )

            nddev_mimocode.acquire_file_lock = traced_acquire
            try:
                observed_external: dict[str, dict[str, str]] = {}
                for command in ("status", "plan", "software-status"):
                    observed_external[command] = {}
                    for label, target in (("real", missing_real), ("alias", missing_alias)):
                        before = len(lock_events)
                        rc, stdout, stderr = run_main_captured(
                            command_argv(command, target=str(target))
                        )
                        require(rc == 0, f"{command} {label} existing marker read failed", errors)
                        require(
                            stderr == "",
                            f"{command} {label} existing marker read wrote stderr",
                            errors,
                        )
                        events = lock_events[before:]
                        kinds = [kind for kind, _path in events]
                        require(
                            kinds.count("product") == 1,
                            f"{command} {label} existing marker product lock mismatch: {events}",
                            errors,
                        )
                        require(
                            kinds.count("external") == 1,
                            f"{command} {label} existing marker external lock mismatch: {events}",
                            errors,
                        )
                        require(
                            "internal" not in kinds,
                            f"{command} {label} existing marker created internal lock",
                            errors,
                        )
                        require(
                            kinds.index("product") < kinds.index("external"),
                            f"{command} {label} existing marker lock order mismatch: {events}",
                            errors,
                        )
                        observed_external[command][label] = [
                            path for kind, path in events if kind == "external"
                        ][0]
                    require(
                        observed_external[command]["real"] == observed_external[command]["alias"],
                        f"{command} real and alias existing marker targets used different canonical external locks",
                        errors,
                    )
            finally:
                nddev_mimocode.acquire_file_lock = original_acquire

            for fixture in ("absent-lock-graph", "preexisting-lock-graph"):
                target = root / fixture
                target.mkdir(mode=0o700)
                target.chmod(0o700)
                if fixture == "preexisting-lock-graph":
                    lock_dir = nddev_mimocode.lock_directory_path(target)
                    lock_dir.mkdir(mode=0o700)
                    lock_dir.chmod(0o700)
                    lock_file = nddev_mimocode.lock_path(target)
                    lock_file.write_bytes(b"preexisting inspection lock\n")
                    lock_file.chmod(0o600)
                    old_ns = 1_700_000_000_123_456_789
                    os.utime(lock_file, ns=(old_ns, old_ns))
                    os.utime(lock_dir, ns=(old_ns, old_ns))
                    os.utime(target, ns=(old_ns, old_ns))
                for command in ("status", "plan", "software-status"):
                    before_graph = exact_tree_identity(target)
                    rc, stdout, stderr = run_main_captured(
                        command_argv(command, target=str(target))
                    )
                    require(rc == 0, f"{command} read-only no-op failed for {fixture}", errors)
                    require(
                        stderr == "",
                        f"{command} read-only no-op wrote stderr for {fixture}",
                        errors,
                    )
                    payload = json.loads(stdout)
                    require(
                        payload.get("ok") is True,
                        f"{command} read-only no-op payload mismatch for {fixture}",
                        errors,
                    )
                    require(
                        exact_tree_identity(target) == before_graph,
                        f"{command} read-only no-op changed target graph for {fixture}",
                        errors,
                    )


def validate_bootstrap_lock_publication_faults(errors: list[str]) -> None:
    source = MANAGER_PATH.read_text(encoding="utf-8")
    require("ftruncate" not in source, "bootstrap lock binding must not truncate in place", errors)
    anchor_start = source.index("def publish_bootstrap_anchor_no_replace")
    anchor_end = source.index("def publish_bootstrap_global_lock_anchor")
    anchor_source = source[anchor_start:anchor_end]
    require(
        "os.replace" not in anchor_source,
        "bootstrap anchors must not use replace-over-final",
        errors,
    )
    require(
        "cleanup_path_with_retries(path" not in anchor_source,
        "bootstrap anchors must not unlink final path after publication",
        errors,
    )
    require(
        "unlink_file_durable(path" not in anchor_source,
        "bootstrap anchors must not unlink final path after publication",
        errors,
    )
    require(
        "os.link(temporary, path)" in anchor_source,
        "bootstrap anchors must use atomic no-replace publication",
        errors,
    )

    def require_no_bootstrap_temp(pool: Path, label: str) -> None:
        snapshot = real_bootstrap_snapshot(pool)
        for entry in snapshot.get("entries", []):
            require(
                ".nddev.tmp." not in entry.get("name", ""),
                f"{label} left bootstrap temp residue",
                errors,
            )

    def require_global_anchor(pool: Path, label: str) -> None:
        path = pool / nddev_mimocode.BOOTSTRAP_GLOBAL_LOCK_NAME
        descriptor = nddev_mimocode.open_bootstrap_anchor_lock_file(
            path, "bootstrap product lock file"
        )
        try:
            nddev_mimocode.acquire_bootstrap_anchor_lock(
                descriptor, path, "bootstrap product lock file"
            )
            nddev_mimocode.validate_bootstrap_global_lock_binding(descriptor, path)
        finally:
            nddev_mimocode.release_file_lock(descriptor)
            os.close(descriptor)
        require_no_bootstrap_temp(pool, label)

    def require_target_anchor(target: Path, label: str) -> None:
        canonical_target = target.parent.resolve() / target.name
        path = (
            nddev_mimocode.bootstrap_lock_pool(canonical_target)
            / f"{nddev_mimocode.bootstrap_lock_key(canonical_target)}{nddev_mimocode.BOOTSTRAP_LOCK_SUFFIX}"
        )
        descriptor = nddev_mimocode.open_bootstrap_anchor_lock_file(
            path, "bootstrap lifecycle lock file"
        )
        try:
            nddev_mimocode.acquire_bootstrap_anchor_lock(
                descriptor, path, "bootstrap lifecycle lock file"
            )
            nddev_mimocode.validate_bootstrap_lock_binding(
                descriptor,
                path,
                canonical_target,
                nddev_mimocode.bootstrap_lock_key(canonical_target),
            )
        finally:
            nddev_mimocode.release_file_lock(descriptor)
            os.close(descriptor)
        require_no_bootstrap_temp(path.parent, label)

    def create_crashed_publication_alias(anchor_path: Path, publish: Any) -> None:
        original_link = nddev_mimocode.os.link
        original_cleanup = nddev_mimocode.cleanup_path_with_retries
        linked = {"value": False}
        injected = {"value": False}

        def traced_link(source: Any, destination: Any, *args: Any, **kwargs: Any) -> None:
            result = original_link(source, destination, *args, **kwargs)
            if Path(destination) == anchor_path:
                linked["value"] = True
            return result

        def fail_temp_alias_cleanup(path: Path, *args: Any, **kwargs: Any) -> None:
            if (
                linked["value"]
                and not injected["value"]
                and nddev_mimocode.is_bootstrap_publication_alias(path, anchor_path)
            ):
                injected["value"] = True
                raise OSError("forced crash after final-path publication")
            return original_cleanup(path, *args, **kwargs)

        try:
            nddev_mimocode.os.link = traced_link
            nddev_mimocode.cleanup_path_with_retries = fail_temp_alias_cleanup
            require_exception(
                publish,
                OSError,
                "crash-after-link publication alias fault must propagate",
                errors,
            )
        finally:
            nddev_mimocode.os.link = original_link
            nddev_mimocode.cleanup_path_with_retries = original_cleanup
        require(
            linked["value"] and injected["value"],
            "crash-after-link publication alias fault was not exercised",
            errors,
        )
        info = anchor_path.lstat()
        require(
            info.st_nlink == 2,
            "crash-after-link final anchor must retain one temp alias before recovery",
            errors,
        )

    def require_unknown_hardlink_fails(
        anchor_path: Path, open_and_recover: Any, label: str
    ) -> None:
        unknown = anchor_path.with_name(f".unknown-{anchor_path.name}.nddev.tmp.1.2")
        os.link(anchor_path, unknown)
        try:
            require_exception(
                open_and_recover,
                nddev_mimocode.MiMoCodeSetupError,
                f"{label} unknown hardlink must fail closed",
                errors,
            )
        finally:
            with contextlib.suppress(FileNotFoundError):
                unknown.unlink()
            with contextlib.suppress(OSError):
                nddev_mimocode.fsync_directory_with_retries(
                    anchor_path.parent, f"{label} unknown hardlink cleanup"
                )

    def install_with_fault(target: Path, fault: str, *, target_only: bool) -> bool:
        original_open = nddev_mimocode.os.open
        original_fchmod = nddev_mimocode.os.fchmod
        original_write_all = nddev_mimocode.write_all
        original_fsync = nddev_mimocode.os.fsync
        original_link = nddev_mimocode.os.link
        original_acquire = nddev_mimocode.acquire_file_lock
        injected_fault = {"value": False}
        armed_file_fsync = {"value": False}

        def is_anchor_temp(raw: Any) -> bool:
            path = Path(raw)
            if ".nddev.tmp." not in path.name:
                return False
            if not target_only:
                return True
            return path.parent == bootstrap_product_root(nddev_mimocode.fixed_system_temp_root())

        def fail_create(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
            if (
                fault == "create"
                and not injected_fault["value"]
                and flags & os.O_CREAT
                and flags & os.O_EXCL
                and is_anchor_temp(path)
            ):
                injected_fault["value"] = True
                raise OSError("forced bootstrap create fault")
            return original_open(path, flags, *args, **kwargs)

        def fail_fchmod(descriptor: int, mode: int) -> None:
            if (
                fault == "fchmod"
                and not injected_fault["value"]
                and mode == nddev_mimocode.OWNER_FILE_MODE
            ):
                injected_fault["value"] = True
                raise OSError("forced bootstrap fchmod fault")
            return original_fchmod(descriptor, mode)

        def fail_write(descriptor: int, content: bytes) -> None:
            if fault == "write" and not injected_fault["value"]:
                injected_fault["value"] = True
                os.write(descriptor, content[: max(1, len(content) // 3)])
                raise OSError("forced bootstrap write fault")
            return original_write_all(descriptor, content)

        def arm_marker_file_fsync(descriptor: int, content: bytes) -> None:
            original_write_all(descriptor, content)
            if fault == "file-fsync":
                armed_file_fsync["value"] = True

        def fail_fsync(descriptor: int) -> None:
            if armed_file_fsync["value"] and not injected_fault["value"]:
                injected_fault["value"] = True
                raise OSError("forced bootstrap file fsync fault")
            return original_fsync(descriptor)

        def fail_link(source: Any, destination: Any, *args: Any, **kwargs: Any) -> None:
            destination_path = Path(destination)
            target_marker = (
                destination_path.name.endswith(nddev_mimocode.BOOTSTRAP_LOCK_SUFFIX)
                and destination_path.name != nddev_mimocode.BOOTSTRAP_GLOBAL_LOCK_NAME
            )
            product_marker = destination_path.name == nddev_mimocode.BOOTSTRAP_GLOBAL_LOCK_NAME
            if (
                fault == "atomic-publish"
                and not injected_fault["value"]
                and ((target_only and target_marker) or (not target_only and product_marker))
            ):
                injected_fault["value"] = True
                raise OSError("forced bootstrap atomic publish fault")
            return original_link(source, destination, *args, **kwargs)

        def fail_acquire(descriptor: int, path: Path, *, shared: bool = False) -> None:
            if (
                fault == "lock-acquisition"
                and not injected_fault["value"]
                and ".nddev.tmp." in path.name
            ):
                injected_fault["value"] = True
                raise OSError("forced bootstrap lock acquisition fault")
            return original_acquire(descriptor, path, shared=shared)

        try:
            nddev_mimocode.os.open = fail_create
            nddev_mimocode.os.fchmod = fail_fchmod
            nddev_mimocode.write_all = fail_write if fault == "write" else arm_marker_file_fsync
            nddev_mimocode.os.fsync = fail_fsync
            nddev_mimocode.os.link = fail_link
            nddev_mimocode.acquire_file_lock = fail_acquire
            require_exception(
                lambda: nddev_mimocode.mutate_setup(
                    target, "nddev-builder", "full-auto", "install"
                ),
                (OSError, nddev_mimocode.MiMoCodeSetupError),
                f"bootstrap {fault} fault must propagate",
                errors,
            )
        finally:
            nddev_mimocode.os.open = original_open
            nddev_mimocode.os.fchmod = original_fchmod
            nddev_mimocode.write_all = original_write_all
            nddev_mimocode.os.fsync = original_fsync
            nddev_mimocode.os.link = original_link
            nddev_mimocode.acquire_file_lock = original_acquire
        return injected_fault["value"]

    for fault in ("create", "fchmod", "write", "file-fsync", "atomic-publish", "lock-acquisition"):
        with isolated_bootstrap_root(errors) as injected:
            with tempfile.TemporaryDirectory(prefix=f"nddev-mimocode-bootstrap-{fault}.") as raw:
                root = Path(raw)
                root.chmod(0o700)
                target_parent = root / "targets"
                target_parent.mkdir(mode=0o700)
                target_parent.chmod(0o700)
                target = target_parent / "target"
                pool = bootstrap_product_root(injected)
                before = real_bootstrap_snapshot(pool)
                require(
                    install_with_fault(target, fault, target_only=False),
                    f"bootstrap product {fault} fault was not exercised",
                    errors,
                )
                require(
                    real_bootstrap_snapshot(pool) == before,
                    f"bootstrap {fault} fault mutated lock pool",
                    errors,
                )
                require(not target.exists(), f"bootstrap {fault} fault created target", errors)

    for fault in ("create", "fchmod", "write", "file-fsync", "atomic-publish", "lock-acquisition"):
        with isolated_bootstrap_root(errors) as injected:
            with tempfile.TemporaryDirectory(
                prefix=f"nddev-mimocode-target-bootstrap-{fault}."
            ) as raw:
                root = Path(raw)
                root.chmod(0o700)
                target_parent = root / "targets"
                target_parent.mkdir(mode=0o700)
                target_parent.chmod(0o700)
                target = target_parent / "target"
                pool = bootstrap_product_root(injected)
                pool.mkdir(mode=0o700)
                pool.chmod(0o700)
                nddev_mimocode.ensure_bootstrap_global_lock_anchor(pool)
                before = real_bootstrap_snapshot(pool)
                require(
                    install_with_fault(target, fault, target_only=True),
                    f"bootstrap target {fault} fault was not exercised",
                    errors,
                )
                require(
                    real_bootstrap_snapshot(pool) == before,
                    f"bootstrap target {fault} fault mutated lock pool",
                    errors,
                )
                require(
                    not target.exists(), f"bootstrap target {fault} fault created target", errors
                )

    with isolated_bootstrap_root(errors) as injected:
        pool = bootstrap_product_root(injected)
        pool.mkdir(mode=0o700)
        pool.chmod(0o700)
        global_anchor = pool / nddev_mimocode.BOOTSTRAP_GLOBAL_LOCK_NAME
        create_crashed_publication_alias(
            global_anchor,
            lambda: nddev_mimocode.publish_bootstrap_global_lock_anchor(global_anchor),
        )
        require_global_anchor(pool, "bootstrap product crash recovery")
        require(
            global_anchor.lstat().st_nlink == 1,
            "product crash recovery did not normalize final nlink",
            errors,
        )
        alias = global_anchor.with_name(f".{global_anchor.name}.nddev.tmp.123.456")
        os.link(global_anchor, alias)
        nddev_mimocode.publish_bootstrap_global_lock_anchor(global_anchor)
        require(
            global_anchor.lstat().st_nlink == 1 and not nddev_mimocode.path_present(alias),
            "product EEXIST waiter did not recover publication alias",
            errors,
        )
        require_unknown_hardlink_fails(
            global_anchor,
            lambda: require_global_anchor(pool, "product unknown hardlink"),
            "product anchor",
        )
        require(
            global_anchor.lstat().st_nlink == 1,
            "product unknown hardlink cleanup did not restore nlink",
            errors,
        )

    with isolated_bootstrap_root(errors) as injected:
        with tempfile.TemporaryDirectory(prefix="nddev-mimocode-target-crash-recovery.") as raw:
            root = Path(raw)
            root.chmod(0o700)
            target_parent = root / "targets"
            target_parent.mkdir(mode=0o700)
            target_parent.chmod(0o700)
            target = target_parent / "target"
            canonical_target = target_parent.resolve() / target.name
            target_key = nddev_mimocode.bootstrap_lock_key(canonical_target)
            pool = bootstrap_product_root(injected)
            pool.mkdir(mode=0o700)
            pool.chmod(0o700)
            nddev_mimocode.ensure_bootstrap_global_lock_anchor(pool)
            target_anchor = pool / f"{target_key}{nddev_mimocode.BOOTSTRAP_LOCK_SUFFIX}"
            create_crashed_publication_alias(
                target_anchor,
                lambda: nddev_mimocode.publish_new_bootstrap_lock_binding(
                    target_anchor, canonical_target, target_key
                ),
            )
            require_target_anchor(target, "bootstrap target crash recovery")
            require(
                target_anchor.lstat().st_nlink == 1,
                "target crash recovery did not normalize final nlink",
                errors,
            )
            alias = target_anchor.with_name(f".{target_anchor.name}.nddev.tmp.123.456")
            os.link(target_anchor, alias)
            descriptor = nddev_mimocode.publish_new_bootstrap_lock_binding(
                target_anchor, canonical_target, target_key
            )
            try:
                require(
                    target_anchor.lstat().st_nlink == 1 and not nddev_mimocode.path_present(alias),
                    "target EEXIST waiter did not recover publication alias",
                    errors,
                )
            finally:
                nddev_mimocode.release_file_lock(descriptor)
                os.close(descriptor)
            require_unknown_hardlink_fails(
                target_anchor,
                lambda: require_target_anchor(target, "target unknown hardlink"),
                "target anchor",
            )
            require(
                target_anchor.lstat().st_nlink == 1,
                "target unknown hardlink cleanup did not restore nlink",
                errors,
            )

    for fault in ("parent-fsync", "handoff"):
        with isolated_bootstrap_root(errors) as injected:
            with tempfile.TemporaryDirectory(
                prefix=f"nddev-mimocode-target-bootstrap-{fault}."
            ) as raw:
                root = Path(raw)
                root.chmod(0o700)
                target_parent = root / "targets"
                target_parent.mkdir(mode=0o700)
                target_parent.chmod(0o700)
                target = target_parent / "target"
                pool = bootstrap_product_root(injected)
                pool.mkdir(mode=0o700)
                pool.chmod(0o700)
                nddev_mimocode.ensure_bootstrap_global_lock_anchor(pool)
                original_fsync_directory = nddev_mimocode.fsync_directory
                original_verify = nddev_mimocode.verify_locked_file_identity
                injected_fault = {"value": False}

                def fail_parent_fsync(path: Path, label: str) -> None:
                    if (
                        label == "bootstrap lifecycle lock pool after binding publish"
                        and not injected_fault["value"]
                    ):
                        injected_fault["value"] = True
                        raise OSError("forced bootstrap parent fsync fault")
                    return original_fsync_directory(path, label)

                def fail_handoff(descriptor: int, path: Path, label: str) -> None:
                    if label == "bootstrap lifecycle lock file" and not injected_fault["value"]:
                        injected_fault["value"] = True
                        raise nddev_mimocode.MiMoCodeSetupError("forced bootstrap handoff fault")
                    return original_verify(descriptor, path, label)

                try:
                    if fault == "parent-fsync":
                        nddev_mimocode.fsync_directory = fail_parent_fsync
                        descriptor = nddev_mimocode.publish_new_bootstrap_lock_binding(
                            pool
                            / f"{nddev_mimocode.bootstrap_lock_key(target_parent.resolve() / target.name)}{nddev_mimocode.BOOTSTRAP_LOCK_SUFFIX}",
                            target_parent.resolve() / target.name,
                            nddev_mimocode.bootstrap_lock_key(
                                target_parent.resolve() / target.name
                            ),
                        )
                        os.close(descriptor)
                    else:
                        nddev_mimocode.verify_locked_file_identity = fail_handoff
                        require_exception(
                            lambda: nddev_mimocode.bootstrap_lifecycle_lock(target).__enter__(),
                            nddev_mimocode.MiMoCodeSetupError,
                            "bootstrap handoff fault must propagate",
                            errors,
                        )
                    require(
                        injected_fault["value"],
                        f"bootstrap {fault} fault was not exercised",
                        errors,
                    )
                finally:
                    nddev_mimocode.fsync_directory = original_fsync_directory
                    nddev_mimocode.verify_locked_file_identity = original_verify
                require_target_anchor(target, f"bootstrap {fault}")
                require(not target.exists(), f"bootstrap {fault} fault created target", errors)


def validate_launch_environment(errors: list[str]) -> None:
    sentinel = "nddev-public-regression-secret-value"
    safe_parent = {
        "CI": "1",
        "COLORTERM": "truecolor",
        "HTTP_PROXY": "http://127.0.0.1:18080",
        "HTTPS_PROXY": "http://127.0.0.1:18443",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "LC_CTYPE": "C.UTF-8",
        "NODE_EXTRA_CA_CERTS": "/tmp/nddev-public-ca-node.pem",
        "NO_COLOR": "1",
        "NO_PROXY": "127.0.0.1,localhost",
        "REQUESTS_CA_BUNDLE": "/tmp/nddev-public-ca-requests.pem",
        "SSL_CERT_DIR": "/tmp/nddev-public-ca-dir",
        "SSL_CERT_FILE": "/tmp/nddev-public-ca-file.pem",
        "SYSTEMROOT": "C:\\Windows",
        "TERM": "xterm-256color",
        "http_proxy": "http://127.0.0.1:28080",
        "https_proxy": "http://127.0.0.1:28443",
        "no_proxy": "localhost,::1",
    }
    secret_parent = {name: sentinel for name in nddev_mimocode.TOKEN_ENV_NAMES}
    secret_parent.update(
        {
            "MIMOCODE_CONFIG": sentinel,
            "MIMOCODE_CONFIG_DIR": sentinel,
            "MIMOCODE_HOME": sentinel,
            "MIMOCODE_MIMO_ONLY": sentinel,
            "PATH": "/untrusted/bin",
            "RANDOM_UNDECLARED_ENV": sentinel,
        }
    )
    secret_parent.update({name: sentinel for name in EXPECTED_FIXED_RUNTIME_ENV})
    original_env = dict(os.environ)
    try:
        os.environ.clear()
        os.environ.update({**safe_parent, **secret_parent})
        with tempfile.TemporaryDirectory(prefix="nddev-mimocode-env-regression.") as raw:
            target = Path(raw) / "target"
            target.mkdir(mode=0o700)
            target.chmod(0o700)
            env = nddev_mimocode.isolated_child_environment(
                target,
                {"MIMOCODE_DANGEROUSLY_SKIP_PERMISSIONS": "1"},
            )
            fixed = {
                "APPDATA",
                "HOME",
                "LOCALAPPDATA",
                "MIMOCODE_CONFIG",
                "MIMOCODE_CONFIG_DIR",
                "MIMOCODE_DANGEROUSLY_SKIP_PERMISSIONS",
                "MIMOCODE_HOME",
                "PATH",
                "SHELL",
                "TEMP",
                "TMP",
                "TMPDIR",
                "USERPROFILE",
                "XDG_CACHE_HOME",
                "XDG_CONFIG_HOME",
                "XDG_DATA_HOME",
                "XDG_STATE_HOME",
            }
            fixed |= set(EXPECTED_FIXED_RUNTIME_ENV)
            allowed_names = set(nddev_mimocode.SAFE_CHILD_INHERITED_ENV_NAMES) | fixed
            require(set(env) <= allowed_names, "launch env contains non-allowlisted names", errors)
            require(
                env.get("PATH") == nddev_mimocode.DETERMINISTIC_PATH, "launch PATH mismatch", errors
            )
            for name, expected in EXPECTED_FIXED_RUNTIME_ENV.items():
                require(env.get(name) == expected, f"fixed runtime env mismatch: {name}", errors)
            require("MIMOCODE_MIMO_ONLY" not in env, "launch env must not force MiMo-only", errors)
            for name, value in safe_parent.items():
                require(env.get(name) == value, f"safe env missing: {name}", errors)
            for name in secret_parent:
                require(env.get(name) != sentinel, f"secret env leaked: {name}", errors)
            for key in (
                "HOME",
                "TMPDIR",
                "XDG_CONFIG_HOME",
                "MIMOCODE_HOME",
                "MIMOCODE_CONFIG_DIR",
            ):
                path = Path(env[key])
                require(
                    path.exists() and os.access(path, os.W_OK),
                    f"runtime path is not writable: {key}",
                    errors,
                )
            probe_env = nddev_mimocode.minimal_process_env(tmp_dir=Path(raw) / "probe-tmp")
            for name, expected in EXPECTED_FIXED_RUNTIME_ENV.items():
                require(probe_env.get(name) == expected, f"probe env mismatch: {name}", errors)
            require_manager_failure(
                lambda: nddev_mimocode.isolated_child_environment(
                    target,
                    {"MIMOCODE_ENABLE_ANALYSIS": "1"},
                ),
                "launch env must reject manager-owned runtime overrides",
                errors,
            )
    finally:
        os.environ.clear()
        os.environ.update(original_env)


def validate_project_boundary(errors: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="nddev-mimocode-boundary.") as raw:
        clean_target = Path(raw) / "clean"
        clean_target.mkdir(mode=0o700)
        clean_target.chmod(0o700)
        nddev_mimocode.validate_launch_project_boundary(clean_target)
        config_root = clean_target / nddev_mimocode.MIMOCODE_CONFIG_DIR_RELATIVE
        config_root.mkdir(mode=0o700, parents=True)
        config_root.chmod(0o700)
        nddev_mimocode.validate_launch_managed_config_boundary(clean_target)
        unknown_skill = config_root / "skills" / "unknown" / "SKILL.md"
        unknown_skill.parent.mkdir(mode=0o700, parents=True)
        unknown_skill.parent.chmod(0o700)
        unknown_skill.write_text("# Unknown\n", encoding="utf-8")
        unknown_skill.chmod(0o600)
        require_manager_failure(
            lambda: nddev_mimocode.validate_launch_managed_config_boundary(clean_target),
            "managed config dir must reject unknown launch inputs",
            errors,
        )
        require(
            unknown_skill.exists(),
            "managed config boundary check must not delete unknown files",
            errors,
        )
        for index, relative in enumerate(nddev_mimocode.PROJECT_BOUNDARY_PATHS):
            target = Path(raw) / f"target-{index}"
            target.mkdir(mode=0o700)
            target.chmod(0o700)
            path = target / relative
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            path.parent.chmod(0o700)
            if relative.suffix:
                path.write_text("{}", encoding="utf-8")
                path.chmod(0o600)
            else:
                path.mkdir(mode=0o700)
                path.chmod(0o700)
            require_manager_failure(
                lambda target=target: nddev_mimocode.validate_launch_project_boundary(target),
                f"project boundary path must be rejected: {relative}",
                errors,
            )


def write_owner_file(target: Path, relative: Path, content: bytes) -> None:
    path = target / relative
    current = target
    for part in relative.parent.parts:
        current = current / part
        current.mkdir(mode=0o700, exist_ok=True)
        current.chmod(0o700)
    path.write_bytes(content)
    path.chmod(0o600)


def make_legacy_target(parent: Path) -> Path:
    target = (parent / "legacy-target").resolve()
    target.mkdir(mode=0o700)
    target.chmod(0o700)
    legacy_contents = {
        Path("config") / "mimocode.json": nddev_mimocode.canonical_json(
            {
                "$schema": "legacy-managed",
                "disabled_providers": ["managed"],
                "permission": "allow",
                "custom_provider": {"id": "preserved"},
                "user_note": "preserved",
            }
        ),
        Path("config") / "AGENTS.md": b"# Legacy instructions\n",
        Path("config") / "skills" / "nddev-builder" / "SKILL.md": b"# Legacy skill\n",
        Path("config") / "agents" / "nddev-builder.md": b"# Legacy agent\n",
        Path("config") / "instructions" / "nddev-builder.md": b"# Legacy builder instructions\n",
        Path(".mimocode") / "workflows" / "nddev-builder.js": b"export default {}\n",
    }
    for relative, content in legacy_contents.items():
        write_owner_file(target, relative, content)
    stamp = {
        "schema_version": 1,
        "product_name": nddev_mimocode.PRODUCT_NAME,
        "build_version": sorted(nddev_mimocode.LEGACY_BUILD_VERSIONS)[0],
        "setup_id": "safe",
        "canonical_target": str(target),
        "managed_files": {
            str(relative): nddev_mimocode.legacy_managed_digest(relative, content)
            for relative, content in legacy_contents.items()
        },
        "builder_projection": "legacy-native-config",
        "launch_args": ["--agent", "plan"],
    }
    write_owner_file(target, Path(nddev_mimocode.STAMP_NAME), nddev_mimocode.canonical_json(stamp))
    return target


def tree_snapshot(root: Path) -> dict[str, tuple[str, int, str | None]]:
    if not root.exists():
        return {}
    result: dict[str, tuple[str, int, str | None]] = {}
    for path in sorted(root.rglob("*"), key=lambda item: str(item.relative_to(root))):
        relative = str(path.relative_to(root))
        info = path.lstat()
        mode = stat.S_IMODE(info.st_mode)
        if stat.S_ISDIR(info.st_mode):
            result[relative] = ("dir", mode, None)
        elif stat.S_ISREG(info.st_mode):
            result[relative] = ("file", mode, hashlib.sha256(path.read_bytes()).hexdigest())
        else:
            result[relative] = ("other", mode, None)
    return result


def exact_tree_identity(root: Path) -> dict[str, tuple[str, int, int, int, int, str | None]]:
    if not root.exists():
        return {}
    result: dict[str, tuple[str, int, int, int, int, str | None]] = {}
    paths = [root, *sorted(root.rglob("*"), key=lambda item: str(item.relative_to(root)))]
    for path in paths:
        relative = "." if path == root else str(path.relative_to(root))
        info = path.lstat()
        mode = stat.S_IMODE(info.st_mode)
        digest = (
            hashlib.sha256(path.read_bytes()).hexdigest() if stat.S_ISREG(info.st_mode) else None
        )
        if stat.S_ISDIR(info.st_mode):
            kind = "dir"
        elif stat.S_ISREG(info.st_mode):
            kind = "file"
        elif stat.S_ISLNK(info.st_mode):
            kind = "symlink"
            digest = os.readlink(path)
        else:
            kind = "other"
        result[relative] = (kind, info.st_ino, info.st_size, mode, info.st_mtime_ns, digest)
    return result


def identity_snapshot(paths: list[Path]) -> dict[str, tuple[int, int, int, int, str | None]]:
    result: dict[str, tuple[int, int, int, int, str | None]] = {}
    for path in sorted(paths, key=str):
        info = path.lstat()
        digest = (
            hashlib.sha256(path.read_bytes()).hexdigest() if stat.S_ISREG(info.st_mode) else None
        )
        result[str(path)] = (
            info.st_ino,
            info.st_size,
            stat.S_IMODE(info.st_mode),
            info.st_mtime_ns,
            digest,
        )
    return result


def managed_identity_snapshot(target: Path) -> dict[str, tuple[int, int, int, int, str | None]]:
    paths = [
        target / relative
        for relative in nddev_mimocode.MANAGED_PATHS
        if (target / relative).exists()
    ]
    return identity_snapshot(paths)


def software_identity_snapshot(target: Path) -> dict[str, tuple[int, int, int, int, str | None]]:
    paths = [
        target / relative
        for relative in nddev_mimocode.software_file_modes()
        if (target / relative).exists()
    ]
    return identity_snapshot(paths)


def require_no_transaction_residue(target: Path, message: str, errors: list[str]) -> None:
    if not target.exists():
        return
    residue = [
        str(path.relative_to(target))
        for path in target.rglob("*")
        if ".nddev.tmp." in path.name
        or ".stage." in path.name
        or ".rollback." in path.name
        or ".retired." in path.name
        or ".recovery." in path.name
    ]
    require(not residue, f"{message}: {residue}", errors)


def make_managed_target(parent: Path, profile_id: str = "full-auto") -> Path:
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent.chmod(0o700)
    target = (parent / f"managed-{profile_id}").resolve()
    nddev_mimocode.mutate_setup(target, "nddev-builder", profile_id, "install")
    return target


def fake_software_manifest(binary: bytes, version: str = "old") -> bytes:
    return nddev_mimocode.canonical_json(
        {
            "schema_version": 2,
            "version": version,
            "command": nddev_mimocode.COMMAND_NAME,
            "executable": f"bin/{nddev_mimocode.COMMAND_NAME}",
            "version_tree_executable": str(
                nddev_mimocode.SOFTWARE_VERSION_RELATIVE / nddev_mimocode.COMMAND_NAME
            ),
            "asset": "test",
            "asset_url": "https://example.invalid/test",
            "asset_size": len(binary),
            "asset_sha256": hashlib.sha256(binary).hexdigest(),
            "archive_member_path": nddev_mimocode.COMMAND_NAME,
            "archive_member_mode": "0755",
            "installer_binary_mode": "0755",
            "installer_url": nddev_mimocode.INSTALLER_URL,
            "installer_size": nddev_mimocode.INSTALLER_SIZE,
            "installer_sha256": nddev_mimocode.INSTALLER_SHA256,
            "binary_size": len(binary),
            "binary_mode": f"{nddev_mimocode.OWNER_EXECUTABLE_MODE:04o}",
            "binary_max_bytes": nddev_mimocode.SOFTWARE_EXECUTABLE_MAX_BYTES,
            "binary_sha256": hashlib.sha256(binary).hexdigest(),
            "version_output": version,
        }
    )


def make_fake_software(target: Path, binary: bytes = b"old-binary\n", version: str = "old") -> None:
    target.mkdir(mode=0o700, exist_ok=True)
    target.chmod(0o700)
    for relative, content, mode in (
        (Path("bin") / nddev_mimocode.COMMAND_NAME, binary, nddev_mimocode.OWNER_EXECUTABLE_MODE),
        (
            nddev_mimocode.SOFTWARE_VERSION_RELATIVE / nddev_mimocode.COMMAND_NAME,
            binary,
            nddev_mimocode.OWNER_EXECUTABLE_MODE,
        ),
        (
            nddev_mimocode.SOFTWARE_MANIFEST_RELATIVE,
            fake_software_manifest(binary, version),
            nddev_mimocode.OWNER_FILE_MODE,
        ),
    ):
        path = target / relative
        current = target
        for part in relative.parent.parts:
            current = current / part
            current.mkdir(mode=0o700, exist_ok=True)
            current.chmod(0o700)
        path.write_bytes(content)
        path.chmod(mode)


def validate_replace_managed_state_cleanup(errors: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="nddev-mimocode-replace-cleanup.") as raw:
        root = Path(raw)
        for label, patched_name in (("replace", "replace"), ("fsync", "fsync")):
            target = root / label
            config_root = target / nddev_mimocode.MIMOCODE_CONFIG_DIR_RELATIVE
            config_root.mkdir(mode=0o700, parents=True)
            target.chmod(0o700)
            config_root.chmod(0o700)
            original_content = b'{"original":true}\n'
            write_owner_file(target, nddev_mimocode.MIMOCODE_CONFIG_RELATIVE, original_content)
            before_entries = sorted(item.name for item in config_root.iterdir())
            original_callable = getattr(nddev_mimocode.os, patched_name)

            def failing_callable(*_args: Any, **_kwargs: Any) -> None:
                raise OSError(f"forced {patched_name} failure")

            setattr(nddev_mimocode.os, patched_name, failing_callable)
            try:
                require_exception(
                    lambda: nddev_mimocode.replace_managed_state(
                        target,
                        {nddev_mimocode.MIMOCODE_CONFIG_RELATIVE: b'{"updated":true}\n'},
                    ),
                    OSError,
                    f"forced {patched_name} failure must propagate",
                    errors,
                )
            finally:
                setattr(nddev_mimocode.os, patched_name, original_callable)
            after_entries = sorted(item.name for item in config_root.iterdir())
            require(
                after_entries == before_entries,
                f"forced {patched_name} failure left temp residue",
                errors,
            )
            config_path = target / nddev_mimocode.MIMOCODE_CONFIG_RELATIVE
            require(
                config_path.read_bytes() == original_content,
                f"forced {patched_name} failure changed original managed file",
                errors,
            )
            nddev_mimocode.validate_launch_managed_config_boundary(target)

        target = root / "temp-fchmod"
        config_root = target / nddev_mimocode.MIMOCODE_CONFIG_DIR_RELATIVE
        config_root.mkdir(mode=0o700, parents=True)
        target.chmod(0o700)
        config_root.chmod(0o700)
        original_content = b'{"original":true}\n'
        write_owner_file(target, nddev_mimocode.MIMOCODE_CONFIG_RELATIVE, original_content)
        config_path = target / nddev_mimocode.MIMOCODE_CONFIG_RELATIVE
        before_entries = sorted(item.name for item in config_root.iterdir())
        original_fchmod = nddev_mimocode.os.fchmod

        def failing_fchmod(*_args: Any, **_kwargs: Any) -> None:
            raise OSError("forced temp fchmod failure")

        nddev_mimocode.os.fchmod = failing_fchmod
        try:
            require_exception(
                lambda: nddev_mimocode.replace_managed_state(
                    target,
                    {nddev_mimocode.MIMOCODE_CONFIG_RELATIVE: b'{"updated":true}\n'},
                ),
                OSError,
                "forced temp fchmod failure must propagate",
                errors,
            )
        finally:
            nddev_mimocode.os.fchmod = original_fchmod
        after_entries = sorted(item.name for item in config_root.iterdir())
        require(
            after_entries == before_entries, "forced temp fchmod failure left temp residue", errors
        )
        require(
            config_path.read_bytes() == original_content,
            "forced temp fchmod failure changed original managed file",
            errors,
        )
        nddev_mimocode.validate_launch_managed_config_boundary(target)

        target = root / "success"
        config_root = target / nddev_mimocode.MIMOCODE_CONFIG_DIR_RELATIVE
        config_root.mkdir(mode=0o700, parents=True)
        target.chmod(0o700)
        config_root.chmod(0o700)
        original_content = b'{"original":true}\n'
        updated_content = b'{"updated":true}\n'
        write_owner_file(target, nddev_mimocode.MIMOCODE_CONFIG_RELATIVE, original_content)
        config_path = target / nddev_mimocode.MIMOCODE_CONFIG_RELATIVE
        before_entries = sorted(item.name for item in config_root.iterdir())
        original_replace = nddev_mimocode.os.replace
        original_path_chmod = Path.chmod
        replace_seen = False
        destination_chmod_after_replace: list[int] = []

        def recording_replace(source: Any, destination: Any, *args: Any, **kwargs: Any) -> None:
            nonlocal replace_seen
            original_replace(source, destination, *args, **kwargs)
            replace_seen = True

        def recording_chmod(self: Path, mode: int, *args: Any, **kwargs: Any) -> None:
            if replace_seen and self == config_path:
                destination_chmod_after_replace.append(mode)
            return original_path_chmod(self, mode, *args, **kwargs)

        nddev_mimocode.os.replace = recording_replace
        Path.chmod = recording_chmod
        try:
            nddev_mimocode.replace_managed_state(
                target,
                {nddev_mimocode.MIMOCODE_CONFIG_RELATIVE: updated_content},
            )
        finally:
            nddev_mimocode.os.replace = original_replace
            Path.chmod = original_path_chmod
        after_entries = sorted(item.name for item in config_root.iterdir())
        require(replace_seen, "successful replace regression did not observe os.replace", errors)
        require(
            not destination_chmod_after_replace,
            "managed replace must not chmod destination after os.replace",
            errors,
        )
        require(after_entries == before_entries, "successful replace left temp residue", errors)
        require(
            config_path.read_bytes() == updated_content,
            "successful replace did not write new managed file",
            errors,
        )
        require(
            stat.S_IMODE(config_path.lstat().st_mode) == 0o600,
            "successful replace did not preserve 0600 mode",
            errors,
        )
        nddev_mimocode.validate_launch_managed_config_boundary(target)


def validate_state_transition_helpers(errors: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="nddev-mimocode-transition.") as raw:
        target = Path(raw) / "target"
        config_dir = target / "config"
        config_dir.mkdir(mode=0o700, parents=True)
        target.chmod(0o700)
        config_dir.chmod(0o700)
        legacy_config = {
            "$schema": "legacy-managed",
            "disabled_providers": ["managed"],
            "permission": "allow",
            "custom_provider": {"id": "preserved"},
            "user_note": "preserved",
        }
        legacy_config_path = config_dir / "mimocode.json"
        legacy_config_path.write_bytes(nddev_mimocode.canonical_json(legacy_config))
        legacy_config_path.chmod(0o600)
        preserved = nddev_mimocode.preserved_legacy_config_for_migration(
            target,
            {"state": "legacy-managed"},
        )
        require(
            preserved == {"custom_provider": {"id": "preserved"}, "user_note": "preserved"},
            "legacy migrate must preserve only unmanaged config keys",
            errors,
        )
        metadata, desired = nddev_mimocode.render_setup(
            "nddev-builder",
            "safe",
            existing_config=preserved,
        )
        require(metadata["id"] == "nddev-builder", "migration setup metadata mismatch", errors)
        rendered_config = json.loads(
            desired[nddev_mimocode.MIMOCODE_CONFIG_RELATIVE].decode("utf-8")
        )
        require(
            rendered_config.get("custom_provider") == {"id": "preserved"},
            "rendered migration config lost custom_provider",
            errors,
        )
        require(
            rendered_config.get("user_note") == "preserved",
            "rendered migration config lost user_note",
            errors,
        )
        require(
            "disabled_providers" not in rendered_config,
            "rendered migration config kept legacy managed key",
            errors,
        )
        require_manager_failure(
            lambda: nddev_mimocode.preserved_legacy_config_for_migration(
                target, {"state": "managed"}
            ),
            "legacy preservation helper must reject non-legacy state",
            errors,
        )

        backup_files = {
            Path(nddev_mimocode.STAMP_NAME): b'{"schema_version":1}\n',
            Path("config") / "mimocode.json": b'{"legacy":true}\n',
        }
        restored = nddev_mimocode.restore_desired_from_backup(backup_files)
        require(
            set(restored) == set(nddev_mimocode.ALL_MANAGED_PATHS),
            "restore desired must cover all known managed paths",
            errors,
        )
        for relative in nddev_mimocode.ALL_MANAGED_PATHS:
            if relative in backup_files:
                require(
                    restored[relative] == backup_files[relative],
                    f"restore desired missing backup file: {relative}",
                    errors,
                )
            else:
                require(
                    restored[relative] is None,
                    f"restore desired must remove absent managed file: {relative}",
                    errors,
                )
        require_manager_failure(
            lambda: nddev_mimocode.restore_desired_from_backup(
                {Path("unknown") / "managed.json": b"{}"}
            ),
            "restore desired must reject unsupported backup paths",
            errors,
        )
        require_manager_failure(
            lambda: nddev_mimocode.restore_desired_from_backup({Path("..") / "escape": b"{}"}),
            "restore desired must reject unsafe backup paths",
            errors,
        )

    with isolated_bootstrap_root(errors):
        with tempfile.TemporaryDirectory(prefix="nddev-mimocode-legacy-plan.") as raw:
            target = make_legacy_target(Path(raw))
            before_snapshot = nddev_mimocode.current_managed_snapshot(target)
            require_manager_failure(
                lambda: nddev_mimocode.update_setup(target),
                "setup update must reject legacy managed targets before migrate",
                errors,
            )
            plan = nddev_mimocode.plan_setup(target, "nddev-builder", "safe")
            after_plan_snapshot = nddev_mimocode.current_managed_snapshot(target)
            require(
                after_plan_snapshot == before_snapshot,
                "legacy plan must not mutate managed state",
                errors,
            )
            require(plan.get("operation") == "migrate", "legacy plan operation mismatch", errors)
            require(plan.get("backup_required") is True, "legacy plan backup flag mismatch", errors)
            migrated = nddev_mimocode.migrate_setup(target, "safe")
            require(
                plan.get("changed") == migrated.get("changed"),
                "legacy plan changed paths must exactly match migrate",
                errors,
            )
            migrated_config = nddev_mimocode.load_json_object(
                target / nddev_mimocode.MIMOCODE_CONFIG_RELATIVE,
                "migrated config",
                owner_only=True,
            )
            require(
                migrated_config.get("custom_provider") == {"id": "preserved"},
                "legacy migrate lost custom_provider",
                errors,
            )
            require(
                migrated_config.get("user_note") == "preserved",
                "legacy migrate lost user_note",
                errors,
            )
            for legacy_path in nddev_mimocode.LEGACY_MANAGED_PATHS:
                if legacy_path in nddev_mimocode.MANAGED_PATHS:
                    continue
                require(
                    not nddev_mimocode.path_present(target / legacy_path),
                    f"legacy migrate left removed path: {legacy_path}",
                    errors,
                )


def validate_dual_locks(errors: list[str]) -> None:
    source = MANAGER_PATH.read_text(encoding="utf-8")
    for name in FORBIDDEN_BOOTSTRAP_OVERRIDE_NAMES:
        require(name not in source, f"forbidden public lock override name appears: {name}", errors)
    with isolated_bootstrap_root(errors) as injected:
        with tempfile.TemporaryDirectory(prefix="nddev-mimocode-lock-regression.") as raw:
            parent = Path(raw)
            parent.chmod(0o700)
            target = parent / "target"
            with nddev_mimocode.locked_new_or_existing_target(target) as canonical:
                require(canonical == target.resolve(), "locked target canonical mismatch", errors)
                external = nddev_mimocode.bootstrap_lock_path(target)
                internal = nddev_mimocode.lock_path(canonical)
                require(
                    str(external).startswith(str(injected)),
                    "external lock used real system root",
                    errors,
                )
                require(external.exists(), "external lock missing", errors)
                require(internal.exists(), "internal lock missing", errors)
                require(
                    stat.S_IMODE(external.lstat().st_mode) == 0o600,
                    "external lock mode mismatch",
                    errors,
                )
                require(
                    stat.S_IMODE(internal.lstat().st_mode) == 0o600,
                    "internal lock mode mismatch",
                    errors,
                )
                require(
                    stat.S_IMODE(nddev_mimocode.lock_directory_path(canonical).lstat().st_mode)
                    == 0o500,
                    "internal lock directory not protected while held",
                    errors,
                )
            require(external.exists(), "external lock must persist after release", errors)
            require(internal.exists(), "internal lock must persist after release", errors)
            binding = json.loads(external.read_text(encoding="utf-8"))
            require(
                binding.get("canonical_target") == str(target.resolve()),
                "external lock binding mismatch",
                errors,
            )


def folded_value(text: str, key: str) -> list[str]:
    marker = f"      {key}: >-"
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line == marker:
            result: list[str] = []
            for candidate in lines[index + 1 :]:
                if not candidate.startswith("        "):
                    break
                result.extend(candidate.strip().split())
            return result
    return []


def mapping_keys_after(text: str, marker: str, indent: int) -> dict[str, str]:
    lines = text.splitlines()
    result: dict[str, str] = {}
    for index, line in enumerate(lines):
        if line == marker:
            for candidate in lines[index + 1 :]:
                if candidate.strip() == "":
                    continue
                current_indent = len(candidate) - len(candidate.lstrip(" "))
                if current_indent <= indent:
                    break
                if current_indent == indent + 2 and ":" in candidate:
                    key, value = candidate.strip().split(":", 1)
                    result[key] = value.strip()
            return result
    return result


def validate_shared_ci(errors: list[str]) -> None:
    workflow_root = ROOT / ".github" / "workflows"
    require(workflow_root.is_dir(), "missing .github/workflows", errors)
    for filename, workflow in SHARED_CALLERS.items():
        path = workflow_root / filename
        require(path.is_file(), f"missing workflow {filename}", errors)
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        expected = f"NDDev-it-com/ci-workflows/{workflow}@{SHARED_CI_COMMIT} # {SHARED_CI_VERSION}"
        require(text.count(expected) == 1, f"{filename} shared CI pin mismatch", errors)


def validate_release_archive(errors: list[str]) -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    require("permissions: {}\n" in workflow, "top-level release permissions must be empty", errors)
    require(
        "uses: NDDev-it-com/ci-workflows/.github/workflows/release-supply-chain.yml@"
        + SHARED_CI_COMMIT
        + f" # {SHARED_CI_VERSION}"
        in workflow,
        "release shared workflow pin mismatch",
        errors,
    )
    require(
        mapping_keys_after(workflow, "    permissions:", 4) == REQUIRED_RELEASE_PERMISSIONS,
        "release permissions keys must be closed",
        errors,
    )
    with_values = mapping_keys_after(workflow, "    with:", 4)
    require(set(with_values) == REQUIRED_RELEASE_INPUTS, "release with keys must be closed", errors)
    archive_paths = folded_value(workflow, "archive_paths")
    runtime_paths = folded_value(workflow, "runtime_paths")
    require(archive_paths == RELEASE_ARCHIVE_PATHS, "release archive paths mismatch", errors)
    require(runtime_paths == RELEASE_RUNTIME_PATHS, "release runtime paths mismatch", errors)
    require(
        set(runtime_paths) <= set(archive_paths), "runtime paths must be archive subset", errors
    )
    for raw in archive_paths:
        path = ROOT / raw
        try:
            info = path.lstat()
        except FileNotFoundError:
            errors.append(f"declared archive path missing: {raw}")
            continue
        require(
            not stat.S_ISLNK(info.st_mode),
            f"declared archive path must not be symlink: {raw}",
            errors,
        )
    require(
        REQUIRED_CONTRACT_ROOTS <= {path.split("/", 1)[0] for path in archive_paths},
        "required source roots missing from archive",
        errors,
    )
    files = relative_files()
    for raw in files:
        require(
            any(raw == root or raw.startswith(root + "/") for root in archive_paths),
            f"tracked source is outside release archive closure: {raw}",
            errors,
        )


def validate_builder_references(errors: list[str]) -> None:
    builder_root = ROOT / "plugins" / "nddev-builder"
    require(builder_root.is_dir(), "builder root missing", errors)
    source_targets = {str(target) for _source, target in nddev_mimocode.BUILDER_SOURCE_FILES}
    require(
        any("skills/nddev-builder/SKILL.md" in item for item in source_targets),
        "builder skill projection missing",
        errors,
    )
    for path in sorted(builder_root.rglob("*.md")):
        relative = path.relative_to(ROOT)
        text = path.read_text(encoding="utf-8")
        for match in re.findall(r"(?<![A-Za-z0-9_.-])([A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+)", text):
            cleaned = match.strip("`.,;:)")
            if not cleaned.startswith(
                (
                    ".claude/",
                    ".gds/",
                    ".github/",
                    "build/",
                    "cli-tools/",
                    "config/",
                    "plugins/",
                    "profiles/",
                    "references/",
                    "setups/",
                )
            ):
                continue
            if cleaned.startswith(("http://", "https://")):
                continue
            candidate = (path.parent / cleaned).resolve()
            root_candidate = (ROOT / cleaned).resolve()
            require(
                (str(candidate).startswith(str(ROOT)) and candidate.exists())
                or (str(root_candidate).startswith(str(ROOT)) and root_candidate.exists()),
                f"unresolved local reference {cleaned} in {relative}",
                errors,
            )


def main() -> int:
    errors: list[str] = []
    real_root = nddev_mimocode.fixed_system_temp_root()
    real_product_root = bootstrap_product_root(real_root)
    real_bootstrap_before = real_bootstrap_snapshot(real_product_root)
    validate_claude_bridge(errors)
    validate_versions(errors)
    validate_assets(errors)
    validate_platform_selection(errors)
    validate_cli_json_and_preflight_boundary(errors)
    validate_setup_profiles(errors)
    validate_read_only_alias_and_lock_noop(errors)
    validate_bootstrap_lock_publication_faults(errors)
    validate_launch_environment(errors)
    validate_project_boundary(errors)
    validate_replace_managed_state_cleanup(errors)
    validate_state_transition_helpers(errors)
    validate_dual_locks(errors)
    validate_release_archive(errors)
    validate_builder_references(errors)
    validate_no_private_markers(errors)
    validate_shared_ci(errors)
    require(
        real_bootstrap_snapshot(real_product_root) == real_bootstrap_before,
        "public validator touched the real system bootstrap lock root outside isolated tests",
        errors,
    )
    if errors:
        for error in errors:
            print(error)
        return 1
    print("nddev-mimocode-app public contracts ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
