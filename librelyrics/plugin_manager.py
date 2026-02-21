"""Plugin manager for installing, removing, and listing plugins.

Uses pip subprocess for package management to leverage pip's
dependency resolution.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from importlib.metadata import distributions

from librelyrics.registry import load_all_plugins

logger = logging.getLogger('librelyrics.plugin_manager')


def install_plugin(package: str) -> bool:
    """Install a plugin package using pip.

    Supports:
    - PyPI packages: `librelyrics-foo`
    - Git URLs: `git+https://github.com/user/librelyrics-foo.git`
    - Local paths: `/path/to/plugin`

    Args:
        package: Package name, git URL, or local path.

    Returns:
        True if installation succeeded, False otherwise.
    """
    logger.info(f"Installing plugin: {package}")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            logger.info(f"Successfully installed: {package}")
            return True
        else:
            logger.error(f"Failed to install {package}: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"Error installing plugin: {e}")
        return False


def remove_plugin(package: str) -> bool:
    """Remove a plugin package using pip.

    Args:
        package: Package name to uninstall.

    Returns:
        True if removal succeeded, False otherwise.
    """
    logger.info(f"Removing plugin: {package}")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "-y", package],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            logger.info(f"Successfully removed: {package}")
            return True
        else:
            logger.error(f"Failed to remove {package}: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"Error removing plugin: {e}")
        return False


def list_plugins(config: dict | None = None) -> list[dict]:
    """List all installed plugins with their metadata.

    Args:
        config: Optional configuration dict.

    Returns:
        List of dictionaries with plugin info:
        - name: Plugin display name
        - package: Python package name
        - version: Package version (if available)
        - position: Resolved position (1 = tried first)
        - requires_auth: Whether plugin requires authentication
    """
    plugins = load_all_plugins(config)
    config = config or {}
    result = []

    for position, plugin_cls in enumerate(plugins, 1):
        meta = plugin_cls.META
        module_name = plugin_cls.__module__

        # Format lyrics types as readable strings
        lyrics_types = [lt.name.replace('_', ' ').title() for lt in meta.lyrics_types]

        plugin_info = {
            'name': meta.name,
            'position': position,
            'requires_auth': meta.requires_auth,
            'description': meta.description,
            'module': module_name,
            'lyrics_types': lyrics_types,
        }

        # Try to get package version
        try:
            pkg_name = module_name.split('.')[0]
            for dist in distributions():
                if dist.name.replace('-', '_') == pkg_name.replace('-', '_'):
                    plugin_info['version'] = dist.version
                    plugin_info['package'] = dist.name
                    break
        except Exception:
            pass

        result.append(plugin_info)

    return result


def format_plugin_list(plugins: list[dict]) -> str:
    """Format plugin list for display.

    Args:
        plugins: List of plugin info dictionaries.

    Returns:
        Formatted string for display.
    """
    if not plugins:
        return "No plugins installed."

    lines = ["Installed plugins:", ""]

    for plugin in plugins:
        version = f" v{plugin.get('version', '?')}" if 'version' in plugin else ""
        auth = " (requires auth)" if plugin['requires_auth'] else ""

        lines.append(f"  • {plugin['name']}{version}{auth}")
        if plugin.get('description'):
            lines.append(f"    {plugin['description']}")
        lines.append(f"    Module: {plugin['module']}")
        lines.append("")


    return "\n".join(lines)
