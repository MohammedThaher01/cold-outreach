import json
import os
import re
from groq import Groq
from prompts import EMAIL_SYSTEM, FOLLOWUP_SYSTEM

client = Groq(api_key=os.environ["GROQ_API_KEY"])

def validate_email(body: str) -> bool:
    lines = body.split('\n')
    if len(lines) > 1:
        inner = '\n'.join(lines[1:])
    else:
        inner = body
        
    inner = re.sub(r'Best,[\s\S]*$', '', inner).strip()
    
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

def generate_followup(original_subject: str, original_body: str, contact_name: str = "") -> dict:
    resp = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": FOLLOWUP_SYSTEM},
            {"role": "user", "content": f"Contact Name: {contact_name}\n\nOriginal Subject: {original_subject}\n\nOriginal Body:\n{original_body}"},
        ],
        response_format={"type": "json_object"},
        temperature=0.4,
    )
    out = json.loads(resp.choices[0].message.content)
    
    clean_subject = original_subject.replace("Re: ", "")
    out["subject"] = f"Re: {clean_subject}"
    
    return out