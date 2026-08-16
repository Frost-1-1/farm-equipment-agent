#!/usr/bin/env python3
"""
Craigslist RSS Scraper - Simple Version
Uses only Flask + requests (built-in XML parsing)
"""

import os
import json
from datetime import datetime, timedelta
from flask import Flask, render_template_string
from threading import Thread
import time
import xml.etree.ElementTree as ET
try:
    from urllib.request import urlopen
except ImportError:
    from urllib2 import urlopen

RESULTS_FILE = "farm_results.json"

# Craigslist RSS URLs
FEEDS = {
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

def scrape_feed(url):
    """Parse RSS feed - minimal dependencies"""
    listings = []
    try:
        response = urlopen(url, timeout=10)
        tree = ET.parse(response)
        root = tree.getroot()
        
        # Get location from URL
        if 'vancouver' in url:
            location = "Vancouver, BC"
        elif 'calgary' in url:
            location = "Calgary, AB"
        elif 'edmonton' in url:
            location = "Edmonton, AB"
        else:
            location = "Craigslist"
        
        # Parse items
        for item in root.findall('.//item')[:15]:
            try:
                title_elem = item.find('title')
                link_elem = item.find('link')
                desc_elem = item.find('description')
                
                if title_elem is None or link_elem is None:
                    continue
                
                title = title_elem.text or "No title"
                link = link_elem.text or ""
                description = desc_elem.text or "" if desc_elem is not None else ""
                
                # Extract price
                price = "Price not listed"
                if '$' in description:
                    parts = description.split('$')
                    if len(parts) > 1:
                        price_str = parts[1].split()[0]
                        if price_str.replace(',', '').isdigit():
                            price = f"${price_str}"
                
                # Clean description
                clean_desc = description.replace('<br>', ' ')
                for tag in ['<p>', '</p>', '<br/>', '&nbsp;']:
                    clean_desc = clean_desc.replace(tag, '')
                clean_desc = clean_desc[:150].strip()
                
                listings.append({
                    'title': title,
                    'price': price,
                    'url': link,
                    'description': clean_desc,
                    'location': location
                })
            except Exception as e:
                continue
        
        print(f"  ✓ {len(listings)} listings from {location}")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    return listings

def load_results():
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, 'r') as f:
            return json.load(f)
    return {"tractor": [], "bunk_trailer": [], "scissor_hoist": [], "two_post_hoist": [], "last_updated": None}

def save_results(data):
    with open(RESULTS_FILE, 'w') as f:
        json.dump(data, f, indent=2, default=str)

