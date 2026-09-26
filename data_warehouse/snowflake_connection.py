from __future__ import annotations

import os
import tomllib
from pathlib import Path


def find_connection_profile(connection_name: str) -> tuple[dict, Path]:
    """Load a Snowflake profile without relying on process-specific app dirs."""
    candidates: list[Path] = []
    explicit = os.getenv("SNOWFLAKE_CONFIG_FILE")
    snowflake_home = os.getenv("SNOWFLAKE_HOME")
    local_app_data = os.getenv("LOCALAPPDATA")

    if explicit:
        candidates.append(Path(explicit).expanduser())
    if snowflake_home:
        candidates.extend(
            [Path(snowflake_home) / "config.toml", Path(snowflake_home) / "connections.toml"]
        )
    if local_app_data:
        candidates.extend(
            [Path(local_app_data) / "snowflake" / "config.toml",
             Path(local_app_data) / "snowflake" / "connections.toml"]
        )
    # Path.home() remains reliable when VS Code does not inherit LOCALAPPDATA.
    candidates.extend(
        [Path.home() / "AppData" / "Local" / "snowflake" / "config.toml",
         Path.home() / "AppData" / "Local" / "snowflake" / "connections.toml",
         Path.home() / ".snowflake" / "config.toml",
         Path.home() / ".snowflake" / "connections.toml"]
    )

    searched: list[str] = []
    for candidate in dict.fromkeys(path.resolve() for path in candidates):
        searched.append(str(candidate))
        if not candidate.is_file():
            continue
        payload = tomllib.loads(candidate.read_text(encoding="utf-8"))
        profiles = payload.get("connections", {}) if candidate.name == "config.toml" else payload
        profile = profiles.get(connection_name)
        if isinstance(profile, dict):
            resolved = dict(profile)
            if resolved.get("token_file_path"):
                token_path = os.path.expandvars(str(resolved["token_file_path"]))
                resolved["token_file_path"] = str(Path(token_path).expanduser())
            return resolved, candidate

    searched_paths = "\n  - ".join(searched)
    raise RuntimeError(
        f"Snowflake connection profile '{connection_name}' was not found. "
        f"Searched:\n  - {searched_paths}\n"
        "Create the profile from data_warehouse/connections.toml.example."
    )


def connect(connection_name: str, bundle_root: Path | None = None):
    try:
        import snowflake.connector
    except ImportError as exc:
        raise RuntimeError(
            "Missing snowflake-connector-python. Run "
            "'.\\data_warehouse\\install_snowflake_tools.ps1' first."
        ) from exc

    if os.name == "nt" and not os.getenv("REQUESTS_CA_BUNDLE"):
        from build_windows_ca_bundle import build

        root = bundle_root or Path(__file__).resolve().parent
        bundle = root / ".venv" / "windows-ca-bundle.pem"
        if not bundle.exists():
            build(bundle)
        os.environ["REQUESTS_CA_BUNDLE"] = str(bundle)
        os.environ.setdefault("SSL_CERT_FILE", str(bundle))

    profile, config_path = find_connection_profile(connection_name)
    print(f"Using Snowflake profile '{connection_name}' from {config_path}", flush=True)
    return snowflake.connector.connect(**profile, autocommit=True)
