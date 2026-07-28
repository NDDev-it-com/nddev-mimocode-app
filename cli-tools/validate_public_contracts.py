#!/usr/bin/env python3
"""Validate nddev-mimocode-app public contracts without live side effects."""

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
SETUP_LIFECYCLE = ["list", "status", "plan", "install", "update", "switch", "migrate", "restore", "remove"]
FULL_LIFECYCLE = [*SETUP_LIFECYCLE, "software-status", "install-cli", "update-cli", "remove-cli", "launch"]
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
REQUIRED_CONTRACT_ROOTS = {"build", "cli-tools", "config", "plugins", "profiles", "references", "setups"}
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


def require_exception(callable_obj: Any, exception_type: type[BaseException], message: str, errors: list[str]) -> None:
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
        record: dict[str, Any] = {"name": child.name, "identity": path_identity(child), "type": "other"}
        if stat.S_ISREG(child_info.st_mode) and child_info.st_size <= nddev_mimocode.METADATA_MAX_BYTES:
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
        require(PLACEHOLDER_MARKER not in text.lower(), f"placeholder marker remains in {raw}", errors)
        for marker in PRIVATE_TEXT_MARKERS:
            require(marker not in text, f"private marker {marker!r} appears in {raw}", errors)


def validate_claude_bridge(errors: list[str]) -> None:
    agents = ROOT / "AGENTS.md"
    claude_dir = ROOT / ".claude"
    bridge = claude_dir / "CLAUDE.md"
    for path, label in ((agents, "AGENTS.md"), (claude_dir, ".claude"), (bridge, ".claude/CLAUDE.md")):
        try:
            info = path.lstat()
        except FileNotFoundError:
            errors.append(f"{label} is missing")
            return
        require(not stat.S_ISLNK(info.st_mode), f"{label} must not be a symlink", errors)
    require(agents.is_file(), "AGENTS.md must be a regular file", errors)
    require(claude_dir.is_dir(), ".claude must be a real directory", errors)
    require(sorted(item.name for item in claude_dir.iterdir()) == ["CLAUDE.md"], ".claude must contain only CLAUDE.md", errors)
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
    require(contract.get("builder_capability", {}).get("version") == version, "builder version mismatch", errors)
    require(build.get("nddev_builder_extension_version") == version, "builder extension version mismatch", errors)
    require(build.get("python_requires") == ">=3.9", "build python_requires mismatch", errors)
    require(build.get("mimocode_tested") == nddev_mimocode.TESTED_VERSION, "tested version mismatch", errors)
    require(build.get("command") == nddev_mimocode.COMMAND_NAME, "command mismatch", errors)
    require(build.get("official_installer") == nddev_mimocode.INSTALLER_URL, "installer URL mismatch", errors)
    require(build.get("official_installer_size") == nddev_mimocode.INSTALLER_SIZE, "installer size mismatch", errors)
    require(build.get("official_installer_sha256") == nddev_mimocode.INSTALLER_SHA256, "installer SHA mismatch", errors)
    runtime = manifest.get("runtime_compatibility")
    require(isinstance(runtime, dict), "manifest runtime_compatibility missing", errors)
    if isinstance(runtime, dict):
        require(runtime.get("github_release_page_asset_count") == RELEASE_PAGE_ASSET_COUNT, "manifest release page asset count mismatch", errors)
        require(runtime.get("generated_source_downloads") == GENERATED_SOURCE_DOWNLOADS, "manifest generated source downloads mismatch", errors)
        require(runtime.get("observed_uploaded_runtime_asset_ids") == OBSERVED_UPLOADED_RUNTIME_ASSET_IDS, "manifest observed runtime asset ids mismatch", errors)
        require(runtime.get("supported_product_host_ids") == SUPPORTED_PRODUCT_HOST_IDS, "manifest product host ids mismatch", errors)
        require(runtime.get("rejected_product_host_ids") == REJECTED_PRODUCT_HOST_IDS, "manifest rejected host ids mismatch", errors)
        require(runtime.get("product_host_asset_selection") == PRODUCT_HOST_ASSET_SELECTION, "manifest product host asset selection mismatch", errors)
        require(runtime.get("platform_selection_source") == "cli-tools/nddev_mimocode.py:detect_platform_selection", "manifest platform source mismatch", errors)
        require(runtime.get("target_preflight_order_source") == "cli-tools/nddev_mimocode.py:run", "manifest preflight source mismatch", errors)
    release = baseline.get("release")
    install = baseline.get("install")
    product_hosts = baseline.get("supported_product_hosts")
    require(isinstance(release, dict), "baseline release missing", errors)
    require(isinstance(install, dict), "baseline install missing", errors)
    require(isinstance(product_hosts, dict), "baseline supported_product_hosts missing", errors)
    if isinstance(release, dict):
        require(release.get("version") == build.get("mimocode_tested"), "baseline release mismatch", errors)
        require(release.get("tag") == build.get("mimocode_release_tag"), "baseline tag mismatch", errors)
        require(release.get("published_at") == build.get("mimocode_published_at"), "baseline published_at mismatch", errors)
        require(release.get("github_release_page_asset_count") == RELEASE_PAGE_ASSET_COUNT, "baseline release page asset count mismatch", errors)
        require(release.get("generated_source_downloads") == GENERATED_SOURCE_DOWNLOADS, "baseline generated source downloads mismatch", errors)
        require(release.get("observed_uploaded_runtime_asset_ids") == OBSERVED_UPLOADED_RUNTIME_ASSET_IDS, "baseline observed runtime asset ids mismatch", errors)
        require(set(release.get("assets", {})) == set(OBSERVED_UPLOADED_RUNTIME_ASSET_IDS), "observed runtime asset key mismatch", errors)
    if isinstance(product_hosts, dict):
        require(product_hosts.get("supported_ids") == SUPPORTED_PRODUCT_HOST_IDS, "baseline product host ids mismatch", errors)
        require(product_hosts.get("rejected_ids") == REJECTED_PRODUCT_HOST_IDS, "baseline rejected host ids mismatch", errors)
        require(product_hosts.get("linux_distro_gate") == "ID=ubuntu", "baseline Ubuntu gate mismatch", errors)
        require(product_hosts.get("linux_libc_gate") == "glibc", "baseline libc gate mismatch", errors)
        require(product_hosts.get("ubuntu_version_floor") is None, "baseline must not invent an Ubuntu version floor", errors)
        require(product_hosts.get("ubuntu_version_floor_semantics") == "no-official-floor", "baseline Ubuntu floor semantics mismatch", errors)
        require(product_hosts.get("product_host_asset_selection") == PRODUCT_HOST_ASSET_SELECTION, "baseline product host asset selection mismatch", errors)
        require(product_hosts.get("selection_source") == "cli-tools/nddev_mimocode.py:detect_platform_selection", "baseline platform selection source mismatch", errors)
    if isinstance(install, dict):
        require(install.get("script") == nddev_mimocode.INSTALLER_URL, "baseline installer URL mismatch", errors)
        require(install.get("script_size") == nddev_mimocode.INSTALLER_SIZE, "baseline installer size mismatch", errors)
        require(install.get("script_sha256") == nddev_mimocode.INSTALLER_SHA256, "baseline installer SHA mismatch", errors)
        require(install.get("package_manager_install") is None, "package manager install must be null", errors)
    native = baseline.get("native_surfaces")
    require(isinstance(native, dict), "baseline native_surfaces missing", errors)
    if isinstance(native, dict):
        flags = native.get("manager_owned_runtime_flags")
        require(isinstance(flags, dict), "baseline runtime flag semantics missing", errors)
        if isinstance(flags, dict):
            require(set(flags) == set(EXPECTED_FIXED_RUNTIME_ENV), "baseline runtime flag key set mismatch", errors)
            require("MIMOCODE_CONFIG_DIR" in flags.get("MIMOCODE_DISABLE_EXTERNAL_SKILLS", ""), "external skill flag semantics must mention MIMOCODE_CONFIG_DIR", errors)
            require("Defaults to enabled" in flags.get("MIMOCODE_ENABLE_ANALYSIS", ""), "analysis flag semantics must record default-on behavior", errors)
            require("manager sets 0" in flags.get("MIMOCODE_ENABLE_ANALYSIS", ""), "analysis flag semantics must record value 0", errors)
        require(native.get("project_boundary_rejected_paths") == EXPECTED_PROJECT_BOUNDARY_PATHS, "baseline project boundary paths mismatch", errors)
        require("unknown files under MIMOCODE_CONFIG_DIR" in native.get("managed_config_dir_launch_closure", ""), "baseline managed config closure missing", errors)
    runtime_launch = contract.get("runtime_launch")
    require(isinstance(runtime_launch, dict), "contract runtime_launch missing", errors)
    if isinstance(runtime_launch, dict):
        require(runtime_launch.get("manager_owned_runtime_env_source") == "cli-tools/nddev_mimocode.py:MIMOCODE_FIXED_RUNTIME_ENV", "runtime env source mismatch", errors)
        require(runtime_launch.get("manager_owned_runtime_env") == EXPECTED_FIXED_RUNTIME_ENV, "runtime env values mismatch", errors)
        require("MIMOCODE_DISABLE_PROJECT_CONFIG=1" in runtime_launch.get("project_config_discovery", ""), "project config disable contract missing", errors)
        require("MIMOCODE_ENABLE_ANALYSIS=0" in runtime_launch.get("external_telemetry", ""), "analysis disable contract missing", errors)
        require(runtime_launch.get("project_boundary_rejected_paths_source") == "cli-tools/nddev_mimocode.py:PROJECT_BOUNDARY_PATHS", "project boundary source mismatch", errors)
        require(runtime_launch.get("managed_config_dir_launch_closure_source") == "cli-tools/nddev_mimocode.py:validate_launch_managed_config_boundary", "managed config closure source mismatch", errors)
        require("unknown files under MIMOCODE_CONFIG_DIR" in runtime_launch.get("managed_config_dir_launch_closure", ""), "managed config closure contract missing", errors)
    transaction = contract.get("transaction_policy")
    require(isinstance(transaction, dict), "contract transaction_policy missing", errors)
    if isinstance(transaction, dict):
        require(transaction.get("legacy_migrate_preserves_unmanaged_config_keys") is True, "legacy migrate preservation contract missing", errors)
        require(transaction.get("durable_write_order") == ["stage", "fchmod", "file-fsync", "replace", "parent-fsync"], "durable write order contract mismatch", errors)
        require(transaction.get("exact_postconditions") is True, "exact postcondition contract missing", errors)
        require("lexical absolute-target validation" in transaction.get("pre_lock_target_observation", ""), "pre-lock target observation contract missing", errors)
        require("inode identity" in transaction.get("rollback_exact_object_graph", ""), "exact object graph contract missing inode identity", errors)
        require("rename-held undo" in transaction.get("rollback_strategy", ""), "rollback strategy contract mismatch", errors)
        require(transaction.get("restore_removes_known_managed_paths_absent_from_backup") is True, "restore deletion contract missing", errors)
        require(transaction.get("restore_unknown_backup_paths") == "fail-closed", "restore unknown-path contract mismatch", errors)
        require(transaction.get("backup_file_records") == "path-size-sha256", "backup file record contract mismatch", errors)
        require("empty extra directories" in transaction.get("backup_physical_topology", ""), "backup topology contract missing", errors)
        require("cleanup failures do not return success" in transaction.get("backup_cleanup_postcondition", ""), "backup cleanup contract missing", errors)
        require(transaction.get("same_uid_recomputed_payload_digest_tamper_machine_capability") is False, "same-UID tamper capability must be false", errors)
        require(transaction.get("setup_update_command") == "update", "setup update command contract missing", errors)
        require("update-cli" in transaction.get("setup_update_scope", ""), "setup update/software update separation missing", errors)
        require("true no-op" in transaction.get("setup_update_noop", ""), "setup update no-op contract missing", errors)
        require("only when update changes" in transaction.get("setup_update_backup", ""), "setup update backup contract missing", errors)
        require("exact desired managed bytes" in transaction.get("setup_update_postcondition", ""), "setup update postcondition contract missing", errors)
    software = contract.get("software_install")
    require(isinstance(software, dict), "contract software_install missing", errors)
    if isinstance(software, dict):
        require(software.get("github_release_page_asset_count") == RELEASE_PAGE_ASSET_COUNT, "contract release page asset count mismatch", errors)
        require(software.get("generated_source_downloads") == GENERATED_SOURCE_DOWNLOADS, "contract generated source downloads mismatch", errors)
        require(software.get("observed_uploaded_runtime_asset_ids") == OBSERVED_UPLOADED_RUNTIME_ASSET_IDS, "contract observed runtime asset ids mismatch", errors)
        require(software.get("supported_product_host_ids") == SUPPORTED_PRODUCT_HOST_IDS, "contract product host ids mismatch", errors)
        require(software.get("rejected_product_host_ids") == REJECTED_PRODUCT_HOST_IDS, "contract rejected host ids mismatch", errors)
        require(software.get("product_host_asset_selection") == PRODUCT_HOST_ASSET_SELECTION, "contract product host asset selection mismatch", errors)
        require(software.get("platform_selection_source") == "cli-tools/nddev_mimocode.py:detect_platform_selection", "contract platform source mismatch", errors)
        require(software.get("ubuntu_version_floor") is None, "contract must not invent an Ubuntu version floor", errors)
        require("upstream publishes no official floor" in software.get("linux_product_scope", ""), "contract must describe no official Ubuntu floor", errors)
        require(software.get("staged_probe_environment_source") == "cli-tools/nddev_mimocode.py:minimal_process_env", "staged probe env source mismatch", errors)
        require("MIMOCODE_ENABLE_ANALYSIS=0" in software.get("staged_probe_telemetry", ""), "staged probe telemetry contract missing", errors)
    require(nddev_mimocode.MIMOCODE_FIXED_RUNTIME_ENV == EXPECTED_FIXED_RUNTIME_ENV, "manager fixed runtime env mismatch", errors)
    require([str(path) for path in nddev_mimocode.PROJECT_BOUNDARY_PATHS] == EXPECTED_PROJECT_BOUNDARY_PATHS, "manager project boundary paths mismatch", errors)
    require(list(nddev_mimocode.OBSERVED_UPLOADED_RUNTIME_ASSET_IDS) == OBSERVED_UPLOADED_RUNTIME_ASSET_IDS, "manager observed runtime asset ids mismatch", errors)
    require(nddev_mimocode.RELEASE_PAGE_ASSET_COUNT == RELEASE_PAGE_ASSET_COUNT, "manager release page asset count mismatch", errors)
    require(list(nddev_mimocode.GENERATED_SOURCE_DOWNLOADS) == GENERATED_SOURCE_DOWNLOADS, "manager generated source downloads mismatch", errors)
    require(list(nddev_mimocode.SUPPORTED_PRODUCT_HOST_IDS) == SUPPORTED_PRODUCT_HOST_IDS, "manager product host ids mismatch", errors)
    require(list(nddev_mimocode.REJECTED_PRODUCT_HOST_IDS) == REJECTED_PRODUCT_HOST_IDS, "manager rejected host ids mismatch", errors)
    for name in EXPECTED_FIXED_RUNTIME_ENV:
        require(name in nddev_mimocode.BLOCKED_MANAGER_ENV_NAMES, f"manager env override not blocked: {name}", errors)
    command_policy = contract.get("command_policy")
    require(isinstance(command_policy, dict), "contract command_policy missing", errors)
    if isinstance(command_policy, dict):
        require(
            command_policy.get("target_preflight_order")
            == ["supported-host", "lexical-absolute-target", "external-lifecycle-lock", "target-filesystem-resolution"],
            "target preflight order contract mismatch",
            errors,
        )
        require("JSON stdout" in command_policy.get("json_argparse_errors", ""), "JSON argparse boundary contract missing", errors)


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
        require(isinstance(asset.get("size"), int) and asset["size"] > 0, f"asset size invalid: {key}", errors)
        require(re.fullmatch(r"[0-9a-f]{64}", str(asset.get("sha256", ""))) is not None, f"asset SHA invalid: {key}", errors)
        require(str(asset.get("url", "")).startswith(prefix), f"asset URL mismatch: {key}", errors)
        if key in {"linux-arm64", "linux-x64", "linux-x64-baseline"}:
            require("-musl" not in asset["name"], f"Ubuntu-selected asset must not use musl archive: {key}", errors)
        if "musl" in key:
            require("-musl" in asset["name"], f"musl observation name mismatch: {key}", errors)
        if key.startswith("windows-"):
            require(asset["name"].startswith("mimocode-windows-"), f"Windows observation name mismatch: {key}", errors)
        if key == "darwin-arm64":
            executable = asset.get("executable")
            require(isinstance(executable, dict), "darwin-arm64 executable metadata missing", errors)
            if isinstance(executable, dict):
                require(executable.get("path") == nddev_mimocode.COMMAND_NAME, "executable path mismatch", errors)
                require(executable.get("installer_mode") == "0755", "installer mode mismatch", errors)
                require(re.fullmatch(r"[0-9a-f]{64}", str(executable.get("sha256", ""))) is not None, "executable SHA invalid", errors)


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
        ("macos x64 baseline", injected_host("darwin", "x86_64", avx2=False), "darwin-x64-baseline", "macos-x64"),
        ("macos translated arm64", injected_host("darwin", "x86_64", avx2=True, darwin_translated=True), "darwin-arm64", "macos-arm64"),
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
            injected_host("linux", "x86_64", libc="glibc", os_id="ubuntu", variant_id="server", avx2=False),
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
        require(selection.get("asset_key") == expected_asset, f"{label} selected wrong asset", errors)
        require(selection.get("product_host_id") == expected_product_host, f"{label} selected wrong product host", errors)
        asset_key, asset = nddev_mimocode.detect_platform_asset(host)
        require(asset_key == expected_asset and isinstance(asset, dict), f"{label} asset lookup failed", errors)

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
        require(payload.get("ok") is False and isinstance(payload.get("error"), str), f"argparse JSON error payload mismatch: {argv}", errors)

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
            require(payload.get("error") == "forced unsupported host", f"{command} did not fail at host preflight", errors)
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

    def traced_acquire(descriptor: int, path: Path) -> None:
        if path.name.endswith(nddev_mimocode.BOOTSTRAP_LOCK_SUFFIX):
            trace.append("external-lock-acquire")
        else:
            trace.append("target-lock-acquire")
        return original_acquire(descriptor, path)

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
                rc, stdout, stderr = run_main_captured(["status", "--target", str(target), "--json"])
                require(rc == 0, "status preflight trace command failed", errors)
                require(stderr == "", "status preflight trace wrote stderr", errors)
                require(json.loads(stdout).get("state") == "unmanaged", "status preflight trace payload mismatch", errors)
                status_trace = list(trace)
                for command in ("install-cli", "update-cli"):
                    trace.clear()
                    command_target = Path(raw) / command
                    traced_target_path["value"] = str(command_target.parent.resolve() / command_target.name)
                    rc, stdout, stderr = run_main_captured([command, "--target", str(command_target), "--json"])
                    require(rc == 2, f"{command} preflight trace command should fail before live work", errors)
                    require(stderr == "", f"{command} preflight trace wrote stderr", errors)
                    payload = json.loads(stdout)
                    if command == "install-cli":
                        require(payload.get("error") == "forced stop before network", "install-cli did not stop at stubbed network boundary", errors)
                    else:
                        require("requires existing" in payload.get("error", ""), "update-cli absent target error mismatch", errors)
                    require(not original_path_present(command_target), f"{command} left a newly created target after failure", errors)
                    require(trace[:2] == ["host", "lexical-target"], f"{command} preflight order mismatch: {trace}", errors)
                    require(
                        "target-path-present" in trace
                        and trace.index("target-path-present") > trace.index("external-lock-acquire"),
                        f"{command} observed target before external lock: {trace}",
                        errors,
                    )
                    require(
                        trace.index("target-path-present") > trace.index("target-fs-canonicalization"),
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
        trace[:4] == ["host", "lexical-target", "external-lock-acquire", "target-fs-canonicalization"],
        f"preflight order mismatch: {trace}",
        errors,
    )
    require("status-read" in trace and trace.index("status-read") > trace.index("target-fs-canonicalization"), "status read occurred before external lock canonicalization", errors)


