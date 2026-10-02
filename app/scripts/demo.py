#!/usr/bin/env python3
"""Run the complete HCP workflow end to end in a throwaway Codex.

This mirrors the flow from BUILD-APP section 21:

    hcp init
      -> write assertion
      -> hcp validate
      -> hcp bundle
      -> AI returns observation
      -> hcp observe
      -> hcp review
      -> Git diff

Run it with ``make demo``. Everything happens in a temporary directory, so it
never touches a real Codex, and no network access is used.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from hcp.bundles.generator import generate_bundle
from hcp.config import init_codex
from hcp.models.assertion import Assertion
from hcp.observations.workflow import ingest_observation, review_observation
from hcp.output.json import export_codex
from hcp.repository.codex import Codex
from hcp.validation.validator import validate_codex

TODAY = date.today().isoformat()


def step(number: int, title: str) -> None:
    print(f"\n\033[1m{number}. {title}\033[0m\n{'-' * (len(title) + 4)}")


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="hcp-demo-")) / "my-codex"
    try:
        step(1, "hcp init")
        codex, created = init_codex(root, title="Demo Codex", codex_id="codex.demo", with_git=True)
        print(f"Created {codex.root} ({len(created)} paths)")

        step(2, "Write assertions")
        today = date.today()
        for identifier, type_, body in [
            (
                "value.intellectual-honesty",
                "value",
                "I value honest assessment over comfortable agreement.",
            ),
            (
                "preference.direct-communication",
                "preference",
                "I prefer direct answers with explicit trade-offs.",
            ),
            (
                "identity.software-professional",
                "identity",
                "I work as a software and knowledge-work professional.",
            ),
            (
                "boundary.no-credentials",
                "boundary",
                "Never store passwords, API keys, or seed phrases in the Codex.",
            ),
        ]:
            assertion = Assertion(
                id=identifier,
                type=type_,
                source="human",
                authority="authoritative",
                status="active",
                created=today,
                updated=today,
                valid_from=today,
                visibility="private",
                body=body,
            )
            codex.add(assertion)
            print(f"  added {identifier}")

        step(3, "hcp validate")
        report = validate_codex(Codex.load(root))
        print(f"  {report.summary()}")
        for issue in report.issues:
            print(f"  {issue.format()}")
        assert report.ok, "the demo Codex should be valid"

        step(4, "hcp export --format json")
        payload = json.loads(export_codex(Codex.load(root)))
        print(f"  {payload['assertion_count']} assertions, {len(payload['documents'])} prose docs")

        step(5, "hcp bundle --scope assistant")
        bundle = generate_bundle(Codex.load(root), ["assistant"], purpose="Personal assistance")
        ids = [a["id"] for a in bundle.assertions]
        print(f"  bundle_id {bundle.bundle_id}")
        print(f"  included  {', '.join(ids)}")
        print(f"  trust     {bundle.trust.covenant} / {bundle.trust.status}")
        print("  withheld  'fact.address' would need a restricted scope")

        step(6, "AI returns an observation")
        payload_path = root.parent / "observation.yaml"
        payload_path.write_text(
            "id: obs.2026-01-01.communication.001\n"
            "confidence: 0.72\n"
            "tags:\n  - communication\n"
            "derived_from:\n  - conversation:demo\n"
            "body: |\n"
            "  The user appears to prefer concise answers followed by deeper\n"
            "  technical detail when the problem is complex.\n",
            encoding="utf-8",
        )
        print(f"  wrote {payload_path.name}")

        step(7, "hcp observe")
        codex = Codex.load(root)
        result = ingest_observation(codex, payload_path, source_label="demo-adapter")
        stored = codex.require(result.observation_id)
        print(f"  {result.observation_id} -> {result.path}")
        print(f"  source={stored.source} authority={stored.authority} status={stored.status}")

        step(8, "hcp review --edit")
        review = review_observation(
            codex,
            result.observation_id,
            "edit",
            body="I prefer concise answers on routine questions, with depth when needed.",
            new_id="preference.concise-with-depth",
            new_type="preference",
            note="Confirmed, but sharper than the AI phrased it.",
        )
        print(f"  created {review.promoted_id}")
        promoted = codex.require("preference.concise-with-depth")
        print(f"  provenance.observation_id = {promoted.provenance.observation_id}")
        retained = result.observation_id in [a.id for a in codex.assertions]
        print(f"  original observation retained: {retained}")

        step(9, "hcp validate again")
        final = validate_codex(Codex.load(root))
        print(f"  {final.summary()}")
        assert final.ok

        step(10, "Git diff (read-only)")
        if shutil.which("git"):
            result = subprocess.run(
                ["git", "-C", str(root), "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=False,
            )
            for line in result.stdout.splitlines()[:10]:
                print(f"  {line}")
            print(f"  ({len(result.stdout.splitlines())} change(s); hcp never commits for you)")
        else:
            print("  git not installed; skipped")

        print("\n\033[1mComplete.\033[0m The Codex stayed local the entire time.")
        print(f"It lives at {root} — inspect it, edit it, delete it.\n")
        return 0
    finally:
        shutil.rmtree(root.parent, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
