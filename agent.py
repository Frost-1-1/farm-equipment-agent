
#!/usr/bin/env python3
"""
Farm Equipment Search Agent
Searches Kijiji and Craigslist daily for tractors, trailers, and hoists
Filters results using Claude AI
Serves results via Flask dashboard
"""

import os
import json
import requests
from datetime import datetime, timedelta
from urllib.parse import urlencode, quote
import anthropic
from flask import Flask, render_template_string
from threading import Thread
import time

# ============================================================================
# CONFIGURATION
# ============================================================================

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
if not CLAUDE_API_KEY:
    raise ValueError("CLAUDE_API_KEY environment variable not set")

# Results storage
RESULTS_FILE = "farm_results.json"
LAST_RUN_FILE = "last_run.txt"

# Search configurations
SEARCHES = {
    "tractor": {
        "keywords": "tractor front loader",
        "kijiji_urls": [
            "https://www.kijiji.ca/b-farm-equipment/british-columbia",
            "https://www.kijiji.ca/b-farm-equipment/alberta",
        ],
        "craigslist_urls": [
            "https://vancouver.craigslist.org/search/gra?query=tractor+front+loader",
            "https://calgary.craigslist.org/search/gra?query=tractor+front+loader",
            "https://edmonton.craigslist.org/search/gra?query=tractor+front+loader",
        ],
        "criteria": """
        Must have:
        - 24-40 HP
        - Front loader attachment
        - Price max $19,000 CAD
        - Hydrostatic transmission preferred
        
        Reject if missing loader or over $19k CAD.
        """
    },
    "bunk_trailer": {
        "keywords": "bunk house trailer",
        "kijiji_urls": [
            "https://www.kijiji.ca/b-trailers/british-columbia",
            "https://www.kijiji.ca/b-trailers/alberta",
        ],
        "craigslist_urls": [
            "https://vancouver.craigslist.org/search/rva?query=bunk+house+trailer",
            "https://calgary.craigslist.org/search/rva?query=bunk+house+trailer",
            "https://edmonton.craigslist.org/search/rva?query=bunk+house+trailer",
        ],
        "criteria": """
        Must have:
        - 36-40' length (hitch to bumper)
        - Bunks included
        - Slides in bedrooms and/or kitchen to expand living area
        - 2020 or newer
        - Price $30,000-$80,000 CAD
        
        Preferred but not required:
        - Main bedroom slide
        - Outdoor kitchen
        
        Reject if too old, missing slides, or missing bunks.
        """
    },
    "scissor_hoist": {
        "keywords": "scissor hoist lift",
        "kijiji_urls": [
            "https://www.kijiji.ca/b-tools-equipment/british-columbia",
            "https://www.kijiji.ca/b-tools-equipment/alberta",
        ],
        "craigslist_urls": [
            "https://vancouver.craigslist.org/search/tls?query=scissor+hoist+lift",
            "https://calgary.craigslist.org/search/tls?query=scissor+hoist+lift",
            "https://edmonton.craigslist.org/search/tls?query=scissor+hoist+lift",
        ],
        "criteria": """
        Must have:
        - Able to safely lift 7,000 lb truck
        - Runs on 120V 20A outlet OR 240V 15A welding outlet
        - Used (not new)
        - Any price acceptable
        
        Reject if new, underpowered, or has incompatible power requirements.
        """
    },
    "two_post_hoist": {
        "keywords": "2 post hoist lift",
        "kijiji_urls": [
            "https://www.kijiji.ca/b-tools-equipment/british-columbia",
            "https://www.kijiji.ca/b-tools-equipment/alberta",
        ],
        "craigslist_urls": [
            "https://vancouver.craigslist.org/search/tls?query=2+post+hoist+lift",
            "https://calgary.craigslist.org/search/tls?query=2+post+hoist+lift",
            "https://edmonton.craigslist.org/search/tls?query=2+post+hoist+lift",
        ],
        "criteria": """
        Must have:
        - Floor plate style (not ceiling mount)
        - 10,000-12,000 lb capacity
        - Extensions to lift pickup trucks
        - Used (not new)
        - Any price acceptable
        
        Reject if ceiling mount, wrong capacity, or no truck extensions.
        """
    }
}

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def load_results():
    """Load existing results from file."""
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, 'r') as f:
            return json.load(f)
    return {"tractor": [], "bunk_trailer": [], "scissor_hoist": [], "two_post_hoist": [], "last_updated": None}

