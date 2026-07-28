#!/usr/bin/env python3
"""Transactional setup manager for an explicit MiMo Code target."""

from __future__ import annotations

import argparse
import contextlib
import errno
import hashlib
import json
import os
import platform
import re
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

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows is rejected for lifecycle.
    fcntl = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[1]
CATALOG_ROOT = ROOT / "setups"
PROFILE_ROOT = ROOT / "profiles"
BUILDER_ROOT = ROOT / "plugins" / "nddev-builder"
VERSION = (ROOT / "VERSION").read_text(encoding="ascii").strip()
PRODUCT_NAME = "nddev-mimocode-app"
COMMAND_NAME = "mimo"
STAMP_NAME = "NDDEV-MIMOCODE-SETUP.json"
BACKUP_POOL_NAME = "NDDEV-MIMOCODE-BACKUPS.json"
BACKUP_NAME = "NDDEV-MIMOCODE-BACKUP.json"
LOCK_DIRECTORY_NAME = ".nddev-mimocode-lock"
LOCK_FILE_NAME = "lock"
BOOTSTRAP_GLOBAL_LOCK_NAME = "global.lock"
BOOTSTRAP_LOCK_SUFFIX = ".lock"
BASELINE_REF = ROOT / "references" / "mimocode-baseline.json"
TESTED_VERSION = "0.1.9"
INSTALLER_URL = "https://mimo.xiaomi.com/install"
INSTALLER_SIZE = 15819
INSTALLER_SHA256 = "2251667c8b12091a1e65744d892c8abfba008e621b22cf5d39338aa36c12efb2"
DEFAULT_SETUP_ID = "nddev-builder"
DEFAULT_PROFILE_ID = "full-auto"
LEGACY_BUILD_VERSIONS = {"0.1.0"}
BASH_PATH = Path("/bin/bash")
TRUSTED_TOOL_PATHS = ("/usr/bin", "/bin", "/usr/sbin", "/sbin", "/opt/homebrew/bin")
DETERMINISTIC_PATH = os.pathsep.join(TRUSTED_TOOL_PATHS)
OWNER_FILE_MODE = 0o600
OWNER_EXECUTABLE_MODE = 0o700
OFFICIAL_INSTALLER_EXECUTABLE_MODE = 0o755
OWNER_DIRECTORY_MODE = 0o700
PROTECTED_DIRECTORY_MODE = 0o500
PROTECTED_EXECUTABLE_MODE = 0o500
METADATA_MAX_BYTES = 256 * 1024
MANAGED_PAYLOAD_MAX_BYTES = 8 * 1024 * 1024
DOWNLOAD_MAX_BYTES = 256 * 1024 * 1024
SOFTWARE_EXECUTABLE_MAX_BYTES = 128 * 1024 * 1024
PROCESS_TIMEOUT_SECONDS = 120
STAGED_VERSION_PROBE_TIMEOUT_SECONDS = 60.0
SETUP_ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
MIMOCODE_HOME_RELATIVE = Path("home") / "mimocode"
MIMOCODE_CONFIG_DIR_RELATIVE = MIMOCODE_HOME_RELATIVE / "config"
MIMOCODE_CONFIG_RELATIVE = MIMOCODE_CONFIG_DIR_RELATIVE / "mimocode.json"
MIMOCODE_AGENTS_RELATIVE = MIMOCODE_CONFIG_DIR_RELATIVE / "AGENTS.md"
SOFTWARE_MANIFEST_RELATIVE = Path("software") / "mimocode.json"
SOFTWARE_VERSION_RELATIVE = Path("software") / "versions" / TESTED_VERSION
SOFTWARE_REPLACE_PATHS = (
    Path("bin") / COMMAND_NAME,
    SOFTWARE_VERSION_RELATIVE / COMMAND_NAME,
    SOFTWARE_MANIFEST_RELATIVE,
)
SOFTWARE_PARENT_PATHS = tuple(
    sorted(
        {relative.parent for relative in SOFTWARE_REPLACE_PATHS if relative.parent != Path(".")},
        key=str,
    )
)
MANAGED_CONFIG_KEYS = (
    "$schema",
    "agent",
    "autoupdate",
    "compaction",
    "default_agent",
    "instructions",
    "mcp",
    "permission",
    "plugin",
    "share",
    "skills",
    "snapshot",
    "watcher",
)
LEGACY_MANAGED_CONFIG_KEYS = (
    "$schema",
    "agent",
    "autoupdate",
    "compaction",
    "default_agent",
    "disabled_providers",
    "instructions",
    "mcp",
    "permission",
    "plugin",
    "share",
    "skills",
    "snapshot",
    "watcher",
)
STAMP_KEYS = {
    "schema_version",
    "product_name",
    "build_version",
    "setup_id",
    "profile_id",
    "canonical_target",
    "managed_files",
    "builder_projection",
    "launch_args",
    "launch_env",
}
LEGACY_STAMP_KEYS = {
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
    "source_profile_id",
    "managed_files",
    "file_records",
    "created_at",
}
BACKUP_POOL_KEYS = {
    "schema_version",
    "product_name",
    "build_version",
    "canonical_target",
}
BOOTSTRAP_GLOBAL_LOCK_KEYS = {"schema_version", "product_name", "anchor"}
BOOTSTRAP_LOCK_KEYS = {"schema_version", "product_name", "canonical_target", "target_key"}
TOKEN_ENV_NAMES = {
    "ANTHROPIC_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "DATABASE_URL",
    "GEMINI_API_KEY",
    "GITHUB_TOKEN",
    "GIT_ASKPASS",
    "GOOGLE_API_KEY",
    "MIMO_ACCESS_TOKEN",
    "MIMO_API_KEY",
    "MIMOCODE_ACCESS_TOKEN",
    "MIMOCODE_API_KEY",
    "MIMOCODE_AUTH_CONTENT",
    "MIMOCODE_CONSOLE_TOKEN",
    "MIMOCODE_SERVER_PASSWORD",
    "MIMOCODE_WORKSPACE_ID",
    "NPM_TOKEN",
    "OPENAI_API_KEY",
    "SSH_ASKPASS",
    "SSH_AUTH_SOCK",
}
SAFE_CHILD_INHERITED_ENV_NAMES = (
    "CI",
    "COLORTERM",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "NODE_EXTRA_CA_CERTS",
    "NO_COLOR",
    "NO_PROXY",
    "REQUESTS_CA_BUNDLE",
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
    "SYSTEMROOT",
    "TERM",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)
MIMOCODE_BOUNDARY_ENV = {
    "MIMOCODE_DISABLE_CLAUDE_CODE": "1",
    "MIMOCODE_DISABLE_CLAUDE_CODE_COMMANDS": "1",
    "MIMOCODE_DISABLE_CLAUDE_CODE_MCP": "1",
    "MIMOCODE_DISABLE_CLAUDE_IMPORT": "1",
    "MIMOCODE_DISABLE_EXTERNAL_SKILLS": "1",
    "MIMOCODE_DISABLE_PROJECT_CONFIG": "1",
    "MIMOCODE_PURE": "1",
}
MIMOCODE_FIXED_RUNTIME_ENV = {
    **MIMOCODE_BOUNDARY_ENV,
    "MIMOCODE_DISABLE_AUTOUPDATE": "1",
    "MIMOCODE_DISABLE_LSP_DOWNLOAD": "1",
    "MIMOCODE_DISABLE_MODELS_FETCH": "1",
    "MIMOCODE_DISABLE_PROVIDER_ENV": "1",
    "MIMOCODE_ENABLE_ANALYSIS": "0",
}
PROJECT_BOUNDARY_PATHS = (
    Path(".mimocode") / "mimocode.json",
    Path(".mimocode") / "mimocode.jsonc",
    Path(".mimocode") / "plugin",
    Path(".mimocode") / "plugins",
    Path(".mimocode") / "tools",
    Path(".mimocode") / "tui",
    Path(".agents") / "skills",
    Path(".claude"),
    Path(".claude.json"),
    Path(".codex") / "skills",
    Path(".opencode") / "skills",
)
OBSERVED_UPLOADED_RUNTIME_ASSET_IDS = (
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
)
RELEASE_PAGE_ASSET_COUNT = 14
GENERATED_SOURCE_DOWNLOADS = (
    {
        "name": "Source code (zip)",
        "url": "https://github.com/XiaomiMiMo/MiMo-Code/archive/refs/tags/v0.1.9.zip",
    },
    {
        "name": "Source code (tar.gz)",
        "url": "https://github.com/XiaomiMiMo/MiMo-Code/archive/refs/tags/v0.1.9.tar.gz",
    },
)
SUPPORTED_PRODUCT_HOST_IDS = (
    "macos-arm64",
    "macos-x64",
    "ubuntu-glibc-arm64",
    "ubuntu-glibc-x64",
)
REJECTED_PRODUCT_HOST_IDS = (
    "windows",
    "non-ubuntu-linux",
    "linux-musl",
    "unsupported-architecture",
)
BLOCKED_LAUNCH_FLAGS = {
    "--agent",
    "--dangerously-skip-permissions",
    "--trust",
    "--never-ask",
}
BLOCKED_LAUNCH_COMMANDS = {"upgrade"}
BLOCKED_MANAGER_ENV_NAMES = {
    "MIMOCODE_AUTO_APPROVE_DELETE",
    "MIMOCODE_CONFIG",
    "MIMOCODE_CONFIG_CONTENT",
    "MIMOCODE_CONFIG_DIR",
    "MIMOCODE_DANGEROUSLY_SKIP_PERMISSIONS",
    "MIMOCODE_HOME",
    "MIMOCODE_MIMO_ONLY",
    "MIMOCODE_PERMISSION",
    *MIMOCODE_FIXED_RUNTIME_ENV,
}
FORBIDDEN_MANAGER_ENV_PREFIXES = (
    "NDDEV_MIMOCODE_BOOTSTRAP_",
    "NDDEV_MIMOCODE_LOCK_",
)
TARGET_BOUND_COMMANDS = {
    "status",
    "software-status",
    "plan",
    "install",
    "update",
    "switch",
    "migrate",
    "restore",
    "remove",
    "install-cli",
    "update-cli",
    "remove-cli",
    "launch",
}


class MiMoCodeSetupError(Exception):
    """A safe user-facing lifecycle failure."""


class ConcurrentTargetChange(MiMoCodeSetupError):
    """A fail-closed target race."""


class RetryBootstrapInspection(Exception):
    """Internal signal for a cold read racing a newly published product anchor."""


class CliArgumentError(Exception):
    """An argparse error that can be rendered through the public JSON boundary."""


class JsonBoundaryArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise CliArgumentError(message)


def fail(message: str) -> NoReturn:
    raise MiMoCodeSetupError(message)


def fail_concurrent(message: str) -> NoReturn:
    raise ConcurrentTargetChange(message)


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_all(descriptor: int, content: bytes) -> None:
    view = memoryview(content)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            fail("short write while staging file")
        view = view[written:]


def fsync_directory(path: Path, label: str) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def staged_file_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.nddev.tmp.{os.getpid()}.{time.time_ns()}")


def create_staged_file(path: Path, content: bytes, mode: int) -> Path:
    temporary = staged_file_path(path)
    descriptor = -1
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        os.fchmod(descriptor, mode)
        write_all(descriptor, content)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        return temporary
    except BaseException:
        if descriptor >= 0:
            with contextlib.suppress(OSError):
                os.close(descriptor)
        cleanup_path_with_retries(temporary)
        raise


def commit_staged_file(temporary: Path, path: Path) -> None:
    os.replace(temporary, path)
    fsync_directory(path.parent, f"parent directory for {path.name}")


def fsync_directory_with_retries(path: Path, label: str, *, attempts: int = 3) -> None:
    last: BaseException | None = None
    for _attempt in range(attempts):
        try:
            fsync_directory(path, label)
            return
        except BaseException as exc:
            last = exc
    if last is not None:
        raise last


def write_durable_file(path: Path, content: bytes, mode: int) -> None:
    temporary = create_staged_file(path, content, mode)
    try:
        commit_staged_file(temporary, path)
    except BaseException:
        cleanup_path_with_retries(temporary)
        raise


def unlink_file_durable(path: Path) -> None:
    parent = path.parent
    path.unlink()
    fsync_directory_with_retries(parent, f"parent directory after unlink {path.name}")


def rmdir_if_empty_durable(path: Path) -> bool:
    parent = path.parent
    path.rmdir()
    fsync_directory_with_retries(parent, f"parent directory after rmdir {path.name}")
    return True


def cleanup_directory_contents_durable(path: Path) -> None:
    for child in sorted(path.iterdir(), key=lambda item: item.name):
        info = child.lstat()
        if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
            cleanup_directory_contents_durable(child)
            rmdir_if_empty_durable(child)
        else:
            unlink_file_durable(child)


def cleanup_path_once(path: Path) -> None:
    parent = path.parent
    if not path_present(path):
        if parent.is_dir():
            fsync_directory_with_retries(parent, f"parent directory after cleanup {path.name}")
        return
    info = path.lstat()
    if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
        cleanup_directory_contents_durable(path)
        rmdir_if_empty_durable(path)
    else:
        unlink_file_durable(path)


def cleanup_path_with_retries(path: Path, *, attempts: int = 3, raise_on_failure: bool = False) -> None:
    last: BaseException | None = None
    for _attempt in range(attempts):
        try:
            cleanup_path_once(path)
            return
        except BaseException as exc:
            last = exc
    if raise_on_failure and last is not None:
        raise last


