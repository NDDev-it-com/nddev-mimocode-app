#!/usr/bin/env python3
"""Transactional setup manager for an explicit MiMo Code target."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import Any, NoReturn
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]
CATALOG_ROOT = ROOT / "setups"
BUILDER_ROOT = ROOT / "plugins" / "nddev-builder"
VERSION = (ROOT / "VERSION").read_text(encoding="ascii").strip()
PRODUCT_NAME = "nddev-mimocode-app"
COMMAND_NAME = "mimo"
STAMP_NAME = "NDDEV-MIMOCODE-SETUP.json"
BACKUP_NAME = "NDDEV-MIMOCODE-BACKUP.json"
BASELINE_REF = ROOT / "references" / "mimocode-baseline.json"
TESTED_VERSION = "0.1.9"
INSTALLER_URL = "https://mimo.xiaomi.com/install"
INSTALLER_SIZE = 15819
INSTALLER_SHA256 = "2251667c8b12091a1e65744d892c8abfba008e621b22cf5d39338aa36c12efb2"
INTERNAL_ASSET_URL_ENV = "NDDEV_MIMOCODE_TEST_ASSET_URL"
INTERNAL_ASSET_SHA256_ENV = "NDDEV_MIMOCODE_TEST_ASSET_SHA256"
INTERNAL_ASSET_SIZE_ENV = "NDDEV_MIMOCODE_TEST_ASSET_SIZE"
INTERNAL_INSTALLER_URL_ENV = "NDDEV_MIMOCODE_TEST_INSTALLER_URL"
INTERNAL_INSTALLER_SHA256_ENV = "NDDEV_MIMOCODE_TEST_INSTALLER_SHA256"
INTERNAL_FAIL_AFTER_BINARY_SWAP_ENV = "NDDEV_MIMOCODE_TEST_FAIL_AFTER_BINARY_SWAP"
INTERNAL_INSTALLER_TIMEOUT_ENV = "NDDEV_MIMOCODE_TEST_INSTALLER_TIMEOUT_SECONDS"
INTERNAL_PROBE_TIMEOUT_ENV = "NDDEV_MIMOCODE_TEST_PROBE_TIMEOUT_SECONDS"
SAFE_SYSTEM_PATH = "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin"
OWNER_FILE_MODE = 0o600
OWNER_EXECUTABLE_MODE = 0o700
OWNER_DIRECTORY_MODE = 0o700
METADATA_MAX_BYTES = 256 * 1024
MANAGED_PAYLOAD_MAX_BYTES = 8 * 1024 * 1024
DOWNLOAD_MAX_BYTES = 256 * 1024 * 1024
PROCESS_TIMEOUT_SECONDS = 120
SETUP_ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
MANAGED_CONFIG_KEYS = (
    "$schema",
    "default_agent",
    "share",
    "autoupdate",
    "permission",
    "agent",
    "skills",
    "instructions",
    "mcp",
    "plugin",
    "compaction",
    "snapshot",
    "watcher",
    "disabled_providers",
)
BUILDER_SOURCE_FILES = (
    (
        Path("skills") / "nddev-builder" / "SKILL.md",
        Path("config") / "skills" / "nddev-builder" / "SKILL.md",
    ),
    (
        Path("agents") / "nddev-builder.md",
        Path("config") / "agents" / "nddev-builder.md",
    ),
    (
        Path("instructions") / "nddev-builder.md",
        Path("config") / "instructions" / "nddev-builder.md",
    ),
    (
        Path("workflows") / "nddev-builder.js",
        Path(".mimocode") / "workflows" / "nddev-builder.js",
    ),
)
MANAGED_PATHS = (
    Path("config") / "mimocode.json",
    Path("config") / "AGENTS.md",
    *(target for _, target in BUILDER_SOURCE_FILES),
    Path(STAMP_NAME),
)
STAMP_KEYS = {
    "schema_version",
    "product_name",
    "build_version",
    "setup_id",
    "canonical_target",
    "managed_files",
    "builder_projection",
    "launch_args",
}
BACKUP_KEYS = {
    "schema_version",
    "product_name",
    "build_version",
    "slot",
    "canonical_target",
    "source_setup_id",
    "managed_files",
    "created_at",
}
TOKEN_ENV_NAMES = {
    "MIMOCODE_AUTH_CONTENT",
    "MIMOCODE_CONSOLE_TOKEN",
    "MIMOCODE_SERVER_PASSWORD",
    "MIMOCODE_WORKSPACE_ID",
    "MIMO_API_KEY",
    "MIMO_ACCESS_TOKEN",
    "MIMOCODE_API_KEY",
    "MIMOCODE_ACCESS_TOKEN",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "SSH_ASKPASS",
    "SSH_AUTH_SOCK",
    "GIT_ASKPASS",
}
FORBIDDEN_LAUNCH_FLAGS = {
    "--dangerously-skip-permissions",
    "--never-ask",
    "--trust",
}
FORBIDDEN_LAUNCH_COMMANDS = {
    "upgrade",
}


class MiMoCodeSetupError(Exception):
    """A safe user-facing lifecycle failure."""


class ConcurrentTargetChange(MiMoCodeSetupError):
    """A fail-closed target race."""


def fail(message: str) -> NoReturn:
    raise MiMoCodeSetupError(message)


def fail_concurrent(message: str) -> NoReturn:
    raise ConcurrentTargetChange(message)


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def identity_of(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def owner_of(info: os.stat_result) -> int | None:
    return info.st_uid if hasattr(info, "st_uid") else None


def is_current_user_owned(info: os.stat_result) -> bool:
    return not hasattr(os, "geteuid") or owner_of(info) == os.geteuid()


def is_owner_only_file(info: os.stat_result) -> bool:
    if stat.S_IMODE(info.st_mode) != OWNER_FILE_MODE:
        return False
    if not is_current_user_owned(info):
        return False
    return True


def is_owner_private_directory(info: os.stat_result) -> bool:
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != OWNER_DIRECTORY_MODE:
        return False
    if not is_current_user_owned(info):
        return False
    return True


def require_directory(path: Path, label: str) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError:
        fail(f"{label} is missing")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        fail(f"{label} must be a real directory")
    return info


def require_regular_file(
    path: Path,
    label: str,
    *,
    owner_only: bool = False,
    max_bytes: int = MANAGED_PAYLOAD_MAX_BYTES,
) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError:
        fail(f"{label} is missing")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        fail(f"{label} must be a regular non-symlink file")
    if info.st_nlink != 1:
        fail(f"{label} must not have hard-link aliases")
    if not is_current_user_owned(info):
        fail(f"{label} must be owned by the current user")
    if owner_only and not is_owner_only_file(info):
        fail(f"{label} must be owned by the current user with mode 0600")
    if info.st_size > max_bytes:
        fail(f"{label} exceeds the {max_bytes}-byte size limit")
    return info


def read_regular_file(
    path: Path,
    label: str,
    *,
    owner_only: bool = False,
    max_bytes: int = MANAGED_PAYLOAD_MAX_BYTES,
) -> tuple[bytes, os.stat_result]:
    before = require_regular_file(path, label, owner_only=owner_only)
    if before.st_size > max_bytes:
        fail(f"{label} exceeds the {max_bytes}-byte size limit")
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if identity_of(opened) != identity_of(before):
            fail_concurrent(f"{label} changed while it was being opened")
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            fail(f"{label} changed to an unsafe file")
        if not is_current_user_owned(opened):
            fail(f"{label} must be owned by the current user")
        if owner_only and not is_owner_only_file(opened):
            fail(f"{label} must be owned by the current user with mode 0600")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                fail(f"{label} exceeds the {max_bytes}-byte size limit")
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    final = require_regular_file(path, label, owner_only=owner_only)
    expected = identity_of(before)
    if identity_of(after) != expected or identity_of(final) != expected:
        fail_concurrent(f"{label} changed while it was being read")
    return b"".join(chunks), final


def parse_json_object(content: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"cannot read valid JSON from {label}: {exc}")
    if not isinstance(value, dict):
        fail(f"{label} must contain a JSON object")
    return value


def load_json_object(path: Path, label: str, *, owner_only: bool = False) -> dict[str, Any]:
    content, _ = read_regular_file(path, label, owner_only=owner_only, max_bytes=METADATA_MAX_BYTES)
    return parse_json_object(content, label)


def missing_directory_chain(path: Path) -> list[Path]:
    chain: list[Path] = []
    current = path
    while current != current.parent and not current.exists() and not current.is_symlink():
        chain.append(current)
        current = current.parent
    return chain


def require_private_directory(path: Path, label: str) -> os.stat_result:
    info = require_directory(path, label)
    if not is_owner_private_directory(info):
        fail(f"{label} must be owned by the current user with mode 0700")
    return info


def create_missing_directories(chain: list[Path]) -> None:
    for path in reversed(chain):
        try:
            path.mkdir(mode=OWNER_DIRECTORY_MODE)
        except FileExistsError:
            fail(f"directory appeared while creating MiMo Code target path: {path}")
        path.chmod(OWNER_DIRECTORY_MODE)
        require_private_directory(path, f"created directory {path}")


def remove_created_empty_directories(chain: list[Path]) -> None:
    for path in chain:
        with contextlib.suppress(FileNotFoundError, OSError):
            path.rmdir()


def require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        fail(
            f"{label} has invalid keys "
            f"(missing={sorted(expected - actual)}, extra={sorted(actual - expected)})"
        )


def validate_setup_id(setup_id: str) -> None:
    if not SETUP_ID_PATTERN.fullmatch(setup_id):
        fail(f"invalid setup id: {setup_id!r}")


def managed_config_view(config: dict[str, Any]) -> dict[str, Any]:
    return {key: config[key] for key in MANAGED_CONFIG_KEYS if key in config}


def merge_config(existing: dict[str, Any] | None, setup_config: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if existing is not None:
        for key, value in existing.items():
            if key not in MANAGED_CONFIG_KEYS:
                result[key] = value
    result.update(managed_config_view(setup_config))
    return result


def managed_digest(relative: Path, content: bytes) -> str:
    if relative == Path("config") / "mimocode.json":
        config = parse_json_object(content, str(relative))
        return sha256_bytes(canonical_json(managed_config_view(config)))
    return sha256_bytes(content)


def validate_permission_leaf(value: Any, label: str) -> None:
    if isinstance(value, str):
        if value not in {"allow", "ask", "deny"}:
            fail(f"{label} must be allow, ask, or deny")
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str):
                fail(f"{label} permission keys must be strings")
            validate_permission_leaf(nested, f"{label}.{key}")
        return
    fail(f"{label} has invalid permission value")


def validate_config(config: dict[str, Any], label: str) -> None:
    if config.get("$schema") != "https://mimo.xiaomi.com/mimocode/config.json":
        fail(f"{label} has invalid schema")
    if config.get("autoupdate") is not False:
        fail(f"{label} must disable automatic updates")
    if config.get("share") != "disabled":
        fail(f"{label} must disable session sharing")
    if "tools" in config:
        fail(f"{label} must not use deprecated tools config")
    permission = config.get("permission")
    if not isinstance(permission, dict):
        fail(f"{label} must define permission rules")
    validate_permission_leaf(permission, f"{label}.permission")
    skill_permission = permission.get("skill")
    if not isinstance(skill_permission, dict) or skill_permission.get("nddev-builder") != "allow":
        fail(f"{label} must allow the nddev-builder skill")
    if config.get("skills") != {"paths": ["./skills"]}:
        fail(f"{label} must load native skills from ./skills")
    instructions = config.get("instructions")
    if instructions != ["./AGENTS.md", "./instructions/nddev-builder.md"]:
        fail(f"{label} must include the managed builder instructions")
    if config.get("mcp") != {}:
        fail(f"{label} must not configure live MCP servers")
    if config.get("plugin") != []:
        fail(f"{label} must not configure unsupported marketplace/plugins")
    agents = config.get("agent")
    if not isinstance(agents, dict) or "nddev-builder" not in agents:
        fail(f"{label} must define the native nddev-builder agent")
    builder = agents["nddev-builder"]
    if not isinstance(builder, dict) or builder.get("mode") != "subagent":
        fail(f"{label} nddev-builder agent must be a subagent")
    if builder.get("prompt") != "{file:./instructions/nddev-builder.md}":
        fail(f"{label} nddev-builder agent prompt must use managed instructions")


def validate_setup_metadata(metadata: dict[str, Any], setup_id: str) -> None:
    require_exact_keys(
        metadata,
        {
            "schema_version",
            "id",
            "description",
            "managed_files",
            "builder_projection",
            "builder_default_on",
            "launch_args",
        },
        f"setup {setup_id} metadata",
    )
    if metadata["schema_version"] != 1:
        fail(f"setup {setup_id} metadata has unsupported schema")
    if metadata["id"] != setup_id:
        fail(f"setup {setup_id} metadata identity mismatch")
    if metadata["managed_files"] != ["config/mimocode.json", "config/AGENTS.md"]:
        fail(f"setup {setup_id} managed file declaration is invalid")
    if (
        metadata["builder_projection"] != "native-config-skills-agents-instructions-workflows"
        or metadata["builder_default_on"] is not True
    ):
        fail(f"setup {setup_id} must enable native builder projection")
    if not isinstance(metadata["launch_args"], list) or not all(
        isinstance(item, str) for item in metadata["launch_args"]
    ):
        fail(f"setup {setup_id} launch_args must be a string array")


def render_builder_files() -> dict[Path, bytes]:
    files: dict[Path, bytes] = {}
    for source_relative, target_relative in BUILDER_SOURCE_FILES:
        content, _ = read_regular_file(
            BUILDER_ROOT / source_relative, f"builder source {source_relative}"
        )
        files[target_relative] = content
    return files


def build_stamp(
    setup_id: str, desired: dict[Path, bytes], launch_args: list[str]
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "product_name": PRODUCT_NAME,
        "build_version": VERSION,
        "setup_id": setup_id,
        "canonical_target": "",
        "managed_files": {
            str(relative): managed_digest(relative, content)
            for relative, content in desired.items()
            if relative != Path(STAMP_NAME)
        },
        "builder_projection": "mimocode-native-config-skills-agents-instructions-workflows",
        "launch_args": launch_args,
    }


def bind_stamp(stamp: dict[str, Any], canonical_target: Path) -> dict[str, Any]:
    bound = dict(stamp)
    bound["canonical_target"] = str(canonical_target)
    return bound


def render_setup(
    setup_id: str, *, existing_config: dict[str, Any] | None = None
) -> tuple[dict[str, Any], dict[Path, bytes]]:
    validate_setup_id(setup_id)
    setup_root = CATALOG_ROOT / setup_id
    if not setup_root.is_dir() or setup_root.is_symlink():
        fail(f"unknown setup: {setup_id}")
    metadata = load_json_object(setup_root / "setup.json", f"setup {setup_id} metadata")
    validate_setup_metadata(metadata, setup_id)
    config = load_json_object(setup_root / "mimocode.json", f"setup {setup_id}/mimocode.json")
    validate_config(config, f"setup {setup_id}/mimocode.json")
    agents_md, _ = read_regular_file(setup_root / "AGENTS.md", f"setup {setup_id}/AGENTS.md")
    desired: dict[Path, bytes] = {
        Path("config") / "mimocode.json": canonical_json(merge_config(existing_config, config)),
        Path("config") / "AGENTS.md": agents_md,
    }
    desired.update(render_builder_files())
    desired[Path(STAMP_NAME)] = canonical_json(
        build_stamp(setup_id, desired, metadata["launch_args"])
    )
    return metadata, desired


def list_setups() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path in sorted(CATALOG_ROOT.iterdir()):
        if not path.is_dir() or path.is_symlink():
            continue
        metadata = load_json_object(path / "setup.json", f"setup {path.name} metadata")
        validate_setup_metadata(metadata, path.name)
        result.append(
            {
                "id": metadata["id"],
                "description": metadata["description"],
                "builder_default_on": metadata["builder_default_on"],
                "launch_args": metadata["launch_args"],
            }
        )
    return result


def backup_pool(target: Path) -> Path:
    return target.parent / f".{target.name}.nddev-mimocode-backups"


def lock_path(target: Path) -> Path:
    return target.parent / f".{target.name}.nddev-mimocode.lock"


@contextlib.contextmanager
def target_lock(target: Path) -> Iterator[None]:
    created_parent_chain = missing_directory_chain(target.parent)
    create_missing_directories(created_parent_chain)
    require_private_directory(target.parent, "target parent")
    path = lock_path(target)
    try:
        os.mkdir(path, OWNER_DIRECTORY_MODE)
    except FileExistsError:
        fail(f"target is locked: {path}")
    try:
        yield
    finally:
        with contextlib.suppress(FileNotFoundError):
            path.rmdir()
        remove_created_empty_directories(created_parent_chain)


def require_explicit_absolute_target(raw_target: str | None) -> Path:
    if not raw_target:
        fail("an explicit --target absolute path is required")
    target = Path(raw_target).expanduser()
    if not target.is_absolute():
        fail("--target must be an absolute path")
    try:
        info = target.lstat()
    except FileNotFoundError:
        return target
    if stat.S_ISLNK(info.st_mode):
        fail("--target must not be a symlink")
    if not stat.S_ISDIR(info.st_mode):
        fail("--target must be a directory")
    return target.resolve()


def ensure_target_directory(target: Path) -> Path:
    if target.exists():
        require_private_directory(target, "target")
        return target.resolve()
    require_private_directory(target.parent, "target parent")
    target.mkdir(mode=OWNER_DIRECTORY_MODE)
    target.chmod(OWNER_DIRECTORY_MODE)
    require_private_directory(target, "target")
    return target.resolve()


def ensure_private_parent(target: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        fail(f"unsafe managed path: {relative}")
    current = target
    for part in relative.parent.parts:
        current = current / part
        if current.exists() or current.is_symlink():
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                fail(f"managed parent {current.relative_to(target)} must be a real directory")
            if not is_owner_private_directory(info):
                fail(
                    f"managed parent {current.relative_to(target)} must be owned by the current user with mode 0700"
                )
        else:
            current.mkdir(mode=OWNER_DIRECTORY_MODE)
            current.chmod(OWNER_DIRECTORY_MODE)
            require_private_directory(current, f"managed parent {current.relative_to(target)}")
    return target / relative


def any_managed_path_exists(target: Path) -> bool:
    return any(
        (target / relative).exists() or (target / relative).is_symlink()
        for relative in MANAGED_PATHS
    )


def load_stamp(target: Path) -> dict[str, Any] | None:
    stamp = target / STAMP_NAME
    if not stamp.exists() and not stamp.is_symlink():
        return None
    value = load_json_object(stamp, "setup stamp", owner_only=True)
    require_exact_keys(value, STAMP_KEYS, "setup stamp")
    if (
        value["schema_version"] != 1
        or value["product_name"] != PRODUCT_NAME
        or value["build_version"] != VERSION
    ):
        fail("setup stamp is not compatible with this build")
    if value["canonical_target"] != str(target):
        fail("setup stamp is bound to a different canonical target")
    if not isinstance(value["managed_files"], dict):
        fail("setup stamp managed_files must be an object")
    validate_setup_id(value["setup_id"])
    return value


def validate_managed_files(target: Path, stamp: dict[str, Any]) -> list[str]:
    expected = stamp["managed_files"]
    ordered = [relative for relative in MANAGED_PATHS if str(relative) in expected]
    ordered.extend(Path(raw) for raw in sorted(set(expected) - {str(item) for item in ordered}))
    drift: list[str] = []
    for relative in ordered:
        if relative.is_absolute() or ".." in relative.parts:
            fail("setup stamp contains an unsafe managed path")
        content, _ = read_regular_file(
            target / relative, f"managed file {relative}", owner_only=True
        )
        if managed_digest(relative, content) != expected[str(relative)]:
            drift.append(str(relative))
    if drift:
        fail(f"managed target drift detected: {', '.join(sorted(drift))}")
    return sorted(expected)


def inspect_target(target: Path) -> dict[str, Any]:
    if not target.exists():
        return {"state": "missing", "target": str(target)}
    require_directory(target, "target")
    stamp = load_stamp(target)
    if stamp is None:
        if any_managed_path_exists(target):
            fail("unmanaged target contains nddev-managed paths")
        return {"state": "unmanaged", "target": str(target)}
    return {
        "ok": True,
        "state": "managed",
        "target": str(target),
        "setup_id": stamp["setup_id"],
        "build_version": stamp["build_version"],
        "managed_files": validate_managed_files(target, stamp),
        "builder_projection": stamp["builder_projection"],
        "launch_args": stamp["launch_args"],
    }


def read_existing_config_if_managed(target: Path, state: dict[str, Any]) -> dict[str, Any] | None:
    if state.get("state") != "managed":
        return None
    return load_json_object(
        target / "config" / "mimocode.json",
        "existing config/mimocode.json",
        owner_only=True,
    )


def current_managed_snapshot(target: Path) -> dict[Path, bytes | None]:
    snapshot: dict[Path, bytes | None] = {}
    for relative in MANAGED_PATHS:
        path = target / relative
        if path.exists() or path.is_symlink():
            content, _ = read_regular_file(path, f"managed file {relative}", owner_only=True)
            snapshot[relative] = content
        else:
            snapshot[relative] = None
    return snapshot


def prune_empty_managed_dirs(target: Path) -> None:
    candidates = sorted(
        {(target / relative).parent for relative in MANAGED_PATHS},
        key=lambda item: len(item.parts),
        reverse=True,
    )
    for directory in candidates:
        while directory != target and directory.is_dir() and not directory.is_symlink():
            try:
                directory.rmdir()
            except OSError:
                break
            directory = directory.parent


def restore_snapshot(target: Path, snapshot: dict[Path, bytes | None]) -> None:
    for relative in sorted(MANAGED_PATHS, key=lambda item: len(item.parts), reverse=True):
        path = target / relative
        if path.exists() or path.is_symlink():
            path.unlink()
    for relative, content in snapshot.items():
        if content is None:
            continue
        path = ensure_private_parent(target, relative)
        path.write_bytes(content)
        path.chmod(OWNER_FILE_MODE)
    prune_empty_managed_dirs(target)


def replace_managed_state(
    target: Path, desired: dict[Path, bytes | None], expected: dict[str, Any]
) -> None:
    del expected
    for relative, content in desired.items():
        path = ensure_private_parent(target, relative)
        if content is None:
            if path.exists() or path.is_symlink():
                require_regular_file(path, f"managed file {relative}", owner_only=True)
                path.unlink()
            continue
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        temporary.chmod(OWNER_FILE_MODE)
        os.replace(temporary, path)
        path.chmod(OWNER_FILE_MODE)
    prune_empty_managed_dirs(target)


def changed_paths(target: Path, desired: dict[Path, bytes | None]) -> list[str]:
    changed: list[str] = []
    for relative, content in desired.items():
        path = target / relative
        if content is None:
            if path.exists() or path.is_symlink():
                changed.append(str(relative))
            continue
        if not path.exists() or path.is_symlink():
            changed.append(str(relative))
            continue
        actual, _ = read_regular_file(path, f"managed file {relative}", owner_only=True)
        if actual != content:
            changed.append(str(relative))
    return sorted(changed)


def refresh_backup_slot_numbers(pool: Path) -> None:
    for slot in range(10):
        envelope_path = pool / str(slot) / BACKUP_NAME
        if not envelope_path.exists():
            continue
        envelope = load_json_object(envelope_path, f"backup slot {slot} envelope", owner_only=True)
        envelope["slot"] = slot
        envelope_path.write_bytes(canonical_json(envelope))
        envelope_path.chmod(OWNER_FILE_MODE)


def create_backup(target: Path, state: dict[str, Any]) -> int:
    pool = backup_pool(target)
    pool.mkdir(mode=OWNER_DIRECTORY_MODE, parents=True, exist_ok=True)
    for slot in range(9, -1, -1):
        current = pool / str(slot)
        if not current.exists():
            continue
        if slot == 9:
            shutil.rmtree(current)
        else:
            os.replace(current, pool / str(slot + 1))
    slot_dir = pool / "0"
    slot_dir.mkdir(mode=OWNER_DIRECTORY_MODE)
    managed_files = list(state["managed_files"])
    for raw_relative in [*managed_files, STAMP_NAME]:
        relative = Path(raw_relative)
        content, _ = read_regular_file(
            target / relative, f"managed file {relative}", owner_only=True
        )
        destination = slot_dir / relative
        destination.parent.mkdir(mode=OWNER_DIRECTORY_MODE, parents=True, exist_ok=True)
        destination.write_bytes(content)
        destination.chmod(OWNER_FILE_MODE)
    envelope = {
        "schema_version": 1,
        "product_name": PRODUCT_NAME,
        "build_version": VERSION,
        "slot": 0,
        "canonical_target": str(target),
        "source_setup_id": state["setup_id"],
        "managed_files": managed_files,
        "created_at": int(time.time()),
    }
    (slot_dir / BACKUP_NAME).write_bytes(canonical_json(envelope))
    (slot_dir / BACKUP_NAME).chmod(OWNER_FILE_MODE)
    refresh_backup_slot_numbers(pool)
    return 0


def load_backup(target: Path, slot: int) -> tuple[dict[str, Any], dict[Path, bytes]]:
    if slot < 0 or slot > 9:
        fail("--backup must be between 0 and 9")
    slot_dir = backup_pool(target) / str(slot)
    require_directory(slot_dir, f"backup slot {slot}")
    envelope = load_json_object(slot_dir / BACKUP_NAME, "backup envelope", owner_only=True)
    require_exact_keys(envelope, BACKUP_KEYS, "backup envelope")
    if (
        envelope["schema_version"] != 1
        or envelope["product_name"] != PRODUCT_NAME
        or envelope["build_version"] != VERSION
    ):
        fail("backup envelope is not compatible with this build")
    if envelope["canonical_target"] != str(target):
        fail("backup belongs to a different canonical target")
    files: dict[Path, bytes] = {}
    for raw_relative in [*envelope["managed_files"], STAMP_NAME]:
        relative = Path(raw_relative)
        content, _ = read_regular_file(
            slot_dir / relative, f"backup file {relative}", owner_only=True
        )
        files[relative] = content
    return envelope, files


def mutate_setup(target: Path, setup_id: str, operation: str) -> dict[str, Any]:
    canonical_target = ensure_target_directory(target)
    with target_lock(canonical_target):
        state = inspect_target(canonical_target)
        existing_config = read_existing_config_if_managed(canonical_target, state)
        metadata, desired = render_setup(setup_id, existing_config=existing_config)
        stamp = bind_stamp(
            parse_json_object(desired[Path(STAMP_NAME)], "desired stamp"), canonical_target
        )
        desired[Path(STAMP_NAME)] = canonical_json(stamp)
        changed = changed_paths(canonical_target, desired)
        backup_slot: int | None = None
        snapshot = current_managed_snapshot(canonical_target)
        try:
            if state["state"] == "managed" and changed:
                backup_slot = create_backup(canonical_target, state)
            if changed:
                replace_managed_state(canonical_target, desired, stamp)
            post = inspect_target(canonical_target)
        except BaseException:
            restore_snapshot(canonical_target, snapshot)
            raise
    return {
        "ok": True,
        "operation": operation,
        "setup_id": setup_id,
        "description": metadata["description"],
        "target": str(canonical_target),
        "changed": changed,
        "backup_slot": backup_slot,
        "state": post["state"],
    }


def plan_setup(target: Path, setup_id: str) -> dict[str, Any]:
    canonical_target = target.resolve() if target.exists() else target
    state = inspect_target(canonical_target)
    existing_config = read_existing_config_if_managed(canonical_target, state)
    _metadata, desired = render_setup(setup_id, existing_config=existing_config)
    if state["state"] == "managed":
        stamp = bind_stamp(
            parse_json_object(desired[Path(STAMP_NAME)], "desired stamp"), canonical_target
        )
        desired[Path(STAMP_NAME)] = canonical_json(stamp)
        changed = changed_paths(canonical_target, desired)
        operation = "switch" if state.get("setup_id") != setup_id else "install"
        backup_required = bool(changed)
    else:
        changed = sorted(str(path) for path in desired)
        operation = "install"
        backup_required = False
    return {
        "ok": True,
        "operation": operation,
        "setup_id": setup_id,
        "target": str(canonical_target),
        "state": state["state"],
        "mutates": False,
        "backup_required": backup_required,
        "changed": changed,
    }


def remove_setup(target: Path) -> dict[str, Any]:
    canonical_target = require_explicit_absolute_target(str(target))
    with target_lock(canonical_target):
        state = inspect_target(canonical_target)
        if state["state"] != "managed":
            fail("target is not managed by nddev-mimocode-app")
        snapshot = current_managed_snapshot(canonical_target)
        desired = {relative: None for relative in MANAGED_PATHS}
        try:
            backup_slot = create_backup(canonical_target, state)
            replace_managed_state(canonical_target, desired, {})
        except BaseException:
            restore_snapshot(canonical_target, snapshot)
            raise
    return {
        "ok": True,
        "operation": "remove",
        "target": str(canonical_target),
        "removed_setup_id": state["setup_id"],
        "backup_slot": backup_slot,
    }


def restore_backup(target: Path, slot: int) -> dict[str, Any]:
    canonical_target = require_explicit_absolute_target(str(target))
    with target_lock(canonical_target):
        state = inspect_target(canonical_target)
        if state["state"] != "managed":
            fail("target is not managed by nddev-mimocode-app")
        envelope, desired = load_backup(canonical_target, slot)
        snapshot = current_managed_snapshot(canonical_target)
        try:
            replace_managed_state(canonical_target, desired, {})
            post = inspect_target(canonical_target)
        except BaseException:
            restore_snapshot(canonical_target, snapshot)
            raise
    return {
        "ok": True,
        "operation": "restore",
        "target": str(canonical_target),
        "setup_id": post["setup_id"],
        "restored_from_slot": slot,
        "restored_source_setup_id": envelope["source_setup_id"],
    }


def load_baseline() -> dict[str, Any]:
    return load_json_object(BASELINE_REF, "MiMo Code baseline")


def detect_platform_asset() -> tuple[str, dict[str, Any]]:
    baseline = load_baseline()
    assets = baseline.get("release", {}).get("assets")
    if not isinstance(assets, dict):
        fail("baseline release assets missing")
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        arch = "x64"
    elif machine in {"arm64", "aarch64"}:
        arch = "arm64"
    else:
        fail(f"unsupported architecture for MiMo Code install: {platform.machine()}")
    if sys.platform == "darwin":
        key = f"darwin-{arch}"
    elif sys.platform.startswith("linux"):
        key = f"linux-{arch}"
    elif sys.platform.startswith("win"):
        key = f"windows-{arch}"
    else:
        fail(f"unsupported platform for MiMo Code install: {sys.platform}")
    asset = assets.get(key)
    if not isinstance(asset, dict):
        fail(f"baseline does not declare asset {key}")
    return key, asset


def software_manifest_path(target: Path) -> Path:
    return target / "software" / "mimocode.json"


def software_tree_binary(target: Path) -> Path:
    suffix = ".exe" if sys.platform.startswith("win") else ""
    return target / "software" / "versions" / TESTED_VERSION / f"{COMMAND_NAME}{suffix}"


def mimo_executable(target: Path) -> Path:
    suffix = ".exe" if sys.platform.startswith("win") else ""
    return target / "bin" / f"{COMMAND_NAME}{suffix}"


def software_presence(target: Path) -> list[str]:
    labels = (
        (mimo_executable(target), f"bin/{mimo_executable(target).name}"),
        (software_manifest_path(target), "software/mimocode.json"),
        (
            software_tree_binary(target),
            f"software/versions/{TESTED_VERSION}/{software_tree_binary(target).name}",
        ),
    )
    return sorted(label for path, label in labels if path.exists() or path.is_symlink())


def software_status(target: Path) -> dict[str, Any]:
    if not target.exists():
        return {
            "ok": True,
            "installed": False,
            "current": False,
            "present": False,
            "presence": [],
            "target": str(target),
            "version": None,
            "executable": None,
            "drift": [],
        }
    canonical_target = require_explicit_absolute_target(str(target))
    require_private_directory(canonical_target, "target")
    executable = mimo_executable(canonical_target)
    tree_binary = software_tree_binary(canonical_target)
    manifest = software_manifest_path(canonical_target)
    presence = software_presence(canonical_target)
    base = {
        "ok": True,
        "installed": False,
        "current": False,
        "present": bool(presence),
        "presence": presence,
        "target": str(canonical_target),
        "version": None,
        "executable": str(executable),
        "drift": [],
    }
    if not executable.exists() or not manifest.exists() or not tree_binary.exists():
        if presence:
            base["drift"] = ["software-incomplete"]
        return base
    binary_bytes, binary_info = read_regular_file(
        executable, "MiMo Code executable", max_bytes=DOWNLOAD_MAX_BYTES
    )
    tree_bytes, tree_info = read_regular_file(
        tree_binary, "MiMo Code version tree executable", max_bytes=DOWNLOAD_MAX_BYTES
    )
    if (
        stat.S_IMODE(binary_info.st_mode) != OWNER_EXECUTABLE_MODE
        or stat.S_IMODE(tree_info.st_mode) != OWNER_EXECUTABLE_MODE
    ):
        base["drift"] = ["software-executable-mode"]
        return base
    info = load_json_object(manifest, "software manifest", owner_only=True)
    binary_sha = sha256_bytes(binary_bytes)
    tree_sha = sha256_bytes(tree_bytes)
    drift: list[str] = []
    if info.get("schema_version") != 2:
        drift.append("schema_version")
    if info.get("version") != TESTED_VERSION:
        drift.append("version")
    if info.get("command") != COMMAND_NAME:
        drift.append("command")
    if info.get("executable") != f"bin/{executable.name}":
        drift.append("executable")
    if (
        info.get("version_tree_executable")
        != f"software/versions/{TESTED_VERSION}/{tree_binary.name}"
    ):
        drift.append("version_tree_executable")
    if info.get("installer_url") != INSTALLER_URL:
        drift.append("installer_url")
    if info.get("installer_size") != INSTALLER_SIZE:
        drift.append("installer_size")
    if info.get("installer_sha256") != INSTALLER_SHA256:
        drift.append("installer_sha256")
    asset_key, asset = detect_platform_asset()
    expected_url = asset.get("url")
    expected_sha = asset.get("sha256")
    expected_size = asset.get("size")
    if info.get("asset") != asset_key:
        drift.append("asset")
    if info.get("asset_url") != expected_url:
        drift.append("asset_url")
    if info.get("asset_sha256") != expected_sha:
        drift.append("asset_sha256")
    if info.get("asset_size") != expected_size:
        drift.append("asset_size")
    if info.get("binary_sha256") != binary_sha or tree_sha != binary_sha:
        drift.append("binary_sha256")
    return {
        **base,
        "installed": True,
        "current": not drift,
        "version": info.get("version"),
        "drift": drift,
        "binary_sha256": binary_sha,
    }


def read_url_or_file(url: str, *, max_bytes: int, expected_size: int | None = None) -> bytes:
    if url.startswith("file://"):
        data, _ = read_regular_file(Path(url[7:]), f"test artifact {url}", max_bytes=max_bytes)
        if expected_size is not None and len(data) != expected_size:
            fail(f"test artifact size mismatch for {url}")
        return data
    request = urllib.request.Request(url, headers={"User-Agent": PRODUCT_NAME})
    try:
        response_context = urllib.request.urlopen(request, timeout=PROCESS_TIMEOUT_SECONDS)
    except TimeoutError:
        fail(f"MiMo Code download timed out for {url}")
    except URLError as exc:
        fail(f"MiMo Code download failed for {url}: {exc.reason}")
    with response_context as response:
        content_length = response.headers.get("Content-Length")
        if content_length is not None:
            length = int(content_length)
            if expected_size is not None and length != expected_size:
                fail(f"MiMo Code download Content-Length mismatch for {url}")
            if length > max_bytes:
                fail("MiMo Code download exceeds bounded size before reading")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                fail("MiMo Code download exceeded the 256 MiB bound")
            chunks.append(chunk)
    data = b"".join(chunks)
    if expected_size is not None and len(data) != expected_size:
        fail(f"MiMo Code downloaded size mismatch for {url}")
    return data


def download_bytes(url: str) -> bytes:
    return read_url_or_file(url, max_bytes=DOWNLOAD_MAX_BYTES)


def safe_tar_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    del archive
    fail("legacy MiMo Code tar extraction helper is not available")


def validate_archive_member_path(name: str) -> None:
    normalized = name.replace("\\", "/")
    if "\x00" in normalized or normalized.startswith("//"):
        fail(f"unsafe archive member path: {name}")
    if re.fullmatch(r"[A-Za-z]:.*", normalized):
        fail(f"unsafe archive member path: {name}")
    path = Path(normalized)
    if path.is_absolute() or ".." in path.parts:
        fail(f"unsafe archive member path: {name}")


def extract_verified_binary(archive_bytes: bytes, asset_name: str) -> bytes:
    candidates: list[tuple[str, bytes]] = []
    expected_names = {COMMAND_NAME, f"{COMMAND_NAME}.exe"}
    if asset_name.endswith(".zip"):
        with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
            for member in archive.infolist():
                validate_archive_member_path(member.filename)
                mode = member.external_attr >> 16
                name = Path(member.filename).name
                if name not in expected_names:
                    continue
                if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or mode == 0):
                    fail(f"unsafe archive member type: {member.filename}")
                if member.file_size > DOWNLOAD_MAX_BYTES:
                    fail("MiMo Code archive binary exceeds bounded size")
                candidates.append((member.filename, archive.read(member)))
    else:
        with tarfile.open(fileobj=BytesIO(archive_bytes), mode="r:*") as archive:
            for member in archive.getmembers():
                validate_archive_member_path(member.name)
                name = Path(member.name).name
                if name not in expected_names:
                    continue
                if member.issym() or member.islnk() or member.isdev() or not member.isfile():
                    fail(f"unsafe archive member type: {member.name}")
                if member.size > DOWNLOAD_MAX_BYTES:
                    fail("MiMo Code archive binary exceeds bounded size")
                extracted = archive.extractfile(member)
                if extracted is None:
                    fail(f"cannot read archive member: {member.name}")
                candidates.append((member.name, extracted.read(DOWNLOAD_MAX_BYTES + 1)))
    if len(candidates) != 1:
        fail(f"archive must contain exactly one MiMo Code executable, found {len(candidates)}")
    name, data = candidates[0]
    if len(data) > DOWNLOAD_MAX_BYTES:
        fail(f"MiMo Code archive member too large: {name}")
    return data


def selected_asset() -> tuple[str, dict[str, Any]]:
    asset_key, asset = detect_platform_asset()
    override_url = os.environ.get(INTERNAL_ASSET_URL_ENV)
    if override_url:
        asset = dict(asset)
        asset["url"] = override_url
        if os.environ.get(INTERNAL_ASSET_SHA256_ENV):
            asset["sha256"] = os.environ[INTERNAL_ASSET_SHA256_ENV]
        if os.environ.get(INTERNAL_ASSET_SIZE_ENV):
            asset["size"] = int(os.environ[INTERNAL_ASSET_SIZE_ENV])
        asset["name"] = Path(override_url).name
        asset_key = "internal-test-asset"
    return asset_key, asset


def read_pinned_installer() -> tuple[bytes, str, str, int]:
    source = os.environ.get(INTERNAL_INSTALLER_URL_ENV) or INSTALLER_URL
    expected_size = None if source != INSTALLER_URL else INSTALLER_SIZE
    installer = read_url_or_file(source, max_bytes=2 * 1024 * 1024, expected_size=expected_size)
    digest = sha256_bytes(installer)
    expected = os.environ.get(INTERNAL_INSTALLER_SHA256_ENV) or INSTALLER_SHA256
    if digest != expected:
        fail("MiMo Code installer SHA-256 mismatch")
    return installer, digest, source, len(installer)


def internal_timeout_seconds(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        timeout = float(value)
    except ValueError:
        fail(f"{name} must be a positive timeout in seconds")
    if timeout <= 0:
        fail(f"{name} must be a positive timeout in seconds")
    return timeout


def minimal_process_env(bin_dir: Path | None = None, *, tmp_dir: Path) -> dict[str, str]:
    path = SAFE_SYSTEM_PATH
    if bin_dir is not None:
        path = f"{bin_dir}:{path}"
    env = {
        "PATH": path,
        "PYTHONDONTWRITEBYTECODE": "1",
        "HOME": "/nonexistent",
        "SHELL": "",
        "TMPDIR": str(tmp_dir),
    }
    for name in ("LANG", "LC_ALL", "LC_CTYPE", "SYSTEMROOT"):
        value = os.environ.get(name)
        if value:
            env[name] = value
    return env


def run_official_installer(
    installer: bytes, installer_source: str, installer_sha256: str, verified_binary: bytes
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=".nddev-mimocode-installer-") as stage_raw:
        stage = Path(stage_raw)
        home = stage / "home"
        tmp_dir = stage / "tmp"
        fds_base = stage / "fds"
        for directory in (
            home,
            tmp_dir,
            fds_base,
            stage / "xdg-config",
            stage / "xdg-data",
            stage / "xdg-state",
            stage / "xdg-cache",
        ):
            directory.mkdir(mode=OWNER_DIRECTORY_MODE)
            directory.chmod(OWNER_DIRECTORY_MODE)
        installer_path = stage / "install.sh"
        binary_path = stage / "verified" / COMMAND_NAME
        binary_path.parent.mkdir(mode=OWNER_DIRECTORY_MODE)
        binary_path.parent.chmod(OWNER_DIRECTORY_MODE)
        installer_path.write_bytes(installer)
        installer_path.chmod(OWNER_EXECUTABLE_MODE)
        binary_path.write_bytes(verified_binary)
        binary_path.chmod(OWNER_EXECUTABLE_MODE)
        env = minimal_process_env(tmp_dir=tmp_dir)
        env.update(
            {
                "HOME": str(home),
                "USERPROFILE": str(home),
                "XDG_CONFIG_HOME": str(stage / "xdg-config"),
                "XDG_DATA_HOME": str(stage / "xdg-data"),
                "XDG_STATE_HOME": str(stage / "xdg-state"),
                "XDG_CACHE_HOME": str(stage / "xdg-cache"),
                "MIMO_FDS_BASE": str(fds_base),
                "MIMOCODE_HOME": str(stage / "mimocode-home"),
                "MIMOCODE_MIMO_ONLY": "1",
                "SHELL": "",
            }
        )
        try:
            completed = subprocess.run(
                [
                    "bash",
                    str(installer_path),
                    "--version",
                    TESTED_VERSION,
                    "--no-modify-path",
                    "--binary",
                    str(binary_path),
                ],
                cwd=stage,
                env=env,
                text=True,
                capture_output=True,
                check=False,
                timeout=internal_timeout_seconds(
                    INTERNAL_INSTALLER_TIMEOUT_ENV, PROCESS_TIMEOUT_SECONDS
                ),
            )
        except FileNotFoundError as exc:
            fail(f"MiMo Code installer runner is missing: {exc.filename or 'bash'}")
        except subprocess.TimeoutExpired:
            fail("MiMo Code official installer timed out")
        if completed.returncode != 0:
            fail(
                "MiMo Code official installer failed: "
                + (completed.stderr or completed.stdout).strip()
            )
        installed = home / ".mimocode" / "bin" / COMMAND_NAME
        binary, info = read_regular_file(
            installed, "MiMo Code staged installer binary", max_bytes=DOWNLOAD_MAX_BYTES
        )
        if stat.S_IMODE(info.st_mode) != OWNER_EXECUTABLE_MODE:
            fail("MiMo Code staged installer binary must have mode 0700")
        probe_env = minimal_process_env(installed.parent, tmp_dir=tmp_dir)
        probe_env["HOME"] = str(stage / "probe-home")
        Path(probe_env["HOME"]).mkdir(mode=OWNER_DIRECTORY_MODE)
        Path(probe_env["HOME"]).chmod(OWNER_DIRECTORY_MODE)
        try:
            probe = subprocess.run(
                [str(installed), "--version"],
                cwd=stage,
                env=probe_env,
                text=True,
                input="",
                capture_output=True,
                check=False,
                timeout=internal_timeout_seconds(INTERNAL_PROBE_TIMEOUT_ENV, 15.0),
            )
        except FileNotFoundError as exc:
            fail(
                f"MiMo Code staged version probe executable is missing: {exc.filename or installed}"
            )
        except subprocess.TimeoutExpired:
            fail("MiMo Code staged version probe timed out")
        version_output = (probe.stdout + probe.stderr).strip()
        if probe.returncode != 0 or TESTED_VERSION not in version_output:
            fail("MiMo Code staged binary did not report the pinned version")
        return {
            "binary": binary,
            "binary_sha256": sha256_bytes(binary),
            "installer_source": installer_source,
            "installer_sha256": installer_sha256,
            "version_output": version_output,
        }


def snapshot_optional_file(path: Path, label: str) -> tuple[bytes | None, int | None]:
    if not path.exists() and not path.is_symlink():
        return None, None
    content, info = read_regular_file(path, label, max_bytes=DOWNLOAD_MAX_BYTES)
    return content, stat.S_IMODE(info.st_mode)


def write_private_file(path: Path, content: bytes, target: Path, mode: int) -> None:
    ensure_private_parent(target, path.relative_to(target))
    temporary = path.with_name(f".{path.name}.nddev.tmp.{os.getpid()}.{time.time_ns()}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()
        raise


def remove_empty_directory_if_created(path: Path, existed_before: bool) -> None:
    if existed_before:
        return
    with contextlib.suppress(FileNotFoundError, OSError):
        path.rmdir()


def validate_safe_software_presence(target: Path) -> None:
    for directory, label in (
        (mimo_executable(target).parent, "bin"),
        (software_manifest_path(target).parent, "software"),
        (software_tree_binary(target).parent.parent, "software/versions"),
        (software_tree_binary(target).parent, f"software/versions/{TESTED_VERSION}"),
    ):
        if directory.exists() or directory.is_symlink():
            require_private_directory(directory, label)
    for file_path, label, mode in (
        (mimo_executable(target), f"bin/{mimo_executable(target).name}", OWNER_EXECUTABLE_MODE),
        (
            software_tree_binary(target),
            f"software/versions/{TESTED_VERSION}/{software_tree_binary(target).name}",
            OWNER_EXECUTABLE_MODE,
        ),
        (software_manifest_path(target), "software/mimocode.json", OWNER_FILE_MODE),
    ):
        if file_path.exists() or file_path.is_symlink():
            info = require_regular_file(file_path, label, max_bytes=DOWNLOAD_MAX_BYTES)
            if stat.S_IMODE(info.st_mode) != mode:
                fail(f"{label} must have mode {mode:04o}")


def install_or_update_cli(target: Path, *, operation: str) -> dict[str, Any]:
    with target_lock(target):
        before_target_exists = target.exists() or target.is_symlink()
        if operation == "update-cli" and not before_target_exists:
            fail("update-cli requires existing target-owned MiMo Code software presence")
        canonical_target = ensure_target_directory(target)
        try:
            status = software_status(canonical_target)
            if operation == "install-cli" and status["present"]:
                fail(
                    "install-cli requires absent target-owned MiMo Code software presence; use update-cli"
                )
            if operation == "update-cli" and not status["present"]:
                fail("update-cli requires existing target-owned MiMo Code software presence")
            if operation == "update-cli" and status["current"]:
                return {
                    "ok": True,
                    "operation": "current",
                    "target": str(canonical_target),
                    "version": TESTED_VERSION,
                    "changed": [],
                    "executable": str(mimo_executable(canonical_target)),
                }
            validate_safe_software_presence(canonical_target)
            before_bin_dir = mimo_executable(canonical_target).parent.exists()
            before_software_dir = software_manifest_path(canonical_target).parent.exists()
            before_versions_dir = software_tree_binary(canonical_target).parent.parent.exists()
            before_version_dir = software_tree_binary(canonical_target).parent.exists()
            before_executable, before_executable_mode = snapshot_optional_file(
                mimo_executable(canonical_target), "MiMo Code executable"
            )
            before_tree, before_tree_mode = snapshot_optional_file(
                software_tree_binary(canonical_target), "MiMo Code version tree executable"
            )
            before_manifest, before_manifest_mode = snapshot_optional_file(
                software_manifest_path(canonical_target), "software manifest"
            )
            asset_key, asset = selected_asset()
            url = asset.get("url")
            expected_sha = asset.get("sha256")
            expected_size = asset.get("size")
            name = asset.get("name") or Path(str(url)).name
            if (
                not isinstance(url, str)
                or not isinstance(expected_sha, str)
                or not isinstance(expected_size, int)
            ):
                fail(f"baseline asset {asset_key} is incomplete")
            archive_bytes = read_url_or_file(
                url, max_bytes=DOWNLOAD_MAX_BYTES, expected_size=expected_size
            )
            if sha256_bytes(archive_bytes) != expected_sha:
                fail(f"downloaded MiMo Code digest mismatch for {asset_key}")
            verified_binary = extract_verified_binary(archive_bytes, str(name))
            installer, installer_sha, installer_source, installer_size = read_pinned_installer()
            artifact = run_official_installer(
                installer, installer_source, installer_sha, verified_binary
            )
            manifest = {
                "schema_version": 2,
                "version": TESTED_VERSION,
                "command": COMMAND_NAME,
                "executable": f"bin/{mimo_executable(canonical_target).name}",
                "version_tree_executable": (
                    f"software/versions/{TESTED_VERSION}/{software_tree_binary(canonical_target).name}"
                ),
                "asset": asset_key,
                "asset_url": url,
                "asset_size": expected_size,
                "asset_sha256": expected_sha,
                "installer_url": artifact["installer_source"],
                "installer_size": installer_size,
                "installer_sha256": artifact["installer_sha256"],
                "binary_sha256": artifact["binary_sha256"],
                "version_output": artifact["version_output"],
            }
            try:
                write_private_file(
                    software_tree_binary(canonical_target),
                    artifact["binary"],
                    canonical_target,
                    OWNER_EXECUTABLE_MODE,
                )
                write_private_file(
                    mimo_executable(canonical_target),
                    artifact["binary"],
                    canonical_target,
                    OWNER_EXECUTABLE_MODE,
                )
                if os.environ.get(INTERNAL_FAIL_AFTER_BINARY_SWAP_ENV) == "1":
                    fail("injected failure after MiMo Code binary swap")
                write_private_file(
                    software_manifest_path(canonical_target),
                    canonical_json(manifest),
                    canonical_target,
                    OWNER_FILE_MODE,
                )
                final = software_status(canonical_target)
                if not final["installed"]:
                    fail("MiMo Code software install did not produce target-owned software")
                if installer_source == INSTALLER_URL and url.startswith("https://"):
                    if not final["current"]:
                        fail(
                            "MiMo Code software install did not produce current target-owned software"
                        )
                else:
                    structural = [
                        item
                        for item in final["drift"]
                        if item
                        not in {
                            "asset",
                            "asset_url",
                            "asset_sha256",
                            "asset_size",
                            "installer_size",
                            "installer_url",
                            "installer_sha256",
                        }
                    ]
                    if structural:
                        fail(
                            "MiMo Code test install produced structural drift: "
                            + ", ".join(structural)
                        )
            except BaseException:
                for path, content, mode in (
                    (mimo_executable(canonical_target), before_executable, before_executable_mode),
                    (software_tree_binary(canonical_target), before_tree, before_tree_mode),
                    (
                        software_manifest_path(canonical_target),
                        before_manifest,
                        before_manifest_mode,
                    ),
                ):
                    if content is None:
                        with contextlib.suppress(FileNotFoundError):
                            path.unlink()
                    else:
                        write_private_file(path, content, canonical_target, mode or OWNER_FILE_MODE)
                remove_empty_directory_if_created(
                    software_tree_binary(canonical_target).parent, before_version_dir
                )
                remove_empty_directory_if_created(
                    software_tree_binary(canonical_target).parent.parent, before_versions_dir
                )
                remove_empty_directory_if_created(
                    software_manifest_path(canonical_target).parent, before_software_dir
                )
                remove_empty_directory_if_created(
                    mimo_executable(canonical_target).parent, before_bin_dir
                )
                raise
            return {
                "ok": True,
                "operation": "install" if operation == "install-cli" else "update",
                "target": str(canonical_target),
                "version": TESTED_VERSION,
                "asset": asset_key,
                "binary_sha256": artifact["binary_sha256"],
                "executable": str(mimo_executable(canonical_target)),
            }
        except BaseException:
            remove_empty_directory_if_created(canonical_target, before_target_exists)
            raise


def remove_cli(target: Path) -> dict[str, Any]:
    canonical_target = require_explicit_absolute_target(str(target))
    with target_lock(canonical_target):
        status = software_status(canonical_target)
        if not status["present"]:
            fail("remove-cli requires existing target-owned MiMo Code software presence")
        validate_safe_software_presence(canonical_target)
        for path in (
            mimo_executable(canonical_target),
            software_tree_binary(canonical_target),
            software_manifest_path(canonical_target),
        ):
            if path.exists() or path.is_symlink():
                require_regular_file(path, f"software file {path.relative_to(canonical_target)}")
                path.unlink()
        for directory in (
            software_tree_binary(canonical_target).parent,
            software_tree_binary(canonical_target).parent.parent,
            software_manifest_path(canonical_target).parent,
            mimo_executable(canonical_target).parent,
        ):
            with contextlib.suppress(FileNotFoundError, OSError):
                directory.rmdir()
    return {"ok": True, "operation": "remove-cli", "target": str(canonical_target), "removed": True}


def isolated_child_environment(target: Path) -> dict[str, str]:
    runtime = target / "runtime"
    tmp = runtime / "tmp"
    for directory in (
        runtime,
        tmp,
        runtime / "xdg-config",
        runtime / "xdg-cache",
        runtime / "xdg-state",
        runtime / "xdg-data",
        target / "home",
    ):
        create_missing_directories(missing_directory_chain(directory))
        require_private_directory(directory, f"runtime directory {directory.relative_to(target)}")
    env: dict[str, str] = {}
    for name, value in os.environ.items():
        if name in TOKEN_ENV_NAMES:
            continue
        if name.startswith("MIMOCODE_") or name.startswith("MIMO_"):
            continue
        env[name] = value
    env.update(
        {
            "HOME": str(target / "home"),
            "USERPROFILE": str(target / "home"),
            "MIMOCODE_HOME": str(target),
            "MIMOCODE_CONFIG_DIR": str(target / "config"),
            "MIMOCODE_DISABLE_CRON": "1",
            "MIMOCODE_DISABLE_LOG_ROTATION": "1",
            "MIMOCODE_MIMO_ONLY": "true",
            "MIMOCODE_PURE": "1",
            "TMPDIR": str(tmp),
            "XDG_CONFIG_HOME": str(runtime / "xdg-config"),
            "XDG_CACHE_HOME": str(runtime / "xdg-cache"),
            "XDG_STATE_HOME": str(runtime / "xdg-state"),
            "XDG_DATA_HOME": str(runtime / "xdg-data"),
            "PATH": SAFE_SYSTEM_PATH,
        }
    )
    return env


def validate_launch_args(args: list[str]) -> None:
    for item in args:
        flag = item.split("=", 1)[0]
        if flag in FORBIDDEN_LAUNCH_FLAGS:
            fail(f"launch argument {flag} is not allowed by the managed MiMo Code scope")
    first_command = next((item for item in args if item and not item.startswith("-")), None)
    if first_command in FORBIDDEN_LAUNCH_COMMANDS:
        fail(f"launch command {first_command} is not allowed by the managed MiMo Code scope")


def launch_mimo(target: Path, args: list[str]) -> int:
    canonical_target = require_explicit_absolute_target(str(target))
    validate_launch_args(args)
    with target_lock(canonical_target):
        state = inspect_target(canonical_target)
        if state["state"] != "managed":
            fail("target is not managed by nddev-mimocode-app")
        status = software_status(canonical_target)
        if not status["installed"] or not status["current"]:
            fail("MiMo Code is not installed at the tested version in this target")
        child_args = list(state["launch_args"]) + args
        executable = mimo_executable(canonical_target)
        require_regular_file(executable, "MiMo Code executable", max_bytes=DOWNLOAD_MAX_BYTES)
        child_env = isolated_child_environment(canonical_target)
    completed = subprocess.run(
        [str(executable), *child_args],
        cwd=canonical_target,
        env=child_env,
        check=False,
        timeout=None,
    )
    return int(completed.returncode)


def print_payload(payload: dict[str, Any], *, json_output: bool) -> None:
    del json_output
    print(json.dumps(payload, indent=2, sort_keys=True))


def add_json_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="print JSON output")


def add_target_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--target", required=True, help="explicit absolute MiMo Code target")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    list_parser = subparsers.add_parser("list", help="list setup variants")
    add_json_argument(list_parser)
    for name in ("status", "software-status"):
        command_parser = subparsers.add_parser(name, help=f"{name} for a target")
        add_target_argument(command_parser)
        add_json_argument(command_parser)
    for name in ("plan", "install", "switch"):
        command_parser = subparsers.add_parser(name, help=f"{name} a setup")
        command_parser.add_argument("--setup", required=True)
        add_target_argument(command_parser)
        add_json_argument(command_parser)
    restore_parser = subparsers.add_parser("restore", help="restore a target-bound backup")
    restore_parser.add_argument("--backup", type=int, required=True)
    add_target_argument(restore_parser)
    add_json_argument(restore_parser)
    remove_parser = subparsers.add_parser("remove", help="remove nddev-managed setup files")
    add_target_argument(remove_parser)
    add_json_argument(remove_parser)
    for name in ("install-cli", "update-cli", "remove-cli"):
        command_parser = subparsers.add_parser(name, help=f"{name} exact tested MiMo Code")
        add_target_argument(command_parser)
        add_json_argument(command_parser)
    launch_parser = subparsers.add_parser("launch", help="launch target-owned MiMo Code")
    add_target_argument(launch_parser)
    add_json_argument(launch_parser)
    launch_parser.add_argument("mimo_args", nargs=argparse.REMAINDER)
    return parser.parse_args(argv)


def error_result(message: str, *, json_output: bool) -> int:
    if json_output:
        print(json.dumps({"ok": False, "error": message}, indent=2, sort_keys=True))
    else:
        print(f"error: {message}", file=sys.stderr)
    return 2


def run(args: argparse.Namespace) -> int:
    if args.command == "list":
        print_payload({"ok": True, "setups": list_setups()}, json_output=args.json)
        return 0
    if args.command == "status":
        target = require_explicit_absolute_target(args.target)
        print_payload({"ok": True, **inspect_target(target)}, json_output=args.json)
        return 0
    if args.command == "software-status":
        target = require_explicit_absolute_target(args.target)
        print_payload(software_status(target), json_output=args.json)
        return 0
    if args.command == "plan":
        target = require_explicit_absolute_target(args.target)
        print_payload(plan_setup(target, args.setup), json_output=args.json)
        return 0
    if args.command in {"install", "switch"}:
        target = require_explicit_absolute_target(args.target)
        print_payload(mutate_setup(target, args.setup, args.command), json_output=args.json)
        return 0
    if args.command == "restore":
        target = require_explicit_absolute_target(args.target)
        print_payload(restore_backup(target, args.backup), json_output=args.json)
        return 0
    if args.command == "remove":
        target = require_explicit_absolute_target(args.target)
        print_payload(remove_setup(target), json_output=args.json)
        return 0
    if args.command == "install-cli":
        target = require_explicit_absolute_target(args.target)
        print_payload(install_or_update_cli(target, operation="install-cli"), json_output=args.json)
        return 0
    if args.command == "update-cli":
        target = require_explicit_absolute_target(args.target)
        print_payload(install_or_update_cli(target, operation="update-cli"), json_output=args.json)
        return 0
    if args.command == "remove-cli":
        target = require_explicit_absolute_target(args.target)
        print_payload(remove_cli(target), json_output=args.json)
        return 0
    if args.command == "launch":
        target = require_explicit_absolute_target(args.target)
        mimo_args = list(args.mimo_args)
        if mimo_args and mimo_args[0] == "--":
            mimo_args = mimo_args[1:]
        return launch_mimo(target, mimo_args)
    fail(f"unknown command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        return run(args)
    except MiMoCodeSetupError as exc:
        json_output = "--json" in (argv if argv is not None else sys.argv[1:])
        return error_result(str(exc), json_output=json_output)


if __name__ == "__main__":
    raise SystemExit(main())
