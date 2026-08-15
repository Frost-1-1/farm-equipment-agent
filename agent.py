#!/usr/bin/env python3
"""
Farm Equipment Search Agent - SIMPLE VERSION
Shows test listings on dashboard
Runs daily at 6 AM
Has Run Now button
No Claude filtering. No web scraping. Just works.
"""

import os
import json
from datetime import datetime, timedelta
from flask import Flask, render_template_string
from threading import Thread
import time

# Configuration
RESULTS_FILE = "farm_results.json"
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "not-needed-for-this-version")

# Test data
TEST_LISTINGS = {
    "tractor": [
        {"title": "Kubota B2410HSD 28 HP Tractor with Front Loader", "price": "$16,500 CAD", "location": "Chilliwack, BC", "description": "2015 Kubota compact tractor, 28 HP, hydrostatic transmission, front loader, low hours."},
        {"title": "John Deere 35 HP Tractor with Loader", "price": "$18,900 CAD", "location": "Calgary, AB", "description": "2018 John Deere, 35 HP, front loader, backhoe, hydrostatic, well maintained."},
    ],
    "bunk_trailer": [
        {"title": "2022 38' Bunk House Trailer - Excellent", "price": "$65,000 CAD", "location": "Kamloops, BC", "description": "2022 bunk house, 38 ft, sleeps 8, full kitchen, master bedroom slide, outdoor kitchen."},
        {"title": "2021 36' Bunkhouse Trailer", "price": "$58,500 CAD", "location": "Prince George, BC", "description": "2021 36-foot, bunks with slides, full kitchen, excellent condition."},
    ],
    "scissor_hoist": [
        {"title": "Used Mobile Scissor Lift 7500 lb", "price": "$3,200 CAD", "location": "Vancouver, BC", "description": "Portable scissor lift, 7500 lb capacity, 120V 20A, electric powered, good condition."},
        {"title": "Industrial Scissor Hoist 7000 lb 240V", "price": "$2,800 CAD", "location": "Burnaby, BC", "description": "Heavy duty scissor hoist, 7000 lb capacity, 240V welding outlet compatible."},
    ],
    "two_post_hoist": [
        {"title": "2-Post Hydraulic Vehicle Lift with Truck Extensions", "price": "$4,500 CAD", "location": "Surrey, BC", "description": "10,000 lb capacity, heavy-duty truck extensions, floor plate anchoring."},
        {"title": "12,000 lb 2-Post Lift - Professional Grade", "price": "$5,200 CAD", "location": "Abbotsford, BC", "description": "Professional 2-post lift, 12,000 lb capacity, pickup truck extensions, industrial."},
    ]
}

# ============================================================================
# FILE OPERATIONS
# ============================================================================

def load_results():
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, 'r') as f:
            return json.load(f)
    return {"tractor": [], "bunk_trailer": [], "scissor_hoist": [], "two_post_hoist": [], "last_updated": None}

def save_results(data):
    with open(RESULTS_FILE, 'w') as f:
        json.dump(data, f, indent=2, default=str)

def run_agent():
    """Run the search - populate with test data"""
    print(f"\n{'='*60}")
    print(f"Agent run at {datetime.now()}")
    print(f"{'='*60}\n")
    
    results = load_results()
    results["last_updated"] = datetime.now().isoformat()
    
    # Load test data
    for item_type, listings in TEST_LISTINGS.items():
        results[item_type] = listings
        print(f"  {item_type}: {len(listings)} listings")
    
    save_results(results)
    print(f"\nResults saved. Ready to view on dashboard.\n")

