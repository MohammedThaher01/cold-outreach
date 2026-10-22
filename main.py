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


def _send_with_cap(rows, cap, sent_today):
    for r in rows:
        if r["status"] != "approved":
            continue
        if sent_today >= cap:
            print(f"daily cap {cap} reached, stopping")
            return sent_today
        try:
            print(f"sending to {r['email']}...")
            send.send_email(r["email"], r["subject"], r["body"])
            store.update(r["email"], status="sent", sent_at=_now().isoformat())
            sent_today += 1
            delay = random.randint(45, 60)
            print(f"  sent. waiting {delay}s")
            time.sleep(delay)
        except Exception as e:
            print(f"  failed: {e}")
    return sent_today


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
            store.update(r["email"], status="need_company")
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
                status="needs_manual_research",
                insight_card=json.dumps(card),
            )
            print("  skipped (weak evidence)")
        else:
            store.update(
                r["email"],
                status="ready_for_email",
                insight_card=json.dumps(card),
            )
            print(f"  ok: {card.get('specific_observation', '')[:70]}")
        time.sleep(2)

    # Phase 2: generate emails for ready rows
    for r in store.load():
        if r["status"] != "ready_for_email":
            continue
        card = json.loads(r["insight_card"])
        print(f"writing email for {r['company_name']}...")
        try:
            out = generate.generate_email(card)
        except Exception as e:
            print(f"  failed: {e}")
            continue

        if out.get("skip"):
            store.update(r["email"], status="skipped")
            print("  skipped")
        else:
            store.update(
                r["email"],
                status="draft_review",
                subject=out["subject"],
                body=out["body"],
            )
            print(f"  subject: {out['subject']}")
        time.sleep(1)

    # Phase 3: auto-approve if enabled
    if auto:
        for r in store.load():
            if r["status"] == "draft_review":
                store.update(r["email"], status="approved")
                print(f"auto-approved: {r['email']}")

    # Phase 4: send approved rows up to daily cap
    rows = store.load()
    sent_today = sum(
        1 for r in rows
        if r["status"] == "sent" and (r.get("sent_at") or "").startswith(_today())
    )
    _send_with_cap(rows, cap, sent_today)


def cmd_run(_args):
    run_once()


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
    })
    store.save(rows)
    print(f"added {args.email}")


def cmd_list(_args):
    drafts = [r for r in store.load() if r["status"] == "draft_review"]
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
    store.update(args.email, status="approved")
    print(f"approved {args.email}")


def cmd_reject(args):
    store.update(args.email, status="rejected")
    print(f"rejected {args.email}")


def cmd_digest(_args):
    today = _today()
    rows = store.load()
    sent_today = [
        r for r in rows
        if r["status"] == "sent" and (r.get("sent_at") or "").startswith(today)
    ]
    skipped = [r for r in rows if r["status"] == "skipped"]
    review = [r for r in rows if r["status"] == "needs_manual_research"]
    no_company = [r for r in rows if r["status"] == "need_company"]

    lines = [f"Cold outreach digest - {today}", ""]
    lines.append(f"Sent today: {len(sent_today)}")
    for r in sent_today:
        lines.append(f"  {r['company_name'] or r['email']} - {r['subject']}")

    if skipped:
        lines.append(f"\nSkipped (weak research): {len(skipped)}")
        for r in skipped[-10:]:
            lines.append(f"  {r['company_name'] or r['email']}")

    if review:
        lines.append(f"\nNeed your input: {len(review)}")
        for r in review[-10:]:
            lines.append(f"  {r['company_name'] or r['email']}")

    if no_company:
        lines.append(f"\nNo company name and free email domain: {len(no_company)}")
        for r in no_company[-10:]:
            lines.append(f"  {r['email']}")

    body = "\n".join(lines)
    print(body)
    send.send_email(os.environ["SELF_EMAIL"], f"Cold outreach digest {today}", body)


def main():
    p = argparse.ArgumentParser(prog="cold-outreach")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("run", help="full pipeline: research, generate, send").set_defaults(func=cmd_run)
    sub.add_parser("list", help="show drafts awaiting review").set_defaults(func=cmd_list)
    sub.add_parser("digest", help="send a daily summary to SELF_EMAIL").set_defaults(func=cmd_digest)

    a = sub.add_parser("add", help="add a lead from the command line")
    a.add_argument("email")
    a.add_argument("--company", default=None)
    a.set_defaults(func=cmd_add)

    ap = sub.add_parser("approve", help="approve a draft by email")
    ap.add_argument("email")
    ap.set_defaults(func=cmd_approve)

    rj = sub.add_parser("reject", help="reject a draft by email")
    rj.add_argument("email")
    rj.set_defaults(func=cmd_reject)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()