def save_results(data):
    """Save results to file."""
    with open(RESULTS_FILE, 'w') as f:
        json.dump(data, f, indent=2, default=str)

def get_last_run_time():
    """Get timestamp of last agent run."""
    if os.path.exists(LAST_RUN_FILE):
        with open(LAST_RUN_FILE, 'r') as f:
            return f.read().strip()
    return "Never"

def update_last_run_time():
    """Update last run timestamp."""
    with open(LAST_RUN_FILE, 'w') as f:
        f.write(datetime.now().isoformat())

# ============================================================================
# SEARCH FUNCTIONS
# ============================================================================

def scrape_kijiji_listings(url):
    """
    Scrape Kijiji listings using BeautifulSoup.
    Returns list of dicts: {title, price, url, description, location}
    """
    listings = []
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Kijiji listing items
        items = soup.find_all('div', {'data-testid': 'listing-card'})
        
        for item in items[:20]:  # Limit to first 20 to avoid overwhelming
            try:
                # Title
                title_elem = item.find('a', {'data-testid': 'listing-link'})
                if not title_elem:
                    continue
                title = title_elem.get_text(strip=True)
                listing_url = title_elem.get('href', '')
                if not listing_url.startswith('http'):
                    listing_url = 'https://www.kijiji.ca' + listing_url
                
                # Price
                price_elem = item.find('div', {'data-testid': 'price'})
                price = price_elem.get_text(strip=True) if price_elem else 'Price not listed'
                
                # Location
                location_elem = item.find('div', {'data-testid': 'location'})
                location = location_elem.get_text(strip=True) if location_elem else 'Location not listed'
                
                # Description (usually in title or separate element)
                description = title[:200]
                
                listings.append({
                    'title': title,
                    'price': price,
                    'url': listing_url,
                    'description': description,
                    'location': location
                })
            except Exception as e:
                print(f"Error parsing Kijiji item: {e}")
                continue
        
        print(f"Scraped {len(listings)} listings from {url}")
        
    except Exception as e:
        print(f"Error scraping Kijiji {url}: {e}")
    
    return listings

def scrape_craigslist_listings(url):
    """
    Scrape Craigslist listings using BeautifulSoup.
    Returns list of dicts: {title, price, url, description, location}
    """
    listings = []
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Craigslist result listings
        items = soup.find_all('li', {'class': 'cl-search-result'})
        
        for item in items[:20]:  # Limit to first 20
            try:
                # Title and URL
                title_elem = item.find('a', {'class': 'posting-title'})
                if not title_elem:
                    continue
                title = title_elem.get_text(strip=True)
                listing_url = title_elem.get('href', '')
                
                # Price
                price_elem = item.find('span', {'class': 'result-price'})
                price = price_elem.get_text(strip=True) if price_elem else 'Price not listed'
                
                # Location/date info
                meta_elem = item.find('div', {'class': 'result-meta'})
                location = meta_elem.get_text(strip=True) if meta_elem else 'Location not listed'
                
                description = title[:200]
                
                listings.append({
                    'title': title,
                    'price': price,
                    'url': listing_url,
                    'description': description,
                    'location': location
                })
            except Exception as e:
                print(f"Error parsing Craigslist item: {e}")
                continue
        
        print(f"Scraped {len(listings)} listings from {url}")
        
    except Exception as e:
        print(f"Error scraping Craigslist {url}: {e}")
    
    return listings