def validate_setup_profiles(errors: list[str]) -> None:
    manifest = read_json("build/manifest.json")
    contract = read_json("config/nddev-contract.json")
    require(manifest.get("setup_ids") == SETUP_IDS, "manifest setup ids mismatch", errors)
    require(manifest.get("profile_ids") == PROFILE_IDS, "manifest profile ids mismatch", errors)
    require(manifest.get("setup_lifecycle") == SETUP_LIFECYCLE, "manifest setup lifecycle mismatch", errors)
    setup_system = contract.get("setup_system")
    require(isinstance(setup_system, dict), "contract setup_system missing", errors)
    if isinstance(setup_system, dict):
        require(setup_system.get("setup_ids") == SETUP_IDS, "contract setup ids mismatch", errors)
        require(setup_system.get("profile_ids") == PROFILE_IDS, "contract profile ids mismatch", errors)
        require(setup_system.get("default_profile_id") == nddev_mimocode.DEFAULT_PROFILE_ID, "default profile mismatch", errors)
        require(setup_system.get("lifecycle") == FULL_LIFECYCLE, "contract setup lifecycle mismatch", errors)
    command_policy = contract.get("command_policy")
    require(isinstance(command_policy, dict), "contract command_policy missing", errors)
    if isinstance(command_policy, dict):
        require(command_policy.get("json_supported") == JSON_COMMANDS, "command JSON support mismatch", errors)
        require(command_policy.get("target_required") == TARGET_COMMANDS, "target command list mismatch", errors)
    update_args = nddev_mimocode.parse_args(["update", "--target", "/tmp/nddev-mimocode-target", "--json"])
    require(update_args.command == "update", "update parser command mismatch", errors)
    require(not hasattr(update_args, "setup") and not hasattr(update_args, "profile"), "setup update must not accept setup/profile arguments", errors)
    listed = nddev_mimocode.list_setups()
    profiles = nddev_mimocode.list_profiles()
    require([item["id"] for item in listed] == SETUP_IDS, "manager setup list mismatch", errors)
    require([item["id"] for item in profiles] == PROFILE_IDS, "manager profile list mismatch", errors)
    for profile_id in PROFILE_IDS:
        _metadata, desired = nddev_mimocode.render_setup("nddev-builder", profile_id)
        config = json.loads(desired[nddev_mimocode.MIMOCODE_CONFIG_RELATIVE].decode("utf-8"))
        require(config.get("$schema") == "https://mimo.xiaomi.com/mimocode/config.json", f"{profile_id} schema mismatch", errors)
        require(config.get("mcp") == {}, f"{profile_id} must not configure live MCP servers", errors)
        require(config.get("plugin") == [], f"{profile_id} must not load default plugins", errors)
        require("tools" not in config, f"{profile_id} must not use deprecated tools config", errors)
        if profile_id == "full-auto":
            require(config.get("permission") == "allow", "full-auto must use native allow-all", errors)
            stamp = json.loads(desired[Path(nddev_mimocode.STAMP_NAME)].decode("utf-8"))
            require(set(stamp["launch_env"]).isdisjoint(EXPECTED_FIXED_RUNTIME_ENV), "full-auto launch_env must not override manager-owned runtime env", errors)
            require("MIMOCODE_MIMO_ONLY" not in stamp["launch_env"], "full-auto must not force MiMo-only", errors)
            require(stamp["launch_env"].get("MIMOCODE_DANGEROUSLY_SKIP_PERMISSIONS") == "1", "full-auto bypass env missing", errors)
        else:
            require(config.get("default_agent") == "plan", "safe profile must use plan agent", errors)
            require(isinstance(config.get("permission"), dict), "safe permission must be object", errors)
            stamp = json.loads(desired[Path(nddev_mimocode.STAMP_NAME)].decode("utf-8"))
            require(stamp["launch_env"] == {}, "safe launch_env must be empty", errors)


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
            require(env.get("PATH") == nddev_mimocode.DETERMINISTIC_PATH, "launch PATH mismatch", errors)
            for name, expected in EXPECTED_FIXED_RUNTIME_ENV.items():
                require(env.get(name) == expected, f"fixed runtime env mismatch: {name}", errors)
            require("MIMOCODE_MIMO_ONLY" not in env, "launch env must not force MiMo-only", errors)
            for name, value in safe_parent.items():
                require(env.get(name) == value, f"safe env missing: {name}", errors)
            for name in secret_parent:
                require(env.get(name) != sentinel, f"secret env leaked: {name}", errors)
            for key in ("HOME", "TMPDIR", "XDG_CONFIG_HOME", "MIMOCODE_HOME", "MIMOCODE_CONFIG_DIR"):
                path = Path(env[key])
                require(path.exists() and os.access(path, os.W_OK), f"runtime path is not writable: {key}", errors)
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
        require(unknown_skill.exists(), "managed config boundary check must not delete unknown files", errors)
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


