import feedparser
import requests
import json
import os
import datetime
from datetime import timezone
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables (useful for local testing)
load_dotenv()

# Configure Gemini API
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("Warning: GEMINI_API_KEY is not set. Classification will return empty or mock data if API limits hit/error. Please configure it.")

genai.configure(api_key=API_KEY)

# Using a standard fast model
model = genai.GenerativeModel('gemini-2.0-flash')

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
    return articles
def categorize_articles(articles):
    if not articles:
        return []

    print(f"Categorizing {len(articles)} articles using Gemini...")
    
    # Create input representation for the AI
    articles_payload = []
    for i, a in enumerate(articles):
        articles_payload.append({
            "idx": i,
            "title": a["title"],
            "desc": a["description"]
        })
    
    prompt = f"""
    Please categorize the following news articles into EXACTLY one of these categories:
    - Bundesinnenpolitik
    - Ausland (DE) (This refers to foreign policy and international news)
    - Landespolitik von ba-Wü (Politics of Baden-Württemberg)
    - Wirtschaft (Economy)
    - Andere (Use this if it doesn't clearly fit any of the above, e.g., sports, entertainment, unrelated local news)

    Also, assess whether the news is highly important ("important": true) or just secondary everyday news ("important": false).

    Articles:
    {json.dumps(articles_payload, ensure_ascii=False)}

    Output valid JSON ONLY. The JSON must be a list of objects, where each object has "idx" (integer), "category" (string), and "important" (boolean). Ensure the output is strictly parsable JSON, no markdown formatting like ```json.
    """
    
    try:
        if not API_KEY:
            raise ValueError("No API Key")
        
        response = model.generate_content(prompt)
        text_response = response.text.strip()
        
        # Remove markdown notation if the model returns it
        if text_response.startswith('```json'):
            text_response = text_response[7:]
        if text_response.endswith('```'):
            text_response = text_response[:-3]
        
        classification_result = json.loads(text_response.strip())
        
        # Map back to articles
        for item in classification_result:
            idx = item.get("idx")
            cat = item.get("category", "Andere")
            important = item.get("important", False)
            if idx is not None and idx < len(articles):
                # Ensure category is exactly one of the known ones
                if cat not in CATEGORIES:
                    cat = "Andere"
                articles[idx]["category"] = cat
                articles[idx]["is_important"] = important
                
    except Exception as e:
        print(f"Error during AI categorization: {e}")
        # Fallback to 'Andere' on error
        for a in articles:
            a["category"] = "Andere"
            a["is_important"] = False
            
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
