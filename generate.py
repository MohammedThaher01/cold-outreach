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
        
    if "[INSERT ACTUAL RESUME LINK" in body:
        print("  validation failed: resume link placeholder not replaced")
        return False
        
    # 3. Check for placeholders
    if "{name}" in body or "[Name]" in body:
        print("  validation failed: unresolved name placeholder")
        return False
        
    # 4. Word count (excluding signature)
    inner = re.sub(r'Best,[\s\S]*$', '', body).strip()
    word_count = len(inner.split())
    if word_count > 120:
        print(f"  validation failed: {word_count} words (max 120)")
        return False
        
    return True

def generate_email(card: dict) -> dict:
    if card.get("skip") or card.get("confidence") == "low":
        return {"skip": True}

    resp = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": EMAIL_SYSTEM},
            {"role": "user", "content": json.dumps(card)},
        ],
        response_format={"type": "json_object"},
        temperature=0.4,
    )
    out = json.loads(resp.choices[0].message.content)
    
    if not out.get("subject") or not out.get("body"):
        return {"skip": True}
        
    if not validate_email(out["body"]):
        return {"skip": True}
        
    return out

def generate_followup(original_subject: str, original_body: str, contact_name: str = "team") -> dict:
    if not contact_name:
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
    
    # Force the subject to be a reply
    clean_subject = original_subject.replace("Re: ", "")
    out["subject"] = f"Re: {clean_subject}"
    
    return out