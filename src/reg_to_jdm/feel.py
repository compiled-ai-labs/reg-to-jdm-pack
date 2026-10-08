"""The FEEL engine: Camunda's DMN engine (dmn-scala) and FEEL engine (feel-scala), at the
versions Camunda 8.9 pins, run as a Java process (runner/). The runtime of the DMN target.

A JDK 21 is needed; Maven builds runner/target/feel-runner.jar on first use. No model.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[2] / "runner"
JAR = RUNNER / "target" / "feel-runner.jar"


class FeelUnavailable(RuntimeError):
    pass


def _java() -> str | None:
    home = os.environ.get("JAVA_HOME")
    if home:
        for name in ("java", "java.exe"):
            p = Path(home) / "bin" / name
            if p.exists():
                return str(p)
    return shutil.which("java")


def available() -> bool:
    return _java() is not None and (JAR.exists() or shutil.which("mvn") is not None)


def build() -> Path:
    if JAR.exists():
        return JAR
    mvn = shutil.which("mvn")
    if mvn is None:
        raise FeelUnavailable("runner/target/feel-runner.jar is missing and mvn is not on PATH")
    subprocess.run([mvn, "-q", "-f", str(RUNNER / "pom.xml"), "package"], check=True)
    return JAR


class Runner:
    """One Java process; requests and answers are JSON lines."""

    def __init__(self):
        java = _java()
        if java is None:
            raise FeelUnavailable("the DMN target needs a Java 21 runtime (JAVA_HOME or PATH)")
        jar = build()
        self.proc = subprocess.Popen(
            [java, "-jar", str(jar)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1)

    def request(self, **req) -> dict:
        self.proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise FeelUnavailable("the FEEL runner stopped")
        return json.loads(line)

    def version(self) -> str:
        return self.request(op="version")["value"]

    def load(self, xml: str) -> str | None:
        """None when the engine parses the DMN (XSD and every FEEL expression), else why."""
        a = self.request(op="load", xml=xml)
        return None if a["ok"] else a["error"]

    def eval(self, decision: str, inp: dict) -> tuple[object, str | None]:
        a = self.request(op="eval", decision=decision, input=inp)
        return (a.get("value"), None) if a["ok"] else (None, a["error"])

    def parse(self, expr: str, unary: bool = False) -> str | None:
        a = self.request(op="parse", expr=expr, unary=unary)
        return None if a["ok"] else a["error"]

    def expr(self, expr: str, context: dict) -> tuple[object, list[str], str | None]:
        """(value, suppressed failures, error)."""
        a = self.request(op="expr", expr=expr, context=context)
        if not a["ok"]:
            return None, [], a["error"]
        return a.get("value"), a.get("failures") or [], None

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.stdin.close()
            self.proc.wait(timeout=30)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
