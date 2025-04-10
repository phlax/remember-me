# Remember Me

A persistence framework for maintaining conversational context and rules in MCP-based language model applications.

## Overview

Remember Me is an MCP server designed to persist chat artifacts and rules. It provides a robust framework for storing, retrieving, and managing different types of persistent resources:

- **Rules**: Define behavior constraints and guidelines for interaction
- **Snippets**: Store reusable pieces of code or text
- **Summaries**: Preserve important contextual information from conversations

The system uses SQLite for persistence and provides a comprehensive API for managing these resources across different contexts.

## Architecture

### Core Components

- **MyContext**: Central manager for all persistence operations
- **PersistentResource**: Base class for all storable resources
  - **Rule**: Commands that define acceptable interaction parameters
  - **Snippet**: Code or text fragments that can be referenced
  - **Summary**: Contextual information about conversations
- **Backup**: System for creating and restoring context states

### Data Model

Resources are stored with the following attributes:
- **Context**: Namespace for the resource (e.g., "me" for global resources)
- **Key**: Unique identifier within a context
- **Content**: The actual data being stored
- **Type/MIME Type**: Format information for appropriate handling

### Rules System

Rules use a structured policy framework:
- **MUST**: Absolute requirements
- **MUST NOT**: Absolute prohibitions
- **SHOULD**: Recommended practices
- **SHOULD NOT**: Discouraged practices
- **MAY**: Optional considerations

## API

### Context Management

- `my_context()`: Load the current context with optional additional contexts
- `my_context_backup_create()`: Create a backup of the current state
- `my_context_backup_restore()`: Restore from a previous backup
- `my_context_backup_list()`: View available backups
- `my_context_backup_remove()`: Delete a specific backup
- `my_context_backup_clear()`: Remove all backups

### Rule Management

- `my_context_rule_list()`: List all rules for a context
- `my_context_rule_set()`: Create or update a rule
- `my_context_rule_remove()`: Delete a rule

### Snippet Management

- `my_context_snippet_list()`: List snippets for a context
- `my_context_snippet_get()`: Retrieve a specific snippet
- `my_context_snippet_set()`: Create or update a snippet
- `my_context_snippet_remove()`: Delete a snippet

### Summary Management

- `my_context_summary_list()`: List summaries for a context
- `my_context_summary_get()`: Retrieve a specific summary
- `my_context_summary_set()`: Create or update a summary
- `my_context_summary_remove()`: Delete a summary

## Using with LLMs

### The "me" Context

The "me" context is a special default context that is always available. It contains global rules, snippets, and summaries that should be applied to every conversation. When loading the context, the "me" context is always included.

### Loading Context

An LLM should load context at the start of a conversation. This retrieves all rules, snippets, and summaries from the "me" context. The LLM should then follow any rules that are returned.

### Extra Contexts

You can load additional contexts beyond "me" by specifying them in the `extra_context` parameter. This allows for organizing different sets of rules, snippets, and summaries for different types of conversations or tasks.

For example, you might have:
- A "coding" context with programming-related snippets
- A "creative" context with writing prompts
- A "technical" context with specialized knowledge

These can be loaded alongside the default "me" context as needed.

### Example LLM Workflow

1. **Start conversation**: Load the context
2. **Access resources**: Retrieve snippets, summaries as needed
3. **Follow rules**: Comply with the rules returned from the context
4. **Add/Update resources**: Store new snippets or summaries based on conversation
5. **Create backups**: Save important states before major changes

## Running the Server

### With MCP Inspector

1. Install the package:
   ```
   pip install -e .
   ```

2. Run the MCP server:
   ```
   python -m mcp.server.run remember_me_mcp_server.server
   ```

3. Connect to the server using MCP Inspector to test and interact with the API endpoints

### With LLMs

1. Ensure the server is running as described above

2. Configure your LLM platform to connect to the MCP server and expose the necessary tools

3. In conversations, the LLM should first load the context and then follow any rules returned
