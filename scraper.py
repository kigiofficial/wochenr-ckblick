import os
import datetime
import time
import json
import feedparser
from datetime import timezone
from mistralai import Mistral
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

M_KEY = os.getenv("MISTRAL_API_KEY")
if not M_KEY:
    print("Warning: MISTRAL_API_KEY is not set in .env")
    
mistral_client = Mistral(api_key=M_KEY)

# Feeds
FEEDS = [
    {"url": "https://www.tagesschau.de/xml/rss2", "source": "Tagesschau"},
    {"url": "https://www.zdf.de/rss/zdf/nachrichten", "source": "ZDF"}
]

CATEGORIES = {
    "Bundesinnenpolitik": {
        "urls": ["/inland/innenpolitik/", "/politik/deutschland/", "/nachrichten/politik/deutschland/"],
        "keywords": ["Bundestag", "Bundesregierung", "Scholz", "Linder", "Habeck", "Baerbock", "Ministerium", "Gesetz", "Wahl", "Partei", "CDU", "SPD", "Grüne", "FDP", "AfD", "Linke", "BSW"]
    },
    "Ausland (DE)": {
        "urls": ["/ausland/", "/nachrichten/politik/ausland/"],
        "keywords": ["EU", "USA", "Russland", "Ukraine", "China", "Israel", "Gaza", "Nahost", "Krieg", "Konflikt", "Gipfel", "Bündnis", "NATO", "Vereinte Nationen"]
    },
    "Landespolitik von ba-Wü": {
        "urls": ["/baden-wuerttemberg/"],
        "keywords": ["Baden-Württemberg", "Stuttgart", "Kretschmann", "Landtag", "BW", "Alb-Donau", "Karlsruhe", "Mannheim", "Freiburg", "Ulm", "Heidelberg"]
    },
    "Wirtschaft": {
        "urls": ["/wirtschaft/"],
        "keywords": ["Börse", "Aktien", "DAX", "Unternehmen", "Inflation", "Zinsen", "Arbeitsmarkt", "Strompreis", "Gaspreis", "Wachstum", "Rezession", "Konzern"]
    }
}


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
                    "source": feed_info['source'],
                    "feed_index": len([a for a in articles if a['source'] == feed_info['source']])
                }
                articles.append(article)
    
    print(f"Total articles fetched: {len(articles)}")
    return articles
import time
def categorize_articles(articles):
    if not articles:
        return []

    print(f"Categorizing {len(articles)} articles using rule-based logic...")
    
    for article in articles:
        title = article["title"].lower()
        desc = article["description"].lower()
        link = article["link"].lower()
        
        assigned_category = "Andere"
        
        # 1. Check URL patterns first (stronger indicator)
        for cat_name, rules in CATEGORIES.items():
            if any(url_part in link for url_part in rules["urls"]):
                assigned_category = cat_name
                break
        
        # 2. Check keywords if no category assigned or to refine
        if assigned_category == "Andere":
            for cat_name, rules in CATEGORIES.items():
                if any(kw.lower() in title or kw.lower() in desc for kw in rules["keywords"]):
                    assigned_category = cat_name
                    break
                    
        article["category"] = assigned_category
        
        # Determine importance with a point system
        score = 0
        
        # 3. Position Bonus (Top Stories)
        if article.get("feed_index", 10) < 5:
            score += 5
            
        # 4. Keyword Scoring (Enhanced for more inclusivity)
        high_priority = ["eilmeldung", "liveblog", "ticker", "breaking", "aktuell", "liveticker", "ukraine", "nahost", "iran", "israel", "krieg", "angriff"]
        medium_priority = ["urteil", "rücktritt", "wahl", "entscheidung", "gipfel", "kultur", "sport", "wissenschaft", "technik", "forschung", "medien", "gesellschaft"]
        low_priority = ["wetter", "lotto", "horoskop", "börsen-update"]
        
        if any(kw in title or kw in desc for kw in high_priority):
            score += 20 # Increased from 15
        if any(kw in title or kw in desc for kw in medium_priority):
            score += 15 # Increased from 10
        if any(kw in title or kw in desc for kw in low_priority):
            score -= 40 # Increased penalty for filler
            
        # Base rank score from rules
        article["rank_score"] = score

    # Now use Mistral to refine ranking for the most recent/relevant ones
    # We rank the top 40 articles (after rule-based scoring and filtering)
    articles_to_rank = sorted(articles, key=lambda x: x["rank_score"], reverse=True)[:40]
    rank_articles_mistral(articles_to_rank)

    # Re-sort all articles by final rank score
    articles.sort(key=lambda x: x.get("rank_score", 0), reverse=True)
    
    # Categorization count (excluding "Andere")
    count = len([a for a in articles if a["category"] != "Andere"])
    print(f"Successfully categorized and ranked {len(articles)} articles.")
    return articles

