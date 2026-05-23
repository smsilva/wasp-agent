"""CLI admin commands for invite/revoke/list identities.

Thin wrapper over `wasp.auth`. Operators invoke via `python -m wasp.auth_cli`
(or the `scripts/admin-*` helpers).
"""

import argparse
import sys

from wasp import auth


def _print_table(rows: list[dict]) -> None:
    headers = ("channel", "channel_id", "user_id", "display_name", "linked_at")
    widths = {h: len(h) for h in headers}
    for row in rows:
        for h in headers:
            widths[h] = max(widths[h], len(str(row[h])))
    fmt = "  ".join(f"{{:<{widths[h]}}}" for h in headers)
    print(fmt.format(*headers))
    print(fmt.format(*("-" * widths[h] for h in headers)))
    for row in rows:
        print(fmt.format(*(str(row[h]) for h in headers)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wasp.auth_cli")
    subs = parser.add_subparsers(dest="cmd", required=True)

    invite = subs.add_parser("invite")
    invite.add_argument("--name", required=True)
    invite.add_argument("--created-by", required=True)
    invite.add_argument("--channel", default=None)

    revoke = subs.add_parser("revoke")
    revoke.add_argument("--channel", required=True)
    revoke.add_argument("--channel-id", required=True)

    subs.add_parser("list")

    args = parser.parse_args(argv)

    if args.cmd == "invite":
        token = auth.create_invite(
            display_name=args.name,
            created_by=args.created_by,
            channel=args.channel,
        )
        print(token)
        return 0

    if args.cmd == "revoke":
        ok = auth.revoke(args.channel, args.channel_id)
        if ok:
            print("revoked")
            return 0
        print("not found", file=sys.stderr)
        return 1

    # args.cmd == "list"
    rows = auth.list_identities()
    if not rows:
        print("(no identities)")
        return 0
    _print_table(rows)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
