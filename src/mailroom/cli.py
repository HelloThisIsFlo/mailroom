"""Click CLI entry point for Mailroom.

Provides `setup` and `run` subcommands. When invoked without a subcommand
(e.g. `python -m mailroom`), defaults to `run` for backward compatibility.
"""

import sys

import click


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Mailroom: Email triage automation for Fastmail."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(run)


@cli.command()
def run() -> None:
    """Run the Mailroom polling service."""
    from mailroom.__main__ import main

    main()


@cli.command()
@click.option("--apply", is_flag=True, default=False, help="Apply changes (default is dry-run)")
@click.option(
    "--ui-guide", is_flag=True, default=False, help="Show Fastmail UI instructions instead of sieve snippets"
)
def setup(apply: bool, ui_guide: bool) -> None:
    """Provision Fastmail resources for configured triage categories."""
    # Stub: Plan 02 will implement run_setup
    click.echo("Setup command not yet implemented.")
    sys.exit(0)
