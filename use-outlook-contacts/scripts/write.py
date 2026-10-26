#!/usr/bin/env python3
"""Build explicit Outlook contact fields for preview or update."""
import argparse
import json
import sys


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)

def build_contact(args):
    body = {}
    fields = {
        "displayName": args.display_name,
        "givenName": args.given_name,
        "surname": args.surname,
        "companyName": args.company,
        "jobTitle": args.job_title,
        "mobilePhone": args.mobile,
        "personalNotes": args.notes,
    }
    for key, value in fields.items():
        if value is not None:
            body[key] = value
    if args.emails:
        label = args.display_name or ""
        body["emailAddresses"] = [{"address": address, "name": label or address} for address in args.emails]
    if args.phones:
        body["businessPhones"] = args.phones
    if not body:
        fail("nothing to build: supply a contact field")
    return body


def main(argv):
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    contact = subparsers.add_parser("contact")
    contact.add_argument("--display-name")
    contact.add_argument("--given-name")
    contact.add_argument("--surname")
    contact.add_argument("--email", action="append", default=[], dest="emails")
    contact.add_argument("--phone", action="append", default=[], dest="phones")
    contact.add_argument("--mobile")
    contact.add_argument("--company")
    contact.add_argument("--job-title")
    contact.add_argument("--notes")

    args = parser.parse_args(argv)
    print(json.dumps(build_contact(args), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