def identity_snapshot(paths: list[Path]) -> dict[str, tuple[int, int, int, int, str | None]]:
    result: dict[str, tuple[int, int, int, int, str | None]] = {}
    for path in sorted(paths, key=str):
        info = path.lstat()
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if stat.S_ISREG(info.st_mode) else None
        result[str(path)] = (info.st_ino, info.st_size, stat.S_IMODE(info.st_mode), info.st_mtime_ns, digest)
    return result


def managed_identity_snapshot(target: Path) -> dict[str, tuple[int, int, int, int, str | None]]:
    paths = [target / relative for relative in nddev_mimocode.MANAGED_PATHS if (target / relative).exists()]
    return identity_snapshot(paths)


def software_identity_snapshot(target: Path) -> dict[str, tuple[int, int, int, int, str | None]]:
    paths = [target / relative for relative in nddev_mimocode.software_file_modes() if (target / relative).exists()]
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
            "version_tree_executable": str(nddev_mimocode.SOFTWARE_VERSION_RELATIVE / nddev_mimocode.COMMAND_NAME),
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
        (nddev_mimocode.SOFTWARE_VERSION_RELATIVE / nddev_mimocode.COMMAND_NAME, binary, nddev_mimocode.OWNER_EXECUTABLE_MODE),
        (nddev_mimocode.SOFTWARE_MANIFEST_RELATIVE, fake_software_manifest(binary, version), nddev_mimocode.OWNER_FILE_MODE),
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
            require(after_entries == before_entries, f"forced {patched_name} failure left temp residue", errors)
            config_path = target / nddev_mimocode.MIMOCODE_CONFIG_RELATIVE
            require(config_path.read_bytes() == original_content, f"forced {patched_name} failure changed original managed file", errors)
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
        require(after_entries == before_entries, "forced temp fchmod failure left temp residue", errors)
        require(config_path.read_bytes() == original_content, "forced temp fchmod failure changed original managed file", errors)
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
        require(not destination_chmod_after_replace, "managed replace must not chmod destination after os.replace", errors)
        require(after_entries == before_entries, "successful replace left temp residue", errors)
        require(config_path.read_bytes() == updated_content, "successful replace did not write new managed file", errors)
        require(stat.S_IMODE(config_path.lstat().st_mode) == 0o600, "successful replace did not preserve 0600 mode", errors)
        nddev_mimocode.validate_launch_managed_config_boundary(target)


