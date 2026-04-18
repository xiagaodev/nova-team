"""
Nova Platform Configuration Module
Supports environment-specific configs (development/production)
"""

import os
import yaml
from pathlib import Path

# Config file locations (checked in order)
CONFIG_LOCATIONS = [
    Path("config.yaml"),
    Path.home() / ".nova-platform" / "config.yaml",
    Path("/etc/nova-platform/config.yaml"),
]

DEFAULT_CONFIG = {
    "environment": "development",
    "server": {
        "host": "0.0.0.0",
        "port": 5000,
        "debug": False,
    },
    "logging": {
        "level": "INFO",
        "file": "~/.nova-platform/nova-server.log",
        "max_size_mb": 10,
        "backup_count": 3,
    },
    "database": {
        "path": "~/.nova-platform/nova.db",
    },
    "star_office": {
        "enabled": True,
        "static_path": "templates/star_office/static",
    },
}


def load_config(config_path: str = None) -> dict:
    """Load configuration from file."""
    config = DEFAULT_CONFIG.copy()
    
    # Expand paths in default config
    for key in ["logging", "database"]:
        if key in config:
            for k, v in config[key].items():
                if isinstance(v, str) and v.startswith("~"):
                    config[key][k] = os.path.expanduser(v)
    
    # Find config file
    if config_path:
        cfg_file = Path(config_path)
    else:
        cfg_file = None
        for loc in CONFIG_LOCATIONS:
            if loc.exists():
                cfg_file = loc
                break
    
    if cfg_file and cfg_file.exists():
        with open(cfg_file, 'r') as f:
            user_config = yaml.safe_load(f) or {}
        
        # Merge user config
        for section, values in user_config.items():
            if isinstance(values, dict) and section in config:
                config[section].update(values)
            else:
                config[section] = values
        
        # Expand paths again after merge
        for key in ["logging", "database"]:
            if key in config:
                for k, v in config[key].items():
                    if isinstance(v, str) and v.startswith("~"):
                        config[key][k] = os.path.expanduser(v)
    
    return config


def get_config() -> dict:
    """Get current configuration (cached)."""
    if not hasattr(get_config, '_config'):
        get_config._config = load_config()
    return get_config._config


def reload_config():
    """Force reload configuration."""
    if hasattr(get_config, '_config'):
        del get_config._config
    return get_config()


# Convenience accessors
def get_server_config() -> dict:
    """Get server configuration."""
    return get_config().get("server", DEFAULT_CONFIG["server"])


def get_env() -> str:
    """Get current environment (development/production)."""
    return get_config().get("environment", "development")


def is_production() -> bool:
    """Check if running in production mode."""
    return get_env() == "production"


def is_development() -> bool:
    """Check if running in development mode."""
    return get_env() == "development"
