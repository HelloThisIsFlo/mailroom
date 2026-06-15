"""FastMCP server for Mailroom: interactive email access for Claude."""

from contextlib import asynccontextmanager

from fastmcp import FastMCP

from mailroom.clients.jmap import JMAPClient
from mailroom.core.config import MailroomSettings
from mailroom.core.logging import configure_logging


@asynccontextmanager
async def app_lifespan(server):
    """Initialize shared resources: config, logging, and a warm JMAPClient."""
    settings = MailroomSettings()
    configure_logging(settings.logging.level)
    jmap = JMAPClient(token=settings.jmap_token)
    jmap.connect()
    yield {"jmap": jmap, "settings": settings}


mcp = FastMCP("Mailroom", lifespan=app_lifespan)

from mailroom.mcp.tools import register_tools

register_tools(mcp)


def main():
    """Entry point for mailroom-mcp script."""
    mcp.run()