def validate_transaction_faults(errors: list[str]) -> None:
    with isolated_bootstrap_root(errors):
        with tempfile.TemporaryDirectory(prefix="nddev-mimocode-transaction.") as raw:
            root = Path(raw)

            target = make_managed_target(root / "noop")
            before_managed_identity = managed_identity_snapshot(target)
            before_backup = nddev_mimocode.backup_pool_snapshot(target)
            result = nddev_mimocode.mutate_setup(target, "nddev-builder", "full-auto", "install")
            require(result.get("changed") == [], "managed no-op must report no changed paths", errors)
            require(managed_identity_snapshot(target) == before_managed_identity, "managed no-op changed file identity", errors)
            require(nddev_mimocode.backup_pool_snapshot(target) == before_backup, "managed no-op changed backup state", errors)
            update_plan = nddev_mimocode.plan_setup(target, "nddev-builder", "full-auto")
            require(update_plan.get("operation") == "update", "managed current plan must route to setup update", errors)
            require(update_plan.get("changed") == [], "managed current update plan must be a no-op", errors)
            update_result = nddev_mimocode.update_setup(target)
            require(update_result.get("operation") == "update", "setup update operation mismatch", errors)
            require(update_result.get("changed") == [], "setup update no-op must report no changed paths", errors)
            require(update_result.get("backup_slot") is None, "setup update no-op must not rotate backups", errors)
            require(update_result.get("needs_update") is False, "setup update no-op must report current state", errors)
            require(managed_identity_snapshot(target) == before_managed_identity, "setup update no-op changed file identity", errors)
            require(nddev_mimocode.backup_pool_snapshot(target) == before_backup, "setup update no-op changed backup state", errors)
            require_manager_failure(lambda: nddev_mimocode.update_setup(root / "missing-update"), "setup update must reject missing targets", errors)

            target = make_managed_target(root / "update-needed")
            stamp_path = target / nddev_mimocode.STAMP_NAME
            stamp = json.loads(stamp_path.read_text(encoding="utf-8"))
            stamp["build_version"] = "0.1.0"
            stamp_path.write_bytes(nddev_mimocode.canonical_json(stamp))
            stamp_path.chmod(0o600)
            require(nddev_mimocode.inspect_target(target).get("needs_update") is True, "setup update fixture must need update", errors)
            before_backup = nddev_mimocode.backup_pool_snapshot(target)
            update_result = nddev_mimocode.update_setup(target)
            require(update_result.get("operation") == "update", "setup update changed operation mismatch", errors)
            require(update_result.get("changed") == [nddev_mimocode.STAMP_NAME], "setup update should change only the stale stamp", errors)
            require(update_result.get("backup_slot") == 0, "setup update with changes must create backup", errors)
            require(update_result.get("needs_update") is False, "setup update did not clear needs_update", errors)
            require(nddev_mimocode.backup_pool_snapshot(target) != before_backup, "setup update with changes did not advance backup state", errors)
            require_no_transaction_residue(target, "setup update with changes left residue", errors)

            target = root / "failed-first-install"
            before_root = tree_snapshot(root)
            original_verify_managed = nddev_mimocode.verify_managed_state
            postcondition_failed = {"value": False}

            def fail_first_install_postcondition(target_arg: Path, desired: dict[Path, bytes | None], label: str) -> None:
                original_verify_managed(target_arg, desired, label)
                if label == "managed postcondition" and not postcondition_failed["value"]:
                    postcondition_failed["value"] = True
                    raise nddev_mimocode.ConcurrentTargetChange("forced first install postcondition failure")

            nddev_mimocode.verify_managed_state = fail_first_install_postcondition
            try:
                require_exception(
                    lambda: nddev_mimocode.mutate_setup(target, "nddev-builder", "safe", "install"),
                    nddev_mimocode.ConcurrentTargetChange,
                    "first setup install postcondition failure must propagate",
                    errors,
                )
            finally:
                nddev_mimocode.verify_managed_state = original_verify_managed
            require(postcondition_failed["value"], "first setup install postcondition fault was not exercised", errors)
            require(tree_snapshot(root) == before_root, "failed first setup install changed the absent target graph", errors)
            require(not nddev_mimocode.path_present(target), "failed first setup install left a target directory", errors)

            for label, patch_name in (("write", "write"), ("fchmod", "fchmod")):
                target = make_managed_target(root / label)
                before = tree_snapshot(target)
                original = getattr(nddev_mimocode.os, patch_name)

                def failing_call(*_args: Any, **_kwargs: Any) -> None:
                    raise OSError(f"forced {patch_name} failure")

                setattr(nddev_mimocode.os, patch_name, failing_call)
                try:
                    require_exception(
                        lambda: nddev_mimocode.mutate_setup(target, "nddev-builder", "safe", "switch"),
                        OSError,
                        f"forced {patch_name} failure must propagate",
                        errors,
                    )
                finally:
                    setattr(nddev_mimocode.os, patch_name, original)
                require(tree_snapshot(target) == before, f"forced {patch_name} failure changed managed tree", errors)
                require_no_transaction_residue(target, f"forced {patch_name} failure left residue", errors)

            target = make_managed_target(root / "parent-fsync")
            before = tree_snapshot(target)
            original_fsync_directory = nddev_mimocode.fsync_directory
            armed = {"value": False}

            def failing_parent_fsync(path: Path, label: str) -> None:
                if armed["value"] and label.startswith("parent directory for "):
                    armed["value"] = False
                    raise OSError("forced parent fsync failure")
                return original_fsync_directory(path, label)

            nddev_mimocode.fsync_directory = failing_parent_fsync
            armed["value"] = True
            try:
                require_exception(
                    lambda: nddev_mimocode.mutate_setup(target, "nddev-builder", "safe", "switch"),
                    OSError,
                    "forced managed parent fsync failure must propagate",
                    errors,
                )
            finally:
                nddev_mimocode.fsync_directory = original_fsync_directory
            require(tree_snapshot(target) == before, "forced parent fsync failure changed managed tree", errors)
            require_no_transaction_residue(target, "forced parent fsync failure left residue", errors)

            target = make_managed_target(root / "postcondition")
            before = nddev_mimocode.current_managed_snapshot(target)
            original_verify_managed = nddev_mimocode.verify_managed_state
            tampered = {"value": False}

            def tampering_verify(target_arg: Path, desired: dict[Path, bytes | None], label: str) -> None:
                if label == "managed replace" and not tampered["value"]:
                    config_path = target_arg / nddev_mimocode.MIMOCODE_CONFIG_RELATIVE
                    config_path.write_bytes(b'{"tampered":true}\n')
                    config_path.chmod(0o600)
                    tampered["value"] = True
                original_verify_managed(target_arg, desired, label)

            nddev_mimocode.verify_managed_state = tampering_verify
            try:
                require_exception(
                    lambda: nddev_mimocode.mutate_setup(target, "nddev-builder", "safe", "switch"),
                    nddev_mimocode.ConcurrentTargetChange,
                    "managed postcondition tamper must fail closed",
                    errors,
                )
            finally:
                nddev_mimocode.verify_managed_state = original_verify_managed
            require(nddev_mimocode.current_managed_snapshot(target) == before, "managed postcondition tamper was not rolled back", errors)
            require_no_transaction_residue(target, "managed postcondition tamper left residue", errors)

            target = make_managed_target(root / "managed-rollback-one-shot")
            before_managed = managed_identity_snapshot(target)
            before_backup = nddev_mimocode.backup_pool_snapshot(target)
            original_verify_managed = nddev_mimocode.verify_managed_state
            original_fsync_directory = nddev_mimocode.fsync_directory
            rollback_armed = {"value": False}
            rollback_failed = {"value": False}

            def original_fails_then_rollback_fault(target_arg: Path, desired: dict[Path, bytes | None], label: str) -> None:
                original_verify_managed(target_arg, desired, label)
                if label == "managed replace" and not rollback_armed["value"]:
                    rollback_armed["value"] = True
                    raise nddev_mimocode.ConcurrentTargetChange("forced managed postcondition failure")

            def one_shot_rollback_parent_fsync(path: Path, label: str) -> None:
                if rollback_armed["value"] and not rollback_failed["value"] and label.startswith("parent directory after rollback restore "):
                    rollback_failed["value"] = True
                    raise OSError("forced managed rollback parent fsync failure")
                return original_fsync_directory(path, label)

            nddev_mimocode.verify_managed_state = original_fails_then_rollback_fault
            nddev_mimocode.fsync_directory = one_shot_rollback_parent_fsync
            try:
                require_exception(
                    lambda: nddev_mimocode.mutate_setup(target, "nddev-builder", "safe", "switch"),
                    nddev_mimocode.ConcurrentTargetChange,
                    "managed rollback one-shot fault must re-raise original failure",
                    errors,
                )
            finally:
                nddev_mimocode.verify_managed_state = original_verify_managed
                nddev_mimocode.fsync_directory = original_fsync_directory
            require(rollback_failed["value"], "managed rollback one-shot fault was not exercised", errors)
            require(managed_identity_snapshot(target) == before_managed, "managed rollback one-shot fault left mixed managed objects", errors)
            require(nddev_mimocode.backup_pool_snapshot(target) == before_backup, "managed rollback one-shot fault changed backup state", errors)
            require_no_transaction_residue(target, "managed rollback one-shot fault left residue", errors)

            target = make_managed_target(root / "backup-schema")
            nddev_mimocode.mutate_setup(target, "nddev-builder", "safe", "switch")
            pool = nddev_mimocode.backup_pool(target)
            envelope, files = nddev_mimocode.load_backup(target, 0)
            require(envelope.get("file_records") == nddev_mimocode.backup_file_records(files), "backup file_records mismatch", errors)
            backup_config = pool / "0" / nddev_mimocode.MIMOCODE_CONFIG_RELATIVE
            backup_stamp = pool / "0" / nddev_mimocode.STAMP_NAME
            tampered_config = b'{"tampered":true}\n'
            backup_config.write_bytes(tampered_config)
            backup_config.chmod(0o600)
            stamp = json.loads(backup_stamp.read_text(encoding="utf-8"))
            stamp["managed_files"][str(nddev_mimocode.MIMOCODE_CONFIG_RELATIVE)] = nddev_mimocode.managed_digest(
                nddev_mimocode.MIMOCODE_CONFIG_RELATIVE,
                tampered_config,
            )
            backup_stamp.write_bytes(nddev_mimocode.canonical_json(stamp))
            backup_stamp.chmod(0o600)
            before_restore = nddev_mimocode.current_managed_snapshot(target)
            require_manager_failure(lambda: nddev_mimocode.restore_backup(target, 0), "tampered backup payload must be rejected", errors)
            require(nddev_mimocode.current_managed_snapshot(target) == before_restore, "tampered backup restore mutated target", errors)

            target = make_managed_target(root / "backup-extra-empty-dir")
            nddev_mimocode.mutate_setup(target, "nddev-builder", "safe", "switch")
            extra_dir = nddev_mimocode.backup_pool(target) / "0" / "empty-extra"
            extra_dir.mkdir(mode=0o700)
            extra_dir.chmod(0o700)
            before_restore = nddev_mimocode.current_managed_snapshot(target)
            require_manager_failure(lambda: nddev_mimocode.restore_backup(target, 0), "backup slot extra empty directory must be rejected", errors)
            require(nddev_mimocode.current_managed_snapshot(target) == before_restore, "extra backup directory restore mutated target", errors)

            target = make_managed_target(root / "rotation")
            for index in range(12):
                profile = "safe" if index % 2 == 0 else "full-auto"
                nddev_mimocode.mutate_setup(target, "nddev-builder", profile, "switch")
            pool = nddev_mimocode.backup_pool(target)
            require(not (pool / "10").exists(), "backup rotation created slot 10", errors)
            for slot in range(10):
                slot_dir = pool / str(slot)
                require(slot_dir.is_dir(), f"backup rotation missing slot {slot}", errors)
                envelope, files = nddev_mimocode.load_backup(target, slot)
                require(envelope["slot"] == slot, f"backup slot {slot} identity mismatch", errors)
                require(envelope["file_records"] == nddev_mimocode.backup_file_records(files), f"backup slot {slot} records mismatch", errors)

            target = make_managed_target(root / "backup-fail")
            before = tree_snapshot(target)
            original_replace = nddev_mimocode.os.replace

            def failing_pool_replace(source: Any, destination: Any, *args: Any, **kwargs: Any) -> None:
                if Path(destination).name == ".nddev-mimocode-backups":
                    raise OSError("forced backup pool replace failure")
                return original_replace(source, destination, *args, **kwargs)

            nddev_mimocode.os.replace = failing_pool_replace
            try:
                require_exception(
                    lambda: nddev_mimocode.mutate_setup(target, "nddev-builder", "safe", "switch"),
                    OSError,
                    "forced backup pool replace failure must propagate",
                    errors,
                )
            finally:
                nddev_mimocode.os.replace = original_replace
            require(tree_snapshot(target) == before, "backup pool replace failure mutated target", errors)
            require_no_transaction_residue(target, "backup pool replace failure left residue", errors)

            target = make_managed_target(root / "backup-rollback-one-shot")
            nddev_mimocode.mutate_setup(target, "nddev-builder", "safe", "switch")
            before_managed = nddev_mimocode.current_managed_snapshot(target)
            before_backup = nddev_mimocode.backup_pool_snapshot(target)
            original_fsync_directory = nddev_mimocode.fsync_directory
            original_replace = nddev_mimocode.os.replace
            publish_failed = {"value": False}
            rollback_replace_failed = {"value": False}
            rollback_fsync_failed = {"value": False}

            def fail_after_backup_publish(path: Path, label: str) -> None:
                if label == "target directory after backup pool replace" and not publish_failed["value"]:
                    publish_failed["value"] = True
                    raise OSError("forced backup publish parent fsync failure")
                if label == "target directory after backup pool restore" and rollback_replace_failed["value"] and not rollback_fsync_failed["value"]:
                    rollback_fsync_failed["value"] = True
                    raise OSError("forced backup rollback parent fsync failure")
                return original_fsync_directory(path, label)

            def fail_one_backup_rollback_replace(source: Any, destination: Any, *args: Any, **kwargs: Any) -> None:
                source_path = Path(source)
                if (
                    publish_failed["value"]
                    and not rollback_replace_failed["value"]
                    and Path(destination) == nddev_mimocode.backup_pool(target)
                    and ".retired." in source_path.name
                ):
                    rollback_replace_failed["value"] = True
                    raise OSError("forced backup rollback replace failure")
                return original_replace(source, destination, *args, **kwargs)

            nddev_mimocode.fsync_directory = fail_after_backup_publish
            nddev_mimocode.os.replace = fail_one_backup_rollback_replace
            try:
                require_exception(
                    lambda: nddev_mimocode.mutate_setup(target, "nddev-builder", "full-auto", "switch"),
                    OSError,
                    "forced backup publish failure must propagate",
                    errors,
                )
            finally:
                nddev_mimocode.fsync_directory = original_fsync_directory
                nddev_mimocode.os.replace = original_replace
            require(
                publish_failed["value"] and rollback_replace_failed["value"] and rollback_fsync_failed["value"],
                "backup rollback one-shot fault was not exercised",
                errors,
            )
            require(nddev_mimocode.current_managed_snapshot(target) == before_managed, "backup rollback one-shot changed managed state", errors)
            require(nddev_mimocode.backup_pool_snapshot(target) == before_backup, "backup rollback one-shot changed backup state", errors)
            require_no_transaction_residue(target, "backup rollback one-shot left residue", errors)

            target = make_managed_target(root / "backup-cleanup-retry")
            nddev_mimocode.mutate_setup(target, "nddev-builder", "safe", "switch")
            before_backup = nddev_mimocode.backup_pool_snapshot(target)
            original_rmdir = nddev_mimocode.rmdir_if_empty_durable
            cleanup_failed = {"value": False}

            def fail_retired_cleanup_once(path: Path) -> bool:
                if ".retired." in str(path) and not cleanup_failed["value"]:
                    cleanup_failed["value"] = True
                    raise OSError("forced backup retired cleanup failure")
                return original_rmdir(path)

            nddev_mimocode.rmdir_if_empty_durable = fail_retired_cleanup_once
            try:
                switched = nddev_mimocode.mutate_setup(target, "nddev-builder", "full-auto", "switch")
            finally:
                nddev_mimocode.rmdir_if_empty_durable = original_rmdir
            require(cleanup_failed["value"], "backup retired cleanup one-shot fault was not exercised", errors)
            require(switched.get("backup_slot") == 0, "backup cleanup retry switch did not create backup", errors)
            require(nddev_mimocode.backup_pool_snapshot(target) != before_backup, "backup cleanup retry did not advance backup pool", errors)
            require_no_transaction_residue(target, "backup cleanup retry left residue", errors)

            target = (root / "remove-cli").resolve()
            make_fake_software(target)
            before = software_identity_snapshot(target)
            original_replace = nddev_mimocode.os.replace
            moved_first = {"value": False}

            def failing_remove_hold(source: Any, destination: Any, *args: Any, **kwargs: Any) -> None:
                source_path = Path(source)
                if source_path == nddev_mimocode.software_tree_binary(target):
                    moved_first["value"] = True
                    return original_replace(source, destination, *args, **kwargs)
                if moved_first["value"] and source_path == nddev_mimocode.mimo_executable(target):
                    raise OSError("forced software hold failure")
                return original_replace(source, destination, *args, **kwargs)

            nddev_mimocode.os.replace = failing_remove_hold
            try:
                require_exception(lambda: nddev_mimocode.remove_cli(target), OSError, "forced remove-cli hold failure must propagate", errors)
            finally:
                nddev_mimocode.os.replace = original_replace
            require(software_identity_snapshot(target) == before, "remove-cli hold failure did not rollback exact software objects", errors)
            require_no_transaction_residue(target, "remove-cli hold failure left residue", errors)

            target = (root / "software-rollback").resolve()
            old_binary = b"old-binary\n"
            new_binary = b"new-binary\n"
            make_fake_software(target, old_binary)
            before_software = software_identity_snapshot(target)
            original_host = nddev_mimocode.require_supported_product_host
            original_status = nddev_mimocode.software_status
            original_selected = nddev_mimocode.selected_asset
            original_read_url = nddev_mimocode.read_url
            original_extract = nddev_mimocode.extract_verified_binary
            original_installer = nddev_mimocode.read_pinned_installer
            original_run_installer = nddev_mimocode.run_official_installer
            original_verify = nddev_mimocode.verify_software_state
            original_fsync_directory = nddev_mimocode.fsync_directory
            status_calls = {"count": 0}
            rollback_fsync_failed = {"value": False}
            rollback_armed = {"value": False}

            nddev_mimocode.require_supported_product_host = lambda _host=None: None
            def fake_status(_target: Path) -> dict[str, Any]:
                status_calls["count"] += 1
                return {"present": True, "installed": True, "current": status_calls["count"] > 1, "drift": []}

            nddev_mimocode.software_status = fake_status
            nddev_mimocode.selected_asset = lambda: ("test", {
                "url": "https://example.invalid/test",
                "sha256": hashlib.sha256(b"x").hexdigest(),
                "size": 1,
                "name": "test.tar.gz",
            })
            nddev_mimocode.read_url = lambda *_args, **_kwargs: b"x"
            nddev_mimocode.extract_verified_binary = lambda *_args, **_kwargs: ("mimo", 0o755, new_binary)
            nddev_mimocode.read_pinned_installer = lambda: (b"install", nddev_mimocode.INSTALLER_SHA256, nddev_mimocode.INSTALLER_URL, nddev_mimocode.INSTALLER_SIZE)
            nddev_mimocode.run_official_installer = lambda *_args, **_kwargs: {
                "binary": new_binary,
                "binary_sha256": hashlib.sha256(new_binary).hexdigest(),
                "installer_binary_mode": "0755",
                "installer_source": nddev_mimocode.INSTALLER_URL,
                "installer_sha256": nddev_mimocode.INSTALLER_SHA256,
                "version_output": nddev_mimocode.TESTED_VERSION,
            }

            def failing_postcondition(target_arg: Path, desired: dict[Path, tuple[bytes | None, int | None]], label: str) -> None:
                original_verify(target_arg, desired, label)
                if label == "software install postcondition":
                    rollback_armed["value"] = True
                    raise nddev_mimocode.ConcurrentTargetChange("forced software postcondition failure")

            def failing_rollback_parent_fsync(path: Path, label: str) -> None:
                if rollback_armed["value"] and not rollback_fsync_failed["value"] and label.startswith("parent directory after rollback restore "):
                    rollback_fsync_failed["value"] = True
                    raise OSError("forced rollback parent fsync failure")
                return original_fsync_directory(path, label)

            nddev_mimocode.verify_software_state = failing_postcondition
            nddev_mimocode.fsync_directory = failing_rollback_parent_fsync
            try:
                require_exception(
                    lambda: nddev_mimocode.install_or_update_cli(target, operation="update-cli"),
                    nddev_mimocode.ConcurrentTargetChange,
                    "software rollback one-shot parent fsync failure must re-raise original postcondition failure",
                    errors,
                )
            finally:
                nddev_mimocode.require_supported_product_host = original_host
                nddev_mimocode.software_status = original_status
                nddev_mimocode.selected_asset = original_selected
                nddev_mimocode.read_url = original_read_url
                nddev_mimocode.extract_verified_binary = original_extract
                nddev_mimocode.read_pinned_installer = original_installer
                nddev_mimocode.run_official_installer = original_run_installer
                nddev_mimocode.verify_software_state = original_verify
                nddev_mimocode.fsync_directory = original_fsync_directory
            require(rollback_fsync_failed["value"], "software rollback one-shot parent fsync fault was not exercised", errors)
            require(software_identity_snapshot(target) == before_software, "software rollback one-shot parent fsync failure left mixed software objects", errors)
            require_no_transaction_residue(target, "software rollback parent fsync failure left residue", errors)

            for fault_kind in ("replace", "parent-fsync"):
                target = (root / f"software-rollback-{fault_kind}").resolve()
                make_fake_software(target, old_binary)
                before_software = software_identity_snapshot(target)
                before_software_payload = nddev_mimocode.current_software_snapshot(target)
                desired_software = {
                    nddev_mimocode.SOFTWARE_VERSION_RELATIVE / nddev_mimocode.COMMAND_NAME: (new_binary, nddev_mimocode.OWNER_EXECUTABLE_MODE),
                    Path("bin") / nddev_mimocode.COMMAND_NAME: (new_binary, nddev_mimocode.OWNER_EXECUTABLE_MODE),
                    nddev_mimocode.SOFTWARE_MANIFEST_RELATIVE: (fake_software_manifest(new_binary, nddev_mimocode.TESTED_VERSION), nddev_mimocode.OWNER_FILE_MODE),
                }
                original_verify = nddev_mimocode.verify_software_state
                original_replace = nddev_mimocode.os.replace
                original_fsync_directory = nddev_mimocode.fsync_directory
                rollback_armed = {"value": False}
                rollback_failed = {"value": False}

                def software_original_fails(target_arg: Path, desired: dict[Path, tuple[bytes | None, int | None]], label: str) -> None:
                    original_verify(target_arg, desired, label)
                    if label == "software test" and not rollback_armed["value"]:
                        rollback_armed["value"] = True
                        raise nddev_mimocode.ConcurrentTargetChange("forced software postcondition failure")

                def one_shot_rollback_replace(source: Any, destination: Any, *args: Any, **kwargs: Any) -> None:
                    if (
                        rollback_armed["value"]
                        and fault_kind == "replace"
                        and not rollback_failed["value"]
                        and Path(destination) == target / nddev_mimocode.SOFTWARE_MANIFEST_RELATIVE
                    ):
                        rollback_failed["value"] = True
                        raise OSError("forced software rollback replace failure")
                    return original_replace(source, destination, *args, **kwargs)

                def one_shot_rollback_parent_fsync(path: Path, label: str) -> None:
                    if rollback_armed["value"] and fault_kind == "parent-fsync" and not rollback_failed["value"] and label.startswith("parent directory after rollback restore "):
                        rollback_failed["value"] = True
                        raise OSError("forced software rollback parent fsync failure")
                    return original_fsync_directory(path, label)

                nddev_mimocode.verify_software_state = software_original_fails
                nddev_mimocode.os.replace = one_shot_rollback_replace
                nddev_mimocode.fsync_directory = one_shot_rollback_parent_fsync
                try:
                    require_exception(
                        lambda: nddev_mimocode.apply_software_state(
                            target,
                            desired_software,
                            expected_before=before_software_payload,
                            rollback_on_error=True,
                            label="software test",
                        ),
                        nddev_mimocode.ConcurrentTargetChange,
                        f"software rollback one-shot {fault_kind} failure must re-raise original failure",
                        errors,
                    )
                finally:
                    nddev_mimocode.verify_software_state = original_verify
                    nddev_mimocode.os.replace = original_replace
                    nddev_mimocode.fsync_directory = original_fsync_directory
                require(rollback_failed["value"], f"software rollback one-shot {fault_kind} fault was not exercised", errors)
                require(software_identity_snapshot(target) == before_software, f"software rollback one-shot {fault_kind} left mixed software objects", errors)
                require_no_transaction_residue(target, f"software rollback one-shot {fault_kind} left residue", errors)

            target = (root / "software-rollback-unlink").resolve()
            target.mkdir(mode=0o700)
            target.chmod(0o700)
            before_empty = nddev_mimocode.current_software_snapshot(target)
            desired_software = {
                nddev_mimocode.SOFTWARE_VERSION_RELATIVE / nddev_mimocode.COMMAND_NAME: (new_binary, nddev_mimocode.OWNER_EXECUTABLE_MODE),
                Path("bin") / nddev_mimocode.COMMAND_NAME: (new_binary, nddev_mimocode.OWNER_EXECUTABLE_MODE),
                nddev_mimocode.SOFTWARE_MANIFEST_RELATIVE: (fake_software_manifest(new_binary, nddev_mimocode.TESTED_VERSION), nddev_mimocode.OWNER_FILE_MODE),
            }
            original_verify = nddev_mimocode.verify_software_state
            original_unlink = Path.unlink
            rollback_armed = {"value": False}
            rollback_failed = {"value": False}

            def software_install_original_fails(target_arg: Path, desired: dict[Path, tuple[bytes | None, int | None]], label: str) -> None:
                original_verify(target_arg, desired, label)
                if label == "software install test" and not rollback_armed["value"]:
                    rollback_armed["value"] = True
                    raise nddev_mimocode.ConcurrentTargetChange("forced software install postcondition failure")

            def one_shot_rollback_unlink(self: Path, *args: Any, **kwargs: Any) -> None:
                if rollback_armed["value"] and not rollback_failed["value"] and self == target / nddev_mimocode.SOFTWARE_MANIFEST_RELATIVE:
                    rollback_failed["value"] = True
                    raise OSError("forced software rollback unlink failure")
                return original_unlink(self, *args, **kwargs)

            nddev_mimocode.verify_software_state = software_install_original_fails
            Path.unlink = one_shot_rollback_unlink
            try:
                require_exception(
                    lambda: nddev_mimocode.apply_software_state(
                        target,
                        desired_software,
                        expected_before=before_empty,
                        rollback_on_error=True,
                        label="software install test",
                    ),
                    nddev_mimocode.ConcurrentTargetChange,
                    "software rollback one-shot unlink failure must re-raise original failure",
                    errors,
                )
            finally:
                nddev_mimocode.verify_software_state = original_verify
                Path.unlink = original_unlink
            require(rollback_failed["value"], "software rollback one-shot unlink fault was not exercised", errors)
            require(nddev_mimocode.current_software_snapshot(target) == before_empty, "software rollback one-shot unlink left mixed state", errors)
            require_no_transaction_residue(target, "software rollback one-shot unlink left residue", errors)


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
        rendered_config = json.loads(desired[nddev_mimocode.MIMOCODE_CONFIG_RELATIVE].decode("utf-8"))
        require(rendered_config.get("custom_provider") == {"id": "preserved"}, "rendered migration config lost custom_provider", errors)
        require(rendered_config.get("user_note") == "preserved", "rendered migration config lost user_note", errors)
        require("disabled_providers" not in rendered_config, "rendered migration config kept legacy managed key", errors)
        require_manager_failure(
            lambda: nddev_mimocode.preserved_legacy_config_for_migration(target, {"state": "managed"}),
            "legacy preservation helper must reject non-legacy state",
            errors,
        )

        backup_files = {
            Path(nddev_mimocode.STAMP_NAME): b'{"schema_version":1}\n',
            Path("config") / "mimocode.json": b'{"legacy":true}\n',
        }
        restored = nddev_mimocode.restore_desired_from_backup(backup_files)
        require(set(restored) == set(nddev_mimocode.ALL_MANAGED_PATHS), "restore desired must cover all known managed paths", errors)
        for relative in nddev_mimocode.ALL_MANAGED_PATHS:
            if relative in backup_files:
                require(restored[relative] == backup_files[relative], f"restore desired missing backup file: {relative}", errors)
            else:
                require(restored[relative] is None, f"restore desired must remove absent managed file: {relative}", errors)
        require_manager_failure(
            lambda: nddev_mimocode.restore_desired_from_backup({Path("unknown") / "managed.json": b"{}"}),
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
            require_manager_failure(lambda: nddev_mimocode.update_setup(target), "setup update must reject legacy managed targets before migrate", errors)
            plan = nddev_mimocode.plan_setup(target, "nddev-builder", "safe")
            after_plan_snapshot = nddev_mimocode.current_managed_snapshot(target)
            require(after_plan_snapshot == before_snapshot, "legacy plan must not mutate managed state", errors)
            require(plan.get("operation") == "migrate", "legacy plan operation mismatch", errors)
            require(plan.get("backup_required") is True, "legacy plan backup flag mismatch", errors)
            migrated = nddev_mimocode.migrate_setup(target, "safe")
            require(plan.get("changed") == migrated.get("changed"), "legacy plan changed paths must exactly match migrate", errors)
            migrated_config = nddev_mimocode.load_json_object(
                target / nddev_mimocode.MIMOCODE_CONFIG_RELATIVE,
                "migrated config",
                owner_only=True,
            )
            require(migrated_config.get("custom_provider") == {"id": "preserved"}, "legacy migrate lost custom_provider", errors)
            require(migrated_config.get("user_note") == "preserved", "legacy migrate lost user_note", errors)
            for legacy_path in nddev_mimocode.LEGACY_MANAGED_PATHS:
                if legacy_path in nddev_mimocode.MANAGED_PATHS:
                    continue
                require(not nddev_mimocode.path_present(target / legacy_path), f"legacy migrate left removed path: {legacy_path}", errors)


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
                require(str(external).startswith(str(injected)), "external lock used real system root", errors)
                require(external.exists(), "external lock missing", errors)
                require(internal.exists(), "internal lock missing", errors)
                require(stat.S_IMODE(external.lstat().st_mode) == 0o600, "external lock mode mismatch", errors)
                require(stat.S_IMODE(internal.lstat().st_mode) == 0o600, "internal lock mode mismatch", errors)
                require(stat.S_IMODE(nddev_mimocode.lock_directory_path(canonical).lstat().st_mode) == 0o500, "internal lock directory not protected while held", errors)
            require(external.exists(), "external lock must persist after release", errors)
            require(internal.exists(), "internal lock must persist after release", errors)
            binding = json.loads(external.read_text(encoding="utf-8"))
            require(binding.get("canonical_target") == str(target.resolve()), "external lock binding mismatch", errors)


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
    prefix = " " * indent
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
    require(mapping_keys_after(workflow, "    permissions:", 4) == REQUIRED_RELEASE_PERMISSIONS, "release permissions keys must be closed", errors)
    with_values = mapping_keys_after(workflow, "    with:", 4)
    require(set(with_values) == REQUIRED_RELEASE_INPUTS, "release with keys must be closed", errors)
    archive_paths = folded_value(workflow, "archive_paths")
    runtime_paths = folded_value(workflow, "runtime_paths")
    require(archive_paths == RELEASE_ARCHIVE_PATHS, "release archive paths mismatch", errors)
    require(runtime_paths == RELEASE_RUNTIME_PATHS, "release runtime paths mismatch", errors)
    require(set(runtime_paths) <= set(archive_paths), "runtime paths must be archive subset", errors)
    for raw in archive_paths:
        path = ROOT / raw
        try:
            info = path.lstat()
        except FileNotFoundError:
            errors.append(f"declared archive path missing: {raw}")
            continue
        require(not stat.S_ISLNK(info.st_mode), f"declared archive path must not be symlink: {raw}", errors)
    require(REQUIRED_CONTRACT_ROOTS <= {path.split("/", 1)[0] for path in archive_paths}, "required source roots missing from archive", errors)
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
    require(any("skills/nddev-builder/SKILL.md" in item for item in source_targets), "builder skill projection missing", errors)
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
    validate_launch_environment(errors)
    validate_project_boundary(errors)
    validate_replace_managed_state_cleanup(errors)
    validate_transaction_faults(errors)
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
