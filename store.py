import csv

FIELDS = ["name", "email", "company_name", "company_url", "status",
          "insight_card", "subject", "body", "sent_at"]

def load():
    with open("leads.csv", newline="") as f:
        reader = csv.DictReader(f)
        rows = []
        for r in reader:
            # Strip out any None keys caused by accidental extra commas
            clean_r = {k: v for k, v in r.items() if k in FIELDS}
            # Ensure all fields exist so the script doesn't crash on missing columns
            for f in FIELDS:
                if f not in clean_r:
                    clean_r[f] = ""
            rows.append(clean_r)
        return rows

def save(rows):
    with open("leads.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        # Only write the keys that belong in FIELDS
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})

def update(email, **kwargs):
    rows = load()
    for r in rows:
        if r["email"] == email:
            r.update({k: v for k, v in kwargs.items() if k in FIELDS})
            break
    save(rows)