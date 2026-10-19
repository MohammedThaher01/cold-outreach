import json
import os
import trafilatura
from ddgs import DDGS
from groq import Groq
from prompts import RESEARCH_SYSTEM

client = Groq(api_key=os.environ["GROQ_API_KEY"])


def search(query: str, n: int = 5):
    with DDGS() as d:
        return list(d.text(query, max_results=n))


def scrape(url: str, limit: int = 4000) -> str:
    html = trafilatura.fetch_url(url)
    if not html:
        return ""
    text = trafilatura.extract(html, include_comments=False, include_tables=False)
    return (text or "")[:limit]


def research_company(company_name: str, company_url: str | None = None) -> dict:
    results = search(
        f"{company_name} AI startup India news OR careers OR product OR blog", 5
    )
    snippets = "\n\n".join(
        f"[{r.get('title','')}] {r.get('href','')}\n{r.get('body','')}" for r in results
    )

    page_text = ""
    source_url = company_url or ""
    if company_url:
        page_text = scrape(company_url)
    else:
        needle = company_name.lower().replace(" ", "")
        for r in results:
            href = r.get("href", "")
            if needle in href.lower().replace("-", "").replace(".", ""):
                page_text = scrape(href)
                source_url = href
                break

    user_msg = f"""company_name: {company_name}
company_url: {source_url or 'unknown'}

SEARCH RESULTS:
{snippets}

WEBSITE CONTENT:
{page_text}

Return the insight card JSON."""

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
    card.setdefault("company_name", company_name)
    if source_url and not card.get("source_url"):
        card["source_url"] = source_url
    return card

FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com",
    "icloud.com", "protonmail.com", "live.com", "aol.com",
}


def infer_company_from_email(email: str) -> tuple[str | None, str | None]:
    domain = email.split("@")[-1].lower().strip()
    if domain in FREE_EMAIL_DOMAINS:
        return None, None
    root = domain.split(".")[0]
    return root, f"https://{domain}"