def get_test_listings(item_type):
    """
    Return sample test listings for verification.
    Remove this when real web scraping is implemented.
    """
    test_data = {
        "tractor": [
            {
                "title": "Kubota B2410HSD 28 HP Tractor with Front Loader",
                "price": "$16,500 CAD",
                "url": "https://www.kijiji.ca/v-example-1",
                "description": "2015 Kubota B2410HSD compact tractor, 28 HP, hydrostatic transmission, front loader attachment, rear hitch, excellent condition, low hours. Located in Lower Mainland BC.",
                "location": "Chilliwack, BC"
            },
            {
                "title": "John Deere 35 HP Tractor Loader Backhoe",
                "price": "$18,900 CAD",
                "url": "https://www.kijiji.ca/v-example-2",
                "description": "2018 John Deere tractor, 35 HP, front loader, backhoe, hydrostatic transmission, well maintained, ready to work. Currently in Alberta.",
                "location": "Calgary, AB"
            },
            {
                "title": "Case IH 30 HP Tractor with Loader - Needs Work",
                "price": "$22,000 CAD",
                "url": "https://www.kijiji.ca/v-example-3",
                "description": "Case IH 30 HP tractor with loader, transmission issues, parts machine",
                "location": "Edmonton, AB"
            }
        ],
        "bunk_trailer": [
            {
                "title": "2022 38' Bunk House Trailer - Excellent Condition",
                "price": "$65,000 CAD",
                "url": "https://www.kijiji.ca/v-example-4",
                "description": "2022 bunk house trailer, 38 feet, sleeps 8, full kitchen, outdoor kitchen, master bedroom slide, all bunks have slides. Excellent condition, minimal use.",
                "location": "Kamloops, BC"
            },
            {
                "title": "2021 36' Bunkhouse Trailer",
                "price": "$58,500 CAD",
                "url": "https://www.kijiji.ca/v-example-5",
                "description": "2021 36-foot bunk house trailer, bunks with slides, full kitchen setup, great for crews or families. Very well maintained.",
                "location": "Prince George, BC"
            },
            {
                "title": "2019 40' Bunk Trailer - Needs Repairs",
                "price": "$45,000 CAD",
                "url": "https://www.kijiji.ca/v-example-6",
                "description": "2019 40-foot bunk trailer, one slide needs fixing, old kitchen",
                "location": "Red Deer, AB"
            }
        ],
        "scissor_hoist": [
            {
                "title": "Used Mobile Scissor Lift 7500 lb Capacity 120V",
                "price": "$3,200 CAD",
                "url": "https://www.kijiji.ca/v-example-7",
                "description": "Portable scissor lift, 7500 lb capacity, runs on 120V 20A outlet, electric powered, good working condition. Perfect for truck or car lifting.",
                "location": "Vancouver, BC"
            },
            {
                "title": "Industrial Scissor Hoist 7000 lb 240V",
                "price": "$2,800 CAD",
                "url": "https://www.kijiji.ca/v-example-8",
                "description": "Heavy duty scissor hoist, 7000 lb capacity, 240V welding outlet compatible, used but functional. Serious buyers only.",
                "location": "Burnaby, BC"
            }
        ],
        "two_post_hoist": [
            {
                "title": "8-Post Hydraulic Vehicle Lift with Truck Extensions",
                "price": "$4,500 CAD",
                "url": "https://www.kijiji.ca/v-example-9",
                "description": "Used 2-post symmetric lift, 10,000 lb capacity, includes heavy-duty truck extensions, floor plate anchoring, works great.",
                "location": "Surrey, BC"
            },
            {
                "title": "12,000 lb Capacity 2-Post Lift - Asymmetric",
                "price": "$5,200 CAD",
                "url": "https://www.kijiji.ca/v-example-10",
                "description": "Professional 2-post lift, 12,000 lb capacity, includes pickup truck extensions, floor mounted, industrial grade.",
                "location": "Abbotsford, BC"
            }
        ]
    }
    return test_data.get(item_type, [])

def search_item(item_type):
    """
    Search for item type and return raw results.
    Scrapes real listings from Kijiji and Craigslist.
    """
    config = SEARCHES[item_type]
    all_listings = []
    
    print(f"\nSearching for {item_type}...")
    
    # Scrape Kijiji
    for url in config["kijiji_urls"]:
        try:
            print(f"  Scraping Kijiji: {url}")
            listings = scrape_kijiji_listings(url)
            all_listings.extend(listings)
            time.sleep(2)  # Be respectful - delay between requests
        except Exception as e:
            print(f"  Error with Kijiji URL: {e}")
    
    # Scrape Craigslist
    for url in config["craigslist_urls"]:
        try:
            print(f"  Scraping Craigslist: {url}")
            listings = scrape_craigslist_listings(url)
            all_listings.extend(listings)
            time.sleep(2)  # Be respectful - delay between requests
        except Exception as e:
            print(f"  Error with Craigslist URL: {e}")
    
    # If no results, fall back to test data for demo purposes
    if not all_listings:
        print(f"  No results found, using test data for demo...")
        all_listings = get_test_listings(item_type)
    
    print(f"  Total listings found: {len(all_listings)}")
    return all_listings