def cleanup_transaction_residue(target: Path) -> None:
    if not path_present(target):
        return
    for path in sorted(target.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        name = path.name
        if (
            ".nddev.tmp." in name
            or ".stage." in name
            or ".rollback." in name
            or ".retired." in name
            or ".recovery." in name
        ):
            cleanup_path_with_retries(path)


def is_transaction_residue_path(path: Path) -> bool:
    return any(
        ".nddev.tmp." in part
        or ".stage." in part
        or ".rollback." in part
        or ".retired." in part
        or ".recovery." in part
        for part in path.parts
    )


FileObjectRecord = dict[str, Any]
FileObjectSnapshot = dict[Path, FileObjectRecord]
DirectoryObjectSnapshot = dict[Path, dict[str, Any]]
DirectoryMetadataRecord = dict[str, int]
BootstrapPoolState = tuple[Path, bool, DirectoryMetadataRecord, DirectoryMetadataRecord]


def absent_file_object() -> FileObjectRecord:
    return {"present": False}


def file_object_record(path: Path, label: str, *, owner_only: bool, max_bytes: int) -> FileObjectRecord:
    if not path_present(path):
        return absent_file_object()
    content, info = read_regular_file(path, label, owner_only=owner_only, max_bytes=max_bytes)
    return {
        "present": True,
        "content": content,
        "mode": stat.S_IMODE(info.st_mode),
        "dev": info.st_dev,
        "ino": info.st_ino,
        "mtime_ns": info.st_mtime_ns,
        "size": info.st_size,
    }


def file_object_matches(
    path: Path,
    record: FileObjectRecord,
    label: str,
    *,
    owner_only: bool,
    max_bytes: int,
) -> bool:
    if not record.get("present"):
        return not path_present(path)
    if not path_present(path):
        return False
    try:
        current = file_object_record(path, label, owner_only=owner_only, max_bytes=max_bytes)
    except MiMoCodeSetupError:
        return False
    return current == record


def verify_file_object_snapshot(
    target: Path,
    snapshot: FileObjectSnapshot,
    label: str,
    *,
    owner_only_for: Any,
    max_bytes_for: Any,
) -> None:
    for relative, record in snapshot.items():
        path = target / relative
        if not file_object_matches(
            path,
            record,
            f"{label} file {relative}",
            owner_only=owner_only_for(relative),
            max_bytes=max_bytes_for(relative),
        ):
            fail_concurrent(f"{label} did not restore exact file object: {relative}")


def directory_metadata_record(path: Path, label: str) -> DirectoryMetadataRecord:
    info = require_directory(path, label)
    return {
        "mode": stat.S_IMODE(info.st_mode),
        "dev": info.st_dev,
        "ino": info.st_ino,
        "mtime_ns": info.st_mtime_ns,
    }


def restore_directory_metadata_record(path: Path, record: DirectoryMetadataRecord, label: str) -> None:
    last: BaseException | None = None
    for _attempt in range(3):
        try:
            info = require_directory(path, label)
            if info.st_dev != record["dev"] or info.st_ino != record["ino"]:
                fail_concurrent(f"{label} directory identity changed")
            if stat.S_IMODE(info.st_mode) != record["mode"]:
                path.chmod(record["mode"])
            current = path.lstat()
            if current.st_mtime_ns != record["mtime_ns"]:
                os.utime(path, ns=(current.st_atime_ns, record["mtime_ns"]))
            fsync_directory_with_retries(path, f"{label} directory fsync")
            verified = require_directory(path, label)
            if (
                verified.st_dev == record["dev"]
                and verified.st_ino == record["ino"]
                and stat.S_IMODE(verified.st_mode) == record["mode"]
                and verified.st_mtime_ns == record["mtime_ns"]
            ):
                return
            fail_concurrent(f"{label} directory metadata did not restore")
        except BaseException as exc:
            last = exc
    if last is not None:
        raise last


def directory_object_snapshot(target: Path) -> DirectoryObjectSnapshot:
    if not path_present(target):
        return {}
    require_directory(target, "directory snapshot target")
    result: DirectoryObjectSnapshot = {}
    directories = [
        item
        for item in target.rglob("*")
        if item.is_dir() and not item.is_symlink() and not is_transaction_residue_path(item.relative_to(target))
    ]
    for path in [target, *sorted(directories, key=lambda entry: str(entry.relative_to(target)))]:
        relative = Path(".") if path == target else path.relative_to(target)
        result[relative] = directory_metadata_record(path, f"directory snapshot {relative}")
    return result


def restore_directory_object_snapshot(target: Path, snapshot: DirectoryObjectSnapshot, label: str) -> None:
    for relative, record in sorted(snapshot.items(), key=lambda item: len(item[0].parts), reverse=True):
        path = target if relative == Path(".") else target / relative
        restore_directory_metadata_record(path, record, f"{label} directory {relative}")
    if path_present(target):
        fsync_directory_with_retries(target, f"{label} target directory after metadata restore")


def rollback_created_target_if_absent(
    canonical_target: Path,
    existed_before: bool,
    parent_record: DirectoryMetadataRecord,
    label: str,
) -> None:
    if existed_before:
        return
    with contextlib.suppress(FileNotFoundError, OSError):
        lock_directory = lock_directory_path(canonical_target)
        info = lock_directory.lstat()
        if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
            lock_directory.chmod(OWNER_DIRECTORY_MODE)
    cleanup_path_with_retries(canonical_target, raise_on_failure=True)
    if path_present(canonical_target):
        fail_concurrent(f"{label} did not remove newly created target")
    restore_directory_metadata_record(canonical_target.parent, parent_record, f"{label} target parent")
    if path_present(canonical_target):
        fail_concurrent(f"{label} recreated target while restoring parent metadata")


class FileUndoTransaction:
    def __init__(
        self,
        target: Path,
        before: FileObjectSnapshot,
        *,
        label: str,
        owner_only_for: Any,
        max_bytes_for: Any,
    ) -> None:
        self.target = target
        self.before = before
        self.label = label
        self.owner_only_for = owner_only_for
        self.max_bytes_for = max_bytes_for
        self.before_directories = directory_object_snapshot(target)
        self.undo_root = target / f".nddev-mimocode.rollback.{os.getpid()}.{time.time_ns()}"
        self.records: dict[Path, Path | None] = {}

    def _undo_path(self, relative: Path) -> Path:
        return self.undo_root / str(len(self.records)) / relative

    def _ensure_undo_parent(self, undo_path: Path) -> None:
        undo_relative = undo_path.parent.relative_to(self.target)
        ensure_private_directory_under_target(self.target, undo_relative, "rollback parent")

    def hold(self, relative: Path, path: Path) -> None:
        if relative in self.records:
            return
        record = self.before[relative]
        undo_path: Path | None = None
        if record.get("present"):
            if not file_object_matches(
                path,
                record,
                f"{self.label} pre-state file {relative}",
                owner_only=self.owner_only_for(relative),
                max_bytes=self.max_bytes_for(relative),
            ):
                fail_concurrent(f"{self.label} pre-state changed before mutation: {relative}")
            undo_path = self._undo_path(relative)
            self._ensure_undo_parent(undo_path)
            self.records[relative] = undo_path
            os.replace(path, undo_path)
            fsync_directory_with_retries(path.parent, f"parent directory after holding {relative}")
            fsync_directory_with_retries(undo_path.parent, f"rollback parent after holding {relative}")
        else:
            self.records[relative] = None

    def rollback_once(self) -> None:
        for relative in reversed(list(self.records)):
            path = self.target / relative
            record = self.before[relative]
            undo_path = self.records[relative]
            if not record.get("present"):
                if path_present(path):
                    require_regular_file(
                        path,
                        f"{self.label} rollback created file {relative}",
                        max_bytes=self.max_bytes_for(relative),
                    )
                    unlink_file_durable(path)
                continue
            if file_object_matches(
                path,
                record,
                f"{self.label} rollback restored file {relative}",
                owner_only=self.owner_only_for(relative),
                max_bytes=self.max_bytes_for(relative),
            ):
                fsync_directory_with_retries(path.parent, f"parent directory after rollback restore {relative}")
                continue
            if path_present(path):
                require_regular_file(
                    path,
                    f"{self.label} rollback replacement file {relative}",
                    max_bytes=self.max_bytes_for(relative),
                )
                unlink_file_durable(path)
            ensure_private_parent(self.target, relative)
            if undo_path is None or not path_present(undo_path):
                fail_concurrent(f"{self.label} rollback material is missing: {relative}")
            os.replace(undo_path, path)
            fsync_directory_with_retries(path.parent, f"parent directory after rollback restore {relative}")
            fsync_directory_with_retries(undo_path.parent, f"rollback parent after rollback restore {relative}")
        verify_file_object_snapshot(
            self.target,
            self.before,
            self.label,
            owner_only_for=self.owner_only_for,
            max_bytes_for=self.max_bytes_for,
        )
        cleanup_path_with_retries(self.undo_root, raise_on_failure=True)
        restore_directory_object_snapshot(self.target, self.before_directories, self.label)

    def rollback(self) -> None:
        last: BaseException | None = None
        for _attempt in range(3):
            try:
                self.rollback_once()
                return
            except BaseException as exc:
                last = exc
        if last is not None:
            raise last

    def commit_cleanup(self) -> None:
        cleanup_path_with_retries(self.undo_root, raise_on_failure=True)


class DirectoryUndoTransaction:
    def __init__(self, target: Path, *, label: str) -> None:
        self.target = target
        self.label = label
        self.undo_root = target / f".nddev-mimocode.rollback.dirs.{os.getpid()}.{time.time_ns()}"
        self.records: dict[Path, Path] = {}

    def _undo_path(self, relative: Path) -> Path:
        return self.undo_root / str(len(self.records)) / relative

    def _ensure_undo_parent(self, undo_path: Path) -> None:
        undo_relative = undo_path.parent.relative_to(self.target)
        ensure_private_directory_under_target(self.target, undo_relative, "directory rollback parent")

    def hold_empty(self, relative: Path) -> bool:
        if relative in self.records:
            return True
        path = self.target / relative
        if not path_present(path):
            return False
        require_private_directory(path, f"{self.label} directory {relative}")
        try:
            next(path.iterdir())
        except StopIteration:
            pass
        except FileNotFoundError:
            return False
        else:
            fail(f"{self.label} directory is not empty: {relative}")
        undo_path = self._undo_path(relative)
        self._ensure_undo_parent(undo_path)
        self.records[relative] = undo_path
        os.replace(path, undo_path)
        fsync_directory_with_retries(path.parent, f"parent directory after holding {relative}")
        fsync_directory_with_retries(undo_path.parent, f"directory rollback parent after holding {relative}")
        return True

    def rollback_once(self) -> None:
        for relative in reversed(list(self.records)):
            path = self.target / relative
            undo_path = self.records[relative]
            if path_present(path):
                current = path.lstat()
                if stat.S_ISDIR(current.st_mode) and not stat.S_ISLNK(current.st_mode):
                    cleanup_path_with_retries(path, raise_on_failure=True)
                else:
                    fail_concurrent(f"{self.label} rollback found non-directory at {relative}")
            ensure_private_directory_under_target(self.target, relative.parent, "directory rollback restore parent")
            if not path_present(undo_path):
                fail_concurrent(f"{self.label} directory rollback material is missing: {relative}")
            os.replace(undo_path, path)
            fsync_directory_with_retries(path.parent, f"parent directory after directory rollback restore {relative}")
            fsync_directory_with_retries(undo_path.parent, f"directory rollback parent after restore {relative}")
        cleanup_path_with_retries(self.undo_root, raise_on_failure=True)

    def rollback(self) -> None:
        last: BaseException | None = None
        for _attempt in range(3):
            try:
                self.rollback_once()
                return
            except BaseException as exc:
                last = exc
        if last is not None:
            raise last

    def commit_cleanup(self) -> None:
        cleanup_path_with_retries(self.undo_root, raise_on_failure=True)


def identity_of(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def owner_of(info: os.stat_result) -> int | None:
    return info.st_uid if hasattr(info, "st_uid") else None


def is_current_user_owned(info: os.stat_result) -> bool:
    return not hasattr(os, "geteuid") or owner_of(info) == os.geteuid()


def is_owner_only_file(info: os.stat_result) -> bool:
    return (
        stat.S_ISREG(info.st_mode)
        and stat.S_IMODE(info.st_mode) == OWNER_FILE_MODE
        and is_current_user_owned(info)
    )


def is_owner_private_directory(info: os.stat_result) -> bool:
    return (
        stat.S_ISDIR(info.st_mode)
        and stat.S_IMODE(info.st_mode) == OWNER_DIRECTORY_MODE
        and is_current_user_owned(info)
    )


def is_owner_protected_directory(info: os.stat_result) -> bool:
    return (
        stat.S_ISDIR(info.st_mode)
        and stat.S_IMODE(info.st_mode) == PROTECTED_DIRECTORY_MODE
        and is_current_user_owned(info)
    )


def path_present(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
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


def require_private_directory(path: Path, label: str) -> os.stat_result:
    info = require_directory(path, label)
    if not is_owner_private_directory(info):
        fail(f"{label} must be owned by the current user with mode 0700")
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
    before = require_regular_file(path, label, owner_only=owner_only, max_bytes=max_bytes)
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            fail(f"{label} must not be a symlink")
        fail(f"cannot open {label}: {exc}")
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
    final = require_regular_file(path, label, owner_only=owner_only, max_bytes=max_bytes)
    if identity_of(after) != identity_of(before) or identity_of(final) != identity_of(before):
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


def legacy_managed_config_view(config: dict[str, Any]) -> dict[str, Any]:
    return {key: config[key] for key in LEGACY_MANAGED_CONFIG_KEYS if key in config}


def merge_config(existing: dict[str, Any] | None, setup_config: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if existing is not None:
        for key, value in existing.items():
            if key not in MANAGED_CONFIG_KEYS:
                result[key] = value
    result.update(managed_config_view(setup_config))
    return result


def managed_digest(relative: Path, content: bytes) -> str:
    if relative == MIMOCODE_CONFIG_RELATIVE:
        config = parse_json_object(content, str(relative))
        return sha256_bytes(canonical_json(managed_config_view(config)))
    return sha256_bytes(content)


def legacy_managed_digest(relative: Path, content: bytes) -> str:
    if relative == Path("config") / "mimocode.json":
        config = parse_json_object(content, str(relative))
        return sha256_bytes(canonical_json(legacy_managed_config_view(config)))
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


def discover_builder_source_files() -> tuple[tuple[Path, Path], ...]:
    if not BUILDER_ROOT.is_dir() or BUILDER_ROOT.is_symlink():
        raise RuntimeError("builder source root is missing")
    result: list[tuple[Path, Path]] = []
    for path in sorted(BUILDER_ROOT.rglob("*"), key=lambda item: str(item.relative_to(BUILDER_ROOT))):
        relative = path.relative_to(BUILDER_ROOT)
        if path.is_dir():
            continue
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"unsafe builder source path: {relative}")
        if relative.parts and relative.parts[0] == "workflows":
            raise RuntimeError("builder workflows are not part of the supported MiMo Code projection")
        result.append((relative, MIMOCODE_CONFIG_DIR_RELATIVE / relative))
    return tuple(result)


BUILDER_SOURCE_FILES = discover_builder_source_files()
MANAGED_PATHS = (
    MIMOCODE_CONFIG_RELATIVE,
    MIMOCODE_AGENTS_RELATIVE,
    *(target for _, target in BUILDER_SOURCE_FILES),
    Path(STAMP_NAME),
)
LEGACY_MANAGED_PATHS = (
    Path("config") / "mimocode.json",
    Path("config") / "AGENTS.md",
    Path("config") / "skills" / "nddev-builder" / "SKILL.md",
    Path("config") / "agents" / "nddev-builder.md",
    Path("config") / "instructions" / "nddev-builder.md",
    Path(".mimocode") / "workflows" / "nddev-builder.js",
    Path(STAMP_NAME),
)
ALL_MANAGED_PATHS = tuple(dict.fromkeys((*MANAGED_PATHS, *LEGACY_MANAGED_PATHS)))


def validate_setup_config(config: dict[str, Any], label: str) -> None:
    if config.get("$schema") != "https://mimo.xiaomi.com/mimocode/config.json":
        fail(f"{label} has invalid schema")
    if config.get("autoupdate") is not False:
        fail(f"{label} must disable automatic updates")
    if config.get("share") != "disabled":
        fail(f"{label} must disable session sharing")
    if "tools" in config:
        fail(f"{label} must not use deprecated tools config")
    if config.get("skills") != {"paths": ["./skills"]}:
        fail(f"{label} must load native skills from ./skills")
    if config.get("instructions") != ["./AGENTS.md", "./instructions/nddev-builder.md"]:
        fail(f"{label} must include the managed builder instructions")
    if config.get("mcp") != {}:
        fail(f"{label} must not configure live MCP servers")
    if config.get("plugin") != []:
        fail(f"{label} must not load managed plugins by default")
    agents = config.get("agent")
    if not isinstance(agents, dict) or "nddev-builder" not in agents:
        fail(f"{label} must define the native nddev-builder agent")
    builder = agents["nddev-builder"]
    if not isinstance(builder, dict) or builder.get("mode") != "subagent":
        fail(f"{label} nddev-builder agent must be a subagent")
    if builder.get("prompt") != "{file:./instructions/nddev-builder.md}":
        fail(f"{label} nddev-builder agent prompt must use managed instructions")


def validate_profile_metadata(metadata: dict[str, Any], profile_id: str) -> None:
    require_exact_keys(
        metadata,
        {
            "schema_version",
            "id",
            "description",
            "default",
            "default_agent",
            "permission",
            "launch_args",
            "launch_env",
        },
        f"profile {profile_id} metadata",
    )
    if metadata["schema_version"] != 1:
        fail(f"profile {profile_id} metadata has unsupported schema")
    if metadata["id"] != profile_id:
        fail(f"profile {profile_id} metadata identity mismatch")
    if profile_id not in {"safe", "full-auto"}:
        fail(f"unsupported profile: {profile_id}")
    if not isinstance(metadata["default"], bool):
        fail(f"profile {profile_id} default must be boolean")
    if not isinstance(metadata["default_agent"], str):
        fail(f"profile {profile_id} default_agent must be a string")
    validate_permission_leaf(metadata["permission"], f"profile {profile_id}.permission")
    if not isinstance(metadata["launch_args"], list) or not all(
        isinstance(item, str) for item in metadata["launch_args"]
    ):
        fail(f"profile {profile_id} launch_args must be a string array")
    launch_env = metadata["launch_env"]
    if not isinstance(launch_env, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in launch_env.items()
    ):
        fail(f"profile {profile_id} launch_env must be a string object")
    blocked_runtime_env = sorted(set(launch_env) & set(MIMOCODE_FIXED_RUNTIME_ENV))
    if blocked_runtime_env:
        fail(f"profile {profile_id} launch_env must not override manager-owned runtime env: {blocked_runtime_env}")
    if profile_id == "full-auto":
        if metadata["default"] is not True or metadata["default_agent"] != "build":
            fail("full-auto must be the default build profile")
        if metadata["permission"] != "allow":
            fail("full-auto permission must be native allow-all")
        if metadata["launch_args"] != []:
            fail("full-auto launch args must not carry caller-visible bypass flags")
        if launch_env != {
            "MIMOCODE_AUTO_APPROVE_DELETE": "1",
            "MIMOCODE_DANGEROUSLY_SKIP_PERMISSIONS": "1",
        }:
            fail("full-auto launch env must enable the source-proven bypass only")
    if profile_id == "safe":
        if metadata["default"] is not False or metadata["default_agent"] != "plan":
            fail("safe must be the non-default plan profile")
        if metadata["launch_args"] != ["--agent", "plan"]:
            fail("safe launch args must select native plan agent")
        if launch_env != {}:
            fail("safe launch env must not enable bypass flags")


def validate_rendered_config(config: dict[str, Any], label: str) -> None:
    validate_setup_config(config, label)
    if config.get("default_agent") not in {"build", "plan"}:
        fail(f"{label} must select a supported native default agent")
    if "permission" not in config:
        fail(f"{label} must define permission")
    validate_permission_leaf(config["permission"], f"{label}.permission")


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
        },
        f"setup {setup_id} metadata",
    )
    if metadata["schema_version"] != 1:
        fail(f"setup {setup_id} metadata has unsupported schema")
    if metadata["id"] != setup_id or metadata["id"] != DEFAULT_SETUP_ID:
        fail(f"setup {setup_id} is not the supported content setup")
    if metadata["managed_files"] != [str(MIMOCODE_CONFIG_RELATIVE), str(MIMOCODE_AGENTS_RELATIVE)]:
        fail(f"setup {setup_id} managed file declaration is invalid")
    if (
        metadata["builder_projection"] != "native-config-skills-agents-instructions"
        or metadata["builder_default_on"] is not True
    ):
        fail(f"setup {setup_id} must enable native builder projection")


def render_builder_files() -> dict[Path, bytes]:
    files: dict[Path, bytes] = {}
    for source_relative, target_relative in BUILDER_SOURCE_FILES:
        content, _ = read_regular_file(BUILDER_ROOT / source_relative, f"builder source {source_relative}")
        files[target_relative] = content
    return files


def build_stamp(
    setup_id: str,
    profile_id: str,
    desired: dict[Path, bytes],
    launch_args: list[str],
    launch_env: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "product_name": PRODUCT_NAME,
        "build_version": VERSION,
        "setup_id": setup_id,
        "profile_id": profile_id,
        "canonical_target": "",
        "managed_files": {
            str(relative): managed_digest(relative, content)
            for relative, content in desired.items()
            if relative != Path(STAMP_NAME)
        },
        "builder_projection": "mimocode-native-config-skills-agents-instructions",
        "launch_args": launch_args,
        "launch_env": launch_env,
    }


def bind_stamp(stamp: dict[str, Any], canonical_target: Path) -> dict[str, Any]:
    bound = dict(stamp)
    bound["canonical_target"] = str(canonical_target)
    return bound


def render_setup(
    setup_id: str,
    profile_id: str,
    *,
    existing_config: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[Path, bytes]]:
    validate_setup_id(setup_id)
    validate_setup_id(profile_id)
    setup_root = CATALOG_ROOT / setup_id
    if not setup_root.is_dir() or setup_root.is_symlink():
        fail(f"unknown setup: {setup_id}")
    profile_root = PROFILE_ROOT / profile_id
    if not profile_root.is_dir() or profile_root.is_symlink():
        fail(f"unknown profile: {profile_id}")
    metadata = load_json_object(setup_root / "setup.json", f"setup {setup_id} metadata")
    validate_setup_metadata(metadata, setup_id)
    profile_metadata = load_json_object(profile_root / "profile.json", f"profile {profile_id} metadata")
    validate_profile_metadata(profile_metadata, profile_id)
    config = load_json_object(setup_root / "mimocode.json", f"setup {setup_id}/mimocode.json")
    validate_setup_config(config, f"setup {setup_id}/mimocode.json")
    config = dict(config)
    config["default_agent"] = profile_metadata["default_agent"]
    config["permission"] = profile_metadata["permission"]
    validate_rendered_config(config, f"rendered {setup_id}/{profile_id} config")
    agents_md, _ = read_regular_file(setup_root / "AGENTS.md", f"setup {setup_id}/AGENTS.md")
    desired: dict[Path, bytes] = {
        MIMOCODE_CONFIG_RELATIVE: canonical_json(merge_config(existing_config, config)),
        MIMOCODE_AGENTS_RELATIVE: agents_md,
    }
    desired.update(render_builder_files())
    desired[Path(STAMP_NAME)] = canonical_json(
        build_stamp(
            setup_id,
            profile_id,
            desired,
            profile_metadata["launch_args"],
            profile_metadata["launch_env"],
        )
    )
    return metadata, desired


def list_setups() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path in sorted(CATALOG_ROOT.iterdir()):
        if not path.is_dir() or path.is_symlink() or not (path / "setup.json").is_file():
            continue
        metadata = load_json_object(path / "setup.json", f"setup {path.name} metadata")
        validate_setup_metadata(metadata, path.name)
        result.append(
            {
                "id": metadata["id"],
                "description": metadata["description"],
                "builder_default_on": metadata["builder_default_on"],
            }
        )
    return result


def list_profiles() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path in sorted(PROFILE_ROOT.iterdir()):
        if not path.is_dir() or path.is_symlink() or not (path / "profile.json").is_file():
            continue
        metadata = load_json_object(path / "profile.json", f"profile {path.name} metadata")
        validate_profile_metadata(metadata, path.name)
        result.append(
            {
                "id": metadata["id"],
                "description": metadata["description"],
                "default": metadata["default"],
                "default_agent": metadata["default_agent"],
            }
        )
    return result


def backup_pool(target: Path) -> Path:
    return target / ".nddev-mimocode-backups"


def legacy_backup_pool(target: Path) -> Path:
    return target.parent / f".{target.name}.nddev-mimocode-backups"


def backup_pool_marker(pool: Path) -> Path:
    return pool / BACKUP_POOL_NAME


def lock_directory_path(target: Path) -> Path:
    return target / LOCK_DIRECTORY_NAME


def lock_path(target: Path) -> Path:
    return lock_directory_path(target) / LOCK_FILE_NAME


def bootstrap_lock_key(target: Path) -> str:
    return hashlib.sha256(f"{PRODUCT_NAME}\0{target}".encode("utf-8")).hexdigest()


def fixed_system_temp_root() -> Path:
    root = Path("/private/tmp") if sys.platform.startswith("darwin") else Path("/tmp")
    resolved = root.resolve()
    info = require_directory(resolved, "bootstrap system temp root")
    if not stat.S_IMODE(info.st_mode) & stat.S_ISVTX:
        fail("bootstrap system temp root must be sticky")
    return resolved


def bootstrap_lock_pool(_target: Path) -> Path:
    uid: int | str
    if hasattr(os, "geteuid"):
        uid = os.geteuid()
    elif hasattr(os, "getuid"):
        uid = os.getuid()
    else:
        uid = "unknown"
    return fixed_system_temp_root() / f".{PRODUCT_NAME}-{uid}-lifecycle-locks"


def bootstrap_global_lock_path() -> Path:
    return bootstrap_lock_pool(Path(".")) / BOOTSTRAP_GLOBAL_LOCK_NAME


def bootstrap_lock_path(target: Path) -> Path:
    canonical_target = canonical_target_for_bootstrap_lock(target)
    return bootstrap_lock_pool(canonical_target) / f"{bootstrap_lock_key(canonical_target)}{BOOTSTRAP_LOCK_SUFFIX}"


def require_safe_target_parent_for_creation(parent: Path) -> None:
    info = require_directory(parent, "target parent")
    if is_owner_private_directory(info):
        return
    if stat.S_IMODE(info.st_mode) & stat.S_ISVTX:
        return
    fail("target parent must be private to the current user or sticky")


def canonical_parent_for_creation(parent: Path) -> Path:
    try:
        canonical_parent = parent.resolve(strict=True)
    except FileNotFoundError:
        fail("target parent is missing")
    except OSError as exc:
        fail(f"cannot resolve target parent: {exc}")
    require_safe_target_parent_for_creation(canonical_parent)
    return canonical_parent


def canonical_target_for_bootstrap_lock(target: Path) -> Path:
    if not target.is_absolute():
        fail("--target must be an absolute path")
    if target.name in {"", ".", ".."}:
        fail("--target must include a literal target directory name")
    try:
        info = target.lstat()
    except FileNotFoundError:
        return canonical_parent_for_creation(target.parent) / target.name
    if stat.S_ISLNK(info.st_mode):
        fail("--target must not be a symlink")
    if not stat.S_ISDIR(info.st_mode):
        fail("--target must be a directory")
    if not is_owner_private_directory(info):
        fail("target must be owned by the current user with mode 0700")
    return target.resolve()


def ensure_bootstrap_lock_pool_state(canonical_target: Path) -> BootstrapPoolState:
    root = fixed_system_temp_root()
    parent_record = directory_metadata_record(root, "bootstrap lifecycle lock pool parent")
    pool = bootstrap_lock_pool(canonical_target)
    existed_before = True
    try:
        info = pool.lstat()
    except FileNotFoundError:
        existed_before = False
        try:
            pool.mkdir(mode=OWNER_DIRECTORY_MODE)
        except FileExistsError:
            existed_before = True
            info = pool.lstat()
        else:
            pool.chmod(OWNER_DIRECTORY_MODE)
            fsync_directory_with_retries(pool.parent, "bootstrap lifecycle lock pool parent after create")
            info = pool.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        fail("bootstrap lifecycle lock pool must be a real directory")
    if not is_owner_private_directory(info):
        fail("bootstrap lifecycle lock pool must be owned by the current user with mode 0700")
    return pool, existed_before, parent_record, directory_metadata_record(pool, "bootstrap lifecycle lock pool")


def ensure_bootstrap_lock_pool(canonical_target: Path) -> Path:
    pool, _existed_before, _parent_record, _pool_record = ensure_bootstrap_lock_pool_state(canonical_target)
    return pool


def restore_bootstrap_lock_pool_state(
    pool: Path,
    *,
    existed_before: bool,
    parent_record: DirectoryMetadataRecord,
    pool_record: DirectoryMetadataRecord,
    label: str,
) -> None:
    if existed_before:
        restore_directory_metadata_record(pool, pool_record, f"{label} bootstrap lock pool")
    else:
        cleanup_path_with_retries(pool, raise_on_failure=True)
        if path_present(pool):
            fail_concurrent(f"{label} left newly-created bootstrap lock pool")
    restore_directory_metadata_record(pool.parent, parent_record, f"{label} bootstrap lock pool parent")


def bootstrap_global_lock_binding() -> dict[str, Any]:
    return {"schema_version": 1, "product_name": PRODUCT_NAME, "anchor": "product"}


def validate_bootstrap_global_lock_binding(descriptor: int, path: Path) -> None:
    verify_locked_file_identity(descriptor, path, "bootstrap product lock file")
    desired = bootstrap_global_lock_binding()
    content = read_lock_file_descriptor(descriptor, label="bootstrap product lock file")
    if not content:
        fail("bootstrap product lock file is empty")
    binding = parse_json_object(content, "bootstrap product lock file")
    require_exact_keys(binding, BOOTSTRAP_GLOBAL_LOCK_KEYS, "bootstrap product lock file")
    if binding != desired:
        fail("bootstrap product lock file is bound to a different product")


def cleanup_bootstrap_anchor_publication_aliases(path: Path, opened: os.stat_result, label: str) -> None:
    if opened.st_nlink == 1:
        return
    for child in sorted(path.parent.iterdir(), key=lambda item: item.name):
        if child == path or ".nddev.tmp." not in child.name:
            continue
        with contextlib.suppress(FileNotFoundError):
            child_info = child.lstat()
            if identity_of(child_info) == identity_of(opened):
                unlink_file_durable(child)
    current = path.lstat()
    if current.st_nlink != 1:
        fail(f"{label} must not have hard-link aliases")


def open_bootstrap_anchor_lock_file(path: Path, label: str) -> int:
    flags = os.O_RDWR
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        raise
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            fail(f"{label} must not be a symlink")
        fail(f"cannot open {label} {path}: {exc}")
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            fail(f"{label} must be a regular file")
        if not is_owner_only_file(opened):
            fail(f"{label} must be owned by the current user with mode 0600")
        cleanup_bootstrap_anchor_publication_aliases(path, opened, label)
        current = require_lock_file(path, label)
        refreshed = os.fstat(descriptor)
        if identity_of(current) != identity_of(refreshed):
            fail_concurrent(f"{label} changed while it was being opened")
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def publish_bootstrap_anchor_no_replace(
    path: Path,
    content: bytes,
    *,
    label: str,
    parent_sync_label: str,
) -> int:
    temporary = staged_file_path(path)
    descriptor = -1
    linked = False
    acquired = False
    try:
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, OWNER_FILE_MODE)
        os.fchmod(descriptor, OWNER_FILE_MODE)
        write_all(descriptor, content)
        os.fsync(descriptor)
        acquire_file_lock(descriptor, temporary)
        acquired = True
        try:
            os.link(temporary, path)
        except FileExistsError:
            cleanup_path_with_retries(temporary, raise_on_failure=True)
            release_file_lock(descriptor)
            acquired = False
            os.close(descriptor)
            descriptor = open_bootstrap_anchor_lock_file(path, label)
            acquire_file_lock(descriptor, path)
            acquired = True
            result = descriptor
            descriptor = -1
            acquired = False
            return result
        else:
            linked = True
            cleanup_path_with_retries(temporary, raise_on_failure=True)
            fsync_directory_with_retries(path.parent, parent_sync_label)
            verify_locked_file_identity(descriptor, path, label)
            if read_lock_file_descriptor(descriptor, label=label) != content:
                fail_concurrent(f"{label} binding changed during publication")
            result = descriptor
            descriptor = -1
            acquired = False
            return result
    except BaseException:
        if not linked:
            cleanup_path_with_retries(temporary)
        raise
    finally:
        if descriptor >= 0 and acquired:
            release_file_lock(descriptor)
        if descriptor >= 0:
            os.close(descriptor)


