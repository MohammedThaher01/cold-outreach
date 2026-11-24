import json
import os
import re
from groq import Groq
from prompts import EMAIL_SYSTEM, FOLLOWUP_SYSTEM

client = Groq(api_key=os.environ["GROQ_API_KEY"])

def validate_email(body: str) -> bool:
    # 1. Check for banned words
    if "scaling" in body.lower() or "scalability" in body.lower():
        print("  validation failed: contains banned word 'scaling'")
        return False
        
    # 2. Check for required elements
    if "Are you currently open to bringing on a GenAI or backend engineer" not in body:
        print("  validation failed: missing hiring CTA")
        return False
        
    if "mohammed-thaher-s.modulify.website" not in body:
        print("  validation failed: missing correct portfolio link")
        return False
        
    # 3. Check for EXACT resume link
    resume_url = "https://drive.google.com/file/d/1d5lYhjRRsHIQXgmCjRAC3C3wRIKdYyiy/view?usp=sharing"
    if resume_url not in body:
        print("  validation failed: missing or incorrect resume link")
        return False
        
    # 4. Check for placeholders
    if "{name}" in body or "[Name]" in body or "[resume link]" in body:
        print("  validation failed: unresolved placeholder")
        return False
        
    # 5. Word count (excluding signature)
    inner = re.sub(r'Best,[\s\S]*$', '', body).strip()
    word_count = len(inner.split())
    if word_count > 120:
        print(f"  validation failed: {word_count} words (max 120)")
        return False
        
    return True

def generate_email(card: dict) -> dict:
    if card.get("skip") or card.get("confidence") == "low":
        return {"skip": True}

    project_name = card.get("best_matching_project")
    if project_name not in config.PROJECTS:
        return {"skip": True}

    project_info = config.PROJECTS[project_name]
    
    # Inject the exact variables into the prompt
    system_prompt = EMAIL_SYSTEM.replace("{project_name}", project_name)
    system_prompt = system_prompt.replace("{project_url}", project_info["url"])
    system_prompt = system_prompt.replace("{project_desc}", project_info["description"])
    system_prompt = system_prompt.replace("{resume_url}", config.RESUME_URL)
    system_prompt = system_prompt.replace("{portfolio_url}", config.PORTFOLIO_URL)

    resp = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(card)},
        ],
        response_format={"type": "json_object"},
        temperature=0.4,
    )
    out = json.loads(resp.choices[0].message.content)
    
    if not out.get("subject") or not out.get("body"):
        return {"skip": True}
        
    if not validate_email(out["subject"], out["body"], project_name):
        return {"skip": True}
        
    return out

def generate_followup(original_subject: str, original_body: str, contact_name: str = "team") -> dict:
    if not contact_name or contact_name.lower() in ["", "mohammed", "thaher"]:
        contact_name = "team"
        
    resp = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": FOLLOWUP_SYSTEM},
            {"role": "user", "content": f"Name: {contact_name}\n\nOriginal Subject: {original_subject}\n\nOriginal Body:\n{original_body}"},
        ],
        response_format={"type": "json_object"},
        temperature=0.4,
    )
    out = json.loads(resp.choices[0].message.content)
    
    clean_subject = original_subject.replace("Re: ", "")
    out["subject"] = f"Re: {clean_subject}"
    
    return out