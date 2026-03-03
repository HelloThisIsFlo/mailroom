"""Sieve rule guidance for Mailroom setup.

Generates human-readable instructions for creating email routing rules.
No sieve introspection -- just prints what rules are needed for all
configured categories. A future milestone will add JMAP Contacts
migration and programmatic sieve rule creation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mailroom.setup.colors import BOLD, CYAN, DIM, GREEN, MAGENTA, color

if TYPE_CHECKING:
    from mailroom.core.config import MailroomSettings, ResolvedCategory


def generate_sieve_guidance(settings: MailroomSettings) -> str:
    """Generate sieve rule guidance for all configured categories.

    Iterates over settings.resolved_categories, groups children under
    their parent for readability, and produces copy-paste sieve-style
    snippets for Fastmail rule creation.

    Args:
        settings: Mailroom config with resolved_categories and screener_mailbox.

    Returns:
        Full multiline guidance string.
    """
    all_cats = settings.resolved_categories
    roots = [c for c in all_cats if c.parent is None]
    children_of: dict[str, list[ResolvedCategory]] = {}
    for c in all_cats:
        if c.parent:
            children_of.setdefault(c.parent, []).append(c)

    return _build_sieve_snippets(roots, children_of, settings.triage.screener_mailbox)


def _format_category_rule(cat: ResolvedCategory, is_child: bool) -> list[str]:
    """Build sieve-snippet lines for a single category rule."""
    lines: list[str] = []
    name_display = color(cat.name, BOLD)

    if is_child:
        annotation = f"  (child of {cat.parent})"
    elif cat.add_to_inbox:
        annotation = f"  {color('(+Inbox)', GREEN)}"
    else:
        annotation = ""

    if cat.add_to_inbox and is_child:
        annotation += f"  {color('(+Inbox)', GREEN)}"

    lines.append(f"    {name_display}{annotation}")
    lines.append(f'      Condition: Sender is in contact group "{cat.contact_group}"')
    lines.append("      Actions:")

    mailbox_display = color(cat.destination_mailbox, CYAN)
    lines.append(f"        1. Add label: {mailbox_display}")

    if cat.add_to_inbox:
        lines.append(f"        2. {color('Continue to apply other rules', MAGENTA)}")
        lines.append(f"        {color('# No archive -- emails stay in Inbox via add_to_inbox', DIM)}")
    else:
        lines.append(f"        2. {color('Archive', MAGENTA)} (remove from Inbox)")
        lines.append(f"        3. {color('Continue to apply other rules', MAGENTA)}")

    return lines


def _build_sieve_snippets(
    roots: list[ResolvedCategory],
    children_of: dict[str, list[ResolvedCategory]],
    screener_mailbox: str,
) -> str:
    """Build default sieve-style snippet guidance."""
    lines: list[str] = []

    lines.append("Sieve Rules")
    lines.append("")
    lines.append("  Routing rules route incoming mail from categorized contacts to the")
    lines.append("  correct mailbox. Create these rules in Fastmail:")
    lines.append("    Settings > Filters & Rules > Add Rule")
    lines.append("")
    lines.append("  Note: Fastmail sieve cannot filter by contact group directly.")
    lines.append("  These rules must be created through the Fastmail UI, which uses")
    lines.append("  the jmapquery extension internally.")
    lines.append("")
    lines.append(
        f"  {color('IMPORTANT', BOLD)}: Every rule below MUST have "
        f'"{color("Continue to apply other rules", MAGENTA)}" enabled.'
    )
    lines.append("  Without this, additive labels from parent/child category rules will not fire.")
    lines.append('  In the Fastmail UI, this is the "then also apply other rules" checkbox.')
    lines.append("")
    lines.append("  Per-category rules:")

    for root in roots:
        lines.append("")
        lines.extend(_format_category_rule(root, is_child=False))

        # Emit children under this root
        for child in children_of.get(root.name, []):
            lines.append("")
            lines.extend(_format_category_rule(child, is_child=True))

    lines.append("")
    lines.append("  Screener catch-all rule:")
    lines.append("")
    lines.append(f"    {screener_mailbox}")
    lines.append("      Condition: All other incoming mail (no specific sender match)")
    lines.append(f'      Action: Move to folder "{screener_mailbox}"')
    lines.append("")
    lines.append("      # This rule should be ordered LAST, after all category rules.")
    lines.append("      # It catches any mail not matched by the per-category rules above.")

    return "\n".join(lines)