def publish_bootstrap_global_lock_anchor(path: Path) -> None:
    descriptor = publish_bootstrap_anchor_no_replace(
        path,
        canonical_json(bootstrap_global_lock_binding()),
        label="bootstrap product lock file",
        parent_sync_label="bootstrap product lock pool after anchor publish",
    )
    try:
        validate_bootstrap_global_lock_binding(descriptor, path)
    finally:
        os.close(descriptor)


def ensure_bootstrap_global_lock_anchor(pool: Path) -> Path:
    path = pool / BOOTSTRAP_GLOBAL_LOCK_NAME
    if not path_present(path):
        publish_bootstrap_global_lock_anchor(path)
    descriptor = open_bootstrap_anchor_lock_file(path, "bootstrap product lock file")
    try:
        validate_bootstrap_global_lock_binding(descriptor, path)
    finally:
        os.close(descriptor)
    return path


@contextlib.contextmanager
def product_lifecycle_lock(path: Path, *, shared: bool = False) -> Iterator[None]:
    descriptor = open_bootstrap_anchor_lock_file(path, "bootstrap product lock file")
    acquired = False
    try:
        acquire_file_lock(descriptor, path, shared=shared)
        acquired = True
        validate_bootstrap_global_lock_binding(descriptor, path)
        yield
    finally:
        if acquired:
            release_file_lock(descriptor)
        os.close(descriptor)


def require_lock_file(path: Path, label: str) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError:
        fail(f"{label} is missing")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        fail(f"{label} must be a regular non-symlink file")
    if info.st_nlink != 1:
        fail(f"{label} must not have hard-link aliases")
    if not is_owner_only_file(info):
        fail(f"{label} must be owned by the current user with mode 0600")
    return info


def open_persistent_lock_file(path: Path, label: str, *, create: bool) -> int:
    flags = os.O_RDWR
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        if not create:
            raise
        try:
            descriptor = os.open(path, flags | os.O_CREAT | os.O_EXCL, OWNER_FILE_MODE)
        except FileExistsError:
            descriptor = os.open(path, flags)
        except OSError as exc:
            fail(f"cannot create {label} {path}: {exc}")
        os.fchmod(descriptor, OWNER_FILE_MODE)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            fail(f"{label} must not be a symlink")
        fail(f"cannot open {label} {path}: {exc}")
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            fail(f"{label} must be a regular file")
        if not is_owner_only_file(opened):
            fail(f"{label} must be owned by the current user with mode 0600")
        current = require_lock_file(path, label)
        if identity_of(current) != identity_of(opened):
            fail_concurrent(f"{label} changed while it was being opened")
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def read_lock_file_descriptor(descriptor: int, *, label: str) -> bytes:
    try:
        size = os.lseek(descriptor, 0, os.SEEK_END)
        if size > METADATA_MAX_BYTES:
            fail(f"{label} exceeds the metadata size limit")
        os.lseek(descriptor, 0, os.SEEK_SET)
        return os.read(descriptor, size)
    except OSError as exc:
        fail(f"cannot read {label}: {exc}")


def acquire_file_lock(descriptor: int, path: Path, *, shared: bool = False) -> None:
    if fcntl is None:
        fail("target lifecycle locks require POSIX fcntl.flock")
    operation = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
    try:
        fcntl.flock(descriptor, operation | fcntl.LOCK_NB)
    except BlockingIOError:
        fail(f"target is locked: {path}")
    except OSError as exc:
        if exc.errno in {errno.EACCES, errno.EAGAIN}:
            fail(f"target is locked: {path}")
        fail(f"cannot acquire target lock {path}: {exc}")


def release_file_lock(descriptor: int) -> None:
    if fcntl is not None:
        with contextlib.suppress(OSError):
            fcntl.flock(descriptor, fcntl.LOCK_UN)


def verify_locked_file_identity(descriptor: int, path: Path, label: str) -> None:
    opened = os.fstat(descriptor)
    current = require_lock_file(path, label)
    if identity_of(current) != identity_of(opened):
        fail_concurrent(f"{label} changed while locked")
    if not is_owner_only_file(opened):
        fail(f"{label} must be owned by the current user with mode 0600")


def bootstrap_lock_binding(canonical_target: Path, target_key: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "product_name": PRODUCT_NAME,
        "canonical_target": str(canonical_target),
        "target_key": target_key,
    }


def validate_bootstrap_lock_binding(descriptor: int, path: Path, canonical_target: Path, target_key: str) -> None:
    verify_locked_file_identity(descriptor, path, "bootstrap lifecycle lock file")
    desired = bootstrap_lock_binding(canonical_target, target_key)
    content = read_lock_file_descriptor(descriptor, label="bootstrap lifecycle lock file")
    if not content:
        fail("bootstrap lifecycle lock file is empty")
    binding = parse_json_object(content, "bootstrap lifecycle lock file")
    require_exact_keys(binding, BOOTSTRAP_LOCK_KEYS, "bootstrap lifecycle lock file")
    if binding != desired:
        fail("bootstrap lifecycle lock file is bound to a different canonical target")


def publish_new_bootstrap_lock_binding(path: Path, canonical_target: Path, target_key: str) -> int:
    desired = canonical_json(bootstrap_lock_binding(canonical_target, target_key))
    return publish_bootstrap_anchor_no_replace(
        path,
        desired,
        label="bootstrap lifecycle lock file",
        parent_sync_label="bootstrap lifecycle lock pool after binding publish",
    )


@contextlib.contextmanager
def bootstrap_lifecycle_lock(target: Path) -> Iterator[Path]:
    if not target.is_absolute():
        fail("--target must be an absolute path")
    pool: Path | None = None
    pool_existed = True
    parent_record: DirectoryMetadataRecord | None = None
    pool_record: DirectoryMetadataRecord | None = None
    descriptor = -1
    acquired = False
    path: Path | None = None
    canonical_target: Path | None = None
    marker_existed = False
    try:
        pool, pool_existed, parent_record, pool_record = ensure_bootstrap_lock_pool_state(Path("."))
        global_path = pool / BOOTSTRAP_GLOBAL_LOCK_NAME
        try:
            ensure_bootstrap_global_lock_anchor(pool)
        except BaseException:
            if not path_present(global_path) and parent_record is not None and pool_record is not None:
                restore_bootstrap_lock_pool_state(
                    pool,
                    existed_before=pool_existed,
                    parent_record=parent_record,
                    pool_record=pool_record,
                    label="bootstrap product anchor rollback",
                )
            raise
        pool_record = directory_metadata_record(pool, "bootstrap lifecycle lock pool after product anchor")
        with product_lifecycle_lock(global_path):
            try:
                canonical_target = canonical_target_for_bootstrap_lock(target)
                target_key = bootstrap_lock_key(canonical_target)
                path = pool / f"{target_key}{BOOTSTRAP_LOCK_SUFFIX}"
                marker_existed = path_present(path)
                if marker_existed:
                    descriptor = open_bootstrap_anchor_lock_file(path, "bootstrap lifecycle lock file")
                    acquire_file_lock(descriptor, path)
                    acquired = True
                    validate_bootstrap_lock_binding(descriptor, path, canonical_target, target_key)
                else:
                    descriptor = publish_new_bootstrap_lock_binding(path, canonical_target, target_key)
                    acquired = True
                    validate_bootstrap_lock_binding(descriptor, path, canonical_target, target_key)
            except BaseException:
                if pool is not None and parent_record is not None and pool_record is not None:
                    restore_directory_metadata_record(pool, pool_record, "bootstrap lifecycle rollback bootstrap lock pool")
                raise
        yield canonical_target
    except BaseException:
        raise
    finally:
        if acquired:
            release_file_lock(descriptor)
        if descriptor >= 0:
            os.close(descriptor)


