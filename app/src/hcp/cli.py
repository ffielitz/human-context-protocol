"""The ``hcp`` command-line interface.

Design principles reflected here (BUILD-APP sections 5 and 22):

* every command takes an explicit Codex path, so nothing acts on "the wrong
  Codex" by accident
* errors are calm, specific, and actionable; exit codes are meaningful
* output is scriptable: ``--format json`` is available wherever it helps
* no command silently sends anything anywhere
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import typer

from .bundles.generator import excluded_reason, generate_bundle, load_scopes
from .config import AppConfig, init_codex
from .constants import APP_VERSION, HCP_VERSION, TRUST_COVENANT
from .errors import HCPError, Issue, Severity
from .ids import is_valid_id, suggest_id
from .models.assertion import Assertion, utc_today
from .models.bundle import TrustConditions
from .observations.workflow import ingest_observation, list_observations, review_observation
from .output.json import codex_to_dict, dumps
from .repository.codex import TYPE_DIRECTORIES, Codex
from .repository.git import diff as git_diff
from .repository.git import history as git_history
from .repository.git import status as git_status
from .validation.validator import validate_codex

app = typer.Typer(
    name="hcp",
    help=(
        "Human Context Protocol — your context, your authority.\n\n"
        "A Codex is a local folder of Markdown you own. AI systems consume "
        "scoped Context Bundles that you explicitly create."
    ),
    add_completion=False,
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

#: Exit code used when a command fails for an expected, reportable reason.
EXIT_ERROR = 1
#: Exit code used when validation finds errors.
EXIT_INVALID = 2

Config = AppConfig.load()


class TypeOption(StrEnum):
    """Assertion types accepted on the command line."""

    FACT = "fact"
    BELIEF = "belief"
    VALUE = "value"
    PRINCIPLE = "principle"
    PREFERENCE = "preference"
    BOUNDARY = "boundary"
    GOAL = "goal"
    ASPIRATION = "aspiration"
    IDENTITY = "identity"
    RELATIONSHIP = "relationship"
    EXPERIENCE = "experience"
    OBSERVATION = "observation"


class VisibilityOption(StrEnum):
    """Disclosure classes accepted on the command line."""

    PUBLIC = "public"
    PRIVATE = "private"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


class ScopeOption(StrEnum):
    """Scopes offered for quick selection on the command line."""

    ASSISTANT = "assistant"
    CAREER = "career"
    WRITING = "writing"
    PUBLIC = "public"


# ----------------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------------


def _fail(message: str, *, code: int = EXIT_ERROR) -> None:
    """Print an error message and exit with ``code``."""
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code)


def _load_codex(path: Path) -> Codex:
    """Load a Codex or exit with a helpful message."""
    try:
        return Codex.load(path)
    except HCPError as exc:
        _fail(str(exc))
        raise  # pragma: no cover - _fail always exits


def _echo_json(data: Any) -> None:
    """Print JSON to stdout."""
    typer.echo(dumps(data))


def _resolve_at(value: str | None) -> date:
    """Parse an optional ``--at YYYY-MM-DD`` value."""
    if not value:
        return utc_today()
    try:
        return date.fromisoformat(value)
    except ValueError:
        _fail(f"--at must be an ISO date (YYYY-MM-DD), got {value!r}")
        raise  # pragma: no cover


def _print_issues(issues: list[Issue], *, quiet: bool = False) -> None:
    """Print validation issues, each with its stable machine-readable code.

    Including the code makes the output greppable and gives a user something to
    search for when they hit a rule they did not expect.
    """
    for issue in issues:
        if quiet and issue.severity is Severity.WARNING:
            continue
        colour = typer.colors.RED if issue.severity is Severity.ERROR else typer.colors.YELLOW
        typer.secho(f"{issue.format()} [{issue.code}]", fg=colour, err=True)


def _version_callback(value: bool) -> None:
    """Print version information and exit."""
    if value:
        typer.echo(f"hcp {APP_VERSION} (HCP {HCP_VERSION}, covenant {TRUST_COVENANT})")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    """Human Context Protocol reference CLI."""


@app.command()
def version() -> None:
    """Show version information."""
    typer.echo(f"hcp {APP_VERSION}")
    typer.echo(f"hcp spec   {HCP_VERSION}")
    typer.echo(f"covenant   {TRUST_COVENANT}")
    typer.echo(f"python     {sys.version.split()[0]}")


# ----------------------------------------------------------------------
# init
# ----------------------------------------------------------------------


@app.command()
def init(
    path: Annotated[
        Path,
        typer.Argument(help="Directory to create the Codex in."),
    ],
    title: Annotated[
        str | None, typer.Option("--title", help="Human-readable Codex title.")
    ] = None,
    codex_id: Annotated[
        str | None, typer.Option("--codex-id", help="Stable Codex identifier, e.g. codex.personal.")
    ] = None,
    language: Annotated[str, typer.Option("--language", help="BCP-47 language tag.")] = "en",
    tz: Annotated[
        str | None, typer.Option("--timezone", help="IANA timezone name, e.g. Europe/Berlin.")
    ] = None,
    visibility: Annotated[
        VisibilityOption,
        typer.Option("--default-visibility", help="Default visibility for new assertions."),
    ] = VisibilityOption.PRIVATE,
    force: Annotated[
        bool, typer.Option("--force", help="Initialise even if the directory is not empty.")
    ] = False,
    git: Annotated[
        bool | None,
        typer.Option(
            "--git/--no-git",
            help="Initialise a Git repository (default: yes, when git is available).",
        ),
    ] = None,
) -> None:
    """Create a new Codex: your own, local, human-readable context folder."""
    if codex_id and not is_valid_id(codex_id):
        _fail(f"--codex-id must be a dotted id such as codex.personal, got {codex_id!r}")

    try:
        codex, created = init_codex(
            path,
            title=title,
            codex_id=codex_id,
            language=language,
            timezone_name=tz,
            default_visibility=str(visibility),
            force=force,
            with_git=git,
        )
    except HCPError as exc:
        _fail(str(exc))
        return

    typer.secho(f"Created Codex at {codex.root}", fg=typer.colors.GREEN)
    typer.echo(f"  codex_id   {codex.manifest.codex_id}")
    typer.echo(f"  title      {codex.manifest.title}")
    typer.echo(f"  created    {len(created)} paths")
    typer.echo()
    typer.echo("Next steps:")
    typer.echo(f'  hcp add {path} --type value --title "What you value"')
    typer.echo(f"  hcp validate {path}")
    typer.echo(f'  hcp bundle {path} --scope assistant --purpose "Personal assistance"')
    typer.secho(
        "This Codex is yours. Nothing leaves this folder unless you create a bundle.",
        fg=typer.colors.CYAN,
    )


# ----------------------------------------------------------------------
# validate
# ----------------------------------------------------------------------


@app.command()
def validate(
    path: Annotated[Path, typer.Argument(help="Path to the Codex.")],
    strict: Annotated[bool, typer.Option("--strict", help="Treat warnings as errors.")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", help="Only print problems.")] = False,
    as_json: Annotated[
        bool, typer.Option("--format", help="Emit a JSON validation report.")
    ] = False,
) -> None:
    """Check a Codex for structural, temporal, and authority problems."""
    codex = _load_codex(path)
    report = validate_codex(codex)

    if as_json:
        _echo_json(
            {
                "codex_id": codex.manifest.codex_id,
                "path": str(codex.root),
                "valid": report.ok,
                "summary": report.summary(),
                "issues": [
                    {
                        "severity": issue.severity.value,
                        "code": issue.code,
                        "path": issue.path,
                        "field": issue.field,
                        "message": issue.message,
                    }
                    for issue in report.issues
                ],
            }
        )
        raise typer.Exit(EXIT_INVALID if report.errors else 0)

    _print_issues(report.issues, quiet=quiet)
    if not quiet:
        if report.ok:
            typer.secho(
                f"{codex.manifest.title}: valid ({len(codex.assertions)} assertions, "
                f"{report.summary()})",
                fg=typer.colors.GREEN,
            )
        else:
            typer.secho(
                f"{codex.manifest.title}: {report.summary()}", fg=typer.colors.RED, err=True
            )

    if report.errors or (strict and report.warnings):
        raise typer.Exit(EXIT_INVALID)


# ----------------------------------------------------------------------
# status
# ----------------------------------------------------------------------


@app.command()
def status(
    path: Annotated[
        Path | None, typer.Argument(help="Path to the Codex (defaults to HCP_CODEX).")
    ] = None,
    as_json: Annotated[bool, typer.Option("--format", help="Emit status as JSON.")] = False,
    no_git: Annotated[bool, typer.Option("--no-git", help="Skip Git information.")] = False,
) -> None:
    """Show a Codex overview: counts, validation, pending reviews, and Git state."""
    root = path or Config.default_codex
    codex = _load_codex(root)
    report = validate_codex(codex)
    counts = codex.counts()
    pending = codex.pending_observations()

    git_info: dict[str, Any] = {"enabled": False}
    if not no_git:
        git_state = git_status(codex.root)
        git_info = {
            "enabled": True,
            "is_repository": git_state.is_repository,
            "branch": git_state.branch,
            "clean": git_state.clean,
            "changes": [{"status": e.status, "path": e.path} for e in git_state.entries],
            "error": git_state.error,
        }

    if as_json:
        _echo_json(
            {
                "codex_id": codex.manifest.codex_id,
                "title": codex.manifest.title,
                "path": str(codex.root),
                "assertions": len(codex.assertions),
                "counts": counts,
                "valid": report.ok,
                "issues": report.summary(),
                "pending_observations": [a.id for a in pending],
                "git": git_info,
            }
        )
        return

    typer.secho(f"{codex.manifest.title}", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"  path        {codex.root}")
    typer.echo(f"  codex_id    {codex.manifest.codex_id}")
    typer.echo(f"  assertions  {len(codex.assertions)}")
    for label in ("type", "status", "source", "authority", "visibility"):
        summary = ", ".join(f"{k}={v}" for k, v in sorted(counts[label].items()))
        typer.echo(f"  {label:<11} {summary or '-'}")

    if report.ok:
        typer.secho(f"  validation  {report.summary()}", fg=typer.colors.GREEN)
    else:
        typer.secho(f"  validation  {report.summary()}", fg=typer.colors.RED)

    if pending:
        typer.secho(
            f"  review      {len(pending)} observation(s) awaiting your decision",
            fg=typer.colors.YELLOW,
        )
        for observation in pending[:5]:
            typer.echo(f"              {observation.id}")

    if not no_git:
        if not git_info["is_repository"]:
            typer.echo(f"  git         {git_info['error'] or 'not a repository'}")
        else:
            changes = git_info["changes"]
            marker = "clean" if not changes else f"{len(changes)} change(s)"
            typer.echo(f"  git         {git_info['branch']} ({marker})")


# ----------------------------------------------------------------------
# add
# ----------------------------------------------------------------------


@app.command("add")
def add(
    path: Annotated[Path, typer.Argument(help="Path to the Codex.")],
    type: Annotated[TypeOption, typer.Option("--type", help="Assertion type.")],
    title: Annotated[
        str | None, typer.Option("--title", help="Short title, used to suggest an ID.")
    ] = None,
    id: Annotated[
        str | None, typer.Option("--id", help="Explicit assertion ID, e.g. value.honesty.")
    ] = None,
    body: Annotated[str | None, typer.Option("--body", help="Assertion text.")] = None,
    body_file: Annotated[
        Path | None, typer.Option("--body-file", help="Read the body from a file.")
    ] = None,
    visibility: Annotated[
        VisibilityOption | None, typer.Option("--visibility", help="Disclosure class.")
    ] = None,
    tags: Annotated[list[str] | None, typer.Option("--tag", help="Add a tag (repeatable).")] = None,
    confidence: Annotated[
        float | None, typer.Option("--confidence", min=0.0, max=1.0, help="Confidence 0..1.")
    ] = None,
    supersedes: Annotated[
        str | None, typer.Option("--supersedes", help="ID of the assertion this replaces.")
    ] = None,
    directory: Annotated[
        str | None, typer.Option("--directory", help="Target directory inside the Codex.")
    ] = None,
) -> None:
    """Create a new human-authored assertion."""
    codex = _load_codex(path)
    type_value = str(type)

    if body and body_file:
        _fail("use either --body or --body-file, not both")
    if body_file:
        try:
            body = body_file.read_text(encoding="utf-8")
        except OSError as exc:
            _fail(f"cannot read {body_file}: {exc}")
            return

    text = body if body is not None else (title or "")
    scaffolded = not text.strip()
    if scaffolded:
        # `hcp add --type value` with no text creates a stub to fill in later.
        # The validator emits an `empty_body` warning for these, so the gap is
        # visible without blocking the write.
        text = f"<!-- Write the {type_value} here. Replace this line. -->"

    existing = {a.id for a in codex.assertions}
    identifier = id or suggest_id(type_value, title, existing)
    if not is_valid_id(identifier):
        _fail(
            f"invalid assertion id {identifier!r}; expected a dotted id such as "
            f"{type_value}.{title and title.lower().replace(' ', '-') or 'example'}"
        )
        return
    if identifier in existing:
        _fail(f"assertion id {identifier!r} already exists")

    if supersedes and supersedes not in existing:
        _fail(f"--supersedes references unknown assertion {supersedes!r}")
        return

    today = utc_today()
    assertion = Assertion(
        hcp=HCP_VERSION,
        id=identifier,
        type=type_value,
        source="human",
        authority="authoritative",
        status="active",
        visibility=str(visibility) if visibility else codex.manifest.default_visibility,
        confidence=confidence,
        created=today,
        updated=today,
        valid_from=today,
        valid_until=None,
        tags=list(tags or []),
        derived_from=[],
        supersedes=supersedes,
        body=text.strip(),
    )

    target = directory or TYPE_DIRECTORIES.get(type_value, "life")
    relative = f"{target.rstrip('/')}/{_stem(identifier)}.md"
    try:
        written = codex.add(assertion, path=relative)
    except HCPError as exc:
        _fail(str(exc))
        return

    typer.secho(f"Created {assertion.id}", fg=typer.colors.GREEN)
    typer.echo(f"  path        {written}")
    typer.echo(f"  type        {assertion.type}")
    typer.echo(f"  visibility  {assertion.visibility}")
    if assertion.tags:
        typer.echo(f"  tags        {', '.join(assertion.tags)}")
    if supersedes:
        typer.echo(f"  supersedes  {supersedes}")
    if scaffolded:
        typer.secho(
            f"  note        this is a placeholder; edit {written} to write the {assertion.type}",
            fg=typer.colors.YELLOW,
        )


def _stem(assertion_id: str) -> str:
    """Return a filename stem derived from an assertion ID."""
    from .ids import slugify

    parts = assertion_id.split(".")
    return slugify(parts[-1] if len(parts) > 1 else parts[0])


# ----------------------------------------------------------------------
# show / edit
# ----------------------------------------------------------------------


@app.command()
def show(
    path: Annotated[Path, typer.Argument(help="Path to the Codex.")],
    assertion_id: Annotated[str, typer.Argument(help="Assertion ID to display.")],
    as_json: Annotated[bool, typer.Option("--format", help="Emit the assertion as JSON.")] = False,
) -> None:
    """Show a single assertion with its metadata, body, and provenance."""
    codex = _load_codex(path)
    assertion = codex.require(assertion_id)

    if as_json:
        _echo_json(assertion.to_json_dict())
        return

    typer.secho(f"{assertion.id}", fg=typer.colors.CYAN, bold=True)
    rows = [
        ("type", assertion.type),
        ("source", assertion.source),
        ("authority", assertion.authority),
        ("status", assertion.status),
        ("visibility", assertion.visibility),
        ("confidence", assertion.confidence),
        ("created", assertion.created.isoformat() if assertion.created else None),
        ("updated", assertion.updated.isoformat() if assertion.updated else None),
        ("valid_from", assertion.valid_from.isoformat() if assertion.valid_from else None),
        ("valid_until", assertion.valid_until.isoformat() if assertion.valid_until else None),
        ("temporal", assertion.temporal_state(utc_today())),
        ("path", assertion.path),
        ("tags", ", ".join(assertion.tags) or None),
        ("supersedes", assertion.supersedes),
        ("derived_from", ", ".join(assertion.derived_from) or None),
    ]
    for label, value in rows:
        if value not in (None, ""):
            typer.echo(f"  {label:<12} {value}")

    if assertion.provenance is not None:
        provenance = assertion.provenance.model_dump(exclude_none=True)
        if provenance:
            typer.echo("  provenance")
            for key, value in sorted(provenance.items()):
                typer.echo(f"    {key:<18} {value}")

    if assertion.unknown_fields():
        typer.echo("  other metadata")
        for key, value in sorted(assertion.unknown_fields().items()):
            typer.echo(f"    {key:<18} {value}")

    typer.echo()
    typer.echo(assertion.body.strip() or "(no body)")


@app.command()
def edit(
    path: Annotated[Path, typer.Argument(help="Path to the Codex.")],
    assertion_id: Annotated[str, typer.Argument(help="Assertion ID to edit.")],
    body: Annotated[str | None, typer.Option("--body", help="Replace the body text.")] = None,
    body_file: Annotated[
        Path | None, typer.Option("--body-file", help="Read the body from a file.")
    ] = None,
    visibility: Annotated[
        VisibilityOption | None, typer.Option("--visibility", help="Change visibility.")
    ] = None,
    add_tag: Annotated[
        list[str] | None, typer.Option("--add-tag", help="Add a tag (repeatable).")
    ] = None,
    confidence: Annotated[
        float | None, typer.Option("--confidence", min=0.0, max=1.0, help="Set confidence.")
    ] = None,
    supersedes: Annotated[
        str | None, typer.Option("--supersedes", help="Mark as superseding another assertion.")
    ] = None,
) -> None:
    """Edit metadata or body text of an existing assertion."""
    codex = _load_codex(path)
    assertion = codex.require(assertion_id)

    if body and body_file:
        _fail("use either --body or --body-file, not both")
    if body_file:
        try:
            body = body_file.read_text(encoding="utf-8")
        except OSError as exc:
            _fail(f"cannot read {body_file}: {exc}")
            return

    if all(v is None for v in (body, visibility, add_tag, confidence, supersedes)):
        _fail(
            "nothing to change; pass --body, --visibility, --add-tag, --confidence, or --supersedes"
        )
        return

    if visibility is not None:
        assertion.visibility = str(visibility)
    if body is not None:
        assertion.body = body.strip()
    if confidence is not None:
        assertion.confidence = confidence
    if supersedes is not None:
        if supersedes not in {a.id for a in codex.assertions}:
            _fail(f"--supersedes references unknown assertion {supersedes!r}")
            return
        assertion.supersedes = supersedes
    for tag in add_tag or []:
        if tag not in assertion.tags:
            assertion.tags.append(tag)

    assertion.updated = utc_today()
    try:
        written = codex.save(assertion)
    except HCPError as exc:
        _fail(str(exc))
        return

    typer.secho(f"Updated {assertion.id}", fg=typer.colors.GREEN)
    typer.echo(f"  path        {written}")
    typer.echo("  review with 'hcp validate' and 'git diff' before committing")


# ----------------------------------------------------------------------
# export
# ----------------------------------------------------------------------


@app.command()
def export(
    path: Annotated[Path, typer.Argument(help="Path to the Codex.")],
    fmt: Annotated[str, typer.Option("--format", help="Output format.")] = "json",
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write to a file instead of stdout.")
    ] = None,
    include_prose: Annotated[
        bool,
        typer.Option("--include-prose/--no-prose", help="Include constitution.md and soul.md."),
    ] = True,
    exclude_pending: Annotated[
        bool, typer.Option("--exclude-pending", help="Omit observations awaiting review.")
    ] = False,
    compact: Annotated[bool, typer.Option("--compact", help="Emit single-line JSON.")] = False,
) -> None:
    """Export the whole Codex as machine-readable JSON."""
    if fmt != "json":
        _fail(f"unsupported format {fmt!r}; only 'json' is implemented in v0.1")

    codex = _load_codex(path)
    payload = codex_to_dict(
        codex,
        include_prose=include_prose,
        include_pending=not exclude_pending,
    )
    text = dumps(payload, indent=None if compact else 2)

    if output:
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            _fail(f"cannot write {output}: {exc}")
            return
        typer.secho(f"Wrote {output}", fg=typer.colors.GREEN)
        typer.echo(f"  assertions  {payload['assertion_count']}")
        return

    typer.echo(text)


# ----------------------------------------------------------------------
# bundle
# ----------------------------------------------------------------------


@app.command()
def bundle(
    path: Annotated[Path, typer.Argument(help="Path to the Codex.")],
    scope: Annotated[
        list[ScopeOption],
        typer.Option("--scope", help="Scope to include; repeatable."),
    ],
    purpose: Annotated[str, typer.Option("--purpose", help="Why this context is being shared.")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write the bundle to a file.")
    ] = None,
    at: Annotated[
        str | None, typer.Option("--at", help="Evaluate validity at this ISO date (YYYY-MM-DD).")
    ] = None,
    expires_in: Annotated[
        int | None, typer.Option("--expires-in", help="Expire the bundle after N hours.")
    ] = None,
    include_restricted: Annotated[
        bool,
        typer.Option(
            "--include-restricted",
            help="Permit restricted visibility. Off by default, by design.",
        ),
    ] = False,
    allow_training: Annotated[
        bool,
        typer.Option(
            "--allow-training", help="Declare that training on this context is permitted."
        ),
    ] = False,
    show_excluded: Annotated[
        bool, typer.Option("--show-excluded", help="Explain what was withheld and why.")
    ] = False,
) -> None:
    """Create a selective Context Bundle for one purpose and one audience.

    The bundle contains only what the requested scopes authorise. Everything it
    contains is accompanied by your HCP-0002 trust declaration; the tool never
    claims a receiving system has accepted it.
    """
    codex = _load_codex(path)
    moment = _resolve_at(at)
    scopes_config = load_scopes(codex)

    scope_names = [str(name) for name in scope]
    unknown = [name for name in scope_names if name not in scopes_config.scopes]
    if unknown:
        _fail(
            f"unknown scope(s): {', '.join(unknown)}; defined: {', '.join(scopes_config.names())}"
        )
        return

    conditions = TrustConditions.strict()
    if allow_training:
        conditions.training = False

    try:
        generated = generate_bundle(
            codex,
            scope_names,
            purpose=purpose,
            config=scopes_config,
            at=moment,
            expires_in=timedelta(hours=expires_in) if expires_in else None,
            include_restricted=include_restricted,
            trust_conditions=conditions,
        )
    except HCPError as exc:
        _fail(str(exc))
        return

    text = dumps(generated.to_json_dict())

    if output:
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            _fail(f"cannot write {output}: {exc}")
            return
        typer.secho(f"Wrote {output}", fg=typer.colors.GREEN)
    else:
        typer.echo(text)
        return

    typer.echo(f"  bundle_id   {generated.bundle_id}")
    typer.echo(f"  purpose     {generated.purpose}")
    typer.echo(f"  scopes      {', '.join(generated.scopes)}")
    typer.echo(f"  assertions  {len(generated.assertions)}")
    typer.echo(f"  trust       {generated.trust.covenant} ({generated.trust.status})")
    typer.secho(
        "The trust declaration is yours. A receiver must confirm it separately.",
        fg=typer.colors.CYAN,
    )

    if show_excluded:
        resolved = [scopes_config.get(name) for name in scope_names]
        selected_ids = {a["id"] for a in generated.assertions}
        selected = [a for a in codex.assertions if a.id in selected_ids]
        reasons = excluded_reason(codex, resolved, selected, at=moment)
        if reasons:
            typer.echo()
            typer.echo("Withheld:")
            for identifier, why in sorted(reasons.items()):
                typer.echo(f"  {identifier}: {', '.join(why)}")


# ----------------------------------------------------------------------
# observe / review
# ----------------------------------------------------------------------


@app.command()
def observe(
    path: Annotated[Path, typer.Argument(help="Path to the Codex.")],
    observation: Annotated[
        Path, typer.Argument(help="YAML or Markdown observation file from an AI system.")
    ],
    id: Annotated[str | None, typer.Option("--id", help="Override the observation ID.")] = None,
    visibility: Annotated[
        VisibilityOption | None,
        typer.Option(
            "--visibility",
            help="Visibility for the stored observation.",
        ),
    ] = None,
    source: Annotated[
        str | None, typer.Option("--source", help="Provenance label, e.g. 'claude:opus'.")
    ] = None,
) -> None:
    """Ingest an AI observation as pending material awaiting your review.

    The observation is always stored as ``source: ai``, ``authority: proposed``,
    ``status: pending``, whatever the source file claims. Nothing an AI produces
    becomes authoritative just by being ingested.
    """
    codex = _load_codex(path)
    try:
        result = ingest_observation(
            codex,
            observation,
            observation_id=id,
            visibility=str(visibility) if visibility else None,
            source_label=source,
        )
    except HCPError as exc:
        _fail(str(exc))
        return

    typer.secho(f"Ingested {result.observation_id}", fg=typer.colors.GREEN)
    typer.echo(f"  path        {result.path}")
    typer.echo("  authority   proposed (pending your review)")
    typer.echo()
    typer.echo("Review it when you agree:")
    typer.echo(f"  hcp review {path} {result.observation_id} --accept")
    typer.echo(f'  hcp review {path} {result.observation_id} --edit --body "corrected text"')
    typer.echo(f"  hcp review {path} {result.observation_id} --reject")


@app.command()
def review(
    path: Annotated[Path, typer.Argument(help="Path to the Codex.")],
    observation_id: Annotated[
        str | None, typer.Argument(help="Observation ID to review (omit when using --list).")
    ] = None,
    accept: Annotated[bool, typer.Option("--accept", help="Accept as authoritative.")] = False,
    edit: Annotated[bool, typer.Option("--edit", help="Accept with human-corrected text.")] = False,
    reject: Annotated[bool, typer.Option("--reject", help="Reject the observation.")] = False,
    archive: Annotated[bool, typer.Option("--archive", help="Archive without deciding.")] = False,
    body: Annotated[str | None, typer.Option("--body", help="Corrected text for --edit.")] = None,
    body_file: Annotated[
        Path | None, typer.Option("--body-file", help="Read corrected text from a file.")
    ] = None,
    new_id: Annotated[
        str | None, typer.Option("--as", help="ID for the assertion created by accept/edit.")
    ] = None,
    new_type: Annotated[
        TypeOption | None,
        typer.Option("--type", help="Type for the created assertion."),
    ] = None,
    note: Annotated[str | None, typer.Option("--note", help="Why you decided this way.")] = None,
    list_pending: Annotated[
        bool, typer.Option("--list", help="List observations instead of reviewing one.")
    ] = False,
    state: Annotated[
        str | None, typer.Option("--state", help="Filter --list by review state.")
    ] = None,
    as_json: Annotated[bool, typer.Option("--format", help="Emit JSON.")] = False,
) -> None:
    """Review AI observations: accept, edit, reject, or archive.

    This is the authority transition. Nothing else in the system can make an AI
    observation authoritative.
    """
    codex = _load_codex(path)

    if list_pending:
        observations = list_observations(codex, state=state)
        if as_json:
            _echo_json(
                [
                    {
                        "id": o.id,
                        "status": o.status,
                        "authority": o.authority,
                        "confidence": o.confidence,
                        "path": o.path,
                        "body": o.body.strip(),
                    }
                    for o in observations
                ]
            )
            return
        if not observations:
            typer.echo("No observations match.")
            return
        for observation in observations:
            marker = {"pending": "*", "rejected": "-", "archived": "~"}.get(observation.status, " ")
            confidence = (
                f" confidence={observation.confidence:.2f}"
                if observation.confidence is not None
                else ""
            )
            typer.echo(f"{marker} {observation.id}  [{observation.status}]{confidence}")
            typer.echo(
                f"    {observation.body.strip().splitlines()[0] if observation.body.strip() else '(empty)'}"
            )
        return

    if not observation_id:
        _fail("provide an observation ID to review, or use --list to see pending observations")
        return

    decisions = [accept, edit, reject, archive]
    if sum(1 for flag in decisions if flag) != 1:
        _fail("choose exactly one of --accept, --edit, --reject, or --archive")
        return
    if body and body_file:
        _fail("use either --body or --body-file, not both")
    if body_file:
        try:
            body = body_file.read_text(encoding="utf-8")
        except OSError as exc:
            _fail(f"cannot read {body_file}: {exc}")
            return

    decision = "accept" if accept else "edit" if edit else "reject" if reject else "archive"
    if edit and body is None:
        _fail("--edit requires the corrected text via --body or --body-file")
        return

    try:
        result = review_observation(
            codex,
            observation_id,
            decision,
            body=body,
            new_id=new_id,
            new_type=str(new_type) if new_type else None,
            note=note,
        )
    except HCPError as exc:
        _fail(str(exc))
        return

    colours = {"accept": typer.colors.GREEN, "edit": typer.colors.GREEN}
    typer.secho(
        f"{decision}: {result.observation_id}", fg=colours.get(decision, typer.colors.YELLOW)
    )
    if result.promoted_id:
        typer.echo(f"  created     {result.promoted_id}")
        typer.echo("  provenance  linked to the original observation, which is retained")
    if note:
        typer.echo(f"  note        {note}")


# ----------------------------------------------------------------------
# list / scopes
# ----------------------------------------------------------------------


@app.command("list")
def list_assertions(
    path: Annotated[Path, typer.Argument(help="Path to the Codex.")],
    type: Annotated[TypeOption | None, typer.Option("--type", help="Filter by type.")] = None,
    visibility: Annotated[
        VisibilityOption | None, typer.Option("--visibility", help="Filter by visibility.")
    ] = None,
    area: Annotated[
        str | None, typer.Option("--area", help="Filter by directory, e.g. identity.")
    ] = None,
    at: Annotated[
        str | None, typer.Option("--at", help="Only assertions valid at this date.")
    ] = None,
    all_states: Annotated[
        bool, typer.Option("--all", help="Include rejected, archived, and pending assertions.")
    ] = False,
    as_json: Annotated[bool, typer.Option("--format", help="Emit JSON.")] = False,
) -> None:
    """List assertions in a Codex."""
    codex = _load_codex(path)
    moment = _resolve_at(at)

    selected = []
    for assertion in codex.assertions:
        if type and assertion.type != str(type):
            continue
        if visibility and assertion.visibility != str(visibility):
            continue
        if area and not (assertion.path or "").startswith(f"{area.rstrip('/')}/"):
            continue
        if at and not assertion.is_valid_at(moment):
            continue
        if not all_states and not (
            assertion.status == "active" and assertion.authority == "authoritative"
        ):
            continue
        selected.append(assertion)

    selected.sort(key=lambda a: a.id)

    if as_json:
        _echo_json([a.to_json_dict() for a in selected])
        return

    if not selected:
        typer.echo("No assertions match.")
        return

    width = max(len(a.id) for a in selected)
    for assertion in selected:
        state = assertion.temporal_state(moment)
        flags = f"{assertion.visibility}/{state}"
        if assertion.status != "active" or assertion.authority != "authoritative":
            flags += f"/{assertion.status}"
        typer.echo(f"{assertion.id:<{width}}  {flags:<28} {assertion.type}")
        summary = assertion.body.strip().splitlines()
        if summary:
            text = summary[0]
            typer.echo(f"{'':<{width}}  {text[:70]}")
    typer.echo()
    typer.echo(f"{len(selected)} assertion(s)")


@app.command()
def scopes(
    path: Annotated[Path, typer.Argument(help="Path to the Codex.")],
    as_json: Annotated[bool, typer.Option("--format", help="Emit JSON.")] = False,
) -> None:
    """Show the disclosure scopes configured for a Codex."""
    codex = _load_codex(path)
    config = load_scopes(codex)

    if as_json:
        _echo_json(
            {
                "source": str(config.source) if config.source else "defaults",
                "scopes": [
                    {
                        "name": scope.name,
                        "description": scope.description,
                        "include": list(scope.include),
                        "exclude": list(scope.exclude),
                        "visibility_ceiling": scope.visibility_ceiling,
                    }
                    for scope in sorted(config.scopes.values(), key=lambda s: s.name)
                ],
            }
        )
        return

    origin = str(config.source) if config.source else "built-in defaults"
    typer.echo(f"Scopes ({origin}):")
    for scope in sorted(config.scopes.values(), key=lambda s: s.name):
        typer.echo()
        typer.secho(f"  {scope.name}", fg=typer.colors.CYAN)
        if scope.description:
            typer.echo(f"    {scope.description}")
        typer.echo(f"    include            {', '.join(scope.include) or '-'}")
        if scope.exclude:
            typer.echo(f"    exclude            {', '.join(scope.exclude)}")
        typer.echo(f"    visibility_ceiling {scope.visibility_ceiling}")
    typer.echo()
    typer.secho(
        "A bundle never includes the whole Codex: you choose the scope.",
        fg=typer.colors.CYAN,
    )


# ----------------------------------------------------------------------
# history / diff
# ----------------------------------------------------------------------


@app.command()
def history(
    path: Annotated[
        Path | None, typer.Argument(help="Path to the Codex (defaults to HCP_CODEX).")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Number of commits.")] = 20,
    file: Annotated[str | None, typer.Option("--file", help="Limit history to one path.")] = None,
    as_json: Annotated[bool, typer.Option("--format", help="Emit JSON.")] = False,
) -> None:
    """Show the Git history of a Codex (read-only).

    HCP uses Git for history and provenance, but never rewrites it and never
    commits on your behalf. Review a change, then commit it yourself.
    """
    root = path or Config.default_codex
    codex = _load_codex(root)

    try:
        commits = git_history(codex.root, limit=limit, path=file)
    except HCPError as exc:
        _fail(str(exc))
        return

    if as_json:
        _echo_json([commit.__dict__ for commit in commits])
        return

    if not commits:
        typer.secho("No commits yet.", fg=typer.colors.YELLOW)
        typer.echo(
            "Nothing has been committed. Review 'hcp diff', then use git yourself:\n"
            f"  git -C {codex.root} add -A && git -C {codex.root} commit -m 'Update Codex'"
        )
        return

    for commit in commits:
        typer.secho(f"{commit.short_hash}", fg=typer.colors.YELLOW, bold=True)
        typer.echo(f"  {commit.subject}")
        typer.echo(f"  {commit.author}  {commit.date}")


@app.command()
def diff(
    path: Annotated[
        Path | None, typer.Argument(help="Path to the Codex (defaults to HCP_CODEX).")
    ] = None,
    file: Annotated[str | None, typer.Option("--file", help="Limit the diff to one path.")] = None,
    staged: Annotated[bool, typer.Option("--staged", help="Show staged changes instead.")] = False,
) -> None:
    """Show uncommitted changes in a Codex (read-only)."""
    root = path or Config.default_codex
    codex = _load_codex(root)

    try:
        text = git_diff(codex.root, path=file, staged=staged)
    except HCPError as exc:
        _fail(str(exc))
        return

    if not text.strip():
        typer.secho("No uncommitted changes.", fg=typer.colors.GREEN)
        return
    typer.echo(text)


def run() -> None:
    """Entry point used by the ``hcp`` console script."""
    try:
        app()
    except HCPError as exc:  # pragma: no cover - defensive top-level guard
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise SystemExit(EXIT_ERROR) from exc
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        typer.secho("Interrupted.", fg=typer.colors.YELLOW, err=True)
        raise SystemExit(130) from None


if __name__ == "__main__":  # pragma: no cover
    run()


__all__ = ["app", "run"]
