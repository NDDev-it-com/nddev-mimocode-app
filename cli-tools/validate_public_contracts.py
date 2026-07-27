#!/usr/bin/env python3
"""Validate nddev-mimocode-app public contracts without side effects."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import tempfile
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
SEMVER = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:[-+].*)?\Z"
)
EXPECTED = {
    "version": "0.1.9",
    "release_tag": "v0.1.9",
    "published_at": "2026-07-24T06:06:13Z",
    "command": "mimo",
    "official_repository": "XiaomiMiMo/MiMo-Code",
    "official_installer": "https://mimo.xiaomi.com/install",
    "official_installer_size": 15819,
    "official_installer_sha256": "2251667c8b12091a1e65744d892c8abfba008e621b22cf5d39338aa36c12efb2",
    "archive_max_bytes": 268435456,
    "executable_max_bytes": 134217728,
    "staged_version_probe_timeout_seconds": 60.0,
    "fds_latest": "0.1.9",
    "home_env": "MIMOCODE_HOME",
    "config_dir_env": "MIMOCODE_CONFIG_DIR",
    "config_file_env": "MIMOCODE_CONFIG",
    "safe_child_env": [
        "CI",
        "COLORTERM",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "NO_COLOR",
        "SYSTEMROOT",
        "TERM",
    ],
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
ASSET_SIZES = {
    "darwin-arm64": 32411159,
    "darwin-x64-baseline": 34781456,
    "darwin-x64": 34787169,
    "linux-arm64-musl": 43519901,
    "linux-arm64": 44914006,
    "linux-x64-baseline-musl": 43661067,
    "linux-x64-baseline": 44875105,
    "linux-x64-musl": 43947655,
    "linux-x64": 45247960,
    "windows-arm64": 45013275,
    "windows-x64-baseline": 46420456,
    "windows-x64": 46757202,
}


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
    require(version != "0.0.0", "VERSION must not be 0.0.0", errors)
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
    require(
        build.get("official_repository") == EXPECTED["official_repository"],
        "repository mismatch",
        errors,
    )
    require(
        build.get("official_installer") == EXPECTED["official_installer"],
        "installer URL mismatch",
        errors,
    )
    require(
        build.get("official_installer_size") == EXPECTED["official_installer_size"],
        "installer size mismatch",
        errors,
    )
    require(
        build.get("official_installer_sha256") == EXPECTED["official_installer_sha256"],
        "installer SHA-256 mismatch",
        errors,
    )
    release = baseline.get("release")
    install = baseline.get("install")
    require(isinstance(release, dict), "baseline release missing", errors)
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
    if isinstance(install, dict):
        require(
            install.get("fds_latest") == build.get("mimocode_tested"),
            "baseline FDS latest mismatch",
            errors,
        )
        require(
            install.get("script") == EXPECTED["official_installer"],
            "baseline installer URL mismatch",
            errors,
        )
        require(
            install.get("script_size") == EXPECTED["official_installer_size"],
            "baseline installer size mismatch",
            errors,
        )
        require(
            install.get("script_sha256") == EXPECTED["official_installer_sha256"],
            "baseline installer SHA-256 mismatch",
            errors,
        )
        require(
            install.get("package_manager_install") is None,
            "package manager install must be null",
            errors,
        )
    surfaces = baseline.get("native_surfaces")
    require(isinstance(surfaces, dict), "baseline native surfaces missing", errors)
    if isinstance(surfaces, dict):
        require(
            surfaces.get("config_root_env") == EXPECTED["home_env"],
            "baseline config root env mismatch",
            errors,
        )
        require(
            surfaces.get("config_file_env") == EXPECTED["config_file_env"],
            "baseline config file env mismatch",
            errors,
        )
        require(
            surfaces.get("config_dir_env") == EXPECTED["config_dir_env"],
            "baseline config dir env mismatch",
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
                runtime.get("official_repository") == build.get("official_repository"),
                f"{owner} repository mismatch",
                errors,
            )
            require(
                runtime.get("command") == build.get("command"), f"{owner} command mismatch", errors
            )
    software = contract.get("software_install")
    require(isinstance(software, dict), "contract software_install missing", errors)
    if isinstance(software, dict):
        require(
            software.get("tested_version") == build.get("mimocode_tested"),
            "software tested version mismatch",
            errors,
        )
        require(
            software.get("official_installer") == EXPECTED["official_installer"],
            "software installer URL mismatch",
            errors,
        )
        require(
            software.get("official_installer_size") == EXPECTED["official_installer_size"],
            "software installer size mismatch",
            errors,
        )
        require(
            software.get("official_installer_sha256") == EXPECTED["official_installer_sha256"],
            "software installer SHA-256 mismatch",
            errors,
        )
        require(
            software.get("package_manager_install") is None,
            "software package manager install must be null",
            errors,
        )
        require(
            software.get("installer_flags")
            == ["--version", "0.1.9", "--no-modify-path", "--binary", "<verified-binary>"],
            "software installer flags mismatch",
            errors,
        )
        executable_policy = software.get("staged_executable_policy")
        require(
            isinstance(executable_policy, dict),
            "staged executable policy missing",
            errors,
        )
        if isinstance(executable_policy, dict):
            require(
                executable_policy.get("verified_asset_metadata")
                == "references/mimocode-baseline.json:release.assets.darwin-arm64.executable",
                "verified executable metadata owner mismatch",
                errors,
            )
            require(
                executable_policy.get("archive_max_bytes") == EXPECTED["archive_max_bytes"],
                "archive size bound mismatch",
                errors,
            )
            require(
                executable_policy.get("executable_max_bytes")
                == EXPECTED["executable_max_bytes"],
                "executable size bound mismatch",
                errors,
            )
            require(
                executable_policy.get("staged_version_probe_timeout_seconds")
                == EXPECTED["staged_version_probe_timeout_seconds"],
                "staged version probe timeout mismatch",
                errors,
            )
            require(
                executable_policy.get("staged_version_probe_timeout_seconds")
                == nddev_mimocode.STAGED_VERSION_PROBE_TIMEOUT_SECONDS,
                "manager staged version probe timeout mismatch",
                errors,
            )
            require(
                executable_policy.get("official_installer_mode") == "0755",
                "official installer executable mode mismatch",
                errors,
            )
            require(
                executable_policy.get("managed_mode") == "0700",
                "managed executable mode mismatch",
                errors,
            )
    launch = contract.get("runtime_launch")
    require(isinstance(launch, dict), "contract runtime_launch missing", errors)
    if isinstance(launch, dict):
        require(
            launch.get("home_environment_variable") == EXPECTED["home_env"],
            "runtime home env mismatch",
            errors,
        )
        require(
            launch.get("config_environment_variable") == EXPECTED["config_file_env"],
            "runtime config file env mismatch",
            errors,
        )
        require(
            "MIMOCODE_CONFIG=<absolute-target>/config/mimocode.json"
            in str(launch.get("direct_command")),
            "runtime direct command must bind MIMOCODE_CONFIG",
            errors,
        )
        require(
            launch.get("blocked_launch_args")
            == ["--dangerously-skip-permissions", "--never-ask", "--trust", "upgrade"],
            "runtime launch guard mismatch",
            errors,
        )
        require(
            launch.get("environment_inheritance") == "allowlist",
            "runtime environment inheritance mismatch",
            errors,
        )
        require(
            launch.get("safe_inherited_environment") == EXPECTED["safe_child_env"],
            "runtime safe child env mismatch",
            errors,
        )
        require(
            tuple(launch.get("safe_inherited_environment", ()))
            == nddev_mimocode.SAFE_CHILD_INHERITED_ENV_NAMES,
            "manager safe child env mismatch",
            errors,
        )
        require(
            launch.get("token_environment_inheritance") == "stripped",
            "runtime token inheritance mismatch",
            errors,
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
                    asset.get("size") == ASSET_SIZES[key],
                    f"asset size mismatch: {key}",
                    errors,
                )
                require(
                    str(asset.get("url", "")).startswith(
                        "https://github.com/XiaomiMiMo/MiMo-Code/releases/download/v0.1.9/"
                    ),
                    f"asset URL mismatch: {key}",
                    errors,
                )
                if key == "darwin-arm64":
                    require(
                        asset.get("executable")
                        == {
                            "path": "mimo",
                            "archive_mode": "0755",
                            "installer_mode": "0755",
                            "size": 94571234,
                            "sha256": (
                                "faf477a3e0ec0ec1bef1b2fb692c2d9f"
                                "dbba9a5864590deaa23e26b5694cb65f"
                            ),
                        },
                        "darwin-arm64 executable metadata mismatch",
                        errors,
                    )


def validate_launch_environment_regression(errors: list[str]) -> None:
    sentinel = "nddev-public-regression-secret-value"
    safe_parent = {
        "CI": "1",
        "COLORTERM": "truecolor",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "LC_CTYPE": "C.UTF-8",
        "NO_COLOR": "1",
        "SYSTEMROOT": "C:\\Windows",
        "TERM": "xterm-256color",
    }
    secret_parent = {
        "ANTHROPIC_API_KEY": sentinel,
        "AWS_PROFILE": sentinel,
        "AWS_SECRET_ACCESS_KEY": sentinel,
        "AWS_SESSION_TOKEN": sentinel,
        "CUSTOM_PROVIDER_TOKEN": sentinel,
        "DATABASE_URL": sentinel,
        "GEMINI_API_KEY": sentinel,
        "GITHUB_TOKEN": sentinel,
        "GOOGLE_API_KEY": sentinel,
        "MIMO_ACCESS_TOKEN": sentinel,
        "MIMO_API_KEY": sentinel,
        "MIMO_FDS_BASE": sentinel,
        "MIMOCODE_ACCESS_TOKEN": sentinel,
        "MIMOCODE_API_KEY": sentinel,
        "MIMOCODE_AUTH_CONTENT": sentinel,
        "MIMOCODE_CONFIG": sentinel,
        "MIMOCODE_CONFIG_DIR": sentinel,
        "MIMOCODE_CONSOLE_TOKEN": sentinel,
        "MIMOCODE_HOME": sentinel,
        "NPM_TOKEN": sentinel,
        "OPENAI_API_KEY": sentinel,
        "PATH": "/untrusted/bin",
        "USERPROFILE": sentinel,
    }
    original_env = dict(os.environ)
    try:
        os.environ.clear()
        os.environ.update({**safe_parent, **secret_parent})
        with tempfile.TemporaryDirectory(prefix="nddev-mimocode-env-regression.") as raw:
            target = Path(raw) / "target"
            target.mkdir(mode=0o700)
            target.chmod(0o700)
            env = nddev_mimocode.isolated_child_environment(target)
            fixed_names = {
                "APPDATA",
                "HOME",
                "LOCALAPPDATA",
                "MIMOCODE_CONFIG",
                "MIMOCODE_CONFIG_DIR",
                "MIMOCODE_DISABLE_AUTOUPDATE",
                "MIMOCODE_DISABLE_LSP_DOWNLOAD",
                "MIMOCODE_DISABLE_MODELS_FETCH",
                "MIMOCODE_ENABLE_ANALYSIS",
                "MIMOCODE_HOME",
                "MIMOCODE_MIMO_ONLY",
                "MIMOCODE_PURE",
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
            allowed_names = set(EXPECTED["safe_child_env"]) | fixed_names
            require(
                set(env) <= allowed_names,
                "launch env contains non-allowlisted names",
                errors,
            )
            for name in safe_parent:
                require(env.get(name) == safe_parent[name], f"safe env missing: {name}", errors)
            for name in secret_parent:
                require(
                    name not in env or env[name] != sentinel,
                    f"secret env leaked: {name}",
                    errors,
                )
            require(sentinel not in env.values(), "sentinel secret value leaked", errors)
            require(
                env.get("PATH") == nddev_mimocode.SAFE_SYSTEM_PATH,
                "launch PATH mismatch",
                errors,
            )
            require(env.get("SHELL") == "/bin/sh", "launch SHELL mismatch", errors)
            expected_paths = {
                "APPDATA": target / "runtime" / "appdata",
                "HOME": target / "home",
                "LOCALAPPDATA": target / "runtime" / "local-appdata",
                "MIMOCODE_CONFIG": target / "config" / "mimocode.json",
                "MIMOCODE_CONFIG_DIR": target / "config",
                "MIMOCODE_HOME": target,
                "TEMP": target / "runtime" / "tmp",
                "TMP": target / "runtime" / "tmp",
                "TMPDIR": target / "runtime" / "tmp",
                "USERPROFILE": target / "home",
                "XDG_CACHE_HOME": target / "runtime" / "xdg-cache",
                "XDG_CONFIG_HOME": target / "runtime" / "xdg-config",
                "XDG_DATA_HOME": target / "runtime" / "xdg-data",
                "XDG_STATE_HOME": target / "runtime" / "xdg-state",
            }
            for name, expected_path in expected_paths.items():
                require(
                    env.get(name) == str(expected_path),
                    f"isolated launch path mismatch: {name}",
                    errors,
                )
    finally:
        os.environ.clear()
        os.environ.update(original_env)


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
            metadata.get("builder_projection")
            == "native-config-skills-agents-instructions-workflows",
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
    workflow = ROOT / "plugins" / "nddev-builder" / "workflows" / "nddev-builder.js"
    for path in (skill, agent, instructions, workflow):
        require(path.is_file(), f"builder native file missing: {path.relative_to(ROOT)}", errors)
    builder = contract.get("builder_capability")
    require(isinstance(builder, dict), "contract builder missing", errors)
    if isinstance(builder, dict):
        require(
            builder.get("projection")
            == "mimocode-native-config-skills-agents-instructions-workflows",
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


def validate_public_identity(errors: list[str]) -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in ROOT.rglob("*")
        if path.is_file() and ".git" not in path.parts and "__pycache__" not in path.parts
    )
    require("MiMo Code" in combined, "current product name missing", errors)
    require("MiMoCode" in combined, "current product spelling missing", errors)
    require("XiaomiMiMo/MiMo-Code" in combined, "current repository identity missing", errors)
    require("mimo" in combined, "current command identity missing", errors)


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
    validate_launch_environment_regression(errors)
    validate_setups(errors)
    validate_builder(errors)
    validate_public_identity(errors)
    validate_shared_ci(errors)
    if errors:
        for error in errors:
            print(error)
        return 1
    print("nddev-mimocode-app public contracts ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
