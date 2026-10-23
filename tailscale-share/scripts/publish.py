#!/usr/bin/env python3
"""Publish static files through separate, persistent Tailscale endpoints."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import quote
from urllib.request import urlopen

PRIVATE_PORT = 8444
PUBLIC_PORT = 8443


def tailscale(*arguments: str) -> str:
    result = subprocess.run(["tailscale", *arguments], capture_output=True, text=True, timeout=45)
    # Direct filesystem serving needs root even on some operator-configured
    # hosts. Elevate only this explicit Serve/Funnel command, never the helper.
    if (result.returncode and arguments and arguments[0] in {"serve", "funnel"}
            and any(argument.startswith("--https=") for argument in arguments)
            and ("Unauthorized" in result.stderr or "must be root" in result.stderr)):
        result = subprocess.run(["sudo", "-n", "tailscale", *arguments], capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Tailscale command failed")
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return result.stdout


def identity() -> str:
    status = json.loads(tailscale("status", "--json"))
    if status.get("BackendState") != "Running":
        raise RuntimeError("Tailscale is disconnected. Run sudo tailscale up, then retry.")
    expected = os.environ.get("TAILSCALE_SHARE_TAILNET")
    actual = status.get("CurrentTailnet", {}).get("Name")
    if expected and actual != expected:
        raise RuntimeError(f"Expected tailnet {expected!r}, found {actual!r}. Check login or TAILSCALE_SHARE_TAILNET.")
    hostname = status.get("Self", {}).get("DNSName", "").rstrip(".")
    if not hostname:
        raise RuntimeError("No MagicDNS name. Enable MagicDNS and HTTPS for this tailnet.")
    return hostname


def share_root() -> Path:
    root = Path(os.environ.get("TAILSCALE_SHARE_ROOT", str(Path.home() / "Public/agent-share"))).expanduser().absolute()
    for component in (root, *root.parents):
        if component.is_symlink():
            raise RuntimeError(f"Share path must not traverse symlinks: {component}")
    return root


def check_tree(path: Path, allow_hidden_root: bool = False) -> None:
    """Copies must not follow links, include dotfiles, or contain special files."""
    items = [path, *path.rglob("*")] if path.is_dir() and not path.is_symlink() else [path]
    for item in items:
        if item.is_symlink():
            raise RuntimeError(f"Refusing symlink: {item}")
        if item.name.startswith(".") and not (allow_hidden_root and item == path):
            raise RuntimeError(f"Refusing hidden file/directory: {item}")
        if not item.is_file() and not item.is_dir():
            raise RuntimeError(f"Not a regular file/directory: {item}")


def endpoint(public: bool) -> tuple[Path, int, str]:
    return share_root() / ("public" if public else "tailnet"), PUBLIC_PORT if public else PRIVATE_PORT, "funnel" if public else "serve"


def check_endpoint(config: dict, host: str, directory: Path, port: int, public: bool) -> bool:
    """Return whether our exact endpoint exists; reject conflicts before changing anything."""
    key = f"{host}:{port}"
    web = config.get("Web", {})
    matching = [name for name in web if name.rsplit(":", 1)[-1] == str(port)]
    tcp = config.get("TCP", {}).get(str(port))
    allowed = config.get("AllowFunnel", {}).get(key, False)
    if not public and allowed:
        raise RuntimeError(f"Port {port} has Funnel enabled; refusing to publish private files.")
    if not matching and tcp is None:
        return False
    expected = {"/": {"Path": str(directory)}}
    if matching != [key] or web[key].get("Handlers") != expected or tcp != {"HTTPS": True}:
        raise RuntimeError(f"Port {port} is already used by another service. The sharing helper will not overwrite it.")
    return bool(allowed) == public


def ensure_endpoint(public: bool = False) -> tuple[Path, str]:
    host = identity()
    directory, port, mode = endpoint(public)
    config = json.loads(tailscale("serve", "status", "--json"))
    active = check_endpoint(config, host, directory, port, public)
    # Refuse a link to another tree even when our route has not been configured yet.
    directory.mkdir(parents=True, exist_ok=True)
    check_tree(directory)
    if not active:
        output = tailscale(mode, "--bg", f"--https={port}", str(directory))
        if output.strip():
            print(output.strip(), file=sys.stderr)
    # Read back actual daemon configuration rather than assuming the command took effect.
    config = json.loads(tailscale("serve", "status", "--json"))
    if not check_endpoint(config, host, directory, port, public):
        raise RuntimeError("Tailscale did not enable the expected endpoint.")
    return directory, f"https://{host}:{port}"


def publish(source: Path, name: str, public: bool = False) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", name):
        raise RuntimeError("Name must be 1–64 lowercase letters, digits, or hyphens, starting with a letter/digit.")
    # Check original path before resolve(), which would conceal a source symlink.
    source = source.expanduser().absolute()
    for component in (source, *source.parents):
        if component.is_symlink():
            raise RuntimeError(f"Source path must not traverse symlinks: {component}")
    check_tree(source)
    directory, base = ensure_endpoint(public)
    root = share_root()
    if source == root or root in source.parents or source in directory.parents:
        raise RuntimeError("Choose an input outside the publishing directory.")
    destination = directory / name
    if destination.exists():
        raise RuntimeError(f"Publication already exists: {destination}. Choose a new --name or remove it first.")
    # Stage beside the served directory so visitors never see a partial copy.
    with tempfile.TemporaryDirectory(prefix=".share-stage-", dir=directory.parent) as temporary:
        staged = Path(temporary) / name
        if source.is_dir():
            shutil.copytree(source, staged, symlinks=True)
            suffix = "/"
        else:
            staged.mkdir()
            shutil.copy2(source, staged / source.name, follow_symlinks=False)
            suffix = "/" + quote(source.name, safe="")
        check_tree(staged)
        staged.rename(destination)
    return f"{base}/{name}{suffix}"


def verify(url: str) -> None:
    try:
        with urlopen(url, timeout=20) as response:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")
            response.read(1)
    except Exception as error:
        raise RuntimeError(f"Copied files, but URL verification failed: {url}: {error}. Check HTTPS, policy, and host connectivity.") from error


def stop(public: bool) -> None:
    host = identity()
    directory, port, mode = endpoint(public)
    config = json.loads(tailscale("serve", "status", "--json"))
    if check_endpoint(config, host, directory, port, public):
        tailscale(mode, f"--https={port}", "off")
    print(f"Stopped {'public' if public else 'tailnet'} endpoint; files retained.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init_parser = commands.add_parser("init", help="Enable persistent sharing of the selected directory")
    init_parser.add_argument("--public", action="store_true")
    publish_parser = commands.add_parser("publish", help="Copy a file or static site, enable sharing, and verify its URL")
    publish_parser.add_argument("source", type=Path)
    publish_parser.add_argument("--name", required=True)
    publish_parser.add_argument("--public", action="store_true")
    commands.add_parser("status", help="Read-only: show identity, folder locations, and Serve configuration")
    stop_parser = commands.add_parser("stop", help="Disable only the selected sharing endpoint")
    stop_parser.add_argument("--public", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.command == "status":
            print(f"Host: {identity()}\nShare root: {share_root()}")
            print(tailscale("serve", "status"))
        elif arguments.command == "stop":
            stop(arguments.public)
        elif arguments.command == "init":
            directory, url = ensure_endpoint(arguments.public)
            print(f"Directory: {directory}\nURL: {url}/")
        else:
            url = publish(arguments.source, arguments.name, arguments.public)
            verify(url)
            print(url)
        return 0
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
