"""Click CLI entry point for Mailroom.

Provides `setup`, `reset`, and `run` subcommands. When invoked without a
subcommand (e.g. `python -m mailroom`), defaults to `run` for backward
compatibility.
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
def setup(apply: bool) -> None:
    """Provision Fastmail resources for configured triage categories."""
    from mailroom.setup.provisioner import run_setup

    exit_code = run_setup(apply=apply)
    sys.exit(exit_code)


@cli.command()
@click.option("--apply", is_flag=True, default=False, help="Apply changes (default is dry-run)")
def reset(apply: bool) -> None:
    """Reset all Mailroom changes: clean contacts, un-label emails, empty groups."""
    from mailroom.reset.resetter import run_reset

    exit_code = run_reset(apply=apply)
    sys.exit(exit_code)