def rank_articles_mistral(articles_batch):
    """Uses Mistral to assign a quality/importance score (0-100) to articles."""
    if not articles_batch: return
    
    print(f"Ranking {len(articles_batch)} articles with Mistral...")
    
    payload = []
    for i, a in enumerate(articles_batch):
        payload.append({
            "id": i,
            "t": a["title"],
            "d": a["description"][:100]
        })
        
    prompt = f"""
    Bewerte die journalistische Wichtigkeit dieser Nachrichtenartikel auf einer Skala von 0 bis 100.
    100 = Weltbewegende Eilmeldung, 0 = Belanglose Randnotiz/Wetter.
    Gib ein JSON-Objekt zurück: {{"scores": [{{ "id": index, "score": 0-100 }}]}}
    Artikel: {json.dumps(payload, ensure_ascii=False)}
    """
    
    try:
        response = mistral_client.chat.complete(
            model="mistral-small-latest",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Du bist ein erfahrener Nachrichtenredakteur."},
                {"role": "user", "content": prompt}
            ]
        )
        result = json.loads(response.choices[0].message.content)
        for item in result.get("scores", []):
            idx = item.get("id")
            score = item.get("score", 0)
            if idx is not None and idx < len(articles_batch):
                # Combine rule score with AI score (AI score has more weight)
                articles_batch[idx]["rank_score"] = (articles_batch[idx].get("rank_score", 0) * 0.3) + (score * 0.7)
                # Ensure is_important matches a lower threshold (more inclusive)
                if score > 50: # Reduced from 70
                    articles_batch[idx]["is_important"] = True
    except Exception as e:
        print(f"Ranking Error: {e}")

def generate_summaries(articles):
    """Generates daily and weekly summaries using Mistral AI."""
    print("Generating AI summaries with Mistral...")
    
    # Group by day and week
    days = {}
    weeks = {}
    
    # Sort articles by date to process most recent first
    sorted_articles = sorted(articles, key=lambda x: x["date"], reverse=True)
    
    for a in sorted_articles:
        if not a.get("is_important", False) and a["category"] == "Andere":
            continue
            
        dt = datetime.datetime.fromisoformat(a["date"])
        day_str = dt.strftime("%Y-%m-%d")
        
        # ISO Week
        week_year, week_num, _ = dt.isocalendar()
        week_str = f"{week_year}-W{week_num:02d}"
        
        if day_str not in days: days[day_str] = []
        if week_str not in weeks: weeks[week_str] = []
        
        days[day_str].append(f"- {a['title']}")
        weeks[week_str].append(f"- {a['title']}")

    summaries = {}
    
    # Process only the most recent day and week to save tokens/time
    target_days = sorted(days.keys(), reverse=True)[:5]
    target_weeks = sorted(weeks.keys(), reverse=True)[:2]
    
    for d in target_days:
        summaries[d] = call_mistral_summary(days[d][:15], "Tagesrückblick")
        
    for w in target_weeks:
        summaries[w] = call_mistral_summary(weeks[w][:25], "Wochenrückblick")
        
    return summaries

def call_mistral_summary(titles, context):
    if not titles: return ""
    
    prompt = f"""
    Erstelle einen detaillierten, professionellen {context} basierend auf diesen Schlagzeilen.
    - Nutze reichhaltiges Markdown:
        - Verwende Überschriften (z.B. ### Top-Themen) für verschiedene Sektionen (Inland, Ausland, etc.).
        - Nutze Fettschrift (**Text**) zur Hervorhebung wichtiger Begriffe oder Namen.
        - Verwende Aufzählungspunkte für eine klare Struktur.
    - Schreibe eine prägnante Einleitung.
    - Achte auf eine journalistisch hochwertige Sprache.
    - Max. 180 Wörter.
    
    Schlagzeilen:
    """ + "\n".join(titles)
    
    try:
        response = mistral_client.chat.complete(
            model="mistral-small-latest",
            messages=[
                {"role": "system", "content": "Du bist ein leitender Nachrichtenredakteur. Antworte in strukturiertem Markdown (Bullet Points)."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Mistral Error: {e}")
        return ""

def merge_and_save_articles(new_articles, summaries):
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
        if a.get("category") == "Andere" and not a.get("is_important", False):
            if a.get("rank_score", 0) < 30: # Even more aggressive filtering for "Other"
                continue
            
        clean_article = {
            "title": a["title"],
            "link": a["link"],
            "description": a["description"],
            "date": a["date"],
            "source": a["source"],
            "category": a.get("category", "Andere"),
            "is_important": a.get("is_important", False),
            "rank_score": a.get("rank_score", 0)
        }
        # Overwrite or add
        articles_dict[a["link"]] = clean_article
        
    final_articles = list(articles_dict.values())
    # Sort by rank score first, then by date as fallback
    final_articles.sort(key=lambda x: (x.get("rank_score", 0), x["date"]), reverse=True)
    
    # Keep only the last 500 articles to avoid infinite growth
    final_articles = final_articles[:500]
    
    output = {
        "lastUpdated": datetime.datetime.now(timezone.utc).isoformat(),
        "articles": final_articles,
        "summaries": summaries
    }
    
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    articles = fetch_feed_data()
    # If there are too many articles, limit to top 150 to keep processing fast
    articles = articles[:150] 
    
    categorized = categorize_articles(articles)
    summaries = generate_summaries(categorized)
    merge_and_save_articles(categorized, summaries)
    
    print("Successfully generated data.json with summaries.")
