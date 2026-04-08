"""
Control Panel for Turtle Trader
Allows users to configure bot parameters and update config.csv
Now includes GitHub integration to push configuration changes to the repository.
"""

import streamlit as st
import pandas as pd
import os
import requests
from datetime import datetime
import base64

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🎛️ Turtle Trader Control Panel",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── Constants ─────────────────────────────────────────────────────────────────
CONFIG_FILE = "config.csv"
GITHUB_REPO = "successugochukwuchi-ux/TURTLE"
GITHUB_PAT = "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"
GITHUB_BRANCH = "main"

# ── Helper Functions ──────────────────────────────────────────────────────────

def load_config():
    """Load configuration from CSV file."""
    if not os.path.exists(CONFIG_FILE):
        # Create default config if it doesn't exist
        default_config = {
            'parameter': [
                'strategy_choice', 'mode', 'symbol', 'interval', 
                'entry_period', 'exit_period', 'scan_interval',
                'risk_reward_ratio', 'tv_username', 'tv_password',
                'tg_token', 'tg_chat'
            ],
            'value': [
                'Turtle Trading', 'gold', 'BTC/USDT', '1h',
                '20', '10', '60',
                '2.5', '', '',
                '8639500812:AAG2cLSiKyRVwazanOlN--PInxu4-m58ES0', '-5137913812'
            ]
        }
        df = pd.DataFrame(default_config)
        df.to_csv(CONFIG_FILE, index=False)
        return df
    
    return pd.read_csv(CONFIG_FILE)


def save_config(config_dict):
    """Save configuration to CSV file and push to GitHub."""
    df = pd.DataFrame(list(config_dict.items()), columns=['parameter', 'value'])
    df.to_csv(CONFIG_FILE, index=False)
    
    # Push to GitHub
    github_result = push_config_to_github(config_dict)
    
    return True, github_result


def push_config_to_github(config_dict):
    """Push config.csv to GitHub repository using Personal Access Token."""
    try:
        # Read the current config file content
        with open(CONFIG_FILE, 'r') as f:
            file_content = f.read()
        
        # Encode content to base64
        encoded_content = base64.b64encode(file_content.encode()).decode('utf-8')
        
        # GitHub API endpoint
        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{CONFIG_FILE}"
        
        # First, get the current file SHA (needed for update)
        headers = {
            "Authorization": f"token {GITHUB_PAT}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        # Try to get existing file info
        response = requests.get(api_url, headers=headers, params={"ref": GITHUB_BRANCH})
        
        sha = None
        if response.status_code == 200:
            # File exists, get its SHA
            file_info = response.json()
            sha = file_info.get("sha")
        
        # Prepare the commit payload
        commit_message = f"Update config.csv - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        payload = {
            "message": commit_message,
            "content": encoded_content,
            "branch": GITHUB_BRANCH
        }
        
        if sha:
            payload["sha"] = sha
        
        # Put (create or update) the file
        response = requests.put(api_url, headers=headers, json=payload)
        
        if response.status_code in [200, 201]:
            result = response.json()
            return {
                "success": True,
                "message": f"✅ Config pushed to GitHub successfully!",
                "commit_url": result.get("commit", {}).get("html_url", ""),
                "sha": result.get("content", {}).get("sha", "")[:7]
            }
        else:
            error_msg = response.json().get("message", "Unknown error")
            return {
                "success": False,
                "message": f"❌ GitHub push failed: {error_msg}",
                "status_code": response.status_code
            }
            
    except Exception as e:
        return {
            "success": False,
            "message": f"❌ GitHub push error: {str(e)}"
        }


def get_config_value(df, param_name, default=None):
    """Get a specific parameter value from config."""
    row = df[df['parameter'] == param_name]
    if len(row) > 0:
        return row.iloc[0]['value']
    return default


# ── Session State Initialization ──────────────────────────────────────────────
if "last_saved" not in st.session_state:
    st.session_state.last_saved = None

# ── Main UI ───────────────────────────────────────────────────────────────────
st.title("🎛️ Turtle Trader Control Panel")
st.markdown("""
Configure your trading bot parameters here. Changes will be saved to `config.csv` 
and will be automatically loaded when the main scanner app starts.
""")

# Load current configuration
config_df = load_config()

