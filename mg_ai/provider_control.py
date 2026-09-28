"""Local owner-only provider control; database access is the administrative boundary."""
import argparse
import json
import os

from mg_ai.state import State

PROVIDERS = ("openrouter", "nvidia", "openai-compatible", "direct", "omniroute")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("list", "disable", "enable"))
    parser.add_argument("provider", choices=PROVIDERS, nargs="?")
    parser.add_argument("--actor")
    parser.add_argument("--reason")
    parser.add_argument("--state", default=os.getenv("MG_STATE_PATH", ".runtime/state.sqlite"))
    args = parser.parse_args()
    if args.action != "list" and (not args.provider or not args.actor or not args.reason):
        parser.error("mutation requires provider, --actor and --reason")
    state = State(args.state)
    try:
        if args.action != "list":
            state.set_provider_enabled(args.provider, args.action == "enable", args.actor, args.reason)
        print(json.dumps({p: state.provider_enabled(p) for p in PROVIDERS}))
        print(json.dumps([dict(row) for row in state.db.execute(
            "SELECT provider,enabled,actor,reason,updated FROM provider_control ORDER BY provider")]))
    finally:
        state.db.close()


if __name__ == "__main__":
    main()
