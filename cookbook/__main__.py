"""Run the desk. One call per message, then the gate in this file's sibling."""

from __future__ import annotations

import argparse
import json
import sys

from cookbook.client import system_one
from cookbook.desk import QUESTIONS, TICKETS, decide, one_question, refund_requested


def _run_ticket(text: str, questions: dict) -> dict:
    return system_one(text, questions)


def report(rows: list[dict], fanout: dict) -> str:
    lines = [
        f"{'id':<5} {'gold':<16} {'action':<16} {'hit':<4} {'p':>5} {'ms':>7}",
        f"{'--':<5} {'----':<16} {'------':<16} {'---':<4} {'-':>5} {'--':>7}",
    ]
    hits = 0
    refund_hits = 0
    for row in rows:
        hits += int(row["hit"])
        refund_hits += int(row["refund_hit"])
        mark = "yes" if row["hit"] else "no"
        lines.append(
            f"{row['id']:<5} {row['gold']:<16} {row['action']:<16} {mark:<4} "
            f"{row['p']:>5.2f} {row['ms']:>7.0f}"
        )
    lines.append("")
    lines.append(f"actions {hits}/{len(rows)}    refund flags {refund_hits}/{len(rows)}")
    lines.append(
        f"one call {fanout['batched_ms']:.0f} ms  {fanout['batched_in']} input tokens"
    )
    lines.append(
        f"eight    {fanout['serial_ms']:.0f} ms  {fanout['serial_in']} input tokens"
    )
    if fanout["batched_ms"] > 0:
        lines.append(
            f"clock    eight calls took {fanout['serial_ms'] / fanout['batched_ms']:.1f}x the one-call wait"
        )
    lines.append(f"model    {fanout['model']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the decision-model desk on ten labeled messages.")
    parser.add_argument("--json", action="store_true", help="print the rows as JSON")
    parser.add_argument("--ticket", help="run one ticket id and print its answers")
    args = parser.parse_args(argv)

    tickets = TICKETS
    if args.ticket:
        tickets = tuple(ticket for ticket in TICKETS if ticket.id == args.ticket)
        if not tickets:
            print(f"unknown ticket {args.ticket}", file=sys.stderr)
            return 2

    rows: list[dict] = []
    model = ""
    for ticket in tickets:
        body = _run_ticket(ticket.text, QUESTIONS)
        model = str(body.get("model") or model)
        answers = body["answers"]
        action = decide(answers)
        team = answers["team"]
        rows.append(
            {
                "id": ticket.id,
                "gold": ticket.action,
                "action": action,
                "hit": action == ticket.action,
                "p": float(team["probabilities"][team["choice"]]),
                "ms": float(body["elapsed_ms"]),
                "refund": refund_requested(answers),
                "refund_gold": ticket.refund,
                "refund_hit": refund_requested(answers) == ticket.refund,
                "choice": team["choice"],
                "urgency": answers["urgency"].get("score"),
                "input_tokens": (body.get("usage") or {}).get("input_tokens"),
                "output_tokens": (body.get("usage") or {}).get("output_tokens"),
            }
        )
        if args.ticket:
            public = {key: answers[key] for key in answers}
            print(json.dumps({"model": model, "elapsed_ms": body["elapsed_ms"], "answers": public}, indent=2))

    sample = tickets[0]
    batched = _run_ticket(sample.text, QUESTIONS)
    serial_ms = 0.0
    serial_in = 0
    for name in QUESTIONS:
        solo = _run_ticket(sample.text, one_question(name))
        serial_ms += float(solo["elapsed_ms"])
        serial_in += int((solo.get("usage") or {}).get("input_tokens") or 0)
    fanout = {
        "calls": len(QUESTIONS),
        "batched_ms": float(batched["elapsed_ms"]),
        "batched_in": int((batched.get("usage") or {}).get("input_tokens") or 0),
        "serial_ms": serial_ms,
        "serial_in": serial_in,
        "model": model or str(batched.get("model") or ""),
    }
    if args.json:
        print(json.dumps({"rows": rows, "fanout": fanout}, indent=2))
    else:
        print(report(rows, fanout))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
