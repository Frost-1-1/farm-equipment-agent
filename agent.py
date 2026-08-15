#!/usr/bin/env python3
"""
Craigslist RSS Scraper - Real Equipment Listings
Pulls actual listings from Craigslist RSS feeds
Shows real prices and links
Runs daily at 6 AM
"""

import os
import json
import re
import feedparser
from datetime import datetime, timedelta
from flask import Flask, render_template_string
from threading import Thread
import time

RESULTS_FILE = "farm_results.json"

# Craigslist RSS URLs for equipment searches
CRAIGSLIST_FEEDS = {
    "tractor": [
        "https://vancouver.craigslist.org/search/gra?query=tractor+front+loader&format=rss",
        "https://calgary.craigslist.org/search/gra?query=tractor+front+loader&format=rss",
        "https://edmonton.craigslist.org/search/gra?query=tractor+front+loader&format=rss",
    ],
    "bunk_trailer": [
        "https://vancouver.craigslist.org/search/rva?query=bunk+house+trailer&format=rss",
        "https://calgary.craigslist.org/search/rva?query=bunk+house+trailer&format=rss",
        "https://edmonton.craigslist.org/search/rva?query=bunk+house+trailer&format=rss",
    ],
    "scissor_hoist": [
        "https://vancouver.craigslist.org/search/tls?query=scissor+hoist&format=rss",
        "https://calgary.craigslist.org/search/tls?query=scissor+hoist&format=rss",
        "https://edmonton.craigslist.org/search/tls?query=scissor+hoist&format=rss",
    ],
    "two_post_hoist": [
        "https://vancouver.craigslist.org/search/tls?query=2+post+hoist&format=rss",
        "https://calgary.craigslist.org/search/tls?query=2+post+hoist&format=rss",
        "https://edmonton.craigslist.org/search/tls?query=2+post+hoist&format=rss",
    ]
}

# ============================================================================
# RSS SCRAPING
# ============================================================================

def scrape_rss_feed(url):
    """Parse Craigslist RSS feed and extract listings"""
    listings = []
    try:
        feed = feedparser.parse(url)
        
        for entry in feed.entries[:15]:  # Get up to 15 listings per feed
            try:
                title = entry.get('title', 'No title')
                link = entry.get('link', '')
                description = entry.get('description', '')
                
                # Extract price from description (usually in format $XXX)
                price = "Price not listed"
                if '$' in description:
                    # Get the price string
                    parts = description.split('$')
                    if len(parts) > 1:
                        price_part = parts[1].split('<')[0].strip()
                        price = f"${price_part}"
                
                # Extract location from description (usually at end)
                location = "Craigslist"
                if url.find('vancouver') > 0:
                    location = "Vancouver, BC"
                elif url.find('calgary') > 0:
                    location = "Calgary, AB"
                elif url.find('edmonton') > 0:
                    location = "Edmonton, AB"
                
                # Clean description (remove HTML tags)
                clean_desc = description.replace('<br>', ' ').replace('<p>', '').replace('</p>', '')
                # Remove HTML tags
                clean_desc = re.sub('<[^<]+?>', '', clean_desc).strip()
                clean_desc = clean_desc[:200]  # First 200 chars
                
                listings.append({
                    'title': title,
                    'price': price,
                    'url': link,
                    'description': clean_desc,
                    'location': location
                })
            except Exception as e:
                print(f"  Error parsing entry: {e}")
                continue
        
        print(f"  Found {len(listings)} listings from {url.split('?')[0].split('/')[-1]}")
    except Exception as e:
        print(f"  Error fetching RSS: {e}")
    
    return listings

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
    """Scrape all Craigslist feeds"""
    print(f"\n{'='*60}")
    print(f"Craigslist Scraper - Run at {datetime.now()}")
    print(f"{'='*60}\n")
    
    results = load_results()
    results["last_updated"] = datetime.now().isoformat()
    
    for item_type, feeds in CRAIGSLIST_FEEDS.items():
        print(f"\nScraping {item_type}...")
        all_listings = []
        
        for feed_url in feeds:
            listings = scrape_rss_feed(feed_url)
            all_listings.extend(listings)
            time.sleep(1)  # Be respectful
        
        results[item_type] = all_listings
        print(f"  Total for {item_type}: {len(all_listings)} listings")
    
    save_results(results)
    print(f"\n{'='*60}")
    print(f"Scraping complete. Results saved.")
    print(f"{'='*60}\n")

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
        .listing-title { font-size: 16px; font-weight: bold; color: #2c3e50; margin-bottom: 8px; }
        .listing-price { font-size: 16px; color: #27ae60; font-weight: bold; margin-bottom: 8px; }
        .listing-meta { font-size: 12px; color: #7f8c8d; margin-bottom: 8px; }
        .listing-description { font-size: 13px; color: #555; margin-bottom: 10px; line-height: 1.4; }
        .listing-link { display: inline-block; background: #3498db; color: white; padding: 8px 16px; border-radius: 4px; text-decoration: none; font-size: 13px; }
        .listing-link:hover { background: #2980b9; }
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
            <p>Real Craigslist Listings - Lower Mainland to Edmonton</p>
            <div class="stats">
                <div class="stat">
                    <div class="stat-number">{{ total_results }}</div>
                    <div class="stat-label">Real Listings</div>
                </div>
                <div class="stat">
                    <div class="stat-number">{{ last_updated }}</div>
                    <div class="stat-label">Last Updated</div>
                </div>
            </div>
        </div>

        <div class="refresh-note">
            ℹ️ Real Craigslist listings from Vancouver, Calgary, and Edmonton
            <br>Agent runs automatically once per day at 6 AM UTC
            <br>Click listing title to view on Craigslist
            <br><button class="button" onclick="location.reload()">🔄 Refresh Dashboard</button>
        </div>

        {% for section_title, items, emoji in sections %}
        <div class="section">
            <div class="section-title">{{ emoji }} {{ section_title }}</div>
            <div class="listings">
                {% if items %}
                    {% for listing in items %}
                    <div class="listing">
                        <div class="listing-title">
                            <a href="{{ listing.url }}" target="_blank" style="color: #2c3e50; text-decoration: none;">
                                {{ listing.title }}
                            </a>
                        </div>
                        <div class="listing-price">{{ listing.price }}</div>
                        <div class="listing-meta">📍 {{ listing.location }}</div>
                        {% if listing.description %}
                        <div class="listing-description">{{ listing.description }}</div>
                        {% endif %}
                        <a href="{{ listing.url }}" target="_blank" class="listing-link">View on Craigslist →</a>
                    </div>
                    {% endfor %}
                {% else %}
                    <div class="empty">No listings found yet. Check back later or refresh the page.</div>
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
        ("36-40' Bunk House Trailers", data.get("bunk_trailer", []), "🏠"),
        ("Scissor Hoists (7,000 lb)", data.get("scissor_hoist", []), "🔧"),
        ("2-Post Vehicle Hoists (10,000-12,000 lb)", data.get("two_post_hoist", []), "🚙"),
    ]
    
    return render_template_string(
        HTML,
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
        print(f"Next scrape in {wait_seconds/3600:.1f} hours")
        
        time.sleep(wait_seconds)
        run_agent()

if __name__ == "__main__":
    # Scrape once on startup
    run_agent()
    
    # Start daily scheduler
    scheduler_thread = Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Start dashboard
    print("Dashboard live at: http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
