"""
Configuration Loader - Loads settings from config.csv (local or GitHub)
"""

import pandas as pd
import requests
import base64
import io
import logging

log = logging.getLogger(__name__)

# GitHub constants
GITHUB_TOKEN = "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"
GITHUB_OWNER = "successugochukwuchi-ux"
GITHUB_REPO = "TURTLE"
GITHUB_PATH = "config.csv"
GITHUB_BRANCH = "main"


def get_github_file():
    """Fetch the current config.csv from GitHub."""
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_PATH}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    params = {"ref": GITHUB_BRANCH}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            return content
        elif response.status_code == 404:
            log.warning("config.csv not found in GitHub repo")
            return None
        else:
            log.error(f"Error fetching file from GitHub: {response.status_code}")
            return None
    except Exception as e:
        log.error(f"Exception fetching config from GitHub: {str(e)}")
        return None


def load_config_from_github():
    """Load configuration from GitHub config.csv."""
    content = get_github_file()
    if content:
        try:
            df = pd.read_csv(io.StringIO(content))
            if len(df) > 0:
                row = df.iloc[0]
                return {
                    "strategy": str(row.get("strategy", "Turtle Trading")),
                    "instrument": str(row.get("instrument", "XAUUSD")),
                    "timeframe": str(row.get("timeframe", "1h")),
                    "entry_period": int(row.get("entry_period", 20)),
                    "exit_period": int(row.get("exit_period", 10)),
                    "risk_reward_ratio": float(row.get("risk_reward_ratio", 2.5)),
                    "scan_interval_seconds": int(row.get("scan_interval_seconds", 60)),
                    "tg_token": str(row.get("tg_token", "")),
                    "tg_chat": str(row.get("tg_chat", "")),
                    "tv_username": str(row.get("tv_username", "")),
                    "tv_password": str(row.get("tv_password", "")),
                }
        except Exception as e:
            log.error(f"Error parsing config CSV: {str(e)}")
    
    # Return default config if loading fails
    return get_default_config()


def get_default_config():
    """Return default configuration."""
    return {
        "strategy": "Turtle Trading",
        "instrument": "XAUUSD",
        "timeframe": "1h",
        "entry_period": 20,
        "exit_period": 10,
        "risk_reward_ratio": 2.5,
        "scan_interval_seconds": 60,
        "tg_token": "8639500812:AAG2cLSiKyRVwazanOlN--PInxu4-m58ES0",
        "tg_chat": "-5137913812",
        "tv_username": "",
        "tv_password": "",
    }


def load_config_local(filepath="config.csv"):
    """Load configuration from local config.csv file."""
    try:
        df = pd.read_csv(filepath)
        if len(df) > 0:
            row = df.iloc[0]
            return {
                "strategy": str(row.get("strategy", "Turtle Trading")),
                "instrument": str(row.get("instrument", "XAUUSD")),
                "timeframe": str(row.get("timeframe", "1h")),
                "entry_period": int(row.get("entry_period", 20)),
                "exit_period": int(row.get("exit_period", 10)),
                "risk_reward_ratio": float(row.get("risk_reward_ratio", 2.5)),
                "scan_interval_seconds": int(row.get("scan_interval_seconds", 60)),
                "tg_token": str(row.get("tg_token", "")),
                "tg_chat": str(row.get("tg_chat", "")),
                "tv_username": str(row.get("tv_username", "")),
                "tv_password": str(row.get("tv_password", "")),
            }
    except Exception as e:
        log.error(f"Error loading local config: {str(e)}")
    
    return get_default_config()