def run_agent():
    """Scrape all feeds"""
    print(f"\n{'='*60}")
    print(f"Scraping at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    
    results = load_results()
    results["last_updated"] = datetime.now().isoformat()
    
    for item_type, feed_urls in FEEDS.items():
        print(f"\n{item_type}:")
        all_listings = []
        for url in feed_urls:
            listings = scrape_feed(url)
            all_listings.extend(listings)
            time.sleep(0.5)
        results[item_type] = all_listings
    
    save_results(results)
    print(f"\n{'='*60}\nDone.\n")

# ============================================================================
# DASHBOARD
# ============================================================================

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Farm Equipment Search</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: #f5f5f5; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: #2c3e50; color: white; padding: 20px; border-radius: 8px; margin-bottom: 30px; }
        .header h1 { font-size: 28px; margin-bottom: 10px; }
        .stats { display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin-top: 15px; }
        .stat { background: rgba(255,255,255,0.1); padding: 15px; border-radius: 6px; }
        .stat-number { font-size: 24px; font-weight: bold; }
        .stat-label { font-size: 12px; opacity: 0.8; margin-top: 5px; }
        .section { background: white; border-radius: 8px; margin-bottom: 25px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow: hidden; }
        .section-title { background: #34495e; color: white; padding: 15px 20px; font-size: 18px; font-weight: bold; }
        .listings { padding: 20px; }
        .listing { border: 1px solid #e0e0e0; border-radius: 6px; padding: 15px; margin-bottom: 15px; }
        .listing-title { font-size: 16px; font-weight: bold; color: #2c3e50; margin-bottom: 8px; }
        .listing-title a { color: #2c3e50; text-decoration: none; }
        .listing-title a:hover { color: #3498db; }
        .listing-price { font-size: 16px; color: #27ae60; font-weight: bold; margin-bottom: 8px; }
        .listing-meta { font-size: 12px; color: #7f8c8d; margin-bottom: 8px; }
        .listing-desc { font-size: 13px; color: #555; margin-bottom: 10px; line-height: 1.4; }
        .listing-link { display: inline-block; background: #3498db; color: white; padding: 6px 12px; border-radius: 4px; text-decoration: none; font-size: 12px; }
        .listing-link:hover { background: #2980b9; }
        .empty { color: #95a5a6; text-align: center; padding: 40px 20px; }
        .note { background: #ecf0f1; padding: 15px; border-radius: 6px; margin-bottom: 20px; font-size: 13px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚜 Farm Equipment Search</h1>
            <p>Real Craigslist Listings - BC & Alberta</p>
            <div class="stats">
                <div class="stat">
                    <div class="stat-number">{{ total }}</div>
                    <div class="stat-label">Listings Found</div>
                </div>
                <div class="stat">
                    <div class="stat-number">{{ updated }}</div>
                    <div class="stat-label">Last Updated</div>
                </div>
            </div>
        </div>

        <div class="note">
            Scrapes real Craigslist listings from Vancouver, Calgary, Edmonton. Updated daily at 6 AM UTC.
        </div>

        {% for title, items, emoji in sections %}
        <div class="section">
            <div class="section-title">{{ emoji }} {{ title }}</div>
            <div class="listings">
                {% if items %}
                    {% for item in items %}
                    <div class="listing">
                        <div class="listing-title">
                            <a href="{{ item.url }}" target="_blank">{{ item.title }}</a>
                        </div>
                        <div class="listing-price">{{ item.price }}</div>
                        <div class="listing-meta">📍 {{ item.location }}</div>
                        {% if item.description %}
                        <div class="listing-desc">{{ item.description }}</div>
                        {% endif %}
                        <a href="{{ item.url }}" target="_blank" class="listing-link">View →</a>
                    </div>
                    {% endfor %}
                {% else %}
                    <div class="empty">No listings found. Check back later.</div>
                {% endif %}
            </div>
        </div>
        {% endfor %}

    </div>
</body>
</html>
"""

@app.route('/')
def index():
    data = load_results()
    total = sum(len(data.get(k, [])) for k in ["tractor", "bunk_trailer", "scissor_hoist", "two_post_hoist"])
    
    updated = "Never"
    if data.get("last_updated"):
        dt = datetime.fromisoformat(data["last_updated"])
        updated = dt.strftime("%b %d %I:%M %p")
    
    sections = [
        ("24-40 HP Tractors with Front Loader", data.get("tractor", []), "🚜"),
        ("36-40' Bunk House Trailers (2020+)", data.get("bunk_trailer", []), "🏠"),
        ("Scissor Hoists (7,000 lb capacity)", data.get("scissor_hoist", []), "🔧"),
        ("2-Post Vehicle Hoists (10,000-12,000 lb)", data.get("two_post_hoist", []), "🚙"),
    ]
    
    return render_template_string(HTML, total=total, updated=updated, sections=sections)

def scheduler():
    """Run at 6 AM daily"""
    while True:
        now = datetime.now()
        target = now.replace(hour=6, minute=0, second=0, microsecond=0)
        if now > target:
            target += timedelta(days=1)
        wait = (target - now).total_seconds()
        time.sleep(wait)
        run_agent()

if __name__ == "__main__":
    # Don't scrape on startup - just start the dashboard
    # Scheduler will handle daily scrapes
    Thread(target=scheduler, daemon=True).start()
    print("Dashboard starting at http://localhost:5000")
    print("Scraping scheduled for 6 AM daily")
    app.run(host="0.0.0.0", port=5000, debug=False)
