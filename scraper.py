import feedparser
import requests
import json
import os
import datetime
from datetime import timezone
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables (useful for local testing)
load_dotenv()

# Configure Gemini API
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("Warning: GEMINI_API_KEY is not set.")

# New SDK Client
client = genai.Client(api_key=API_KEY)

# News often contains sensitive topics which can trigger safety filters.
# We set these to BLOCK_NONE to ensure the scraper works for all news.
safety_settings = [
    types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
    types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
    types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
    types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
]

# Using 2.0 flash as it is the latest and fastest
MODEL_ID = 'gemini-2.0-flash'

# Feeds
FEEDS = [
    {"url": "https://www.tagesschau.de/xml/rss2", "source": "Tagesschau"},
    {"url": "https://www.zdf.de/rss/zdf/nachrichten", "source": "ZDF"}
]

CATEGORIES = [
    "Bundesinnenpolitik",
    "Ausland (DE)",
    "Landespolitik von ba-Wü",
    "Wirtschaft",
    "Andere"  # We will ignore this one later
]

def fetch_feed_data():
    articles = []
    now = datetime.datetime.now(timezone.utc)
    
    for feed_info in FEEDS:
        print(f"Fetching RSS feed from {feed_info['source']}...")
        parsed_feed = feedparser.parse(feed_info["url"])
        
        if not parsed_feed.entries:
            print(f"Warning: No entries found for {feed_info['source']}.")
        
        for entry in parsed_feed.entries:
            # Parse published date
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_date = datetime.datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            else:
                continue
                
            # Filter for the last 14 days to have enough history
            days_old = (now - pub_date).days
            if days_old <= 14:
                description = getattr(entry, 'description', '')
                
                # Get the most reliable link
                link = getattr(entry, 'link', '')
                if not link and hasattr(entry, 'links'):
                    for l in entry.links:
                        if l.get('rel') == 'alternate' or not l.get('rel'):
                            link = l.get('href')
                            break
                
                if not link:
                    continue

                article = {
                    "id": link,
                    "title": entry.title,
                    "link": link,
                    "description": description,
                    "date": pub_date.isoformat(),
                    "source": feed_info['source']
                }
                articles.append(article)
    
    print(f"Total articles fetched: {len(articles)}")
    return articles
import time

def categorize_articles(articles):
    if not articles:
        return []

    # Limit to 100 articles to avoid hitting token limits or timeout
    articles = articles[:100]
    print(f"Categorizing {len(articles)} articles using Gemini (with retry logic)...")
    
    # Create input representation
    articles_payload = []
    for i, a in enumerate(articles):
        articles_payload.append({
            "idx": i,
            "title": a["title"],
            "desc": a["description"]
        })
    
    prompt = f"""
    Categorize these news articles into:
    - Bundesinnenpolitik
    - Ausland (DE)
    - Landespolitik von ba-Wü
    - Wirtschaft
    - Andere (if no clear match)

    Also assess importance ("important": true/false).
    Articles: {json.dumps(articles_payload, ensure_ascii=False)}
    Output valid JSON array of objects with "idx", "category", "important".
    """
    
    max_retries = 3
    retry_delay = 5 # seconds
    
    for attempt in range(max_retries):
        try:
            if not API_KEY:
                raise ValueError("GEMINI_API_KEY is not set.")
            
            response = client.models.generate_content(
                model=MODEL_ID,
                contents=prompt,
                config=types.GenerateContentConfig(
                    safety_settings=safety_settings,
                    response_mime_type='application/json'
                )
            )
            
            classification_result = response.parsed
            
            if not classification_result and response.text:
                # Fallback for manual parsing
                text = response.text.strip()
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                classification_result = json.loads(text)
            
            if classification_result:
                count = 0
                for item in classification_result:
                    idx = item.get("idx")
                    if idx is not None and idx < len(articles):
                        articles[idx]["category"] = item.get("category", "Andere")
                        articles[idx]["is_important"] = item.get("important", False)
                        count += 1
                print(f"Successfully categorized {count} articles.")
                return articles
                
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if "429" in str(e) or "Too Many Requests" in str(e):
                if attempt < max_retries - 1:
                    print(f"Rate limited. Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2 # Exponential backoff
                    continue
            
            # For other errors or if out of retries
            break
            
    print("Categorization failed after retries. Keeping original data.")
    for a in articles:
        a["category"] = a.get("category", "Andere")
        a["is_important"] = a.get("is_important", False)
    return articles

def merge_and_save_articles(new_articles):
    data_file = "data.json"
    existing_articles = []
    
    if os.path.exists(data_file):
        try:
            with open(data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "articles" in data:
                    existing_articles = data["articles"]
        except Exception as e:
            print(f"Error reading existing data: {e}")

    # Merge by URL to prevent duplicates and keep history
    articles_dict = {a["link"]: a for a in existing_articles}
    
    for a in new_articles:
        if a.get("category") == "Andere":
            continue
            
        clean_article = {
            "title": a["title"],
            "link": a["link"],
            "description": a["description"],
            "date": a["date"],
            "source": a["source"],
            "category": a.get("category", "Andere"),
            "is_important": a.get("is_important", False)
        }
        # Overwrite or add
        articles_dict[a["link"]] = clean_article
        
    final_articles = list(articles_dict.values())
    # Sort by date descending
    final_articles.sort(key=lambda x: x["date"], reverse=True)
    
    # Keep only the last 500 articles to avoid infinite growth
    final_articles = final_articles[:500]
    
    output = {
        "lastUpdated": datetime.datetime.now(timezone.utc).isoformat(),
        "articles": final_articles
    }
    
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    articles = fetch_feed_data()
    # If there are too many articles, limit to top 150 to keep processing fast
    articles = articles[:150] 
    
    categorized = categorize_articles(articles)
    merge_and_save_articles(categorized)
    
    print("Successfully generated data.json")