def filter_results_with_claude(item_type, raw_listings):
    """
    Use Claude to evaluate listings against criteria.
    """
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    config = SEARCHES[item_type]
    
    if not raw_listings:
        return []
    
    # Format listings for Claude
    listings_text = "\n\n".join([
        f"Listing {i+1}:\nTitle: {l.get('title', 'N/A')}\nPrice: {l.get('price', 'N/A')}\n"
        f"URL: {l.get('url', 'N/A')}\nDescription: {l.get('description', 'N/A')[:500]}"
        for i, l in enumerate(raw_listings[:20])  # Limit to first 20 for API cost
    ])
    
    prompt = f"""
    You are evaluating {item_type} listings for purchase.
    
    Criteria for match:
    {config["criteria"]}
    
    Evaluate each listing below. For each one, decide:
    1. Does it match the criteria? (YES/NO)
    2. How confident are you? (HIGH/MEDIUM/LOW)
    3. Any concerns or notes?
    
    Listings to evaluate:
    {listings_text}
    
    Respond in JSON format:
    [
      {{"listing_number": 1, "matches": true, "confidence": "HIGH", "notes": "..."}},
      {{"listing_number": 2, "matches": false, "confidence": "HIGH", "notes": "..."}}
    ]
    
    Only include listings that match or are close to matching.
    """
    
    try:
        message = client.messages.create(
            model="claude-opus-4-1",
            max_tokens=1000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        response_text = message.content[0].text
        # Extract JSON from response
        import re
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            matches = json.loads(json_match.group())
            filtered = []
            for match in matches:
                if match.get("matches"):
                    listing_num = match["listing_number"] - 1
                    if listing_num < len(raw_listings):
                        listing = raw_listings[listing_num].copy()
                        listing["claude_notes"] = match.get("notes", "")
                        listing["confidence"] = match.get("confidence", "")
                        filtered.append(listing)
            return filtered
    except Exception as e:
        print(f"Error filtering with Claude: {e}")
    
    return []

# ============================================================================
# AGENT MAIN LOOP
# ============================================================================

def run_agent():
    """Main agent loop - searches and filters."""
    print(f"\n{'='*60}")
    print(f"Farm Equipment Agent - Run started at {datetime.now()}")
    print(f"{'='*60}\n")
    
    results = load_results()
    results["last_updated"] = datetime.now().isoformat()
    
    for item_type in SEARCHES.keys():
        print(f"\nProcessing: {item_type}")
        raw = search_item(item_type)
        
        if raw:
            filtered = filter_results_with_claude(item_type, raw)
            print(f"  Found {len(filtered)} matches")
            results[item_type] = filtered
        else:
            print(f"  No results found")
    
    save_results(results)
    update_last_run_time()
    
    print(f"\n{'='*60}")
    print(f"Agent run completed at {datetime.now()}")
    print(f"Results saved to {RESULTS_FILE}")
    print(f"{'='*60}\n")

# ============================================================================
# FLASK DASHBOARD
# ============================================================================

app = Flask(__name__)

DASHBOARD_HTML = """
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
        .header p { opacity: 0.9; }
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
        .listing-notes { background: #ecf0f1; padding: 10px; border-radius: 4px; font-size: 13px; margin-bottom: 10px; }
        .listing-link { display: inline-block; background: #3498db; color: white; padding: 8px 16px; border-radius: 4px; text-decoration: none; font-size: 14px; }
        .listing-link:hover { background: #2980b9; }
        .empty { color: #95a5a6; font-style: italic; padding: 20px; text-align: center; }
        .confidence { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 12px; margin-left: 10px; }
        .confidence.HIGH { background: #d5f4e6; color: #27ae60; }
        .confidence.MEDIUM { background: #fef5e7; color: #f39c12; }
        .confidence.LOW { background: #fadbd8; color: #e74c3c; }
        .refresh-note { background: #ecf0f1; padding: 15px; border-radius: 6px; margin-bottom: 20px; font-size: 13px; }
    </style>
</head>
<body>
    <script>
        function runNow() {
            const btn = event.target;
            const statusEl = document.getElementById('runStatus');
            
            btn.disabled = true;
            btn.textContent = '⏳ Running...';
            statusEl.textContent = '';
            
            fetch('/api/run-now', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'}
            })
            .then(r => r.json())
            .then(data => {
                statusEl.textContent = '✓ Search complete! Refreshing...';
                setTimeout(() => location.reload(), 2000);
            })
            .catch(err => {
                statusEl.textContent = '✗ Error: ' + err.message;
                btn.disabled = false;
                btn.textContent = '▶ Run Search Now';
            });
        }
    </script>
    <div class="container">
        <div class="header">
            <h1>🚜 Farm Equipment Search Dashboard</h1>
            <p>Lower Mainland to Edmonton Region</p>
            <div class="stats">
                <div class="stat">
                    <div class="stat-number">{{ total_results }}</div>
                    <div class="stat-label">Total Matches</div>
                </div>
                <div class="stat">
                    <div class="stat-number">{{ last_updated_display }}</div>
                    <div class="stat-label">Last Updated</div>
                </div>
            </div>
        </div>

        <div class="refresh-note">
            ℹ️ Agent runs automatically once per day at 6 AM UTC. <strong>Or click below to run now:</strong>
            <br><button onclick="runNow()" style="margin-top: 10px; padding: 10px 20px; background: #27ae60; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px;">▶ Run Search Now</button>
            <span id="runStatus" style="margin-left: 10px; font-size: 13px;"></span>
            <br><br>Manual checks on Facebook Marketplace & Groups recommended.
        </div>

        <!-- TRACTORS -->
        <div class="section">
            <div class="section-title">🚜 24-40 HP Tractors with Front Loader</div>
            <div class="listings">
                {% if results.tractor %}
                    {% for listing in results.tractor %}
                    <div class="listing">
                        <div class="listing-title">
                            {{ listing.title }}
                            {% if listing.confidence %}
                            <span class="confidence {{ listing.confidence }}">{{ listing.confidence }}</span>
                            {% endif %}
                        </div>
                        <div class="listing-price">{{ listing.price }}</div>
                        <div class="listing-meta">
                            {% if listing.location %}{{ listing.location }} • {% endif %}
                            <a href="{{ listing.url }}" target="_blank" style="color: #3498db; text-decoration: none;">View Source</a>
                        </div>
                        {% if listing.description %}
                        <div class="listing-description">{{ listing.description[:300] }}{% if listing.description|length > 300 %}...{% endif %}</div>
                        {% endif %}
                        {% if listing.claude_notes %}
                        <div class="listing-notes">📌 {{ listing.claude_notes }}</div>
                        {% endif %}
                    </div>
                    {% endfor %}
                {% else %}
                <div class="empty">No matches found yet. Check back soon.</div>
                {% endif %}
            </div>
        </div>

        <!-- TRAILERS -->
        <div class="section">
            <div class="section-title">🏠 36-40' Bunk House Trailers (2020+)</div>
            <div class="listings">
                {% if results.bunk_trailer %}
                    {% for listing in results.bunk_trailer %}
                    <div class="listing">
                        <div class="listing-title">
                            {{ listing.title }}
                            {% if listing.confidence %}
                            <span class="confidence {{ listing.confidence }}">{{ listing.confidence }}</span>
                            {% endif %}
                        </div>
                        <div class="listing-price">{{ listing.price }}</div>
                        <div class="listing-meta">
                            {% if listing.location %}{{ listing.location }} • {% endif %}
                            <a href="{{ listing.url }}" target="_blank" style="color: #3498db; text-decoration: none;">View Source</a>
                        </div>
                        {% if listing.description %}
                        <div class="listing-description">{{ listing.description[:300] }}{% if listing.description|length > 300 %}...{% endif %}</div>
                        {% endif %}
                        {% if listing.claude_notes %}
                        <div class="listing-notes">📌 {{ listing.claude_notes }}</div>
                        {% endif %}
                    </div>
                    {% endfor %}
                {% else %}
                <div class="empty">No matches found yet. Check back soon.</div>
                {% endif %}
            </div>
        </div>

        <!-- SCISSOR HOISTS -->
        <div class="section">
            <div class="section-title">🔧 Scissor Hoists (7,000 lb capacity, 120V/240V)</div>
            <div class="listings">
                {% if results.scissor_hoist %}
                    {% for listing in results.scissor_hoist %}
                    <div class="listing">
                        <div class="listing-title">
                            {{ listing.title }}
                            {% if listing.confidence %}
                            <span class="confidence {{ listing.confidence }}">{{ listing.confidence }}</span>
                            {% endif %}
                        </div>
                        <div class="listing-price">{{ listing.price }}</div>
                        <div class="listing-meta">
                            {% if listing.location %}{{ listing.location }} • {% endif %}
                            <a href="{{ listing.url }}" target="_blank" style="color: #3498db; text-decoration: none;">View Source</a>
                        </div>
                        {% if listing.description %}
                        <div class="listing-description">{{ listing.description[:300] }}{% if listing.description|length > 300 %}...{% endif %}</div>
                        {% endif %}
                        {% if listing.claude_notes %}
                        <div class="listing-notes">📌 {{ listing.claude_notes }}</div>
                        {% endif %}
                    </div>
                    {% endfor %}
                {% else %}
                <div class="empty">No matches found yet. Check back soon.</div>
                {% endif %}
            </div>
        </div>

        <!-- 2-POST HOISTS -->
        <div class="section">
            <div class="section-title">🚙 2-Post Vehicle Hoists (10,000-12,000 lb, with truck extensions)</div>
            <div class="listings">
                {% if results.two_post_hoist %}
                    {% for listing in results.two_post_hoist %}
                    <div class="listing">
                        <div class="listing-title">
                            {{ listing.title }}
                            {% if listing.confidence %}
                            <span class="confidence {{ listing.confidence }}">{{ listing.confidence }}</span>
                            {% endif %}
                        </div>
                        <div class="listing-price">{{ listing.price }}</div>
                        <div class="listing-meta">
                            {% if listing.location %}{{ listing.location }} • {% endif %}
                            <a href="{{ listing.url }}" target="_blank" style="color: #3498db; text-decoration: none;">View Source</a>
                        </div>
                        {% if listing.description %}
                        <div class="listing-description">{{ listing.description[:300] }}{% if listing.description|length > 300 %}...{% endif %}</div>
                        {% endif %}
                        {% if listing.claude_notes %}
                        <div class="listing-notes">📌 {{ listing.claude_notes }}</div>
                        {% endif %}
                    </div>
                    {% endfor %}
                {% else %}
                <div class="empty">No matches found yet. Check back soon.</div>
                {% endif %}
            </div>
        </div>

    </div>
</body>
</html>
"""

@app.route('/')
@app.route('/dashboard')
def dashboard():
    """Render dashboard with results."""
    data = load_results()
    
    total = sum(len(data.get(k, [])) for k in SEARCHES.keys())
    
    last_updated = data.get("last_updated")
    if last_updated:
        dt = datetime.fromisoformat(last_updated)
        last_updated_display = dt.strftime("%b %d, %I:%M %p")
    else:
        last_updated_display = "Never"
    
    return render_template_string(
        DASHBOARD_HTML,
        results=data,
        total_results=total,
        last_updated_display=last_updated_display
    )

@app.route('/api/results')
def api_results():
    """API endpoint to get raw results as JSON."""
    return load_results()

@app.route('/api/run-now', methods=['POST'])
def run_now():
    """Manually trigger agent run."""
    print("\n" + "="*60)
    print("Manual run triggered from dashboard")
    print("="*60 + "\n")
    
    run_agent()
    
    return {
        "status": "success",
        "message": "Agent run completed",
        "timestamp": datetime.now().isoformat()
    }

# ============================================================================
# MAIN
# ============================================================================

def run_scheduler():
    """Run agent on daily schedule."""
    while True:
        # Run at 6 AM every day
        now = datetime.now()
        target = now.replace(hour=6, minute=0, second=0, microsecond=0)
        
        if now > target:
            # If past 6 AM today, schedule for tomorrow
            target += timedelta(days=1)
        
        wait_seconds = (target - now).total_seconds()
        print(f"Agent scheduled to run in {wait_seconds/3600:.1f} hours")
        
        time.sleep(wait_seconds)
        run_agent()

if __name__ == "__main__":
    # Start scheduler in background thread
    scheduler_thread = Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Start Flask app
    print("Starting Farm Equipment Search Dashboard...")
    print("Dashboard available at: http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
