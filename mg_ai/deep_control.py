"""Local owner controls; never establishes a ChatGPT session or makes an inference call."""
import argparse
import json
import os

from mg_ai.deep_state import DeepState


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("status", "enable", "disable", "session-ready",
                                           "session-unavailable", "reconcile"))
    parser.add_argument("--actor", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--execution-id", default="")
    parser.add_argument("--outcome", choices=("CONFIRMED_NOT_EXECUTED", "CONFIRMED_FAILED",
                                               "CONFIRMED_COMPLETED", "UNRESOLVED"))
    parser.add_argument("--state", default=os.getenv("MG_STATE_PATH", ".runtime/state.sqlite"))
    args = parser.parse_args()
    if args.action != "status" and (not args.actor.strip() or not args.reason.strip()):
        parser.error("owner actor and reason required")
    state = DeepState(args.state)
    try:
        if args.action == "reconcile":
            if not args.execution_id or not args.outcome:
                parser.error("reconcile requires --execution-id and --outcome")
            state.reconcile(args.execution_id, args.outcome, args.actor, args.reason)
        elif args.action != "status":
            state.configure(args.action, args.actor, args.reason)
        print(json.dumps({**state.control(), "concurrency": 1,
                          "provider_enabled": state.provider_enabled("omniroute"),
                          "claimed": bool(state.db.execute("SELECT 1 FROM deep_claim").fetchone())}))
    finally:
        state.db.close()


if __name__ == "__main__":
    main()
