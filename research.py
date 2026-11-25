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

def normalize_text(text: str) -> str:
    text = html.unescape(text)
    text = unicodedata.normalize('NFKD', text)
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def verify_continuous_quote(quote: str, source_text: str) -> bool:
    if not quote or len(quote) < 10:
        return False
    norm_quote = normalize_text(quote)
    norm_source = normalize_text(source_text)
    return norm_quote in norm_source

def research_company(company_name: str, company_url: str | None = None, description: str = "", funding_info: str = "") -> dict:
    
    page_text = ""
    snippets = ""
    source_url = company_url or ""

    # IF WE HAVE RICH CSV DATA, BYPASS THE WEB SCRAPE
    if description or funding_info:
        print("  Using rich CSV data (skipping web scrape)...")
        snippets = f"Company Description: {description}\nFunding Info: {funding_info}"
        page_text = snippets 
    else:
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

    user_msg = f"""company_name: {company_name}
company_url: {source_url}

SEARCH RESULTS / PROVIDED DATA:
{snippets}

WEBSITE CONTENT:
{page_text}

Return the insight card JSON."""

    try:
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
    except Exception as e:
        print(f"  [Reject] LLM failed to generate valid JSON: {e}")
        return {"skip": True, "confidence": "low"}
    
    # VALIDATION
    if card.get("skip") or card.get("confidence") == "low":
        card["skip"] = True
        return card
        
    if not verify_continuous_quote(card.get("evidence_quote", ""), snippets + " " + page_text):
        print("  [Reject] Evidence quote is paraphrased or fabricated.")
        card["skip"] = True
        return card
        
    # Clean up the project name if the LLM added descriptions
    project_name = card.get("best_matching_project", "")
    if " - " in project_name:
        project_name = project_name.split(" - ")[0].strip()
    
    if project_name not in config.PROJECTS:
        print(f"  [Reject] Invalid project selected: {project_name}")
        card["skip"] = True
        return card
    else:
        card["best_matching_project"] = project_name

    card.setdefault("company_name", company_name)
    if source_url and not card.get("source_url"):
        card["source_url"] = source_url
        
    return card