# 🐢 Turtle Trader — Web Control Panel

A Flask-based control panel for the Turtle Trading scanner. Runs the signal loop
in a background thread — **no terminal needed, works 24/7**.

## Features
- Start / Stop the scanner from the browser
- Switch between XAUUSD and BTC/USDT
- Adjust timeframe, entry/exit periods, check interval
- Live signal log (auto-refreshes every 5s)
- Telegram test button
- Ready for Railway or Render

---

## Deploy to Render (Free, 24/7 with UptimeRobot)

### 1. Push to GitHub
```bash
git init
git add .
git commit -m "init"
git remote add origin https://github.com/YOUR_USERNAME/turtle-trader-gui.git
git push -u origin main
```

### 2. Create Render Web Service
1. Go to [render.com](https://render.com) → **New** → **Web Service**
2. Connect your GitHub repo
3. Render auto-detects everything from `render.yaml` — just click **Deploy**
4. You get a free subdomain: `your-app.onrender.com`

### 3. Prevent sleeping with UptimeRobot (free)
Render's free tier sleeps after 15 min of no traffic. Fix:
1. Go to [uptimerobot.com](https://uptimerobot.com) → create free account
2. **New Monitor** → HTTP(s) → paste your `your-app.onrender.com` URL
3. Set interval to **5 minutes** → Save
4. UptimeRobot pings your app every 5 min — it never sleeps

### 4. Open your URL — done
Click **▶ START SCANNER**, close the browser.
Telegram alerts keep arriving 24/7.

---

## Deploy to Railway (Alternative, $5/mo for 24/7)

1. Go to [railway.app](https://railway.app) → **New Project** → Deploy from GitHub
2. Settings → Networking → **Generate Domain**
3. Free tier sleeps — upgrade to Hobby ($5/mo) to avoid it

---

## Local Development
```bash
pip install -r requirements.txt
python app.py
# Open http://localhost:5000
```

---

## Credentials
Hardcoded in `app.py`:
```python
TG_TOKEN = "your_token_here"
TG_CHAT  = "your_chat_id_here"
```

---

## Important Notes
- Always use **1 gunicorn worker** — the background scanner thread must live in the same process
- Signal log persists to `signals.json` on disk (resets on redeploy)
- Both `render.yaml` and `railway.json` + `Procfile` are included — works on either platform