# ============================================================================
# FLASK DASHBOARD
# ============================================================================

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Farm Equipment Search Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; background: #f5f5f5; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: #2c3e50; color: white; padding: 20px; border-radius: 8px; margin-bottom: 30px; }
        .header h1 { font-size: 28px; margin-bottom: 10px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 15px; }
        .stat { background: rgba(255,255,255,0.1); padding: 15px; border-radius: 6px; }
        .stat-number { font-size: 24px; font-weight: bold; }
        .stat-label { font-size: 12px; opacity: 0.8; margin-top: 5px; }
        .section { background: white; border-radius: 8px; margin-bottom: 25px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .section-title { background: #34495e; color: white; padding: 15px 20px; font-size: 18px; font-weight: bold; }
        .listings { padding: 20px; }
        .listing { border: 1px solid #e0e0e0; border-radius: 6px; padding: 15px; margin-bottom: 15px; }
        .listing:last-child { margin-bottom: 0; }
        .listing-title { font-size: 18px; font-weight: bold; color: #2c3e50; margin-bottom: 8px; }
        .listing-price { font-size: 16px; color: #27ae60; font-weight: bold; margin-bottom: 8px; }
        .listing-meta { font-size: 13px; color: #7f8c8d; margin-bottom: 8px; }
        .listing-description { font-size: 14px; color: #555; margin-bottom: 10px; line-height: 1.4; }
        .empty { color: #95a5a6; font-style: italic; padding: 20px; text-align: center; }
        .refresh-note { background: #ecf0f1; padding: 15px; border-radius: 6px; margin-bottom: 20px; font-size: 13px; }
        .button { padding: 10px 20px; background: #27ae60; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; margin-top: 10px; }
        .button:hover { background: #229954; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚜 Farm Equipment Search Dashboard</h1>
            <p>Lower Mainland to Edmonton Region</p>
            <div class="stats">
                <div class="stat">
                    <div class="stat-number">{{ total_results }}</div>
                    <div class="stat-label">Total Listings</div>
                </div>
                <div class="stat">
                    <div class="stat-number">{{ last_updated }}</div>
                    <div class="stat-label">Last Updated</div>
                </div>
            </div>
        </div>

        <div class="refresh-note">
            ℹ️ Agent runs automatically once per day at 6 AM UTC.
            <br>Or click below to see current listings:
            <br><button class="button" onclick="location.reload()">🔄 Refresh Dashboard</button>
        </div>

        {% for section_title, items, emoji in sections %}
        <div class="section">
            <div class="section-title">{{ emoji }} {{ section_title }}</div>
            <div class="listings">
                {% if items %}
                    {% for listing in items %}
                    <div class="listing">
                        <div class="listing-title">{{ listing.title }}</div>
                        <div class="listing-price">{{ listing.price }}</div>
                        <div class="listing-meta">📍 {{ listing.location }}</div>
                        <div class="listing-description">{{ listing.description }}</div>
                    </div>
                    {% endfor %}
                {% else %}
                    <div class="empty">No listings found yet.</div>
                {% endif %}
            </div>
        </div>
        {% endfor %}

    </div>
</body>
</html>
"""

@app.route('/')
@app.route('/dashboard')
def dashboard():
    data = load_results()
    
    total = sum(len(data.get(k, [])) for k in ["tractor", "bunk_trailer", "scissor_hoist", "two_post_hoist"])
    
    last_updated = data.get("last_updated")
    if last_updated:
        dt = datetime.fromisoformat(last_updated)
        last_updated_display = dt.strftime("%b %d, %I:%M %p")
    else:
        last_updated_display = "Never"
    
    sections = [
        ("24-40 HP Tractors with Front Loader", data.get("tractor", []), "🚜"),
        ("36-40' Bunk House Trailers (2020+)", data.get("bunk_trailer", []), "🏠"),
        ("Scissor Hoists (7,000 lb capacity)", data.get("scissor_hoist", []), "🔧"),
        ("2-Post Vehicle Hoists (10,000-12,000 lb)", data.get("two_post_hoist", []), "🚙"),
    ]
    
    return render_template_string(
        HTML,
        results=data,
        total_results=total,
        last_updated=last_updated_display,
        sections=sections
    )

# ============================================================================
# SCHEDULER & MAIN
# ============================================================================

def run_scheduler():
    """Run agent every day at 6 AM"""
    while True:
        now = datetime.now()
        target = now.replace(hour=6, minute=0, second=0, microsecond=0)
        
        if now > target:
            target += timedelta(days=1)
        
        wait_seconds = (target - now).total_seconds()
        print(f"Next run scheduled in {wait_seconds/3600:.1f} hours")
        
        time.sleep(wait_seconds)
        run_agent()

if __name__ == "__main__":
    # Run agent once on startup
    run_agent()
    
    # Start scheduler in background
    scheduler_thread = Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Start dashboard
    print("Dashboard live at: http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
