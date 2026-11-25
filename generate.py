import json
import os
import re
from groq import Groq
from prompts import EMAIL_SYSTEM, FOLLOWUP_SYSTEM
import config

client = Groq(api_key=os.environ["GROQ_API_KEY"])

def count_words(text: str) -> int:
    # Exclude signature if present
    text = re.sub(r'Best,[\s\S]*$', '', text).strip()
    # Remove URLs from the text so they don't count as words
    text = re.sub(r'https?://\S+', '', text)
    # Use regex to count actual words
    return len(re.findall(r'\b\w+\b', text))

def validate_email(subject: str, body: str, expected_project_name: str) -> bool:
    # 1. Subject validation (3-5 words, lowercase)
    subj_words = subject.strip().split()
    if not (3 <= len(subj_words) <= 5):
        print(f"  validation failed: subject has {len(subj_words)} words (needs 3-5)")
        return False
    if subject != subject.lower():
        print("  validation failed: subject is not lowercase")
        return False

    # 2. Required static elements
    resume_url = config.RESUME_URL
    portfolio_url = config.PORTFOLIO_URL
    
    if "open to bringing on a GenAI or backend engineer" not in body:
        print("  validation failed: missing hiring CTA")
        return False
        
    if resume_url not in body:
        print("  validation failed: missing exact resume URL")
        return False
    if portfolio_url not in body:
        print("  validation failed: missing exact portfolio URL")
        return False
        
    # 3. Required project URL
    if expected_project_name not in config.PROJECTS:
        return False
    expected_project_url = config.PROJECTS[expected_project_name]["url"]
    if expected_project_url not in body:
        print(f"  validation failed: missing exact project URL for {expected_project_name}")
        return False

    # 4. Placeholders and Banned words
    if "{name}" in body or "[Name]" in body or "[resume link]" in body:
        print("  validation failed: unresolved placeholder")
        return False
    if "scaling" in body.lower() or "as more users join" in body.lower():
        print("  validation failed: contains banned word 'scaling'")
        return False
        
    # 5. Word count (Now that URLs are removed, max 120 is very generous)
    words = count_words(body)
    if words > 120:
        print(f"  validation failed: {words} words (max 120)")
        return False
        
    # 6. Signature
    if not body.strip().endswith(f"Best,\nThaher\n{portfolio_url}"):
        print("  validation failed: signature formatting incorrect")
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
    
    if count_words(out["body"]) > 30:
        return {"skip": True}
        
    clean_subject = original_subject.replace("Re: ", "")
    out["subject"] = f"Re: {clean_subject}"
    
    return out