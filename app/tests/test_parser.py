"""Tests for Markdown and frontmatter parsing."""

from __future__ import annotations

from datetime import date

import pytest

from hcp.errors import DocumentError
from hcp.parser.frontmatter import dump_frontmatter, safe_load_yaml, split_frontmatter
from hcp.parser.markdown import (
    assertion_from_markdown,
    assertion_to_markdown,
    looks_like_assertion,
)


def test_valid_frontmatter_is_parsed() -> None:
    assertion = assertion_from_markdown('---\nid: "value.a"\ntype: "value"\n---\n\nBody text.\n')
    assert assertion.id == "value.a"
    assert assertion.type == "value"
    assert assertion.body.strip() == "Body text."


def test_missing_frontmatter_is_reported() -> None:
    with pytest.raises(DocumentError) as excinfo:
        assertion_from_markdown("# Just prose\n\nNo frontmatter here.\n")
    assert excinfo.value.issues[0].code == "missing_frontmatter"


def test_malformed_yaml_is_reported() -> None:
    with pytest.raises(DocumentError) as excinfo:
        assertion_from_markdown('---\nid: "a.b"\n  bad: [unclosed\n---\n\nBody\n')
    assert excinfo.value.issues[0].code == "malformed_yaml"


def test_unterminated_frontmatter_is_reported() -> None:
    with pytest.raises(DocumentError) as excinfo:
        assertion_from_markdown('---\nid: "a.b"\ntype: "value"\n')
    assert excinfo.value.issues[0].code == "unterminated_frontmatter"


def test_frontmatter_must_be_a_mapping() -> None:
    with pytest.raises(DocumentError) as excinfo:
        assertion_from_markdown("---\n- just\n- a list\n---\n\nBody\n")
    assert excinfo.value.issues[0].code == "frontmatter_not_mapping"


def test_unicode_is_preserved() -> None:
    body = "Ich schätze ehrliche Rückmeldung. 日本語も動く。Ελληνικά."
    assertion = assertion_from_markdown(f'---\nid: "value.unicode"\ntype: "value"\n---\n\n{body}\n')
    assert assertion.body.strip() == body
    assert "日本語" in assertion_to_markdown(assertion)


def test_multiline_markdown_body_is_preserved() -> None:
    body = "First paragraph.\n\n- bullet one\n- bullet two\n\nSecond paragraph."
    assertion = assertion_from_markdown(f'---\nid: "value.multi"\ntype: "value"\n---\n\n{body}\n')
    assert assertion.body.strip() == body


def test_empty_body_is_allowed() -> None:
    assertion = assertion_from_markdown('---\nid: "value.empty"\ntype: "value"\n---\n')
    assert assertion.body.strip() == ""


def test_empty_frontmatter_is_treated_as_empty_mapping() -> None:
    raw, body = split_frontmatter("---\n---\n\nBody\n")
    assert safe_load_yaml(raw) == {}
    assert body.strip() == "Body"


def test_bom_prefixed_document_is_parsed() -> None:
    assertion = assertion_from_markdown('\ufeff---\nid: "value.bom"\ntype: "value"\n---\n\nB\n')
    assert assertion.id == "value.bom"


def test_dates_are_coerced_to_date_objects() -> None:
    assertion = assertion_from_markdown(
        '---\nid: "value.d"\ntype: "value"\ncreated: "2024-03-01"\n'
        'valid_from: "2024-01-01"\nvalid_until: "2025-01-01"\n---\n\nB\n'
    )
    assert assertion.created == date(2024, 3, 1)
    assert assertion.valid_until == date(2025, 1, 1)


def test_null_valid_until_is_none() -> None:
    assertion = assertion_from_markdown(
        '---\nid: "value.n"\ntype: "value"\nvalid_until: null\n---\n\nB\n'
    )
    assert assertion.valid_until is None


def test_unknown_metadata_is_preserved() -> None:
    assertion = assertion_from_markdown(
        '---\nid: "value.f"\ntype: "value"\nfuture_field: "keep me"\n---\n\nB\n'
    )
    assert assertion.unknown_fields().get("future_field") == "keep me"
    assert "future_field: keep me" in assertion_to_markdown(assertion)


def test_missing_id_is_reported() -> None:
    with pytest.raises(DocumentError) as excinfo:
        assertion_from_markdown('---\ntype: "value"\n---\n\nBody\n')
    assert excinfo.value.issues[0].code == "missing_required_field"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("---\nid: a\n---\n", True),
        ("no frontmatter", False),
        ("# Heading", False),
    ],
)
def test_looks_like_assertion(text: str, expected: bool) -> None:
    assert looks_like_assertion(text) is expected


def test_round_trip_is_stable() -> None:
    original = assertion_from_markdown(
        '---\nid: "value.round"\ntype: "value"\nsource: "human"\n'
        'authority: "authoritative"\nstatus: "active"\nvisibility: "private"\n'
        'confidence: 0.75\ncreated: "2024-01-01"\ntags:\n  - a\n  - b\n---\n\nBody.\n'
    )
    text = assertion_to_markdown(original)
    again = assertion_from_markdown(text)
    assert again.id == original.id
    assert again.confidence == original.confidence
    assert again.tags == original.tags
    assert again.body == original.body
    assert assertion_to_markdown(again) == text


def test_dump_frontmatter_without_body() -> None:
    text = dump_frontmatter({"id": "a.b", "type": "value"}, "")
    assert text.endswith("---\n")
    assert "id: a.b" in text


def test_markdown_is_never_executed() -> None:
    """A body containing shell/markdown directives must remain inert text."""
    body = "$(rm -rf /) `whoami` {% import os %} {{ 7*7 }}"
    assertion = assertion_from_markdown(f'---\nid: "value.inert"\ntype: "value"\n---\n\n{body}\n')
    assert assertion.body.strip() == body
