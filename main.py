import argparse
import datetime
import json
import os
import random
import time

from dotenv import load_dotenv

load_dotenv()

import store
import research
import generate
import send


def _now():
    return datetime.datetime.now()


def _today():
    return _now().date().isoformat()


def _send_with_cap(rows):
    now = _now()
    
    # 1. Check business hours (9 AM - 5 PM Asia/Kolkata)
    if not (9 <= now.hour < 17):
        print("Outside business hours. Skipping send.")
        return 0
        
    # 2. Calendar-hour bucket check
    sends_this_hour = 0
    last_send_time = None
    
    for r in rows:
        if r["status"] in ["SENT", "FOLLOWED_UP"] and r.get("sent_at"):
            try:
                sent_dt = datetime.datetime.fromisoformat(r["sent_at"])
                if sent_dt.tzinfo is None:
                    sent_dt = sent_dt.replace(tzinfo=TZ)
                
                # Check if in same calendar year, month, day, and hour
                if (sent_dt.year == now.year and sent_dt.month == now.month and 
                    sent_dt.day == now.day and sent_dt.hour == now.hour):
                    sends_this_hour += 1
                    
                # Track most recent successful send overall
                if not last_send_time or sent_dt > last_send_time:
                    last_send_time = sent_dt
            except:
                pass
                
    # Enforce Max 2 per calendar hour
    if sends_this_hour >= config.HOURLY_CAP:
        print(f"Calendar hour cap ({config.HOURLY_CAP}) reached. Stopping.")
        return 0
        
    # Enforce Min 30 minutes between sends
    if last_send_time and (now - last_send_time).total_seconds() < 1800:
        print("Less than 30 minutes since last successful send. Stopping.")
        return 0

    # 3. Send exactly 1 email
    sent_count = 0
    for r in rows:
        if r["status"] != "APPROVED":
            continue
        if sent_count >= 1: # Max 1 per execution
            break
            
        try:
            print(f"sending to {r['email']}...")
            is_followup = r["subject"].startswith("Re: ")
            in_reply_to = r.get("message_id") if is_followup else None
            
            # If this throws an exception, the code jumps to 'except', 
            # meaning store.update is NOT called, so it doesn't count.
            new_msg_id = send.send_email(r["email"], r["subject"], r["body"], in_reply_to=in_reply_to)
            
            new_status = "FOLLOWED_UP" if is_followup else "SENT"
            store.update(r["email"], status=new_status, sent_at=_now().isoformat(), message_id=new_msg_id)
            sent_count += 1
            
        except Exception as e:
            print(f"  failed: {e}")
            
    return sent_count


def run_once():
    all_rows = store.load()
    new_count = sum(1 for r in all_rows if r["status"] == "NEW")
    print(f"loaded {len(all_rows)} leads, {new_count} with status NEW")

    auto = os.environ.get("AUTO_SEND", "0") == "1"
    cap = int(os.environ.get("DAILY_CAP", "8"))

    # Phase 1: research NEW rows
    for r in store.load():
        if r["status"] != "NEW":
            continue
        company, url = r["company_name"], r["company_url"]
        if not company:
            company, url = research.infer_company_from_email(r["email"])
        if not company:
            store.update(r["email"], status="NEED_COMPANY")
            print(f"{r['email']}: no company name and free email domain, flagged")
            continue

        print(f"researching {company}...")
        try:
            card = research.research_company(company, url or None)
        except Exception as e:
            print(f"  failed: {e}")
            continue

        if card.get("skip"):
            store.update(
                r["email"],
                status="NEEDS_MANUAL_RESEARCH",
                insight_card=json.dumps(card),
            )
            print("  skipped (weak evidence)")
        else:
            store.update(
                r["email"],
                status="READY_FOR_EMAIL",
                insight_card=json.dumps(card),
            )
            print(f"  ok: {card.get('specific_observation', '')[:70]}")
        time.sleep(2)

    # Phase 2: generate emails for ready rows
    for r in store.load():
        if r["status"] != "READY_FOR_EMAIL":
            continue
        card = json.loads(r["insight_card"])
        print(f"writing email for {r['company_name']}...")
        try:
            out = generate.generate_email(card)
        except Exception as e:
            print(f"  failed: {e}")
            continue

        if out.get("skip"):
            store.update(r["email"], status="SKIPPED")
            print("  skipped")
        else:
            store.update(
                r["email"],
                status="DRAFT_REVIEW",
                subject=out["subject"],
                body=out["body"],
            )
            print(f"  subject: {out['subject']}")
        time.sleep(1)

    # Phase 3: auto-approve if enabled
    if auto:
        for r in store.load():
            if r["status"] == "DRAFT_REVIEW":
                store.update(r["email"], status="APPROVED")
                print(f"auto-approved: {r['email']}")

    # Phase 4: send approved rows up to daily cap
    rows = store.load()
    sent_today = sum(
        1 for r in rows
        if r["status"] in ["SENT", "FOLLOWED_UP"] and (r.get("sent_at") or "").startswith(_today())
    )
    _send_with_cap(rows, cap, sent_today)


