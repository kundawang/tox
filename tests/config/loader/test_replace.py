from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, ClassVar, cast

import pytest

from tox.config.loader.api import ConfigLoadArgs
from tox.config.loader.replacer import MatchExpression, find_replace_expr, replace_factor
from tox.report import HandledError

if TYPE_CHECKING:
    from tests.config.loader.conftest import ReplaceOne
    from tox.config.main import Config


@pytest.mark.parametrize(
    ("value", "exp_output"),
    [
        ("[]", [MatchExpression([["posargs"]])]),
        ("123[]", ["123", MatchExpression([["posargs"]])]),
        ("[]123", [MatchExpression([["posargs"]]), "123"]),
        (r"\[\] []", ["[] ", MatchExpression([["posargs"]])]),
        (r"[\] []", ["[] ", MatchExpression([["posargs"]])]),
        (r"\[] []", ["[] ", MatchExpression([["posargs"]])]),
        ("{foo}", [MatchExpression([["foo"]])]),
        (r"\{foo} {bar}", ["{foo} ", MatchExpression([["bar"]])]),
        ("{foo} {bar}", [MatchExpression([["foo"]]), " ", MatchExpression([["bar"]])]),
        (r"{foo\} {bar}", ["{foo} ", MatchExpression([["bar"]])]),
        (r"{foo:{bar}}", [MatchExpression([["foo"], [MatchExpression([["bar"]])]])]),
        (r"{foo\::{bar}}", [MatchExpression([["foo:"], [MatchExpression([["bar"]])]])]),
        (r"{foo:B:c:D:e}", [MatchExpression([["foo"], ["B"], ["c"], ["D"], ["e"]])]),
        (r"{\{}", [MatchExpression([["{"]])]),
        (r"{\}}", [MatchExpression([["}"]])]),
        (
            r"p{foo:b{a{r}:t}:{ba}z}s",
            [
                "p",
                MatchExpression(
                    [
                        ["foo"],
                        [
                            "b",
                            MatchExpression(
                                [
                                    ["a", MatchExpression([["r"]])],
                                    ["t"],
                                ],
                            ),
                        ],
                        [
                            MatchExpression(
                                [["ba"]],
                            ),
                            "z",
                        ],
                    ],
                ),
                "s",
            ],
        ),
        ("\\", ["\\"]),
        (r"\d", ["\\d"]),
        (r"C:\WINDOWS\foo\bar", [r"C:\WINDOWS\foo\bar"]),
    ],
)
def test_match_expr(value: str, exp_output: list[str | MatchExpression]) -> None:
    assert find_replace_expr(value) == exp_output


@pytest.mark.parametrize(
    ("value", "exp_exception"),
    [
        ("py-{foo,bar}", None),
        ("py37-{base,i18n},b", None),
        ("py37-{i18n,base},b", None),
        ("{toxinidir,}", None),
        ("{env}", r"MatchError\('No variable name was supplied in {env} substitution'\)"),
        ("{factor}", r"MatchError\('No label was supplied in {factor} substitution'\)"),
    ],
)
def test_dont_replace(replace_one: ReplaceOne, value: str, exp_exception: str | None) -> None:
    """Test that invalid expressions are not replaced."""
    if exp_exception:
        with pytest.raises(HandledError, match=exp_exception):
            replace_one(value)
    else:
        assert replace_one(value) == value


@pytest.mark.parametrize(
    ("match_expression", "exp_repr"),
    [
        (MatchExpression([["posargs"]]), "MatchExpression(expr=[['posargs']], term_pos=None)"),
        (MatchExpression([["posargs"]], 1), "MatchExpression(expr=[['posargs']], term_pos=1)"),
        (MatchExpression("foo", -42), "MatchExpression(expr='foo', term_pos=-42)"),
    ],
)
def test_match_expression_repr(match_expression: MatchExpression, exp_repr: str) -> None:
    print(match_expression)  # ruff:ignore[print]
    assert repr(match_expression) == exp_repr


class _FactorLabelConf:
    """Minimal stand-in for :class:`tox.config.main.Config` carrying factor labels."""

    factor_labels: ClassVar[dict[str, Any]] = {
        "django": SimpleNamespace(values=["django42", "django50"], default="django50"),
    }


@pytest.mark.parametrize(
    ("env_name", "args", "override", "expected"),
    [
        pytest.param("task-django42", ["django"], None, "django42", id="active-factor"),
        pytest.param("other", ["django"], None, "django50", id="group-default"),
        pytest.param("other", ["django", "django42"], None, "django42", id="inline-fallback-beats-group-default"),
        pytest.param("other", ["django", ""], None, "", id="empty-fallback-beats-group-default"),
        pytest.param("other", ["unknown", ""], None, "", id="unknown-label-empty-fallback"),
        pytest.param("task-django42", ["django", ""], None, "django42", id="active-factor-beats-empty-fallback"),
        pytest.param("task-django42", ["django"], "django60", "django60", id="override-beats-active-factor"),
        pytest.param("task-django42", ["django"], "", "", id="empty-override-beats-active-factor"),
        pytest.param("other", ["django"], "", "", id="empty-override-beats-group-default"),
        pytest.param(None, ["django", ""], None, "", id="core-empty-fallback"),
    ],
)
def test_replace_factor_priority(
    monkeypatch: pytest.MonkeyPatch,
    env_name: str | None,
    args: list[str],
    override: str | None,
    expected: str,
) -> None:
    """``{factor:label}`` resolves as: override > active factor > inline fallback > group default."""
    if override is not None:
        monkeypatch.setenv("TOX_FACTOR_django", override)
    else:
        monkeypatch.delenv("TOX_FACTOR_django", raising=False)
    conf_args = ConfigLoadArgs(chain=[], name=env_name, env_name=env_name)
    assert replace_factor(cast("Config", _FactorLabelConf()), args, conf_args) == expected
