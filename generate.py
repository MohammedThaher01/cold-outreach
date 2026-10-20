import json
import os
import re
from groq import Groq
from prompts import EMAIL_SYSTEM

client = Groq(api_key=os.environ["GROQ_API_KEY"])

def validate_email(body: str) -> bool:
    # Strip the first line (greeting)
    lines = body.split('\n')
    if len(lines) > 1:
        inner = '\n'.join(lines[1:])
    else:
        inner = body
        
    # Strip everything from "Best," onwards
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
        model="openai/gpt-oss-20b",
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
        
    # Run the validator
    if not validate_email(out["body"]):
        return {"skip": True}
        
    return out