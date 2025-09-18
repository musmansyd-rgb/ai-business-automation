# dashboard.py
import os
from datetime import datetime, timedelta, timezone

import requests
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# --- CONFIG ---
load_dotenv()

BREVO_API_KEY = os.getenv("BREVO_API_KEY") or ""
USE_MOCK = os.getenv("USE_MOCK", "0") == "1"
BREVO_BASE = "https://api.brevo.com/v3"
BREVO_HEADERS = {"api-key": BREVO_API_KEY, "Content-Type": "application/json"}

# --- MOCK HELPERS ---
def mock_brevo_contacts():
    now = datetime.now(timezone.utc)  # tz-aware
    return {
        "contacts": [
            {"email": "a@example.com", "id": 1, "createdAt": (now - timedelta(days=10)).isoformat()},
            {"email": "b@example.com", "id": 2, "createdAt": (now - timedelta(days=3)).isoformat()},
            {"email": "c@example.com", "id": 3, "createdAt": (now - timedelta(days=1)).isoformat()},
        ],
        "count": 3,
    }

def mock_brevo_campaigns():
    return {
        "count": 2,
        "campaigns": [
            {"id": 1, "name": "Launch", "status":"sent", 
             "statistics":{"globalStats": {"sent":100,"delivered":95,"uniqueClicks":20,"uniqueViews":40}}},
            {"id": 2, "name": "Weekly", "status":"sent", 
             "statistics":{"globalStats": {"sent":200,"delivered":190,"uniqueClicks":50,"uniqueViews":80}}},
        ],
    }

# --- API CALLS ---
@st.cache_data(ttl=60)
def fetch_brevo_contacts(limit=50, offset=0):
    if USE_MOCK or not BREVO_API_KEY:
        return mock_brevo_contacts()
    url = f"{BREVO_BASE}/contacts"
    resp = requests.get(url, headers=BREVO_HEADERS, params={"limit": limit, "offset": offset}, timeout=15)
    resp.raise_for_status()
    return resp.json()

@st.cache_data(ttl=60)
def fetch_brevo_campaigns(limit=50, offset=0):
    if USE_MOCK or not BREVO_API_KEY:
        return mock_brevo_campaigns()
    url = f"{BREVO_BASE}/emailCampaigns"
    resp = requests.get(url, headers=BREVO_HEADERS, params={"limit": limit, "offset": offset}, timeout=15)
    resp.raise_for_status()
    return resp.json()

# --- PARSERS ---
def parse_contacts(resp):
    df = pd.DataFrame(resp.get("contacts", []))
    if not df.empty and "createdAt" in df.columns:
        # Always tz-aware UTC
        df["createdAt"] = pd.to_datetime(df["createdAt"], utc=True)
    return df

def parse_campaigns(resp):
    rows = []
    for c in resp.get("campaigns", []):
        stats = c.get("statistics", {}).get("globalStats", {})
        rows.append({
            "id": c.get("id"),
            "name": c.get("name"),
            "status": c.get("status"),
            "sent": stats.get("sent", 0),
            "delivered": stats.get("delivered", 0),
            "uniqueClicks": stats.get("uniqueClicks", 0),
            "uniqueViews": stats.get("uniqueViews", 0),
        })
    return pd.DataFrame(rows)

# --- UI ---
st.set_page_config(page_title="Day 11 — Business Dashboard", layout="wide")
st.title("📊 Day 11 — Analytics Dashboard")

# Sidebar
st.sidebar.header("Settings")
BREVO_API_KEY = st.sidebar.text_input("Brevo API Key", value=BREVO_API_KEY, type="password")
USE_MOCK = st.sidebar.checkbox("Use mock data", value=USE_MOCK)

# --- Leads (Brevo contacts) ---
st.subheader("Leads Overview")
contacts_resp = fetch_brevo_contacts(limit=50)
contacts_df = parse_contacts(contacts_resp)
total_leads = int(contacts_resp.get("count", len(contacts_df)))

col1, col2 = st.columns(2)
col1.metric("Total Leads", total_leads)
if not contacts_df.empty:
    # Compare tz-aware to tz-aware
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    new_7d = contacts_df[contacts_df["createdAt"] >= cutoff]
    col2.metric("New Leads (7d)", len(new_7d))
else:
    col2.metric("New Leads (7d)", "N/A")

st.markdown("---")

# --- Social Engagement (CSV upload + mock fallback) ---
st.subheader("Social Engagement (CSV or Mock)")

uploaded_file = st.file_uploader("Upload CSV (columns: platform, reach, clicks, likes)", type=["csv"])
if uploaded_file:
    try:
        df_social = pd.read_csv(uploaded_file, encoding="utf-8")
    except UnicodeDecodeError:
        df_social = pd.read_csv(uploaded_file, encoding="latin1")

    # Normalize column names
    df_social.columns = [c.strip().lower() for c in df_social.columns]

    required_cols = {"platform", "reach", "clicks", "likes"}
    if required_cols.issubset(df_social.columns):
        st.dataframe(df_social)
        st.bar_chart(df_social.set_index("platform")[["reach", "clicks", "likes"]])
    else:
        st.error(f"CSV must contain columns: {', '.join(required_cols)}. Found: {list(df_social.columns)}")
else:
    st.info("No CSV uploaded. Showing mock social data.")
    df_social = pd.DataFrame([
        {"platform":"Twitter","reach":1200,"clicks":50,"likes":30},
        {"platform":"Facebook","reach":800,"clicks":40,"likes":20},
        {"platform":"LinkedIn","reach":600,"clicks":25,"likes":15},
    ])
    st.bar_chart(df_social.set_index("platform"))


# --- Email Campaign Performance (Brevo) ---
st.subheader("Email Campaign Performance")
campaigns_resp = fetch_brevo_campaigns(limit=50)
campaigns_df = parse_campaigns(campaigns_resp)

if campaigns_df.empty:
    st.info("No campaigns found.")
else:
    campaigns_df["open_rate_est"] = campaigns_df.apply(
        lambda r: (r["uniqueViews"] / r["delivered"] * 100) if r["delivered"] else 0, axis=1)
    campaigns_df["click_rate_est"] = campaigns_df.apply(
        lambda r: (r["uniqueClicks"] / r["delivered"] * 100) if r["delivered"] else 0, axis=1)

    st.dataframe(campaigns_df[["id","name","status","sent","delivered","uniqueViews","uniqueClicks",
                               "open_rate_est","click_rate_est"]])

    st.bar_chart(campaigns_df.set_index("name")[["delivered","uniqueClicks"]])

st.markdown("---")
st.caption("🔑 Brevo API live. Social data via CSV upload or mock demo. All times in UTC.")
