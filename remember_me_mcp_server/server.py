import argparse
import asyncio
import base64
import collections
import hashlib
import json
import os
import pathlib
import re
import signal
import sys
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import Context, Image, FastMCP
from mcp.server.fastmcp.prompts import base

from remember_me_mcp_server.backup import Backup
from remember_me_mcp_server.context import MyContext
from remember_me_mcp_server.errors import BackupError, ResourceError

MY_CONTEXT_DB_PATH = "/tmp/me/my.db"
MY_CONTEXT_BACKUP_PATH = "~/.mcp/me/backups"

ResultDict = dict[str, str | bool | dict]


@dataclass
class AppContext:
    backup: Backup
    my: MyContext

# TODO: re/move this once resource contexts are fixed
my = MyContext(MY_CONTEXT_DB_PATH)


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage application lifecycle with type-safe context"""
    backup = Backup(MY_CONTEXT_DB_PATH, MY_CONTEXT_BACKUP_PATH)
    try:
        yield AppContext(backup=backup, my=my)
    finally:
        await my.close()

mcp = FastMCP("Me", lifespan=app_lifespan)


# RESOURCES

@mcp.resource("my://{context}/{resource}")
async def my_context_list_resource(context: str, resource: str) -> list[dict]:
    """My snippets"""
    action = None
    if ":" in resource:
        resource, action = resource.split(":")
    if resource not in dict(MyContext.resource_types):
        raise ResourceError(f"Unrecognized resource type: {resource}")
    return my[resource].list(context, include_content=action == "all")


@mcp.resource("my://{context}/{resource}/{key}")
async def my_context_get_resource(context: str, resource: str, key: str) -> dict[str, str]:
    """My snippets"""
    if resource not in dict(MyContext.resource_types):
        raise ResourceError(f"Unrecognized resource type: {resource}")
    content, mime_type = my[resource].get(context, key)
    return dict(content=content, mime_type=mime_type)


# TOOLS

@mcp.tool()
async def my_context(ctx: Context, extra_context: list[str] | None = None) -> ResultDict:
    """Context for working with me

    This MUST always be loaded when working with me.
    """
    rules = await ctx.read_resource(f"my://me/rule")
    for extra in (extra_context or []):
        rules += await ctx.read_resource(f"my://{extra}/rule")
    result = []
    for c in rules:
        for rule in json.loads(c.content):
            result.append(f"{rule['policy']}: {rule['rule']}")
    summary = await ctx.read_resource(f"my://me/summary:all")
    summary_result = []
    for c in summary:
        for _summary in json.loads(c.content):
            _summary["context"] = "me"
            summary_result.append(_summary)
    for extra in (extra_context or []):
        summary = await ctx.read_resource(f"my://{extra}/summary")
        for c in summary:
            for _summary in json.loads(c.content):
                _summary["context"] = extra
                summary_result.append(_summary)
    snippet = await ctx.read_resource(f"my://me/snippet")
    snippet_result = []
    for c in snippet:
        for _snippet in json.loads(c.content):
            _snippet["context"] = "me"
            snippet_result.append(_snippet)
    for extra in (extra_context or []):
        snippet = await ctx.read_resource(f"my://{extra}/snippet")
        for c in snippet:
            for _snippet in json.loads(c.content):
                _snippet["context"] = extra
                snippet_result.append(_snippet)
    return dict(
        success=True,
        data=dict(
            rules=result,
            snippet=snippet_result,
            summary=summary_result))


## SNIPPETS

@mcp.tool()
async def my_context_snippet_get(
        context: str,
        key: str,
        ctx: Context) -> dict[str, str | bool | Exception]:
    """Get snippet for a context when working with me

    Args:
        context: Context key the snippet is stored within
        key: Key to reference the snippet with
    """
    try:
        return dict(
            success=True,
            data=json.loads(
                (await ctx.read_resource(
                    f"my://{context}/snippet/{key}"))[0].content))
    except ValueError as e:
        return dict(success=False, error=str(e))


@mcp.tool()
async def my_context_snippet_list(
        context: str,
        ctx: Context,
        include_snippets: bool = False) -> dict[str, str | bool | Exception]:
    """List snippets for a context when working with me

    Args:
        context: Context key the snippet is stored within
        include_snippets: Include the full snippet content
    """
    suffix = ":all" if include_snippets else ""
    try:
        result_list = await ctx.read_resource(f"my://{context}/snippet{suffix}")
        return dict(success=True, data=json.loads(result_list[0].content))
    except ResourceError as e:
        return dict(success=False, error=str(e))


@mcp.tool()
async def my_context_snippet_remove(
        context: str,
        key: str,
        ctx: Context) -> str:
    """Remove a snippet from the context for working with me

    SHOULD ONLY EVER BE USED TO REMOVE **SNIPPETS**
    SHOULD NOT BE USED TO REMOVE ANY OTHER TYPES

    Args:
        context: Context key to store snippet within
        key: Key to reference the snippet with
    """
    try:
        return dict(
            success=True,
            data=ctx.request_context.lifespan_context.my["snippet"].remove(
                context, key))
    except ResourceError as e:
        return dict(success=False, error=str(e))


@mcp.tool()
async def my_context_snippet_set(
        context: str,
        key: str,
        snippet: str,
        mime_type: str,
        ctx: Context) -> str:
    """Set context snippet for working with me

    SHOULD ONLY EVER BE USED TO SAVE **SNIPPETS**
    SHOULD NOT BE USED TO SAVE ANY OTHER TYPES

    Store contextual snippets of code or text.

    Args:
        context: Context key to store snippet within
        mime_type: Mimetype of the snippet
        key: Key to reference the snippet with
        snippet: Content of the snippet **as string** - convert to string if required!
    """
    try:
        return dict(
            success=True,
            data=ctx.request_context.lifespan_context.my["snippet"].set(
                context, key, snippet, mime_type))
    except ResourceError as e:
        return dict(success=False, error=str(e))


## Summary

@mcp.tool()
async def my_context_summary_get(
        context: str,
        key: str,
        ctx: Context) -> ResultDict:
    """Get summary for a context when working with me

    Args:
        context: Context key the summary is stored within
        key: Key to reference the snippet with
    """
    try:
        return dict(
            success=True,
            data=json.loads(
                (await ctx.read_resource(
                    f"my://{context}/summary/{key}"))[0].content))
    except ValueError as e:
        return dict(success=False, error=str(e))


@mcp.tool()
async def my_context_summary_list(
        context: str,
        ctx: Context,
        include_summary: bool = False) -> ResultDict:
    """List summaries for a context when working with me

    Args:
        context: Context key the summary is stored within
        include_summary: Include the full summary content
    """
    suffix = ":all" if include_summary else ""
    try:
        result_list = await ctx.read_resource(f"my://{context}/summary{suffix}")
        return dict(success=True, data=json.loads(result_list[0].content))
    except ResourceError as e:
        return dict(success=False, error=str(e))


@mcp.tool()
async def my_context_summary_remove(
        context: str,
        key: str,
        ctx: Context) -> ResultDict:
    """Remove a summary from the context for working with me

    SHOULD ONLY EVER BE USED TO REMOVE **SUMMARIES**
    SHOULD NOT BE USED TO REMOVE ANY OTHER TYPES

    Args:
        context: Context key to store summary within
        key: Key to reference the summary with
    """
    try:
        return dict(
            success=True,
            data=ctx.request_context.lifespan_context.my["summary"].remove(
                context, key))
    except ResourceError as e:
        return dict(success=False, error=str(e))


@mcp.tool()
async def my_context_summary_set(
        context: str,
        key: str,
        summary: str,
        ctx: Context,
        mime_type: str = "text/markdown",
) -> ResultDict:
    """Set context summary for working with me

    SHOULD ONLY EVER BE USED TO SAVE **SUMMARIES**
    SHOULD NOT BE USED TO SAVE ANY OTHER TYPES

    Store contextual summaries of conversations or aspects thereof.

    Args:
        context: Context key to store summary within. Generally the format should be markdown.
        mime_type: Mimetype of the summary. Should be markdown or another text format as appropriate.
        key: Key to reference the summary with
        summary: Content of the summary
    """
    try:
        return dict(
            success=True,
            data=ctx.request_context.lifespan_context.my["summary"].set(
                context, key, summary, mime_type))
    except ResourceError as e:
        return dict(success=False, error=str(e))


## Rules

@mcp.tool()
async def my_context_rule_list(
        ctx: Context,
        context: str | None = "me") -> ResultDict:
    """List rules for when working with me

    Args:
        context: Context the rule is stored within
    """
    rules = (
        await ctx.read_resource(
            f"my://{context or 'me'}/rule"))[0].content
    return dict(
        success=True,
        data=[f"{item['policy']}: {item['rule']}" for item in json.loads(rules)])


@mcp.tool()
async def my_context_rule_remove(
        rule: str,
        ctx: Context,
        context: str | None = "me",
        policy: str | None = None) -> str:
    """Remove context rule for working with me
    
    Args:
        rule: Rule text to remove
        context: Context the rule is stored within (default: "me")
        policy: Optional policy to specify when multiple rules with same text exist
    """
    try:
        # Parse combined format if present
        if policy is None and ": " in rule:
            policy, rule = rule.split(": ", 1)
            
        return dict(
            success=True,
            data=ctx.request_context.lifespan_context.my["rule"].remove(
                context or "me", rule, policy))
    except ResourceError as e:
        return dict(success=False, error=str(e))


@mcp.tool()
async def my_context_rule_set(
        policy: str,
        rule: str,
        ctx: Context,
        context: str | None = "me") -> str:
    """Set context rule for working with me"""
    try:
        return dict(
            success=True,
            data=ctx.request_context.lifespan_context.my["rule"].set(context or "me", policy, rule))
    except ResourceError as e:
        return dict(success=False, error=str(e))


## Backups


@mcp.tool()
async def my_context_backup_create(ctx: Context, name: str | None = None) -> ResultDict:
    """Create a backup of the context for working with me

    Args:
        name: Name of the backup (defaults to timestamp). Only set this if specifically asked.
    """
    try:
        ctx.request_context.lifespan_context.backup.create(name)
        return dict(success=True, data=f"Backup created: {name}")
    except BackupError as e:
        return dict(success=False, error=str(e))


@mcp.tool()
async def my_context_backup_clear(ctx: Context) -> dict[str, str | bool | Exception]:
    """Clear ALL backups of the context for working with me

    NEVER DO THIS UNLESS DIRECTLY REQUESTED!!!
    """
    try:
        ctx.request_context.lifespan_context.backup.clear()
        return dict(success=True, data="All backups cleared")
    except BackupError as e:
        return dict(success=False, error=str(e))


@mcp.tool()
async def my_context_backup_list(ctx: Context) -> dict[str, str | bool | Exception]:
    """List backups of the context for working with me"""
    try:
        return dict(
            success=True,
            data="\n".join(ctx.request_context.lifespan_context.backup.list()))
    except BackupError as e:
        return dict(success=False, error=str(e))


@mcp.tool()
async def my_context_backup_remove(
        ctx: Context,
        name: str) -> dict[str, str | bool | Exception]:
    """Remove a backup of the context for working with me

    Args:
        name: Name of the backup to remove
    """
    try:
        ctx.request_context.lifespan_context.backup.remove(name)
        return dict(success=True, data=f"Backup removed: {name}")
    except BackupError as e:
        return dict(success=False, error=str(e))


@mcp.tool()
async def my_context_backup_restore(
        name: str,
        ctx: Context,
        backup_current: bool = True) -> dict[str, str | bool | Exception]:
    """Restore a backup of the context for working with me

    Args:
        name: Name of the backup to restore
        backup_current: Make a backup of the current context before restoring
    """
    try:
        messages = []
        if backup_current:
            backup_name = ctx.request_context.lifespan_context.backup.create()
            messages.append(f"Backup created: {backup_name}")
        ctx.request_context.lifespan_context.backup.restore(name)
        messages.append(f"Backup restored: {name}")
        return dict(success=True, data="\n".join(messages))
    except BackupError as e:
        return dict(success=False, error=str(e))


# PROMPTS

@mcp.prompt()
def my_prompt() -> str:
    """Create my prompt"""
    current_file = pathlib.Path(__file__)
    context_file_path = current_file.parent / "prompt.txt"
    return context_file_path.read_text()
