import csv

FIELDS = ["name", "email", "company_name", "company_url", "status",
          "insight_card", "subject", "body", "sent_at", "message_id"]

def load():
    with open("leads.csv", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = []
        for r in reader:
            clean_r = {k: v for k, v in r.items() if k in FIELDS}
            for f in FIELDS:
                if f not in clean_r:
                    clean_r[f] = ""
            if clean_r["status"]:
                clean_r["status"] = clean_r["status"].strip().upper()
            rows.append(clean_r)
        return rows

def save(rows):
    with open("leads.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})

def update(email, **kwargs):
    rows = load()
    for r in rows:
        if r["email"] == email:
            r.update({k: v for k, v in kwargs.items() if k in FIELDS})
            break
    save(rows)