@contextlib.contextmanager
def bootstrap_inspection_coordination(target: Path) -> Iterator[Path]:
    if not target.is_absolute():
        fail("--target must be an absolute path")
    descriptor = -1
    acquired = False
    try:
        global_path = bootstrap_global_lock_path()
        if not path_present(global_path):
            canonical_target = canonical_target_for_bootstrap_lock(target)
            yield canonical_target
            if path_present(global_path):
                raise RetryBootstrapInspection
            return
        with product_lifecycle_lock(global_path, shared=True):
            canonical_target = canonical_target_for_bootstrap_lock(target)
            target_key = bootstrap_lock_key(canonical_target)
            pool = bootstrap_lock_pool(canonical_target)
            require_private_directory(pool, "bootstrap lifecycle lock pool")
            path = pool / f"{target_key}{BOOTSTRAP_LOCK_SUFFIX}"
            try:
                descriptor = open_bootstrap_anchor_lock_file(path, "bootstrap lifecycle lock file")
            except FileNotFoundError:
                yield canonical_target
                return
            acquire_file_lock(descriptor, path, shared=True)
            acquired = True
            validate_bootstrap_lock_binding(descriptor, path, canonical_target, target_key)
        yield canonical_target
    finally:
        if acquired:
            release_file_lock(descriptor)
        if descriptor >= 0:
            os.close(descriptor)


def recover_protected_lock_directory_if_unlocked(target: Path, info: os.stat_result) -> None:
    lock_directory = lock_directory_path(target)
    if not is_owner_protected_directory(info):
        return
    if not path_present(lock_path(target)):
        lock_directory.chmod(OWNER_DIRECTORY_MODE)
        return
    try:
        descriptor = open_persistent_lock_file(lock_path(target), "target lock file", create=False)
    except FileNotFoundError:
        lock_directory.chmod(OWNER_DIRECTORY_MODE)
        return
    try:
        acquire_file_lock(descriptor, lock_path(target))
        lock_directory.chmod(OWNER_DIRECTORY_MODE)
    finally:
        release_file_lock(descriptor)
        os.close(descriptor)


def ensure_lock_directory(target: Path) -> Path:
    require_private_directory(target, "target lock parent")
    lock_directory = lock_directory_path(target)
    try:
        info = lock_directory.lstat()
    except FileNotFoundError:
        lock_directory.mkdir(mode=OWNER_DIRECTORY_MODE)
        lock_directory.chmod(OWNER_DIRECTORY_MODE)
        return lock_directory
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        fail("target lock directory must be a real directory")
    if is_owner_private_directory(info):
        return lock_directory
    recover_protected_lock_directory_if_unlocked(target, info)
    info = require_directory(lock_directory, "target lock directory")
    if is_owner_private_directory(info):
        return lock_directory
    fail("target lock directory must be owned by the current user with mode 0700")


@contextlib.contextmanager
def target_lock(target: Path) -> Iterator[None]:
    target_record = directory_metadata_record(target, "target lock parent")
    lock_directory = lock_directory_path(target)
    lock_directory_existed = path_present(lock_directory)
    lock_directory_record = (
        directory_metadata_record(lock_directory, "target lock directory pre-state") if lock_directory_existed else None
    )
    lock_file_record = file_object_record(
        lock_path(target),
        "target lock file pre-state",
        owner_only=True,
        max_bytes=METADATA_MAX_BYTES,
    )
    lock_directory = ensure_lock_directory(target)
    path = lock_path(target)
    descriptor = open_persistent_lock_file(path, "target lock file", create=True)
    acquired = False
    protected = False
    failed = False

    def restore_lock_graph_after_failure() -> None:
        if not path_present(target):
            return
        with contextlib.suppress(FileNotFoundError, OSError):
            current = lock_directory.lstat()
            if stat.S_ISDIR(current.st_mode) and not stat.S_ISLNK(current.st_mode):
                lock_directory.chmod(OWNER_DIRECTORY_MODE)
        if not lock_file_record.get("present"):
            if path_present(path):
                require_regular_file(path, "target lock rollback created file", owner_only=True, max_bytes=METADATA_MAX_BYTES)
                unlink_file_durable(path)
        elif not file_object_matches(
            path,
            lock_file_record,
            "target lock rollback pre-existing file",
            owner_only=True,
            max_bytes=METADATA_MAX_BYTES,
        ):
            fail_concurrent("target lock rollback did not preserve pre-existing lock file")
        if not lock_directory_existed:
            if path_present(lock_directory):
                cleanup_path_with_retries(lock_directory, raise_on_failure=True)
        elif lock_directory_record is not None:
            restore_directory_metadata_record(lock_directory, lock_directory_record, "target lock rollback directory")
        restore_directory_metadata_record(target, target_record, "target lock rollback parent")

    try:
        acquire_file_lock(descriptor, path)
        acquired = True
        lock_directory.chmod(PROTECTED_DIRECTORY_MODE)
        protected = True
        try:
            yield
        except BaseException:
            failed = True
            raise
    finally:
        if protected:
            with contextlib.suppress(FileNotFoundError, OSError):
                current = lock_directory.lstat()
                if stat.S_ISDIR(current.st_mode) and not stat.S_ISLNK(current.st_mode):
                    lock_directory.chmod(OWNER_DIRECTORY_MODE)
        if failed:
            restore_lock_graph_after_failure()
        if acquired:
            release_file_lock(descriptor)
        os.close(descriptor)


@contextlib.contextmanager
def locked_new_or_existing_target(target: Path) -> Iterator[Path]:
    with locked_new_or_existing_target_state(target) as (canonical_target, _existed_before, _parent_record):
        yield canonical_target


@contextlib.contextmanager
def locked_new_or_existing_target_state(target: Path) -> Iterator[tuple[Path, bool, DirectoryMetadataRecord]]:
    with bootstrap_lifecycle_lock(target) as locked_target:
        existed_before = path_present(locked_target)
        parent_record = directory_metadata_record(locked_target.parent, "target parent")
        try:
            canonical_target = ensure_target_directory(locked_target)
        except BaseException:
            rollback_created_target_if_absent(locked_target, existed_before, parent_record, "target creation rollback")
            raise
        if canonical_target != locked_target:
            fail_concurrent("target canonical path changed during lifecycle lock acquisition")
        with target_lock(canonical_target):
            yield canonical_target, existed_before, parent_record


@contextlib.contextmanager
def locked_existing_target(target: Path) -> Iterator[Path]:
    with bootstrap_lifecycle_lock(target) as canonical_target:
        require_private_directory(canonical_target, "target")
        with target_lock(canonical_target):
            yield canonical_target


@contextlib.contextmanager
def locked_inspection_target(target: Path) -> Iterator[Path]:
    with bootstrap_inspection_coordination(target) as canonical_target:
        if path_present(canonical_target):
            require_private_directory(canonical_target, "target")
            yield canonical_target
        else:
            yield canonical_target


def run_locked_inspection(target: Path, operation: Any) -> Any:
    for _attempt in range(3):
        try:
            with locked_inspection_target(target) as canonical_target:
                return operation(canonical_target)
        except RetryBootstrapInspection:
            continue
    fail_concurrent("bootstrap product anchor changed during read-only inspection")


def require_absolute_target_argument(raw_target: str | None) -> Path:
    if not raw_target:
        fail("an explicit --target absolute path is required")
    target = Path(raw_target)
    if not target.is_absolute():
        fail("--target must be an absolute path")
    return target


def require_explicit_absolute_target(raw_target: str | None) -> Path:
    target = require_absolute_target_argument(raw_target)
    try:
        info = target.lstat()
    except FileNotFoundError:
        return target
    if stat.S_ISLNK(info.st_mode):
        fail("--target must not be a symlink")
    if not stat.S_ISDIR(info.st_mode):
        fail("--target must be a directory")
    if not is_owner_private_directory(info):
        fail("target must be owned by the current user with mode 0700")
    return target.resolve()


def ensure_target_directory(target: Path) -> Path:
    try:
        info = target.lstat()
    except FileNotFoundError:
        require_safe_target_parent_for_creation(target.parent)
        target.mkdir(mode=OWNER_DIRECTORY_MODE)
        target.chmod(OWNER_DIRECTORY_MODE)
        created = target.resolve()
        require_private_directory(created, "target")
        return created
    if stat.S_ISLNK(info.st_mode):
        fail("target must not be a symlink")
    if not stat.S_ISDIR(info.st_mode):
        fail("target must be a directory")
    if not is_owner_private_directory(info):
        fail("target must be owned by the current user with mode 0700")
    return target.resolve()


def ensure_private_directory_under_target(target: Path, relative: Path, label: str) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        fail(f"unsafe {label}: {relative}")
    current = target
    for part in relative.parts:
        current = current / part
        if path_present(current):
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                fail(f"{label} {current.relative_to(target)} must be a real directory")
            if not is_owner_private_directory(info):
                fail(f"{label} {current.relative_to(target)} must be owned by the current user with mode 0700")
        else:
            current.mkdir(mode=OWNER_DIRECTORY_MODE)
            current.chmod(OWNER_DIRECTORY_MODE)
            require_private_directory(current, f"{label} {current.relative_to(target)}")
    return current