with st.form("config_form"):
    st.subheader("📊 Strategy Settings")
    
    # Strategy Selection
    strategy_choice = st.selectbox(
        "Choose Strategy",
        ["Turtle Trading", "1-Minute Scalping", "MA Ribbon Entry", "Bollinger Band Scalping"],
        index=0 if get_config_value(config_df, 'strategy_choice', 'Turtle Trading') == 'Turtle Trading' else 
               ["Turtle Trading", "1-Minute Scalping", "MA Ribbon Entry", "Bollinger Band Scalping"].index(
                   get_config_value(config_df, 'strategy_choice', 'Turtle Trading')
               ) if get_config_value(config_df, 'strategy_choice', 'Turtle Trading') in ["Turtle Trading", "1-Minute Scalping", "MA Ribbon Entry", "Bollinger Band Scalping"] else 0,
        help="Select your trading strategy. Each has optimized parameters for different timeframes."
    )
    
    st.subheader("🏷️ Market Settings")
    
    # Asset Type
    mode = st.radio(
        "Asset Type", 
        ["gold", "crypto"], 
        index=0 if get_config_value(config_df, 'mode', 'gold') == 'gold' else 1,
        horizontal=True
    )
    
    # Crypto Symbol (only relevant if crypto mode)
    crypto_symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
    saved_symbol = get_config_value(config_df, 'symbol', 'BTC/USDT')
    symbol_index = crypto_symbols.index(saved_symbol) if saved_symbol in crypto_symbols else 0
    symbol = st.selectbox("Crypto Pair", crypto_symbols, index=symbol_index)
    
    # Timeframe
    timeframes = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
    saved_interval = get_config_value(config_df, 'interval', '1h')
    interval_index = timeframes.index(saved_interval) if saved_interval in timeframes else 4
    interval = st.selectbox("Timeframe", timeframes, index=interval_index)
    
    # Strategy-specific parameters
    st.subheader("⚙️ Strategy Parameters")
    
    if strategy_choice == "Turtle Trading":
        saved_entry = int(get_config_value(config_df, 'entry_period', '20'))
        saved_exit = int(get_config_value(config_df, 'exit_period', '10'))
        entry = st.slider("Entry Period", 5, 50, saved_entry, 1)
        exit_p = st.slider("Exit Period", 5, 50, saved_exit, 1)
    elif strategy_choice == "1-Minute Scalping":
        st.info("Uses 13 & 26 EMA + Stochastic (14,3,3)")
        entry = 20
        exit_p = 10
    elif strategy_choice == "MA Ribbon Entry":
        st.info("Uses 5, 8, 13 SMA ribbon")
        entry = 15
        exit_p = 10
    elif strategy_choice == "Bollinger Band Scalping":
        st.info("Uses 20 SMA ± 2 StdDev")
        entry = 20
        exit_p = 10
    
    # Risk Management
    st.subheader("💰 Risk Management")
    saved_rr = float(get_config_value(config_df, 'risk_reward_ratio', '2.5'))
    risk_reward_ratio = st.number_input(
        "Risk/Reward Ratio",
        min_value=0.5,
        max_value=5.0,
        value=saved_rr,
        step=0.1,
        help="Set your desired risk/reward ratio. TP will be calculated as SL distance × this ratio."
    )
    
    # Scanner Settings
    st.subheader("🔍 Scanner Settings")
    saved_scan_interval = int(get_config_value(config_df, 'scan_interval', '60'))
    scan_interval = st.slider("Scan Interval (seconds)", 10, 300, saved_scan_interval, 10)
    
    # Telegram Settings
    st.subheader("📱 Telegram Bot Settings")
    saved_tg_token = get_config_value(config_df, 'tg_token', '8639500812:AAG2cLSiKyRVwazanOlN--PInxu4-m58ES0')
    saved_tg_chat = get_config_value(config_df, 'tg_chat', '-5137913812')
    tg_token = st.text_input("Telegram Bot Token", value=saved_tg_token, help="Your Telegram bot token from @BotFather")
    tg_chat = st.text_input("Telegram Chat ID", value=saved_tg_chat, help="The chat ID where signals will be sent")
    
    # TradingView Settings
    st.subheader("📺 TradingView Credentials (Optional)")
    saved_tv_user = get_config_value(config_df, 'tv_username', '')
    saved_tv_pass = get_config_value(config_df, 'tv_password', '')
    tv_username = st.text_input("TV Username", value=saved_tv_user, help="TradingView username for premium data")
    tv_password = st.text_input("TV Password", value=saved_tv_pass, type="password", help="TradingView password")
    
    st.divider()
    
    # Submit button
    submitted = st.form_submit_button("💾 Save Configuration", type="primary", use_container_width=True)

if submitted:
    # Build config dictionary
    config_dict = {
        'strategy_choice': strategy_choice,
        'mode': mode,
        'symbol': symbol,
        'interval': interval,
        'entry_period': str(entry),
        'exit_period': str(exit_p),
        'scan_interval': str(scan_interval),
        'risk_reward_ratio': str(risk_reward_ratio),
        'tg_token': tg_token,
        'tg_chat': tg_chat,
        'tv_username': tv_username,
        'tv_password': tv_password
    }
    
    # Save to CSV and push to GitHub
    _, github_result = save_config(config_dict)
    st.session_state.last_saved = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Show save results
    if github_result.get("success"):
        st.success(github_result["message"])
        if github_result.get("commit_url"):
            st.markdown(f"[🔗 View commit on GitHub]({github_result['commit_url']})")
    else:
        st.warning(github_result.get("message", "GitHub push failed"))
    
    st.info("📝 The main scanner app will use these settings on next access.")
    
    # Show summary
    with st.expander("📋 Configuration Summary"):
        st.write(f"**Strategy:** {strategy_choice}")
        st.write(f"**Market:** {mode.upper()} ({symbol if mode == 'crypto' else 'XAUUSD'})")
        st.write(f"**Timeframe:** {interval}")
        st.write(f"**Entry Period:** {entry}")
        st.write(f"**Exit Period:** {exit_p}")
        st.write(f"**Risk/Reward Ratio:** 1:{risk_reward_ratio}")
        st.write(f"**Scan Interval:** {scan_interval} seconds")
        st.write(f"**Telegram Chat:** {tg_chat}")
        st.write(f"**TradingView:** {'Configured' if tv_username else 'Not configured'}")

# Display current configuration
st.divider()
st.subheader("📄 Current Configuration File")
st.code(open(CONFIG_FILE).read(), language="csv")

# Footer
st.divider()
st.markdown("""
<div style='text-align: center; color: gray;'>
    🎛️ Control Panel · Turtle Trader System<br>
    Last saved: {}
</div>
""".format(st.session_state.last_saved if st.session_state.last_saved else "Never"), unsafe_allow_html=True)
