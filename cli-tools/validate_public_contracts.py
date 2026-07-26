#!/usr/bin/env python3
"""Validate nddev-mimocode-app public contracts without side effects."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:[-+].*)?\Z")
EXPECTED = {
    "version": "0.1.9",
    "release_tag": "v0.1.9",
    "published_at": "2026-07-24T06:06:13Z",
    "command": "mimo",
    "npm_package": "@mimo-ai/cli",
    "npm_integrity": "sha512-YFqiotp1sHDmj2BOiw2AbgCY2zm+c7Z36lh5JNL6KACEvYgerB5kqqldqcy/xI4Erry501DsTN1YPxo2mw6fAQ==",
    "fds_latest": "0.1.9",
}
SETUP_IDS = ["safe", "balanced", "full-auto"]
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
ASSET_DIGESTS = {
    "darwin-arm64": "a46f1fc7f2a770d84ff5a3a731bc86ec54a3aa40ce22efd71e3c114f2b42ef83",
    "darwin-x64-baseline": "fdf326bf8d8d9b4a5e524e0d15f17e8f894b0d0d278287d0c20de646f52184b1",
    "darwin-x64": "710618322abeb01a2b1130c6099fe7ff68b3efc4da19545817926b22afcc5f10",
    "linux-arm64-musl": "aa3290ee7977ac295a4912344e564bda3d1806244a372f3822890bd2dc922d15",
    "linux-arm64": "801bb33a18c66bfffaf342735780bb2635f419044003550d0e167eaf776e0db0",
    "linux-x64-baseline-musl": "2fd48541f6d3c3df5ef48096fbe376535b44c89554ecabf4041f52a5e6ff78b4",
    "linux-x64-baseline": "104b736967db1772ccc12648c6b2b7e8bf05862794f254c70a23d950d5278081",
    "linux-x64-musl": "cb5a4e799bb6b0dfa425cf4c757c644c02bc9487e4c8c33733a6bb19a9167762",
    "linux-x64": "99ade0a26235d80db7bb6ac0319b0f6508dfe684e2cfab7a00801ad6aa2ac673",
    "windows-arm64": "35f6261707861f463948186f9cc40bb3bc6dd955563ea87858a5247f741edf47",
    "windows-x64-baseline": "49d43de637054ec8cd069a73b1e4ca0f980e84b5ac65a04f1dad104f10ceb8fd",
    "windows-x64": "514b60dfd3b2d9ee8f6c3fb852398bbd2101f9b58f0ab271d8edb3acaa4375d4",
}
PLACEHOLDER_MARKER = "skele" + "ton"
RETIRED_MARKERS = ("q" + "coder", "qwen" + " code", "qwen" + "-code", "gh" + "-copilot")


def read_json(relative: str) -> dict[str, Any]:
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"{relative} must contain a JSON object")
    return value


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate_versions(errors: list[str]) -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    build = read_json("build/version.json")
    manifest = read_json("build/manifest.json")
    contract = read_json("config/nddev-contract.json")
    baseline = read_json("references/mimocode-baseline.json")
    require(SEMVER.fullmatch(version) is not None, "VERSION is not SemVer", errors)
    require(version != "0.0.0", "VERSION must not be placeholder 0.0.0", errors)
    require(build.get("schema_version") == 2, "build schema mismatch", errors)
    require(manifest.get("schema_version") == 2, "manifest schema mismatch", errors)
    require(contract.get("contract_version") == 2, "contract version mismatch", errors)
    require(build.get("build_version") == version, "build version mismatch", errors)
    require(manifest.get("build_version") == version, "manifest version mismatch", errors)
    require(build.get("mimocode_tested") == EXPECTED["version"], "tested version mismatch", errors)
    require(
        build.get("mimocode_release_tag") == EXPECTED["release_tag"], "release tag mismatch", errors
    )
    require(
        build.get("mimocode_published_at") == EXPECTED["published_at"],
        "published_at mismatch",
        errors,
    )
    require(build.get("command") == EXPECTED["command"], "command mismatch", errors)
    require(build.get("npm_package") == EXPECTED["npm_package"], "package mismatch", errors)
    require(
        build.get("npm_integrity") == EXPECTED["npm_integrity"], "npm integrity mismatch", errors
    )
    release = baseline.get("release")
    npm = baseline.get("npm")
    install = baseline.get("install")
    require(isinstance(release, dict), "baseline release missing", errors)
    require(isinstance(npm, dict), "baseline npm missing", errors)
    require(isinstance(install, dict), "baseline install missing", errors)
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
    if isinstance(npm, dict):
        require(npm.get("package") == build.get("npm_package"), "baseline package mismatch", errors)
        require(
            npm.get("version") == build.get("mimocode_tested"),
            "baseline package version mismatch",
            errors,
        )
        require(
            npm.get("integrity") == build.get("npm_integrity"),
            "baseline npm integrity mismatch",
            errors,
        )
    if isinstance(install, dict):
        require(
            install.get("fds_latest") == build.get("mimocode_tested"),
            "baseline FDS latest mismatch",
            errors,
        )
    for owner, runtime in (
        ("manifest", manifest.get("runtime_compatibility")),
        ("contract", contract.get("runtime_compatibility")),
    ):
        require(isinstance(runtime, dict), f"{owner} runtime_compatibility missing", errors)
        if isinstance(runtime, dict):
            require(
                runtime.get("tested_version") == build.get("mimocode_tested"),
                f"{owner} tested version mismatch",
                errors,
            )
            require(
                runtime.get("npm_package") == build.get("npm_package"),
                f"{owner} package mismatch",
                errors,
            )
            require(
                runtime.get("command") == build.get("command"), f"{owner} command mismatch", errors
            )


def validate_assets(errors: list[str]) -> None:
    baseline = read_json("references/mimocode-baseline.json")
    assets = baseline.get("release", {}).get("assets")
    require(isinstance(assets, dict), "baseline assets missing", errors)
    if isinstance(assets, dict):
        for key, digest in ASSET_DIGESTS.items():
            asset = assets.get(key)
            require(isinstance(asset, dict), f"asset missing: {key}", errors)
            if isinstance(asset, dict):
                require(asset.get("sha256") == digest, f"asset digest mismatch: {key}", errors)
                require(
                    str(asset.get("url", "")).startswith(
                        "https://github.com/XiaomiMiMo/MiMo-Code/releases/download/v0.1.9/"
                    ),
                    f"asset URL mismatch: {key}",
                    errors,
                )


def validate_permission_tree(value: Any, label: str, errors: list[str]) -> None:
    if isinstance(value, str):
        require(value in {"allow", "ask", "deny"}, f"{label} invalid permission value", errors)
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            require(isinstance(key, str), f"{label} permission key is not a string", errors)
            validate_permission_tree(nested, f"{label}.{key}", errors)
        return
    errors.append(f"{label} invalid permission shape")


def validate_setups(errors: list[str]) -> None:
    manifest = read_json("build/manifest.json")
    contract = read_json("config/nddev-contract.json")
    require(manifest.get("setup_ids") == SETUP_IDS, "manifest setup ids mismatch", errors)
    setup_system = contract.get("setup_system")
    require(isinstance(setup_system, dict), "contract setup_system missing", errors)
    if isinstance(setup_system, dict):
        require(setup_system.get("setup_ids") == SETUP_IDS, "contract setup ids mismatch", errors)
        require(setup_system.get("builder_default_on") is True, "builder default mismatch", errors)
    for setup_id in SETUP_IDS:
        metadata = read_json(f"setups/{setup_id}/setup.json")
        config = read_json(f"setups/{setup_id}/mimocode.json")
        require(metadata.get("id") == setup_id, f"{setup_id} id mismatch", errors)
        require(metadata.get("launch_args") == [], f"{setup_id} launch args mismatch", errors)
        require(
            metadata.get("builder_default_on") is True, f"{setup_id} builder not default-on", errors
        )
        require(
            metadata.get("builder_projection") == "native-config-skills-agents-instructions",
            f"{setup_id} builder projection mismatch",
            errors,
        )
        require(
            config.get("$schema") == "https://mimo.xiaomi.com/mimocode/config.json",
            f"{setup_id} schema mismatch",
            errors,
        )
        require(
            config.get("autoupdate") is False, f"{setup_id} autoupdate must be disabled", errors
        )
        require(config.get("share") == "disabled", f"{setup_id} share must be disabled", errors)
        require("tools" not in config, f"{setup_id} must not use deprecated tools config", errors)
        require(config.get("plugin") == [], f"{setup_id} marketplace/plugins must be empty", errors)
        require(config.get("mcp") == {}, f"{setup_id} must not start MCP servers", errors)
        require(
            config.get("skills") == {"paths": ["./skills"]},
            f"{setup_id} skills path mismatch",
            errors,
        )
        require(
            config.get("instructions") == ["./AGENTS.md", "./instructions/nddev-builder.md"],
            f"{setup_id} instructions mismatch",
            errors,
        )
        permission = config.get("permission")
        require(isinstance(permission, dict), f"{setup_id} permission missing", errors)
        if isinstance(permission, dict):
            validate_permission_tree(permission, f"{setup_id}.permission", errors)
            skill = permission.get("skill")
            require(isinstance(skill, dict), f"{setup_id} skill permission missing", errors)
            if isinstance(skill, dict):
                require(
                    skill.get("nddev-builder") == "allow",
                    f"{setup_id} builder skill not allowed",
                    errors,
                )
        agent = config.get("agent")
        require(isinstance(agent, dict), f"{setup_id} agents missing", errors)
        if isinstance(agent, dict):
            builder = agent.get("nddev-builder")
            require(isinstance(builder, dict), f"{setup_id} builder agent missing", errors)
            if isinstance(builder, dict):
                require(
                    builder.get("mode") == "subagent",
                    f"{setup_id} builder agent mode mismatch",
                    errors,
                )
                require(
                    builder.get("prompt") == "{file:./instructions/nddev-builder.md}",
                    f"{setup_id} builder prompt mismatch",
                    errors,
                )


def validate_builder(errors: list[str]) -> None:
    build = read_json("build/version.json")
    contract = read_json("config/nddev-contract.json")
    skill = ROOT / "plugins" / "nddev-builder" / "skills" / "nddev-builder" / "SKILL.md"
    agent = ROOT / "plugins" / "nddev-builder" / "agents" / "nddev-builder.md"
    instructions = ROOT / "plugins" / "nddev-builder" / "instructions" / "nddev-builder.md"
    for path in (skill, agent, instructions):
        require(path.is_file(), f"builder native file missing: {path.relative_to(ROOT)}", errors)
    builder = contract.get("builder_capability")
    require(isinstance(builder, dict), "contract builder missing", errors)
    if isinstance(builder, dict):
        require(
            builder.get("projection") == "mimocode-native-config-skills-agents-instructions",
            "builder projection mismatch",
            errors,
        )
        require(builder.get("default_on") is True, "builder default_on mismatch", errors)
        require(builder.get("marketplace") is None, "builder marketplace must be null", errors)
        require(
            builder.get("version") == build.get("nddev_builder_extension_version"),
            "builder version mismatch",
            errors,
        )
    skill_text = skill.read_text(encoding="utf-8") if skill.is_file() else ""
    require("name: nddev-builder" in skill_text, "builder skill name missing", errors)


def validate_absence_of_stale_terms(errors: list[str]) -> None:
    for path in ROOT.rglob("*"):
        if ".git" in path.parts or path.is_dir():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for marker in (PLACEHOLDER_MARKER, *RETIRED_MARKERS):
            require(
                marker not in text,
                f"retired marker {marker!r} found in {path.relative_to(ROOT)}",
                errors,
            )


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


def main() -> int:
    errors: list[str] = []
    validate_versions(errors)
    validate_assets(errors)
    validate_setups(errors)
    validate_builder(errors)
    validate_absence_of_stale_terms(errors)
    validate_shared_ci(errors)
    if errors:
        for error in errors:
            print(error)
        return 1
    print("nddev-mimocode-app public contracts ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
