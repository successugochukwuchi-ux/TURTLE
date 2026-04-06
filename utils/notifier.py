import requests
import streamlit as st

def send_telegram_message(message):
    """Send message to Telegram if configured"""
    # Retrieve credentials from secrets or environment
    # In Streamlit Cloud, use st.secrets["telegram_bot_token"]
    try:
        token = st.secrets.get("telegram_bot_token")
        chat_id = st.secrets.get("telegram_chat_id")
        
        if not token or not chat_id:
            # Fallback for local testing if secrets not set
            token = st.session_state.get("tg_token")
            chat_id = st.session_state.get("tg_chat_id")

        if token and chat_id:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            response = requests.post(url, json=payload, timeout=5)
            if response.status_code != 200:
                st.warning(f"Telegram API Error: {response.text}")
    except Exception as e:
        st.error(f"Failed to send notification: {str(e)}")