def cmd_run(_args):
    run_once()


def cmd_followup(_args):
    today = datetime.date.today()
    rows = store.load()
    generated_count = 0
    
    for r in rows:
        if r["status"] != "SENT" or not r.get("sent_at"):
            continue
            
        sent_date = datetime.datetime.fromisoformat(r["sent_at"]).date()
        days_since = (today - sent_date).days
        
        if days_since >= 5:
            print(f"generating follow-up for {r['email']} (sent {days_since} days ago)...")
            
            contact_name = "team"
            try:
                card = json.loads(r.get("insight_card", "{}"))
                if card.get("contact_name"):
                    contact_name = card.get("contact_name")
            except:
                pass
                
            try:
                out = generate.generate_followup(r["subject"], r["body"], contact_name)
                store.update(
                    r["email"], 
                    status="APPROVED", 
                    subject=out["subject"], 
                    body=out["body"]
                )
                print(f"  ready: {out['subject']}")
                generated_count += 1
            except Exception as e:
                print(f"  failed: {e}")
                
    if generated_count == 0:
        print("No emails are ready for follow-up today.")


def cmd_add(args):
    rows = store.load()
    if any(r["email"] == args.email for r in rows):
        print(f"{args.email} already exists")
        return
    rows.append({
        "name": "",
        "email": args.email,
        "company_name": args.company or "",
        "company_url": "",
        "status": "NEW",
        "insight_card": "",
        "subject": "",
        "body": "",
        "sent_at": "",
        "message_id": ""
    })
    store.save(rows)
    print(f"added {args.email}")


def cmd_list(_args):
    drafts = [r for r in store.load() if r["status"] == "DRAFT_REVIEW"]
    if not drafts:
        print("no drafts to review")
        return
    for r in drafts:
        print("=" * 60)
        print(f"TO:      {r['email']}  ({r['company_name']})")
        print(f"SUBJECT: {r['subject']}")
        print()
        print(r["body"])
        print()


def cmd_approve(args):
    store.update(args.email, status="APPROVED")
    print(f"approved {args.email}")


def cmd_reject(args):
    store.update(args.email, status="REJECTED")
    print(f"rejected {args.email}")


def cmd_bounce(args):
    store.update(args.email, status="BOUNCED")
    print(f"marked {args.email} as bounced")


def cmd_digest(_args):
    today = _today()
    rows = store.load()
    sent_today = [
        r for r in rows
        if r["status"] in ["SENT", "FOLLOWED_UP"] and (r.get("sent_at") or "").startswith(today)
    ]
    skipped = [r for r in rows if r["status"] in ["SKIPPED", "NEEDS_MANUAL_RESEARCH"]]
    no_company = [r for r in rows if r["status"] == "NEED_COMPANY"]

    lines = [f"Cold outreach digest - {today}", ""]
    lines.append(f"Sent today: {len(sent_today)}")
    for r in sent_today:
        lines.append(f"  {r['company_name'] or r['email']} - {r['subject']}")

    if skipped:
        lines.append(f"\nSkipped (weak research): {len(skipped)}")
        for r in skipped[-10:]:
            lines.append(f"  {r['company_name'] or r['email']}")

    if no_company:
        lines.append(f"\nNo company name: {len(no_company)}")
        for r in no_company[-10:]:
            lines.append(f"  {r['email']}")

    body = "\n".join(lines)
    print(body)
    send.send_email(os.environ["SELF_EMAIL"], f"Cold outreach digest {today}", body)


def main():
    p = argparse.ArgumentParser(prog="cold-outreach")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("run", help="full pipeline").set_defaults(func=cmd_run)
    sub.add_parser("list", help="show drafts").set_defaults(func=cmd_list)
    sub.add_parser("digest", help="send daily summary").set_defaults(func=cmd_digest)
    
    f = sub.add_parser("followup", help="generate follow-ups")
    f.set_defaults(func=cmd_followup)

    a = sub.add_parser("add", help="add a lead")
    a.add_argument("email")
    a.add_argument("--company", default=None)
    a.set_defaults(func=cmd_add)

    ap = sub.add_parser("approve", help="approve a draft")
    ap.add_argument("email")
    ap.set_defaults(func=cmd_approve)

    rj = sub.add_parser("reject", help="reject a draft")
    rj.add_argument("email")
    rj.set_defaults(func=cmd_reject)

    b = sub.add_parser("bounce", help="mark as bounced")
    b.add_argument("email")
    b.set_defaults(func=cmd_bounce)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()