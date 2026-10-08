"""The FEEL engine for the DMN tests: Camunda's DMN engine behind runner/ (feel.py).

It needs a JDK 21 (and Maven to build the jar once). Without one, the DMN tests skip locally;
with REQUIRE_FEEL=1, which CI sets, they fail instead, so the gate is never skipped in CI.
"""

import os

import pytest

from reg_to_jdm import feel


@pytest.fixture(scope="session")
def feel_runner():
    if not feel.available():
        if os.environ.get("REQUIRE_FEEL") == "1":
            pytest.fail("REQUIRE_FEEL=1 but no Java 21 / Maven for the FEEL runner")
        pytest.skip("no Java 21 / Maven: the DMN target is not tested here")
    runner = feel.Runner()
    yield runner
    runner.close()
