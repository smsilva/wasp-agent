import pytest
from radon.complexity import cc_visit
from pathlib import Path

MAX_COMPLEXITY = 10

SOURCE_FILES = sorted(Path("wasp").glob("**/*.py")) + [Path("main.py")]


@pytest.mark.parametrize("path", SOURCE_FILES, ids=str)
def test_cyclomatic_complexity(path):
    results = cc_visit(path.read_text())
    violations = [
        f"  {r.name} (linha {r.lineno}): {r.complexity}"
        for r in results
        if r.complexity > MAX_COMPLEXITY
    ]
    assert not violations, (
        f"{path}: funções acima do limite {MAX_COMPLEXITY}:\n" + "\n".join(violations)
    )