def ensure_private_parent(target: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        fail(f"unsafe managed path: {relative}")
    ensure_private_directory_under_target(target, relative.parent, "managed parent")
    return target / relative


def any_managed_path_exists(target: Path) -> bool:
    return any(path_present(target / relative) for relative in ALL_MANAGED_PATHS)


def load_stamp(target: Path) -> dict[str, Any] | None:
    stamp = target / STAMP_NAME
    if not path_present(stamp):
        return None
    value = load_json_object(stamp, "setup stamp", owner_only=True)
    actual_keys = set(value)
    if actual_keys == STAMP_KEYS:
        if value["schema_version"] != 1 or value["product_name"] != PRODUCT_NAME:
            fail("setup stamp schema or product identity is not compatible with this manager")
        if not isinstance(value["build_version"], str):
            fail("setup stamp build_version must be a string")
        validate_setup_id(value["profile_id"])
        if not isinstance(value["launch_env"], dict):
            fail("setup stamp launch_env must be an object")
        value["legacy"] = False
        value["needs_update"] = value["build_version"] != VERSION
    elif actual_keys == LEGACY_STAMP_KEYS:
        if (
            value["schema_version"] != 1
            or value["product_name"] != PRODUCT_NAME
            or value["build_version"] not in LEGACY_BUILD_VERSIONS
        ):
            fail("legacy setup stamp is not compatible with this manager")
        value["profile_id"] = None
        value["launch_env"] = {}
        value["legacy"] = True
        value["needs_update"] = True
    else:
        fail(
            "setup stamp has invalid keys "
            f"(missing={sorted(STAMP_KEYS - actual_keys)}, extra={sorted(actual_keys - STAMP_KEYS)})"
        )
    if value["canonical_target"] != str(target):
        fail("setup stamp is bound to a different canonical target")
    if not isinstance(value["managed_files"], dict):
        fail("setup stamp managed_files must be an object")
    validate_setup_id(value["setup_id"])
    return value


def validate_managed_files(target: Path, stamp: dict[str, Any]) -> list[str]:
    expected = stamp["managed_files"]
    known = ALL_MANAGED_PATHS if stamp.get("legacy") else MANAGED_PATHS
    ordered = [relative for relative in known if str(relative) in expected]
    ordered.extend(Path(raw) for raw in sorted(set(expected) - {str(item) for item in ordered}))
    drift: list[str] = []
    for relative in ordered:
        if relative.is_absolute() or ".." in relative.parts:
            fail("setup stamp contains an unsafe managed path")
        content, _ = read_regular_file(target / relative, f"managed file {relative}", owner_only=True)
        digest = legacy_managed_digest(relative, content) if stamp.get("legacy") else managed_digest(relative, content)
        if digest != expected[str(relative)]:
            drift.append(str(relative))
    if drift:
        fail(f"managed target drift detected: {', '.join(sorted(drift))}")
    return sorted(expected)


def inspect_target(target: Path) -> dict[str, Any]:
    if not path_present(target):
        return {"state": "missing", "target": str(target)}
    require_private_directory(target, "target")
    stamp = load_stamp(target)
    if stamp is None:
        if any_managed_path_exists(target):
            fail("unmanaged target contains nddev-managed paths")
        return {"state": "unmanaged", "target": str(target)}
    state_name = "legacy-managed" if stamp.get("legacy") else "managed"
    result = {
        "state": state_name,
        "target": str(target),
        "setup_id": stamp["setup_id"],
        "profile_id": stamp["profile_id"],
        "build_version": stamp["build_version"],
        "managed_files": validate_managed_files(target, stamp),
        "builder_projection": stamp["builder_projection"],
        "launch_args": stamp["launch_args"],
        "launch_env": stamp["launch_env"],
        "needs_update": stamp["needs_update"],
    }
    if stamp.get("legacy"):
        result["launch_supported"] = False
        result["migration_required"] = True
    return result


def read_existing_config_if_managed(target: Path, state: dict[str, Any]) -> dict[str, Any] | None:
    if state.get("state") != "managed":
        return None
    return load_json_object(target / MIMOCODE_CONFIG_RELATIVE, f"existing {MIMOCODE_CONFIG_RELATIVE}", owner_only=True)


def preserved_legacy_config_for_migration(target: Path, state: dict[str, Any]) -> dict[str, Any]:
    if state.get("state") != "legacy-managed":
        fail("legacy config preservation requires a legacy managed target")
    config = load_json_object(target / Path("config") / "mimocode.json", "legacy config/mimocode.json", owner_only=True)
    return {key: value for key, value in config.items() if key not in LEGACY_MANAGED_CONFIG_KEYS}


def current_managed_snapshot(target: Path, paths: tuple[Path, ...] = ALL_MANAGED_PATHS) -> dict[Path, bytes | None]:
    snapshot: dict[Path, bytes | None] = {}
    for relative in paths:
        path = target / relative
        if path_present(path):
            content, _ = read_regular_file(path, f"managed file {relative}", owner_only=True)
            snapshot[relative] = content
        else:
            snapshot[relative] = None
    return snapshot


def managed_owner_only(_relative: Path) -> bool:
    return True


def managed_max_bytes(_relative: Path) -> int:
    return MANAGED_PAYLOAD_MAX_BYTES


def current_managed_object_snapshot(target: Path, paths: tuple[Path, ...] = ALL_MANAGED_PATHS) -> FileObjectSnapshot:
    return {
        relative: file_object_record(
            target / relative,
            f"managed file {relative}",
            owner_only=True,
            max_bytes=MANAGED_PAYLOAD_MAX_BYTES,
        )
        for relative in paths
    }


def managed_payload_snapshot(snapshot: FileObjectSnapshot) -> dict[Path, bytes | None]:
    return {
        relative: (record["content"] if record.get("present") else None)
        for relative, record in snapshot.items()
    }


def prune_empty_managed_dirs(target: Path, paths: tuple[Path, ...] = ALL_MANAGED_PATHS) -> None:
    candidates = sorted(
        {(target / relative).parent for relative in paths},
        key=lambda item: len(item.parts),
        reverse=True,
    )
    protected = {target, lock_directory_path(target), backup_pool(target)}
    for directory in candidates:
        while directory not in protected and directory != target and directory.is_dir() and not directory.is_symlink():
            try:
                rmdir_if_empty_durable(directory)
            except OSError:
                break
            directory = directory.parent


def managed_write_order(state: dict[Path, bytes | None]) -> list[Path]:
    writes = sorted(relative for relative, content in state.items() if content is not None and relative != Path(STAMP_NAME))
    stamp = [Path(STAMP_NAME)] if state.get(Path(STAMP_NAME)) is not None else []
    removals = sorted((relative for relative, content in state.items() if content is None), key=lambda item: (len(item.parts), str(item)), reverse=True)
    return [*writes, *stamp, *removals]


def verify_managed_state(target: Path, desired: dict[Path, bytes | None], label: str) -> None:
    for relative, content in desired.items():
        path = target / relative
        if content is None:
            if path_present(path):
                fail_concurrent(f"{label} left unexpected managed file: {relative}")
            continue
        actual, info = read_regular_file(path, f"{label} managed file {relative}", owner_only=True)
        if actual != content or stat.S_IMODE(info.st_mode) != OWNER_FILE_MODE:
            fail_concurrent(f"{label} managed file mismatch: {relative}")


def apply_managed_state(
    target: Path,
    desired: dict[Path, bytes | None],
    *,
    expected_before: dict[Path, bytes | None] | None = None,
    rollback_on_error: bool,
    label: str,
    cleanup_on_success: bool = True,
) -> FileUndoTransaction:
    paths = tuple(desired)
    before_objects = current_managed_object_snapshot(target, paths)
    before = managed_payload_snapshot(before_objects)
    if expected_before is not None and before != {relative: expected_before.get(relative) for relative in paths}:
        fail_concurrent(f"{label} pre-state changed before mutation")
    undo = FileUndoTransaction(
        target,
        before_objects,
        label=label,
        owner_only_for=managed_owner_only,
        max_bytes_for=managed_max_bytes,
    )
    staged: dict[Path, Path] = {}

    def cleanup_staged() -> None:
        for temporary in staged.values():
            cleanup_path_with_retries(temporary)
        staged.clear()

    try:
        for relative, content in desired.items():
            if content is not None:
                ensure_private_parent(target, relative)
                staged[relative] = create_staged_file(target / relative, content, OWNER_FILE_MODE)
        for relative in managed_write_order(desired):
            path = target / relative
            content = desired[relative]
            if content is None:
                if path_present(path):
                    require_regular_file(path, f"{label} managed file {relative}", owner_only=True)
                    undo.hold(relative, path)
                continue
            temporary = staged[relative]
            undo.hold(relative, path)
            commit_staged_file(temporary, path)
            del staged[relative]
        verify_managed_state(target, desired, label)
        if cleanup_on_success:
            undo.commit_cleanup()
    except BaseException:
        cleanup_staged()
        if rollback_on_error:
            undo.rollback()
        raise
    finally:
        cleanup_staged()
    with contextlib.suppress(OSError):
        prune_empty_managed_dirs(target, tuple(desired))
    return undo


def restore_managed_snapshot_with_retries(target: Path, snapshot: FileObjectSnapshot | dict[Path, bytes | None], *, label: str) -> None:
    last: BaseException | None = None
    if all(isinstance(record, dict) for record in snapshot.values()):
        object_snapshot = snapshot  # type: ignore[assignment]
        for _attempt in range(3):
            try:
                verify_file_object_snapshot(
                    target,
                    object_snapshot,
                    label,
                    owner_only_for=managed_owner_only,
                    max_bytes_for=managed_max_bytes,
                )
                cleanup_transaction_residue(target)
                return
            except BaseException as exc:
                last = exc
                cleanup_transaction_residue(target)
        if last is not None:
            raise last
        return
    desired = snapshot  # type: ignore[assignment]
    for attempt in range(3):
        try:
            apply_managed_state(
                target,
                desired,
                rollback_on_error=False,
                label=f"{label} attempt {attempt + 1}",
            )
            verify_managed_state(target, desired, label)
            cleanup_transaction_residue(target)
            return
        except BaseException as exc:
            last = exc
            cleanup_transaction_residue(target)
    if last is not None:
        raise last


def restore_snapshot(target: Path, snapshot: FileObjectSnapshot | dict[Path, bytes | None]) -> None:
    restore_managed_snapshot_with_retries(target, snapshot, label="rollback restore")


def replace_managed_state(
    target: Path,
    desired: dict[Path, bytes | None],
    *,
    expected_before: dict[Path, bytes | None] | None = None,
    cleanup_on_success: bool = True,
) -> FileUndoTransaction:
    return apply_managed_state(
        target,
        desired,
        expected_before=expected_before,
        rollback_on_error=True,
        label="managed replace",
        cleanup_on_success=cleanup_on_success,
    )


def changed_paths(target: Path, desired: dict[Path, bytes | None]) -> list[str]:
    changed: list[str] = []
    for relative, content in desired.items():
        path = target / relative
        if content is None:
            if path_present(path):
                changed.append(str(relative))
            continue
        if not path_present(path):
            changed.append(str(relative))
            continue
        actual, _ = read_regular_file(path, f"managed file {relative}", owner_only=True)
        if actual != content:
            changed.append(str(relative))
    return sorted(changed)


def validate_backup_pool_marker(target: Path, pool: Path) -> None:
    marker = load_json_object(backup_pool_marker(pool), "backup pool marker", owner_only=True)
    require_exact_keys(marker, BACKUP_POOL_KEYS, "backup pool marker")
    if marker["schema_version"] != 1 or marker["product_name"] != PRODUCT_NAME:
        fail("backup pool marker schema or product identity is not compatible with this manager")
    if marker["canonical_target"] != str(target):
        fail("backup pool is bound to a different canonical target")


def write_backup_pool_marker(target: Path, pool: Path) -> None:
    marker = {
        "schema_version": 1,
        "product_name": PRODUCT_NAME,
        "build_version": VERSION,
        "canonical_target": str(target),
    }
    write_durable_file(backup_pool_marker(pool), canonical_json(marker), OWNER_FILE_MODE)


def backup_file_record(relative: Path, content: bytes) -> dict[str, Any]:
    return {"path": str(relative), "size": len(content), "sha256": sha256_bytes(content)}


def backup_file_records(files: dict[Path, bytes]) -> list[dict[str, Any]]:
    return [backup_file_record(relative, files[relative]) for relative in sorted(files)]


def directory_tree_snapshot(path: Path) -> dict[str, tuple[str, int, str | None]]:
    if not path_present(path):
        return {}
    info = require_directory(path, str(path))
    result: dict[str, tuple[str, int, str | None]] = {".": ("dir", stat.S_IMODE(info.st_mode), None)}
    for item in sorted(path.rglob("*"), key=lambda entry: str(entry.relative_to(path))):
        relative = str(item.relative_to(path))
        item_info = item.lstat()
        mode = stat.S_IMODE(item_info.st_mode)
        if stat.S_ISDIR(item_info.st_mode):
            result[relative] = ("dir", mode, None)
        elif stat.S_ISREG(item_info.st_mode):
            content, _ = read_regular_file(item, f"tree file {item}", max_bytes=MANAGED_PAYLOAD_MAX_BYTES)
            result[relative] = ("file", mode, sha256_bytes(content))
        else:
            fail(f"tree contains unsupported path type: {item}")
    return result


def backup_pool_snapshot(target: Path) -> dict[str, tuple[str, int, str | None]]:
    return directory_tree_snapshot(backup_pool(target))


def copy_tree_durable(source: Path, destination: Path) -> None:
    if path_present(destination):
        fail(f"copy destination already exists: {destination}")
    source_info = require_directory(source, "copy source")
    destination.mkdir(mode=stat.S_IMODE(source_info.st_mode))
    destination.chmod(stat.S_IMODE(source_info.st_mode))
    for item in sorted(source.rglob("*"), key=lambda entry: str(entry.relative_to(source))):
        relative = item.relative_to(source)
        item_info = item.lstat()
        target_path = destination / relative
        if stat.S_ISDIR(item_info.st_mode):
            target_path.mkdir(mode=stat.S_IMODE(item_info.st_mode), exist_ok=True)
            target_path.chmod(stat.S_IMODE(item_info.st_mode))
        elif stat.S_ISREG(item_info.st_mode):
            target_path.parent.mkdir(mode=OWNER_DIRECTORY_MODE, parents=True, exist_ok=True)
            target_path.parent.chmod(OWNER_DIRECTORY_MODE)
            content, _ = read_regular_file(item, f"copy source file {relative}", max_bytes=MANAGED_PAYLOAD_MAX_BYTES)
            write_durable_file(target_path, content, stat.S_IMODE(item_info.st_mode))
        else:
            fail(f"copy source contains unsupported path type: {relative}")
    fsync_directory(destination, f"copied tree {destination.name}")
    fsync_directory(destination.parent, f"parent directory after copy {destination.name}")


def write_backup_file(slot_dir: Path, relative: Path, content: bytes) -> None:
    destination = slot_dir / relative
    ensure_private_directory_under_target(slot_dir, relative.parent, "backup parent")
    write_durable_file(destination, content, OWNER_FILE_MODE)


def write_backup_envelope(slot_dir: Path, envelope: dict[str, Any]) -> None:
    write_durable_file(slot_dir / BACKUP_NAME, canonical_json(envelope), OWNER_FILE_MODE)


def copy_backup_slot(source: Path, destination: Path, target: Path, source_slot: int, new_slot: int) -> None:
    envelope, files = load_backup_slot(target, source, source_slot)
    destination.mkdir(mode=OWNER_DIRECTORY_MODE)
    destination.chmod(OWNER_DIRECTORY_MODE)
    for relative, content in files.items():
        write_backup_file(destination, relative, content)
    envelope["slot"] = new_slot
    envelope["file_records"] = backup_file_records(files)
    write_backup_envelope(destination, envelope)


def restore_backup_pool_from_source(
    target: Path,
    source: Path | None,
    expected_snapshot: dict[str, tuple[str, int, str | None]],
) -> None:
    pool = backup_pool(target)
    last: BaseException | None = None
    for _attempt in range(3):
        try:
            if backup_pool_snapshot(target) == expected_snapshot:
                fsync_directory_with_retries(target, "target directory after backup pool restore")
                return
            if path_present(pool):
                cleanup_path_with_retries(pool, raise_on_failure=True)
            if source is not None and path_present(source):
                os.replace(source, pool)
                fsync_directory_with_retries(target, "target directory after backup pool restore")
            if backup_pool_snapshot(target) != expected_snapshot:
                fail_concurrent("backup pool rollback did not restore exact pre-state")
            return
        except BaseException as exc:
            last = exc
    if last is not None:
        raise last


def publish_backup_pool(
    target: Path,
    staged_pool: Path,
    expected_before: dict[str, tuple[str, int, str | None]],
) -> None:
    pool = backup_pool(target)
    actual_before = backup_pool_snapshot(target)
    if actual_before != expected_before:
        fail_concurrent("backup pool pre-state changed before publication")
    desired_snapshot = directory_tree_snapshot(staged_pool)
    recovery_pool = target / f".{pool.name}.recovery.{os.getpid()}.{time.time_ns()}"
    retired_pool = target / f".{pool.name}.retired.{os.getpid()}.{time.time_ns()}"
    pool_was_present = path_present(pool)
    moved_old = False
    installed_new = False
    try:
        if pool_was_present:
            copy_tree_durable(pool, recovery_pool)
            os.replace(pool, retired_pool)
            moved_old = True
            fsync_directory(target, "target directory after backup pool staging")
        os.replace(staged_pool, pool)
        installed_new = True
        fsync_directory(target, "target directory after backup pool replace")
        if backup_pool_snapshot(target) != desired_snapshot:
            fail_concurrent("backup pool publication did not produce exact desired state")
        cleanup_path_with_retries(retired_pool, raise_on_failure=True)
        cleanup_path_with_retries(recovery_pool, raise_on_failure=True)
    except BaseException:
        if installed_new and path_present(pool):
            cleanup_path_with_retries(pool, raise_on_failure=True)
        restore_source = retired_pool if path_present(retired_pool) else recovery_pool if path_present(recovery_pool) else None
        restore_backup_pool_from_source(target, restore_source, expected_before)
        cleanup_path_with_retries(staged_pool, raise_on_failure=True)
        cleanup_path_with_retries(retired_pool, raise_on_failure=True)
        cleanup_path_with_retries(recovery_pool, raise_on_failure=True)
        fsync_directory_with_retries(target, "target directory after backup pool rollback")
        raise


def stage_backup_pool(target: Path, state: dict[str, Any]) -> Path:
    pool = backup_pool(target)
    if path_present(pool):
        require_private_directory(pool, "backup pool")
        validate_backup_pool_marker(target, pool)
    staged_pool = target / f".{pool.name}.stage.{os.getpid()}.{time.time_ns()}"
    staged_pool.mkdir(mode=OWNER_DIRECTORY_MODE)
    try:
        staged_pool.chmod(OWNER_DIRECTORY_MODE)
        write_backup_pool_marker(target, staged_pool)
        if path_present(pool):
            for slot in range(8, -1, -1):
                source = pool / str(slot)
                if path_present(source):
                    require_private_directory(source, f"backup slot {slot}")
                    copy_backup_slot(source, staged_pool / str(slot + 1), target, slot, slot + 1)
        slot_dir = staged_pool / "0"
        slot_dir.mkdir(mode=OWNER_DIRECTORY_MODE)
        slot_dir.chmod(OWNER_DIRECTORY_MODE)
        files: dict[Path, bytes] = {}
        managed_files = list(state["managed_files"])
        for raw_relative in [*managed_files, STAMP_NAME]:
            relative = Path(raw_relative)
            content, _ = read_regular_file(target / relative, f"managed file {relative}", owner_only=True)
            files[relative] = content
            write_backup_file(slot_dir, relative, content)
        envelope = {
            "schema_version": 1,
            "product_name": PRODUCT_NAME,
            "build_version": VERSION,
            "slot": 0,
            "canonical_target": str(target),
            "source_setup_id": state["setup_id"],
            "source_profile_id": state.get("profile_id"),
            "managed_files": managed_files,
            "file_records": backup_file_records(files),
            "created_at": int(time.time()),
        }
        write_backup_envelope(slot_dir, envelope)
        return staged_pool
    except BaseException:
        cleanup_path_with_retries(staged_pool)
        raise


def prepare_backup_transaction(
    target: Path,
    state: dict[str, Any],
) -> tuple[dict[str, tuple[str, int, str | None]], Path | None, Path]:
    before = backup_pool_snapshot(target)
    recovery: Path | None = None
    pool = backup_pool(target)
    try:
        if path_present(pool):
            recovery = target / f".{pool.name}.lifecycle.recovery.{os.getpid()}.{time.time_ns()}"
            copy_tree_durable(pool, recovery)
        staged = stage_backup_pool(target, state)
        return before, recovery, staged
    except BaseException:
        if recovery is not None:
            cleanup_path_with_retries(recovery, raise_on_failure=True)
        raise


def rollback_backup_transaction(
    target: Path,
    before: dict[str, tuple[str, int, str | None]],
    recovery: Path | None,
    staged: Path | None,
) -> None:
    if staged is not None:
        cleanup_path_with_retries(staged, raise_on_failure=True)
    if backup_pool_snapshot(target) != before:
        restore_backup_pool_from_source(target, recovery if recovery is not None and path_present(recovery) else None, before)
    if recovery is not None:
        cleanup_path_with_retries(recovery, raise_on_failure=True)


def finish_backup_transaction(
    target: Path,
    before: dict[str, tuple[str, int, str | None]],
    recovery: Path | None,
    staged: Path,
) -> int:
    publish_backup_pool(target, staged, before)
    if recovery is not None:
        cleanup_path_with_retries(recovery, raise_on_failure=True)
    return 0


def find_backup_slot(target: Path, slot: int) -> Path:
    if slot < 0 or slot > 9:
        fail("--backup must be between 0 and 9")
    pool = backup_pool(target)
    if path_present(pool):
        require_private_directory(pool, "backup pool")
        validate_backup_pool_marker(target, pool)
        return pool / str(slot)
    legacy_pool = legacy_backup_pool(target)
    if path_present(legacy_pool):
        require_private_directory(legacy_pool, "legacy backup pool")
        return legacy_pool / str(slot)
    fail("backup pool is missing")


def load_backup_slot(target: Path, slot_dir: Path, slot: int) -> tuple[dict[str, Any], dict[Path, bytes]]:
    require_private_directory(slot_dir, f"backup slot {slot}")
    envelope = load_json_object(slot_dir / BACKUP_NAME, "backup envelope", owner_only=True)
    require_exact_keys(envelope, BACKUP_KEYS, "backup envelope")
    if envelope["schema_version"] != 1 or envelope["product_name"] != PRODUCT_NAME:
        fail("backup envelope schema or product identity is not compatible with this manager")
    if envelope["slot"] != slot:
        fail("backup envelope slot identity mismatch")
    if envelope["canonical_target"] != str(target):
        fail("backup belongs to a different canonical target")
    managed_files = envelope["managed_files"]
    if not isinstance(managed_files, list) or not all(isinstance(item, str) for item in managed_files):
        fail("backup envelope managed_files must be a string list")
    expected_paths = [Path(raw) for raw in [*managed_files, STAMP_NAME]]
    if len({str(path) for path in expected_paths}) != len(expected_paths):
        fail("backup envelope contains duplicate managed paths")
    records = envelope["file_records"]
    if not isinstance(records, list):
        fail("backup envelope file_records must be a list")
    record_map: dict[Path, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            fail("backup envelope file record must be an object")
        require_exact_keys(record, {"path", "size", "sha256"}, "backup envelope file record")
        if not isinstance(record["path"], str) or not isinstance(record["size"], int) or not isinstance(record["sha256"], str):
            fail("backup envelope file record has invalid value types")
        if re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is None:
            fail("backup envelope file record sha256 is invalid")
        relative = Path(record["path"])
        if relative in record_map:
            fail("backup envelope contains duplicate file records")
        record_map[relative] = record
    if sorted(str(path) for path in record_map) != sorted(str(path) for path in expected_paths):
        fail("backup envelope file records do not match managed_files")
    files: dict[Path, bytes] = {}
    for relative in expected_paths:
        if relative.is_absolute() or ".." in relative.parts:
            fail("backup envelope contains an unsafe managed path")
        if relative not in ALL_MANAGED_PATHS:
            fail(f"backup envelope contains an unsupported managed path: {relative}")
        content, _ = read_regular_file(slot_dir / relative, f"backup file {relative}", owner_only=True)
        record = record_map[relative]
        if record["size"] != len(content) or record["sha256"] != sha256_bytes(content):
            fail(f"backup file record mismatch: {relative}")
        files[relative] = content
    expected_regular = {Path(BACKUP_NAME), *expected_paths}
    expected_directories = {Path(".")}
    for expected in expected_regular:
        parent = expected.parent
        while parent != Path("."):
            expected_directories.add(parent)
            parent = parent.parent
    for path in sorted(slot_dir.rglob("*"), key=lambda item: str(item.relative_to(slot_dir))):
        info = path.lstat()
        relative = path.relative_to(slot_dir)
        if stat.S_ISDIR(info.st_mode):
            if relative not in expected_directories:
                fail(f"backup slot contains unrecorded directory: {relative}")
            if not is_owner_private_directory(info):
                fail(f"backup slot directory must be owned by the current user with mode 0700: {relative}")
            continue
        if relative not in expected_regular:
            fail(f"backup slot contains unrecorded payload: {relative}")
        if not stat.S_ISREG(info.st_mode):
            fail(f"backup slot contains unsupported payload type: {relative}")
    return envelope, files


def load_backup(target: Path, slot: int) -> tuple[dict[str, Any], dict[Path, bytes]]:
    slot_dir = find_backup_slot(target, slot)
    return load_backup_slot(target, slot_dir, slot)


def restore_desired_from_backup(files: dict[Path, bytes]) -> dict[Path, bytes | None]:
    desired: dict[Path, bytes | None] = {relative: None for relative in ALL_MANAGED_PATHS}
    for relative, content in files.items():
        if relative.is_absolute() or ".." in relative.parts:
            fail("backup contains an unsafe managed path")
        if relative not in ALL_MANAGED_PATHS:
            fail(f"backup contains an unsupported managed path: {relative}")
        desired[relative] = content
    return desired


def mutate_setup(target: Path, setup_id: str, profile_id: str, operation: str) -> dict[str, Any]:
    with locked_new_or_existing_target_state(target) as (canonical_target, target_existed_before, target_parent_record):
        managed_undo: FileUndoTransaction | None = None
        backup_before: dict[str, tuple[str, int, str | None]] | None = None
        backup_recovery: Path | None = None
        staged_backup: Path | None = None
        try:
            state = inspect_target(canonical_target)
            if state["state"] == "legacy-managed":
                fail("legacy managed target must be migrated before install, update, or switch")
            existing_config = read_existing_config_if_managed(canonical_target, state)
            metadata, desired = render_setup(setup_id, profile_id, existing_config=existing_config)
            stamp = bind_stamp(parse_json_object(desired[Path(STAMP_NAME)], "desired stamp"), canonical_target)
            desired[Path(STAMP_NAME)] = canonical_json(stamp)
            changed = changed_paths(canonical_target, desired)
            backup_slot: int | None = None
            lifecycle_directories = directory_object_snapshot(canonical_target)
            snapshot = current_managed_object_snapshot(canonical_target)
            snapshot_payload = managed_payload_snapshot(snapshot)
            if state["state"] == "managed" and changed:
                backup_before, backup_recovery, staged_backup = prepare_backup_transaction(canonical_target, state)
            if changed:
                managed_undo = replace_managed_state(
                    canonical_target,
                    desired,
                    expected_before=snapshot_payload,
                    cleanup_on_success=False,
                )
            post = inspect_target(canonical_target)
            if changed:
                verify_managed_state(canonical_target, desired, "managed postcondition")
            if staged_backup is not None and backup_before is not None:
                backup_slot = finish_backup_transaction(canonical_target, backup_before, backup_recovery, staged_backup)
                staged_backup = None
                backup_recovery = None
            if managed_undo is not None:
                managed_undo.commit_cleanup()
        except BaseException:
            if managed_undo is not None:
                managed_undo.rollback()
            else:
                if "snapshot" in locals():
                    restore_snapshot(canonical_target, snapshot)
            if backup_before is not None:
                rollback_backup_transaction(canonical_target, backup_before, backup_recovery, staged_backup)
            if target_existed_before and "lifecycle_directories" in locals():
                restore_directory_object_snapshot(canonical_target, lifecycle_directories, "lifecycle rollback")
            else:
                rollback_created_target_if_absent(
                    canonical_target,
                    target_existed_before,
                    target_parent_record,
                    "lifecycle rollback",
                )
            raise
    return {
        "ok": True,
        "operation": operation,
        "setup_id": setup_id,
        "profile_id": profile_id,
        "description": metadata["description"],
        "target": str(canonical_target),
        "changed": changed,
        "backup_slot": backup_slot,
        "state": post["state"],
    }


def update_setup(target: Path) -> dict[str, Any]:
    with locked_existing_target(target) as canonical_target:
        state = inspect_target(canonical_target)
        if state["state"] == "legacy-managed":
            fail("legacy managed target must be migrated before update")
        if state["state"] != "managed":
            fail("update requires an existing managed target")
        profile_id = state.get("profile_id")
        if not isinstance(profile_id, str):
            fail("managed target is missing a profile_id")
        existing_config = read_existing_config_if_managed(canonical_target, state)
        metadata, desired = render_setup(state["setup_id"], profile_id, existing_config=existing_config)
        stamp = bind_stamp(parse_json_object(desired[Path(STAMP_NAME)], "desired stamp"), canonical_target)
        desired[Path(STAMP_NAME)] = canonical_json(stamp)
        changed = changed_paths(canonical_target, desired)
        lifecycle_directories = directory_object_snapshot(canonical_target)
        snapshot = current_managed_object_snapshot(canonical_target)
        snapshot_payload = managed_payload_snapshot(snapshot)
        managed_undo: FileUndoTransaction | None = None
        backup_before: dict[str, tuple[str, int, str | None]] | None = None
        backup_recovery: Path | None = None
        staged_backup: Path | None = None
        backup_slot: int | None = None
        try:
            if changed:
                backup_before, backup_recovery, staged_backup = prepare_backup_transaction(canonical_target, state)
                managed_undo = replace_managed_state(
                    canonical_target,
                    desired,
                    expected_before=snapshot_payload,
                    cleanup_on_success=False,
                )
            post = inspect_target(canonical_target)
            if changed:
                verify_managed_state(canonical_target, desired, "update postcondition")
            if staged_backup is not None and backup_before is not None:
                backup_slot = finish_backup_transaction(canonical_target, backup_before, backup_recovery, staged_backup)
                staged_backup = None
                backup_recovery = None
            if managed_undo is not None:
                managed_undo.commit_cleanup()
        except BaseException:
            if managed_undo is not None:
                managed_undo.rollback()
            else:
                restore_snapshot(canonical_target, snapshot)
            if backup_before is not None:
                rollback_backup_transaction(canonical_target, backup_before, backup_recovery, staged_backup)
            restore_directory_object_snapshot(canonical_target, lifecycle_directories, "lifecycle rollback")
            raise
    return {
        "ok": True,
        "operation": "update",
        "setup_id": state["setup_id"],
        "profile_id": profile_id,
        "description": metadata["description"],
        "target": str(canonical_target),
        "changed": changed,
        "backup_slot": backup_slot,
        "state": post["state"],
        "needs_update": post.get("needs_update"),
    }


def migration_profile_for_legacy(state: dict[str, Any], requested: str | None) -> str:
    if requested:
        validate_setup_id(requested)
        return requested
    if state.get("setup_id") == "safe":
        return "safe"
    if state.get("setup_id") == "full-auto":
        return "full-auto"
    fail("legacy balanced setup has no native mapping; pass --profile safe or --profile full-auto")


def render_legacy_migration_desired(
    target: Path,
    state: dict[str, Any],
    profile_id: str | None,
) -> tuple[str, dict[Path, bytes | None]]:
    selected_profile = migration_profile_for_legacy(state, profile_id)
    existing_config = preserved_legacy_config_for_migration(target, state)
    _metadata, rendered = render_setup(DEFAULT_SETUP_ID, selected_profile, existing_config=existing_config)
    desired: dict[Path, bytes | None] = dict(rendered)
    stamp = bind_stamp(parse_json_object(rendered[Path(STAMP_NAME)], "desired stamp"), target)
    desired[Path(STAMP_NAME)] = canonical_json(stamp)
    for legacy_path in LEGACY_MANAGED_PATHS:
        if legacy_path not in desired:
            desired[legacy_path] = None
    return selected_profile, desired


def migrate_setup(target: Path, profile_id: str | None) -> dict[str, Any]:
    with locked_existing_target(target) as canonical_target:
        state = inspect_target(canonical_target)
        if state["state"] != "legacy-managed":
            fail("migrate requires a legacy managed target")
        selected_profile, desired = render_legacy_migration_desired(canonical_target, state, profile_id)
        changed = changed_paths(canonical_target, desired)
        lifecycle_directories = directory_object_snapshot(canonical_target)
        snapshot = current_managed_object_snapshot(canonical_target)
        snapshot_payload = managed_payload_snapshot(snapshot)
        managed_undo: FileUndoTransaction | None = None
        backup_before: dict[str, tuple[str, int, str | None]] | None = None
        backup_recovery: Path | None = None
        staged_backup: Path | None = None
        backup_slot: int | None = None
        try:
            backup_before, backup_recovery, staged_backup = prepare_backup_transaction(canonical_target, state)
            managed_undo = replace_managed_state(
                canonical_target,
                desired,
                expected_before=snapshot_payload,
                cleanup_on_success=False,
            )
            post = inspect_target(canonical_target)
            verify_managed_state(canonical_target, desired, "migrate postcondition")
            backup_slot = finish_backup_transaction(canonical_target, backup_before, backup_recovery, staged_backup)
            staged_backup = None
            backup_recovery = None
            managed_undo.commit_cleanup()
        except BaseException:
            if managed_undo is not None:
                managed_undo.rollback()
            else:
                restore_snapshot(canonical_target, snapshot)
            if backup_before is not None:
                rollback_backup_transaction(canonical_target, backup_before, backup_recovery, staged_backup)
            restore_directory_object_snapshot(canonical_target, lifecycle_directories, "lifecycle rollback")
            raise
    return {
        "ok": True,
        "operation": "migrate",
        "target": str(canonical_target),
        "setup_id": post["setup_id"],
        "profile_id": post["profile_id"],
        "changed": changed,
        "backup_slot": backup_slot,
    }


def plan_setup(target: Path, setup_id: str, profile_id: str) -> dict[str, Any]:
    def build_plan(canonical_target: Path) -> dict[str, Any]:
        state = inspect_target(canonical_target)
        existing_config = read_existing_config_if_managed(canonical_target, state)
        _metadata, desired = render_setup(setup_id, profile_id, existing_config=existing_config)
        if state["state"] == "managed":
            stamp = bind_stamp(parse_json_object(desired[Path(STAMP_NAME)], "desired stamp"), canonical_target)
            desired[Path(STAMP_NAME)] = canonical_json(stamp)
            changed = changed_paths(canonical_target, desired)
            operation = "switch" if state.get("setup_id") != setup_id or state.get("profile_id") != profile_id else "update"
            backup_required = bool(changed)
        elif state["state"] == "legacy-managed":
            _selected_profile, migration_desired = render_legacy_migration_desired(canonical_target, state, profile_id)
            changed = changed_paths(canonical_target, migration_desired)
            operation = "migrate"
            backup_required = True
        else:
            changed = sorted(str(path) for path in desired)
            operation = "install"
            backup_required = False
        return {
            "ok": True,
            "operation": operation,
            "setup_id": setup_id,
            "profile_id": profile_id,
            "target": str(canonical_target),
            "state": state["state"],
            "mutates": False,
            "backup_required": backup_required,
            "changed": changed,
        }

    return run_locked_inspection(target, build_plan)


def remove_setup(target: Path) -> dict[str, Any]:
    with locked_existing_target(target) as canonical_target:
        state = inspect_target(canonical_target)
        if state["state"] not in {"managed", "legacy-managed"}:
            fail("target is not managed by nddev-mimocode-app")
        paths = ALL_MANAGED_PATHS if state["state"] == "legacy-managed" else MANAGED_PATHS
        lifecycle_directories = directory_object_snapshot(canonical_target)
        snapshot = current_managed_object_snapshot(canonical_target, paths)
        snapshot_payload = managed_payload_snapshot(snapshot)
        desired = {relative: None for relative in paths}
        managed_undo: FileUndoTransaction | None = None
        backup_before: dict[str, tuple[str, int, str | None]] | None = None
        backup_recovery: Path | None = None
        staged_backup: Path | None = None
        backup_slot: int | None = None
        try:
            backup_before, backup_recovery, staged_backup = prepare_backup_transaction(canonical_target, state)
            managed_undo = replace_managed_state(
                canonical_target,
                desired,
                expected_before=snapshot_payload,
                cleanup_on_success=False,
            )
            verify_managed_state(canonical_target, desired, "remove postcondition")
            backup_slot = finish_backup_transaction(canonical_target, backup_before, backup_recovery, staged_backup)
            staged_backup = None
            backup_recovery = None
            managed_undo.commit_cleanup()
        except BaseException:
            if managed_undo is not None:
                managed_undo.rollback()
            else:
                restore_snapshot(canonical_target, snapshot)
            if backup_before is not None:
                rollback_backup_transaction(canonical_target, backup_before, backup_recovery, staged_backup)
            restore_directory_object_snapshot(canonical_target, lifecycle_directories, "lifecycle rollback")
            raise
    return {
        "ok": True,
        "operation": "remove",
        "target": str(canonical_target),
        "removed_setup_id": state["setup_id"],
        "removed_profile_id": state.get("profile_id"),
        "backup_slot": backup_slot,
    }


def restore_backup(target: Path, slot: int) -> dict[str, Any]:
    with locked_existing_target(target) as canonical_target:
        state = inspect_target(canonical_target)
        if state["state"] not in {"managed", "legacy-managed"}:
            fail("target is not managed by nddev-mimocode-app")
        envelope, files = load_backup(canonical_target, slot)
        desired = restore_desired_from_backup(files)
        lifecycle_directories = directory_object_snapshot(canonical_target)
        snapshot = current_managed_object_snapshot(canonical_target)
        snapshot_payload = managed_payload_snapshot(snapshot)
        managed_undo: FileUndoTransaction | None = None
        try:
            managed_undo = replace_managed_state(
                canonical_target,
                desired,
                expected_before=snapshot_payload,
                cleanup_on_success=False,
            )
            post = inspect_target(canonical_target)
            verify_managed_state(canonical_target, desired, "restore postcondition")
            managed_undo.commit_cleanup()
        except BaseException:
            if managed_undo is not None:
                managed_undo.rollback()
            else:
                restore_snapshot(canonical_target, snapshot)
            restore_directory_object_snapshot(canonical_target, lifecycle_directories, "lifecycle rollback")
            raise
    return {
        "ok": True,
        "operation": "restore",
        "target": str(canonical_target),
        "setup_id": post["setup_id"],
        "profile_id": post.get("profile_id"),
        "restored_from_slot": slot,
        "restored_source_setup_id": envelope["source_setup_id"],
        "restored_source_profile_id": envelope["source_profile_id"],
    }


def load_baseline() -> dict[str, Any]:
    return load_json_object(BASELINE_REF, "MiMo Code baseline")


def run_absolute(argv: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
        env={"PATH": DETERMINISTIC_PATH, "LC_ALL": "C", "LANG": "C"},
    )


def parse_os_release_text(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        result[key] = value
    return result


def read_os_release(path: Path = Path("/etc/os-release")) -> dict[str, str]:
    try:
        return parse_os_release_text(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return {}


def current_host_metadata() -> dict[str, Any]:
    libc, libc_version = platform.libc_ver()
    metadata: dict[str, Any] = {
        "sys_platform": sys.platform,
        "machine": platform.machine(),
        "libc": libc.lower(),
        "libc_version": libc_version,
        "os_release": {},
    }
    if sys.platform.startswith("linux"):
        metadata["os_release"] = read_os_release()
    return metadata


def normalize_host_arch(machine: str) -> str:
    normalized = machine.lower()
    if normalized in {"x86_64", "amd64"}:
        return "x64"
    if normalized in {"arm64", "aarch64"}:
        return "arm64"
    fail(f"unsupported architecture for MiMo Code install: {machine}")


def host_supports_avx2(host: dict[str, Any] | None = None) -> bool:
    host = current_host_metadata() if host is None else host
    machine = str(host.get("machine", ""))
    if normalize_host_arch(machine) != "x64":
        return True
    if "avx2" in host:
        return bool(host["avx2"])
    sys_platform = str(host.get("sys_platform", sys.platform))
    if sys_platform == "darwin":
        sysctl = Path("/usr/sbin/sysctl")
        if not sysctl.exists():
            return False
        completed = run_absolute([str(sysctl), "-n", "hw.optional.avx2_0"], timeout=10)
        return completed.returncode == 0 and completed.stdout.strip() == "1"
    if sys_platform.startswith("linux"):
        cpuinfo = Path("/proc/cpuinfo")
        if not cpuinfo.exists():
            return False
        try:
            data = cpuinfo.read_bytes()[: 8 * 1024 * 1024]
        except OSError:
            return False
        return b"avx2" in data.lower()
    return False


def host_is_darwin_translated(host: dict[str, Any]) -> bool:
    if "darwin_translated" in host:
        return bool(host["darwin_translated"])
    sysctl = Path("/usr/sbin/sysctl")
    if not sysctl.exists():
        return False
    translated = run_absolute([str(sysctl), "-n", "sysctl.proc_translated"], timeout=10)
    return translated.returncode == 0 and translated.stdout.strip() == "1"


def require_ubuntu_glibc_host(host: dict[str, Any]) -> None:
    os_release = host.get("os_release")
    if not isinstance(os_release, dict):
        fail("Linux host metadata must include structured os-release data")
    ubuntu_id = str(os_release.get("ID", "")).lower()
    if ubuntu_id != "ubuntu":
        fail("only Ubuntu Linux desktop/server hosts are supported by this module")


def detect_platform_selection(host: dict[str, Any] | None = None) -> dict[str, Any]:
    host = current_host_metadata() if host is None else host
    sys_platform = str(host.get("sys_platform", ""))
    machine = str(host.get("machine", ""))
    arch = normalize_host_arch(machine)
    product_host_id: str
    if sys_platform == "darwin":
        if arch == "x64" and host_is_darwin_translated(host):
            arch = "arm64"
        asset_key = f"darwin-{arch}"
        product_host_id = f"macos-{arch}"
    elif sys_platform.startswith("linux"):
        if str(host.get("libc", "")).lower() != "glibc":
            fail("musl or non-glibc Linux is not supported by this module")
        require_ubuntu_glibc_host(host)
        asset_key = f"linux-{arch}"
        product_host_id = f"ubuntu-glibc-{arch}"
    elif sys_platform.startswith("win"):
        fail("Windows is not supported by this module")
    else:
        fail(f"unsupported platform for MiMo Code install: {sys_platform}")
    if arch == "x64" and not host_supports_avx2(host):
        asset_key = f"{asset_key}-baseline"
    return {"asset_key": asset_key, "product_host_id": product_host_id, "arch": arch}


def detect_platform_asset(host: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    baseline = load_baseline()
    assets = baseline.get("release", {}).get("assets")
    if not isinstance(assets, dict):
        fail("baseline release assets missing")
    selection = detect_platform_selection(host)
    key = selection["asset_key"]
    asset = assets.get(key)
    if not isinstance(asset, dict):
        fail(f"baseline does not declare asset {key}")
    return key, asset


def require_supported_product_host(host: dict[str, Any] | None = None) -> None:
    detect_platform_asset(host)


def software_manifest_path(target: Path) -> Path:
    return target / SOFTWARE_MANIFEST_RELATIVE


def software_tree_binary(target: Path) -> Path:
    return target / SOFTWARE_VERSION_RELATIVE / COMMAND_NAME


def mimo_executable(target: Path) -> Path:
    return target / "bin" / COMMAND_NAME


def software_presence(target: Path) -> list[str]:
    labels = (
        (mimo_executable(target), f"bin/{COMMAND_NAME}"),
        (software_manifest_path(target), str(SOFTWARE_MANIFEST_RELATIVE)),
        (software_tree_binary(target), str(SOFTWARE_VERSION_RELATIVE / COMMAND_NAME)),
    )
    return sorted(label for path, label in labels if path_present(path))


def software_status(target: Path) -> dict[str, Any]:
    if not path_present(target):
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
    require_private_directory(target, "target")
    executable = mimo_executable(target)
    tree_binary = software_tree_binary(target)
    manifest = software_manifest_path(target)
    presence = software_presence(target)
    base = {
        "ok": True,
        "installed": False,
        "current": False,
        "present": bool(presence),
        "presence": presence,
        "target": str(target),
        "version": None,
        "executable": str(executable),
        "drift": [],
    }
    if not path_present(executable) or not path_present(manifest) or not path_present(tree_binary):
        if presence:
            base["drift"] = ["software-incomplete"]
        return base
    binary_bytes, binary_info = read_regular_file(executable, "MiMo Code executable", max_bytes=SOFTWARE_EXECUTABLE_MAX_BYTES)
    tree_bytes, tree_info = read_regular_file(tree_binary, "MiMo Code version tree executable", max_bytes=SOFTWARE_EXECUTABLE_MAX_BYTES)
    if stat.S_IMODE(binary_info.st_mode) != OWNER_EXECUTABLE_MODE or stat.S_IMODE(tree_info.st_mode) != OWNER_EXECUTABLE_MODE:
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
    if info.get("executable") != f"bin/{COMMAND_NAME}":
        drift.append("executable")
    if info.get("version_tree_executable") != str(SOFTWARE_VERSION_RELATIVE / COMMAND_NAME):
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
    executable_baseline = asset.get("executable")
    if isinstance(executable_baseline, dict):
        for key in ("archive_member_path", "archive_member_mode", "installer_binary_mode", "binary_size"):
            expected_key = {"archive_member_path": "path", "archive_member_mode": "archive_mode", "installer_binary_mode": "installer_mode", "binary_size": "size"}[key]
            if info.get(key) != executable_baseline.get(expected_key):
                drift.append(key)
        if binary_sha != executable_baseline.get("sha256"):
            drift.append("baseline_binary_sha256")
    if info.get("binary_mode") != f"{OWNER_EXECUTABLE_MODE:04o}":
        drift.append("binary_mode")
    if info.get("binary_max_bytes") != SOFTWARE_EXECUTABLE_MAX_BYTES:
        drift.append("binary_max_bytes")
    if info.get("binary_sha256") != binary_sha or tree_sha != binary_sha:
        drift.append("binary_sha256")
    return {**base, "installed": True, "current": not drift, "version": info.get("version"), "drift": drift, "binary_sha256": binary_sha}


def read_url(url: str, *, max_bytes: int, expected_size: int | None = None) -> bytes:
    if not url.startswith("https://"):
        fail(f"MiMo Code download URL must use https: {url}")
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
                fail("MiMo Code download exceeded the bounded size")
            chunks.append(chunk)
    data = b"".join(chunks)
    if expected_size is not None and len(data) != expected_size:
        fail(f"MiMo Code downloaded size mismatch for {url}")
    return data


def validate_archive_member_path(name: str) -> None:
    normalized = name.replace("\\", "/")
    if "\x00" in normalized or normalized.startswith("//") or re.fullmatch(r"[A-Za-z]:.*", normalized):
        fail(f"unsafe archive member path: {name}")
    path = Path(normalized)
    if path.is_absolute() or ".." in path.parts:
        fail(f"unsafe archive member path: {name}")


def extract_verified_binary(archive_bytes: bytes, asset_name: str) -> tuple[str, int, bytes]:
    candidates: list[tuple[str, int, bytes]] = []
    expected_names = {COMMAND_NAME}
    if asset_name.endswith(".zip"):
        with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
            for member in archive.infolist():
                validate_archive_member_path(member.filename)
                mode = member.external_attr >> 16
                if Path(member.filename).name not in expected_names:
                    continue
                if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or mode == 0):
                    fail(f"unsafe archive member type: {member.filename}")
                if member.file_size > SOFTWARE_EXECUTABLE_MAX_BYTES:
                    fail("MiMo Code archive binary exceeds bounded size")
                candidates.append((member.filename, stat.S_IMODE(mode), archive.read(member)))
    else:
        with tarfile.open(fileobj=BytesIO(archive_bytes), mode="r:*") as archive:
            for member in archive.getmembers():
                validate_archive_member_path(member.name)
                if Path(member.name).name not in expected_names:
                    continue
                if member.issym() or member.islnk() or member.isdev() or not member.isfile():
                    fail(f"unsafe archive member type: {member.name}")
                if member.size > SOFTWARE_EXECUTABLE_MAX_BYTES:
                    fail("MiMo Code archive binary exceeds bounded size")
                extracted = archive.extractfile(member)
                if extracted is None:
                    fail(f"cannot read archive member: {member.name}")
                candidates.append((member.name, stat.S_IMODE(member.mode), extracted.read(SOFTWARE_EXECUTABLE_MAX_BYTES + 1)))
    if len(candidates) != 1:
        fail(f"archive must contain exactly one MiMo Code executable, found {len(candidates)}")
    name, mode, data = candidates[0]
    if len(data) > SOFTWARE_EXECUTABLE_MAX_BYTES:
        fail(f"MiMo Code archive member too large: {name}")
    return name, mode, data


def selected_asset() -> tuple[str, dict[str, Any]]:
    return detect_platform_asset()


def read_pinned_installer() -> tuple[bytes, str, str, int]:
    installer = read_url(INSTALLER_URL, max_bytes=2 * 1024 * 1024, expected_size=INSTALLER_SIZE)
    digest = sha256_bytes(installer)
    if digest != INSTALLER_SHA256:
        fail("MiMo Code installer SHA-256 mismatch")
    return installer, digest, INSTALLER_URL, len(installer)


def minimal_process_env(bin_dir: Path | None = None, *, tmp_dir: Path) -> dict[str, str]:
    path = DETERMINISTIC_PATH
    if bin_dir is not None:
        path = f"{bin_dir}{os.pathsep}{path}"
    env = {
        "PATH": path,
        "PYTHONDONTWRITEBYTECODE": "1",
        "HOME": "/nonexistent",
        "SHELL": "",
        "TMPDIR": str(tmp_dir),
    }
    env.update(MIMOCODE_FIXED_RUNTIME_ENV)
    for name in ("LANG", "LC_ALL", "LC_CTYPE", "SYSTEMROOT"):
        value = os.environ.get(name)
        if value:
            env[name] = value
    return env


def run_official_installer(
    installer: bytes,
    installer_source: str,
    installer_sha256: str,
    verified_binary: bytes,
) -> dict[str, Any]:
    if not BASH_PATH.exists():
        fail("trusted /bin/bash is required for the official MiMo Code installer")
    with tempfile.TemporaryDirectory(prefix=".nddev-mimocode-installer-") as stage_raw:
        stage = Path(stage_raw)
        home = stage / "home"
        tmp_dir = stage / "tmp"
        for directory in (
            home,
            tmp_dir,
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
                "MIMOCODE_HOME": str(stage / "mimocode-home"),
                "MIMOCODE_CONFIG_DIR": str(stage / "mimocode-config"),
                "MIMOCODE_CONFIG": str(stage / "mimocode-config" / "mimocode.json"),
                "SHELL": "",
            }
        )
        (stage / "mimocode-config").mkdir(mode=OWNER_DIRECTORY_MODE)
        (stage / "mimocode-config").chmod(OWNER_DIRECTORY_MODE)
        try:
            completed = subprocess.run(
                [
                    str(BASH_PATH),
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
                timeout=PROCESS_TIMEOUT_SECONDS,
                close_fds=True,
            )
        except subprocess.TimeoutExpired:
            fail("MiMo Code official installer timed out")
        if completed.returncode != 0:
            fail("MiMo Code official installer failed: " + (completed.stderr or completed.stdout).strip())
        installed = home / ".mimocode" / "bin" / COMMAND_NAME
        binary, info = read_regular_file(installed, "MiMo Code staged installer binary", max_bytes=SOFTWARE_EXECUTABLE_MAX_BYTES)
        installer_mode = stat.S_IMODE(info.st_mode)
        if installer_mode != OFFICIAL_INSTALLER_EXECUTABLE_MODE:
            fail(f"MiMo Code staged installer binary must have official installer mode {OFFICIAL_INSTALLER_EXECUTABLE_MODE:04o}")
        probe_env = minimal_process_env(installed.parent, tmp_dir=tmp_dir)
        probe_home = stage / "probe-home"
        probe_config = stage / "probe-config"
        probe_mimocode_home = stage / "probe-mimocode-home"
        probe_home.mkdir(mode=OWNER_DIRECTORY_MODE)
        probe_home.chmod(OWNER_DIRECTORY_MODE)
        probe_config.mkdir(mode=OWNER_DIRECTORY_MODE)
        probe_config.chmod(OWNER_DIRECTORY_MODE)
        probe_mimocode_home.mkdir(mode=OWNER_DIRECTORY_MODE)
        probe_mimocode_home.chmod(OWNER_DIRECTORY_MODE)
        probe_env.update(
            {
                "HOME": str(probe_home),
                "USERPROFILE": str(probe_home),
                "MIMOCODE_HOME": str(probe_mimocode_home),
                "MIMOCODE_CONFIG_DIR": str(probe_config),
                "MIMOCODE_CONFIG": str(probe_config / "mimocode.json"),
            }
        )
        try:
            probe = subprocess.run(
                [str(installed), "--version"],
                cwd=stage,
                env=probe_env,
                text=True,
                input="",
                capture_output=True,
                check=False,
                timeout=STAGED_VERSION_PROBE_TIMEOUT_SECONDS,
                close_fds=True,
            )
        except subprocess.TimeoutExpired:
            fail("MiMo Code staged version probe timed out")
        version_output = (probe.stdout + probe.stderr).strip()
        if probe.returncode != 0 or TESTED_VERSION not in version_output:
            fail("MiMo Code staged binary did not report the pinned version")
        return {
            "binary": binary,
            "binary_sha256": sha256_bytes(binary),
            "installer_binary_mode": f"{installer_mode:04o}",
            "installer_source": installer_source,
            "installer_sha256": installer_sha256,
            "version_output": version_output,
        }


def snapshot_optional_file(path: Path, label: str, *, max_bytes: int) -> tuple[bytes | None, int | None]:
    if not path_present(path):
        return None, None
    content, info = read_regular_file(path, label, max_bytes=max_bytes)
    return content, stat.S_IMODE(info.st_mode)


def write_private_file(path: Path, content: bytes, target: Path, mode: int) -> None:
    ensure_private_parent(target, path.relative_to(target))
    write_durable_file(path, content, mode)


def software_file_modes() -> dict[Path, int]:
    return {
        Path("bin") / COMMAND_NAME: OWNER_EXECUTABLE_MODE,
        SOFTWARE_VERSION_RELATIVE / COMMAND_NAME: OWNER_EXECUTABLE_MODE,
        SOFTWARE_MANIFEST_RELATIVE: OWNER_FILE_MODE,
    }


def software_max_bytes(relative: Path) -> int:
    if relative == SOFTWARE_MANIFEST_RELATIVE:
        return METADATA_MAX_BYTES
    return SOFTWARE_EXECUTABLE_MAX_BYTES


def current_software_snapshot(target: Path) -> dict[Path, tuple[bytes | None, int | None]]:
    snapshot: dict[Path, tuple[bytes | None, int | None]] = {}
    for relative in software_file_modes():
        snapshot[relative] = snapshot_optional_file(target / relative, f"software file {relative}", max_bytes=software_max_bytes(relative))
    return snapshot


def software_owner_only(_relative: Path) -> bool:
    return False


def current_software_object_snapshot(target: Path) -> FileObjectSnapshot:
    return {
        relative: file_object_record(
            target / relative,
            f"software file {relative}",
            owner_only=False,
            max_bytes=software_max_bytes(relative),
        )
        for relative in software_file_modes()
    }


def software_payload_snapshot(snapshot: FileObjectSnapshot) -> dict[Path, tuple[bytes | None, int | None]]:
    return {
        relative: (
            record["content"] if record.get("present") else None,
            record["mode"] if record.get("present") else None,
        )
        for relative, record in snapshot.items()
    }


def verify_software_state(target: Path, desired: dict[Path, tuple[bytes | None, int | None]], label: str) -> None:
    for relative, (content, mode) in desired.items():
        path = target / relative
        if content is None:
            if path_present(path):
                fail_concurrent(f"{label} left unexpected software file: {relative}")
            continue
        actual, info = read_regular_file(path, f"{label} software file {relative}", max_bytes=software_max_bytes(relative))
        if actual != content or stat.S_IMODE(info.st_mode) != mode:
            fail_concurrent(f"{label} software file mismatch: {relative}")


def software_commit_order(state: dict[Path, tuple[bytes | None, int | None]], *, rollback: bool) -> list[Path]:
    ordered = [
        SOFTWARE_VERSION_RELATIVE / COMMAND_NAME,
        Path("bin") / COMMAND_NAME,
        SOFTWARE_MANIFEST_RELATIVE,
    ]
    if rollback:
        ordered = [
            SOFTWARE_MANIFEST_RELATIVE,
            SOFTWARE_VERSION_RELATIVE / COMMAND_NAME,
            Path("bin") / COMMAND_NAME,
        ]
    return [relative for relative in ordered if relative in state]


def apply_software_state(
    target: Path,
    desired: dict[Path, tuple[bytes | None, int | None]],
    *,
    expected_before: dict[Path, tuple[bytes | None, int | None]] | None = None,
    rollback_on_error: bool,
    label: str,
    rollback_order: bool = False,
    cleanup_on_success: bool = True,
) -> FileUndoTransaction:
    before_objects = current_software_object_snapshot(target)
    before = software_payload_snapshot(before_objects)
    if expected_before is not None and before != expected_before:
        fail_concurrent(f"{label} pre-state changed before mutation")
    undo = FileUndoTransaction(
        target,
        before_objects,
        label=label,
        owner_only_for=software_owner_only,
        max_bytes_for=software_max_bytes,
    )
    staged: dict[Path, Path] = {}

    def cleanup_staged() -> None:
        for temporary in staged.values():
            cleanup_path_with_retries(temporary)
        staged.clear()

    try:
        for relative, (content, mode) in desired.items():
            if content is None:
                continue
            ensure_private_parent(target, relative)
            staged[relative] = create_staged_file(target / relative, content, mode or software_file_modes()[relative])
        for relative in software_commit_order(desired, rollback=rollback_order):
            path = target / relative
            content, mode = desired[relative]
            if content is None:
                if path_present(path):
                    require_regular_file(path, f"{label} software file {relative}", max_bytes=software_max_bytes(relative))
                    undo.hold(relative, path)
                continue
            temporary = staged[relative]
            undo.hold(relative, path)
            commit_staged_file(temporary, path)
            del staged[relative]
        verify_software_state(target, desired, label)
        if cleanup_on_success:
            undo.commit_cleanup()
    except BaseException:
        cleanup_staged()
        if rollback_on_error:
            undo.rollback()
        raise
    finally:
        cleanup_staged()
    return undo


def restore_software_snapshot_with_retries(
    target: Path,
    snapshot: FileObjectSnapshot | dict[Path, tuple[bytes | None, int | None]],
    *,
    label: str,
) -> None:
    last: BaseException | None = None
    if all(isinstance(record, dict) for record in snapshot.values()):
        object_snapshot = snapshot  # type: ignore[assignment]
        for _attempt in range(3):
            try:
                verify_file_object_snapshot(
                    target,
                    object_snapshot,
                    label,
                    owner_only_for=software_owner_only,
                    max_bytes_for=software_max_bytes,
                )
                cleanup_transaction_residue(target)
                return
            except BaseException as exc:
                last = exc
                cleanup_transaction_residue(target)
        if last is not None:
            raise last
        return
    desired = snapshot  # type: ignore[assignment]
    for attempt in range(3):
        try:
            apply_software_state(target, desired, rollback_on_error=False, label=f"{label} attempt {attempt + 1}", rollback_order=True)
            verify_software_state(target, desired, label)
            cleanup_transaction_residue(target)
            return
        except BaseException as exc:
            last = exc
            cleanup_transaction_residue(target)
    if last is not None:
        raise last


def restore_software_snapshot(target: Path, snapshot: FileObjectSnapshot | dict[Path, tuple[bytes | None, int | None]]) -> None:
    restore_software_snapshot_with_retries(target, snapshot, label="software rollback")


def remove_empty_directory_if_created(path: Path, existed_before: bool | None) -> None:
    if existed_before:
        return
    if existed_before is None:
        return
    cleanup_path_with_retries(path, raise_on_failure=True)


def validate_safe_software_presence(target: Path) -> None:
    for directory, label in (
        (mimo_executable(target).parent, "bin"),
        (software_manifest_path(target).parent, "software"),
        (software_tree_binary(target).parent.parent, "software/versions"),
        (software_tree_binary(target).parent, f"software/versions/{TESTED_VERSION}"),
    ):
        if path_present(directory):
            require_private_directory(directory, label)
    for file_path, label, mode, max_bytes in (
        (mimo_executable(target), f"bin/{COMMAND_NAME}", OWNER_EXECUTABLE_MODE, SOFTWARE_EXECUTABLE_MAX_BYTES),
        (software_tree_binary(target), f"software/versions/{TESTED_VERSION}/{COMMAND_NAME}", OWNER_EXECUTABLE_MODE, SOFTWARE_EXECUTABLE_MAX_BYTES),
        (software_manifest_path(target), "software/mimocode.json", OWNER_FILE_MODE, METADATA_MAX_BYTES),
    ):
        if path_present(file_path):
            info = require_regular_file(file_path, label, max_bytes=max_bytes)
            if stat.S_IMODE(info.st_mode) != mode:
                fail(f"{label} must have mode {mode:04o}")


def install_or_update_cli(target: Path, *, operation: str) -> dict[str, Any]:
    require_supported_product_host()
    with locked_new_or_existing_target_state(target) as (canonical_target, target_existed_before, target_parent_record):
        software_undo: FileUndoTransaction | None = None
        before_software: FileObjectSnapshot | None = None
        before_bin_dir: bool | None = None
        before_software_dir: bool | None = None
        before_versions_dir: bool | None = None
        before_version_dir: bool | None = None
        try:
            status = software_status(canonical_target)
            if operation == "install-cli" and status["present"]:
                fail("install-cli requires absent target-owned MiMo Code software presence; use update-cli")
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
            before_bin_dir = path_present(mimo_executable(canonical_target).parent)
            before_software_dir = path_present(software_manifest_path(canonical_target).parent)
            before_versions_dir = path_present(software_tree_binary(canonical_target).parent.parent)
            before_version_dir = path_present(software_tree_binary(canonical_target).parent)
            before_software = current_software_object_snapshot(canonical_target)
            before_software_payload = software_payload_snapshot(before_software)
            asset_key, asset = selected_asset()
            url = asset.get("url")
            expected_sha = asset.get("sha256")
            expected_size = asset.get("size")
            name = asset.get("name") or Path(str(url)).name
            if not isinstance(url, str) or not isinstance(expected_sha, str) or not isinstance(expected_size, int):
                fail(f"baseline asset {asset_key} is incomplete")
            archive_bytes = read_url(url, max_bytes=DOWNLOAD_MAX_BYTES, expected_size=expected_size)
            if sha256_bytes(archive_bytes) != expected_sha:
                fail(f"downloaded MiMo Code digest mismatch for {asset_key}")
            archive_member_path, archive_member_mode, verified_binary = extract_verified_binary(archive_bytes, str(name))
            executable_baseline = asset.get("executable")
            if executable_baseline is not None:
                expected_executable = {
                    "path": archive_member_path,
                    "archive_mode": f"{archive_member_mode:04o}",
                    "installer_mode": f"{OFFICIAL_INSTALLER_EXECUTABLE_MODE:04o}",
                    "size": len(verified_binary),
                    "sha256": sha256_bytes(verified_binary),
                }
                if executable_baseline != expected_executable:
                    fail(f"downloaded MiMo Code executable metadata mismatch for {asset_key}")
            installer, installer_sha, installer_source, installer_size = read_pinned_installer()
            artifact = run_official_installer(installer, installer_source, installer_sha, verified_binary)
            manifest = {
                "schema_version": 2,
                "version": TESTED_VERSION,
                "command": COMMAND_NAME,
                "executable": f"bin/{COMMAND_NAME}",
                "version_tree_executable": str(SOFTWARE_VERSION_RELATIVE / COMMAND_NAME),
                "asset": asset_key,
                "asset_url": url,
                "asset_size": expected_size,
                "asset_sha256": expected_sha,
                "archive_member_path": archive_member_path,
                "archive_member_mode": f"{archive_member_mode:04o}",
                "installer_binary_mode": artifact["installer_binary_mode"],
                "installer_url": artifact["installer_source"],
                "installer_size": installer_size,
                "installer_sha256": artifact["installer_sha256"],
                "binary_size": len(artifact["binary"]),
                "binary_mode": f"{OWNER_EXECUTABLE_MODE:04o}",
                "binary_max_bytes": SOFTWARE_EXECUTABLE_MAX_BYTES,
                "binary_sha256": artifact["binary_sha256"],
                "version_output": artifact["version_output"],
            }
            desired_software = {
                SOFTWARE_VERSION_RELATIVE / COMMAND_NAME: (artifact["binary"], OWNER_EXECUTABLE_MODE),
                Path("bin") / COMMAND_NAME: (artifact["binary"], OWNER_EXECUTABLE_MODE),
                SOFTWARE_MANIFEST_RELATIVE: (canonical_json(manifest), OWNER_FILE_MODE),
            }
            software_undo = apply_software_state(
                canonical_target,
                desired_software,
                expected_before=before_software_payload,
                rollback_on_error=True,
                label="software install",
                cleanup_on_success=False,
            )
            final = software_status(canonical_target)
            if not final["installed"] or not final["current"]:
                fail("MiMo Code software install did not produce current target-owned software")
            verify_software_state(canonical_target, desired_software, "software install postcondition")
            software_undo.commit_cleanup()
        except BaseException:
            if software_undo is not None:
                software_undo.rollback()
            elif before_software is not None:
                restore_software_snapshot(canonical_target, before_software)
            remove_empty_directory_if_created(software_tree_binary(canonical_target).parent, before_version_dir)
            remove_empty_directory_if_created(software_tree_binary(canonical_target).parent.parent, before_versions_dir)
            remove_empty_directory_if_created(software_manifest_path(canonical_target).parent, before_software_dir)
            remove_empty_directory_if_created(mimo_executable(canonical_target).parent, before_bin_dir)
            rollback_created_target_if_absent(
                canonical_target,
                target_existed_before,
                target_parent_record,
                "software lifecycle rollback",
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


def remove_cli(target: Path) -> dict[str, Any]:
    with locked_existing_target(target) as canonical_target:
        status = software_status(canonical_target)
        if not status["present"]:
            fail("remove-cli requires existing target-owned MiMo Code software presence")
        validate_safe_software_presence(canonical_target)
        before_software = current_software_object_snapshot(canonical_target)
        before_software_payload = software_payload_snapshot(before_software)
        desired = {relative: (None, None) for relative in software_file_modes()}
        software_undo: FileUndoTransaction | None = None
        directory_undo: DirectoryUndoTransaction | None = None
        software_cleanup_done = False
        directory_cleanup_done = False
        committed = False
        try:
            software_undo = apply_software_state(
                canonical_target,
                desired,
                expected_before=before_software_payload,
                rollback_on_error=True,
                label="software remove",
                cleanup_on_success=False,
            )
            final = software_status(canonical_target)
            if final["present"]:
                fail("MiMo Code software remove left target-owned files")
            directory_undo = DirectoryUndoTransaction(canonical_target, label="software remove")
            for relative in (
                software_tree_binary(canonical_target).parent.relative_to(canonical_target),
                software_tree_binary(canonical_target).parent.parent.relative_to(canonical_target),
                software_manifest_path(canonical_target).parent.relative_to(canonical_target),
                mimo_executable(canonical_target).parent.relative_to(canonical_target),
            ):
                directory_undo.hold_empty(relative)
            final_after_dirs = software_status(canonical_target)
            if final_after_dirs["present"]:
                fail("MiMo Code software remove left target-owned files after directory cleanup")
            directory_undo.commit_cleanup()
            directory_cleanup_done = True
            software_undo.commit_cleanup()
            software_cleanup_done = True
            committed = True
        except BaseException:
            if directory_undo is not None and not directory_cleanup_done and not committed:
                directory_undo.rollback()
            if software_undo is not None and not software_cleanup_done and not committed:
                software_undo.rollback()
            elif software_undo is None:
                restore_software_snapshot(canonical_target, before_software)
            raise
    return {"ok": True, "operation": "remove-cli", "target": str(canonical_target), "removed": True}


def isolated_child_environment(target: Path, launch_env: dict[str, str]) -> dict[str, str]:
    blocked_runtime_env = sorted(set(launch_env) & set(MIMOCODE_FIXED_RUNTIME_ENV))
    if blocked_runtime_env:
        fail(f"launch env must not override manager-owned runtime env: {blocked_runtime_env}")
    for relative in (
        Path("runtime"),
        Path("runtime") / "tmp",
        Path("runtime") / "appdata",
        Path("runtime") / "local-appdata",
        Path("runtime") / "xdg-config",
        Path("runtime") / "xdg-cache",
        Path("runtime") / "xdg-state",
        Path("runtime") / "xdg-data",
        Path("home"),
        Path("home") / "user",
        MIMOCODE_HOME_RELATIVE,
        MIMOCODE_CONFIG_DIR_RELATIVE,
    ):
        ensure_private_directory_under_target(target, relative, "runtime directory")
    runtime = target / "runtime"
    tmp = runtime / "tmp"
    env: dict[str, str] = {}
    for name in SAFE_CHILD_INHERITED_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            env[name] = value
    env.update(
        {
            "APPDATA": str(runtime / "appdata"),
            "HOME": str(target / "home" / "user"),
            "LOCALAPPDATA": str(runtime / "local-appdata"),
            "USERPROFILE": str(target / "home" / "user"),
            "MIMOCODE_HOME": str(target / MIMOCODE_HOME_RELATIVE),
            "MIMOCODE_CONFIG_DIR": str(target / MIMOCODE_CONFIG_DIR_RELATIVE),
            "MIMOCODE_CONFIG": str(target / MIMOCODE_CONFIG_RELATIVE),
            "SHELL": "/bin/sh",
            "TEMP": str(tmp),
            "TMP": str(tmp),
            "TMPDIR": str(tmp),
            "XDG_CONFIG_HOME": str(runtime / "xdg-config"),
            "XDG_CACHE_HOME": str(runtime / "xdg-cache"),
            "XDG_STATE_HOME": str(runtime / "xdg-state"),
            "XDG_DATA_HOME": str(runtime / "xdg-data"),
            "PATH": DETERMINISTIC_PATH,
        }
    )
    env.update(MIMOCODE_FIXED_RUNTIME_ENV)
    env.update(launch_env)
    for name in TOKEN_ENV_NAMES:
        if name in env and name not in launch_env:
            del env[name]
    return env


def validate_launch_args(args: list[str]) -> None:
    for item in args:
        flag = item.split("=", 1)[0]
        if flag in BLOCKED_LAUNCH_FLAGS:
            fail(f"launch argument {flag} is managed by nddev-mimocode-app")
    first_command = next((item for item in args if item and not item.startswith("-")), None)
    if first_command in BLOCKED_LAUNCH_COMMANDS:
        fail(f"launch command {first_command} is not allowed by the managed MiMo Code scope")


def validate_launch_project_boundary(target: Path) -> None:
    for relative in PROJECT_BOUNDARY_PATHS:
        path = target / relative
        if path_present(path):
            fail(f"launch project boundary path is not managed by nddev-mimocode-app: {relative}")


def validate_launch_managed_config_boundary(target: Path) -> None:
    config_root = target / MIMOCODE_CONFIG_DIR_RELATIVE
    if not path_present(config_root):
        fail("managed MiMo Code config directory is missing")
    require_private_directory(config_root, "managed MiMo Code config directory")
    allowed_files = {
        relative for relative in MANAGED_PATHS if MIMOCODE_CONFIG_DIR_RELATIVE in relative.parents
    }
    for path in sorted(config_root.rglob("*"), key=lambda item: str(item.relative_to(target))):
        relative = path.relative_to(target)
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            fail(f"managed MiMo Code config path must not be a symlink: {relative}")
        if stat.S_ISDIR(info.st_mode):
            continue
        if relative not in allowed_files:
            fail(f"managed MiMo Code config directory contains unmanaged launch input: {relative}")
        require_regular_file(path, f"managed config file {relative}", owner_only=True)


def protect_directory(path: Path, label: str) -> tuple[Path, int] | None:
    if not path_present(path):
        return None
    info = require_directory(path, label)
    if not is_current_user_owned(info):
        fail(f"{label} must be owned by the current user")
    mode = stat.S_IMODE(info.st_mode)
    if mode == OWNER_DIRECTORY_MODE:
        path.chmod(PROTECTED_DIRECTORY_MODE)
    elif mode != PROTECTED_DIRECTORY_MODE:
        fail(f"{label} must be owned by the current user with mode 0700")
    return path, mode


@contextlib.contextmanager
def protected_launch_artifacts(target: Path) -> Iterator[None]:
    protected: list[tuple[Path, int]] = []
    for relative in (Path("bin"), Path("software"), Path("software") / "versions", SOFTWARE_VERSION_RELATIVE):
        item = protect_directory(target / relative, str(relative))
        if item is not None:
            protected.append(item)
    try:
        yield
    finally:
        for path, mode in reversed(protected):
            with contextlib.suppress(FileNotFoundError, OSError):
                info = path.lstat()
                if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
                    path.chmod(mode)


def verify_executable_for_launch(target: Path) -> None:
    status = software_status(target)
    if not status["installed"] or not status["current"]:
        fail("MiMo Code is not installed at the tested version in this target")
    executable = mimo_executable(target)
    manifest = load_json_object(software_manifest_path(target), "software manifest", owner_only=True)
    binary, _info = read_regular_file(executable, "MiMo Code executable", max_bytes=SOFTWARE_EXECUTABLE_MAX_BYTES)
    if manifest.get("binary_sha256") != sha256_bytes(binary):
        fail_concurrent("MiMo Code executable changed before launch")


def launch_mimo(target: Path, args: list[str]) -> int:
    validate_launch_args(args)
    with locked_existing_target(target) as canonical_target:
        state = inspect_target(canonical_target)
        if state["state"] == "legacy-managed":
            fail("legacy managed target must be migrated before launch")
        if state["state"] != "managed":
            fail("target is not managed by nddev-mimocode-app")
        validate_launch_project_boundary(canonical_target)
        validate_launch_managed_config_boundary(canonical_target)
        require_supported_product_host()
        child_args = list(state["launch_args"]) + args
        child_env = isolated_child_environment(canonical_target, state["launch_env"])
        executable = mimo_executable(canonical_target)
        with protected_launch_artifacts(canonical_target):
            verify_executable_for_launch(canonical_target)
            completed = subprocess.run(
                [str(executable), *child_args],
                cwd=canonical_target,
                env=child_env,
                check=False,
                timeout=None,
                close_fds=True,
            )
    return int(completed.returncode)


def print_payload(payload: dict[str, Any], *, json_output: bool) -> None:
    del json_output
    print(json.dumps(payload, indent=2, sort_keys=True))


def add_json_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="print JSON output")


def add_target_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--target", required=True, help="explicit absolute MiMo Code target")


def add_setup_profile_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--setup", default=DEFAULT_SETUP_ID)
    parser.add_argument("--profile", default=DEFAULT_PROFILE_ID)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = JsonBoundaryArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=JsonBoundaryArgumentParser)
    list_parser = subparsers.add_parser("list", help="list setup and profile variants")
    add_json_argument(list_parser)
    for name in ("status", "software-status"):
        command_parser = subparsers.add_parser(name, help=f"{name} for a target")
        add_target_argument(command_parser)
        add_json_argument(command_parser)
    for name in ("plan", "install", "switch"):
        command_parser = subparsers.add_parser(name, help=f"{name} a setup/profile")
        add_setup_profile_arguments(command_parser)
        add_target_argument(command_parser)
        add_json_argument(command_parser)
    update_parser = subparsers.add_parser("update", help="update the current managed setup/profile")
    add_target_argument(update_parser)
    add_json_argument(update_parser)
    migrate_parser = subparsers.add_parser("migrate", help="migrate a legacy managed target")
    migrate_parser.add_argument("--profile")
    add_target_argument(migrate_parser)
    add_json_argument(migrate_parser)
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
    for name in os.environ:
        if name in BLOCKED_MANAGER_ENV_NAMES:
            fail(f"{name} is managed by nddev-mimocode-app and must not be supplied by the caller")
        if name.startswith(FORBIDDEN_MANAGER_ENV_PREFIXES):
            fail(f"{name} is not a supported public override")
    if args.command in TARGET_BOUND_COMMANDS:
        require_supported_product_host()
    if args.command == "list":
        print_payload({"ok": True, "setups": list_setups(), "profiles": list_profiles(), "default_profile": DEFAULT_PROFILE_ID}, json_output=args.json)
        return 0
    if args.command == "status":
        target = require_absolute_target_argument(args.target)
        payload = run_locked_inspection(target, lambda canonical_target: {"ok": True, **inspect_target(canonical_target)})
        print_payload(payload, json_output=args.json)
        return 0
    if args.command == "software-status":
        target = require_absolute_target_argument(args.target)
        payload = run_locked_inspection(target, software_status)
        print_payload(payload, json_output=args.json)
        return 0
    if args.command == "plan":
        target = require_absolute_target_argument(args.target)
        print_payload(plan_setup(target, args.setup, args.profile), json_output=args.json)
        return 0
    if args.command in {"install", "switch"}:
        target = require_absolute_target_argument(args.target)
        print_payload(mutate_setup(target, args.setup, args.profile, args.command), json_output=args.json)
        return 0
    if args.command == "update":
        target = require_absolute_target_argument(args.target)
        print_payload(update_setup(target), json_output=args.json)
        return 0
    if args.command == "migrate":
        target = require_absolute_target_argument(args.target)
        print_payload(migrate_setup(target, args.profile), json_output=args.json)
        return 0
    if args.command == "restore":
        target = require_absolute_target_argument(args.target)
        print_payload(restore_backup(target, args.backup), json_output=args.json)
        return 0
    if args.command == "remove":
        target = require_absolute_target_argument(args.target)
        print_payload(remove_setup(target), json_output=args.json)
        return 0
    if args.command == "install-cli":
        target = require_absolute_target_argument(args.target)
        print_payload(install_or_update_cli(target, operation="install-cli"), json_output=args.json)
        return 0
    if args.command == "update-cli":
        target = require_absolute_target_argument(args.target)
        print_payload(install_or_update_cli(target, operation="update-cli"), json_output=args.json)
        return 0
    if args.command == "remove-cli":
        target = require_absolute_target_argument(args.target)
        print_payload(remove_cli(target), json_output=args.json)
        return 0
    if args.command == "launch":
        target = require_absolute_target_argument(args.target)
        mimo_args = list(args.mimo_args)
        if mimo_args and mimo_args[0] == "--":
            mimo_args = mimo_args[1:]
        return launch_mimo(target, mimo_args)
    fail(f"unknown command: {args.command}")


def json_requested(argv: list[str] | None) -> bool:
    return "--json" in (argv if argv is not None else sys.argv[1:])


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        return run(args)
    except CliArgumentError as exc:
        return error_result(str(exc), json_output=json_requested(argv))
    except MiMoCodeSetupError as exc:
        return error_result(str(exc), json_output=json_requested(argv))


if __name__ == "__main__":
    raise SystemExit(main())
