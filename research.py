import json
import os
import re
import html
import unicodedata
import trafilatura
from ddgs import DDGS
from groq import Groq
from prompts import RESEARCH_SYSTEM
import config

client = Groq(api_key=os.environ["GROQ_API_KEY"])

FREE_EMAIL_DOMAINS = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com", "protonmail.com", "live.com", "aol.com"}

def infer_company_from_email(email: str) -> tuple[str | None, str | None]:
    domain = email.split("@")[-1].lower().strip()
    if domain in FREE_EMAIL_DOMAINS:
        return None, None
    root = domain.split(".")[0]
    return root, f"https://{domain}"

def search(query: str, n: int = 5):
    try:
        with DDGS() as d:
            return list(d.text(query, max_results=n))
    except Exception:
        return []

def scrape(url: str, limit: int = 4000) -> str:
    try:
        html_content = trafilatura.fetch_url(url)
        if not html_content:
            return ""
        text = trafilatura.extract(html_content, include_comments=False, include_tables=False)
        return (text or "")[:limit]
    except Exception:
        return ""

# --- NEW EXACT PHRASE MATCHER ---
def normalize_text(text: str) -> str:
    # 1. Decode HTML entities
    text = html.unescape(text)
    # 2. Unicode normalization (NFKD)
    text = unicodedata.normalize('NFKD', text)
    # 3. Lowercase
    text = text.lower()
    # 4. Remove punctuation (keep only alphanumeric and spaces)
    text = re.sub(r'[^\w\s]', '', text)
    # 5. Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def verify_continuous_quote(quote: str, source_text: str) -> bool:
    if not quote or len(quote) < 10:
        return False
    norm_quote = normalize_text(quote)
    norm_source = normalize_text(source_text)
    # Must appear as a continuous phrase in the exact word order
    return norm_quote in norm_source

def research_company(company_name: str, company_url: str | None = None) -> dict:
    if not company_url:
        company_url = f"https://{company_name.lower().replace(' ', '')}.com"

    results = search(f'"{company_name}" product OR features OR pricing')
    if not results:
        results = search(company_name)

    snippets = "\n\n".join(f"[{r.get('title','')}] {r.get('href','')}\n{r.get('body','')}" for r in results)
    page_text = scrape(company_url)
    source_url = company_url

    if len(page_text) < 100 and results:
        for r in results[:2]:
            href = r.get("href", "")
            if href:
                page_text = scrape(href)
                if len(page_text) > 100:
                    source_url = href
                    break

    user_msg = f"company_name: {company_name}\ncompany_url: {source_url}\n\nSEARCH RESULTS:\n{snippets}\n\nWEBSITE CONTENT:\n{page_text}\n\nReturn the insight card JSON."

    resp = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": RESEARCH_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    card = json.loads(resp.choices[0].message.content)
    
    # VALIDATION
    if card.get("skip") or card.get("confidence") == "low":
        card["skip"] = True
        return card
        
    # Verify exact continuous phrase
    if not verify_continuous_quote(card.get("evidence_quote", ""), snippets + " " + page_text):
        print("  [Reject] Evidence quote is paraphrased or fabricated.")
        card["skip"] = True
        return card
        
    if card.get("best_matching_project") not in config.PROJECTS:
        print("  [Reject] Invalid project selected.")
        card["skip"] = True
        return card

    card.setdefault("company_name", company_name)
    if source_url and not card.get("source_url"):
        card["source_url"] = source_url
    return card