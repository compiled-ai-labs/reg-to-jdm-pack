"""Deploy out/pack/rules.dmn to a running Camunda 8 and evaluate every pack test there.

Camunda 8 Run (c8run) listens on http://localhost:8080 with no authentication by default. The
script deploys the DMN (POST /v2/deployments), evaluates the `results` decision for every
tests/*.json input (POST /v2/decision-definitions/evaluation), and prints each paragraph's
verdict next to the ZEN engine's and dmn-scala's, as a Markdown table. Exit code 1 when any
of the three differ or a test's expected verdict is not met.

    uv run python scripts/camunda_run_check.py [--url http://localhost:8080] [--user demo]

Standard library only, besides this package. Not part of CI: it needs a running Camunda 8.
"""

import argparse
import base64
import json
import sys
import urllib.request
import uuid
from pathlib import Path

import zen

from reg_to_jdm.feel import Runner
from reg_to_jdm.validator import evaluate

PACK = Path(__file__).resolve().parents[1] / "out" / "pack"


def _request(url: str, data: bytes, content_type: str, auth: str | None) -> dict:
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": content_type,
                                          "Accept": "application/json"})
    if auth:
        req.add_header("Authorization", "Basic " + base64.b64encode(auth.encode()).decode())
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def deploy(base: str, auth: str | None) -> dict:
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"resources\"; "
            f"filename=\"rules.dmn\"\r\nContent-Type: application/xml\r\n\r\n").encode()
    body += (PACK / "rules.dmn").read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    return _request(f"{base}/v2/deployments", body,
                    f"multipart/form-data; boundary={boundary}", auth)


def evaluate_c8(base: str, auth: str | None, inp: dict) -> dict:
    body = json.dumps({"decisionDefinitionId": "results", "variables": inp}).encode()
    answer = _request(f"{base}/v2/decision-definitions/evaluation", body, "application/json",
                      auth)
    return json.loads(answer["output"])


def verdict(result: dict, key: str, rule_id: str | None) -> str:
    entries = (result.get("results") or {}).get(key) or []
    if rule_id:
        entries = [e for e in entries if e["rule_id"] == rule_id]
    got = sorted({e["result"] for e in entries})
    if not got:
        return "not_applicable"
    return "fail" if "fail" in got else got[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8080")
    ap.add_argument("--user", help="user:password for basic authentication, if enabled")
    args = ap.parse_args()
    deployed = deploy(args.url, args.user)
    decisions = sorted(d["decisionDefinition"]["decisionDefinitionId"]
                       for d in deployed["deployments"] if d.get("decisionDefinition"))
    print(f"deployed {len(decisions)} decisions: {', '.join(decisions)} "
          f"(deployment key {deployed['deploymentKey']})\n")
    receipts = json.loads((PACK / "receipts.json").read_text("utf-8"))
    decision = zen.ZenEngine().create_decision((PACK / "rules.jdm.json").read_text("utf-8"))
    runner = Runner()
    problem = runner.load((PACK / "rules.dmn").read_text("utf-8"))
    if problem:
        print(f"dmn-scala does not load rules.dmn: {problem}")
        return 1
    print("| Test | Expected | ZEN (JDM) | dmn-scala (DMN) | Camunda 8.9.23 (DMN) |")
    print("| - | - | - | - | - |")
    bad = 0
    for path in sorted((PACK / "tests").glob("*.json")):
        test = json.loads(path.read_text("utf-8"))
        inp = test["input"]
        jdm, _ = evaluate(decision, inp)
        dmn, _ = runner.eval("results", inp)
        c8 = evaluate_c8(args.url, args.user, inp)
        if "field" in test:
            field = test["field"].split(".")
            want = test["expected"]

            def value(result, field=field):
                for part in field:
                    result = (result or {}).get(part)
                return result

            if "value" in want:
                shown = [repr(value(r)) for r in (jdm, dmn, c8)]
                ok = all(value(r) == want["value"] for r in (jdm, dmn, c8))
                expected = repr(want["value"])
            else:
                def holds(r, want=want):
                    days = value(r) or []
                    return all(d in days for d in want.get("includes", [])) and \
                        not any(d in days for d in want.get("excludes", []))
                shown = ["holds" if holds(r) else "does not hold" for r in (jdm, dmn, c8)]
                ok = all(holds(r) for r in (jdm, dmn, c8))
                expected = "includes/excludes"
        else:
            key = receipts["rules"][test["rule_id"]]["dmn"]["decision"] if test.get("rule_id") \
                else test["subsection_key"]
            rid = None if "subsection" in test else test["rule_id"]
            shown = [verdict(r, key, rid) for r in (jdm, dmn, c8)]
            expected = test["expected"]["result"]
            ok = len(set(shown)) == 1 and shown[0] == expected
        bad += not ok
        print(f"| {path.stem} | {expected} | " + " | ".join(shown) + " |")
    runner.close()
    print(f"\n{'all agree' if not bad else f'{bad} test(s) differ'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
