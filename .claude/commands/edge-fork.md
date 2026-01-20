# /edge-fork - Smart Forking (v1.1)

Semantic search across past Claude sessions and fork from relevant historical context.

## What This Command Does

1. **Indexes sessions** - Scans your Claude session history and creates embeddings
2. **Searches semantically** - Finds sessions similar to your query using vector similarity
3. **Enables forking** - Provides the command to fork from a discovered session
4. **Auto-suggests** - Shows related sessions at session start based on objective
5. **Cross-project** - Search across all your projects (optional)

## Prerequisites

- **LM Studio** running locally with an embedding model
- Default URL: `http://192.168.254.68:1234`
- Recommended model: `nomic-embed-text-v1.5`

## Usage

```bash
/edge-fork                           # Show help and status
/edge-fork "query"                   # Search for similar sessions
/edge-fork --index                   # Build/rebuild embedding index
/edge-fork --status                  # Show connection info
/edge-fork <session-id>              # Show fork command for session
```

## Cross-Project Search (v1.1)

```bash
/edge-fork --all-projects --index    # Index all projects
/edge-fork --all-projects "query"    # Search across all projects
/edge-fork --all-projects --status   # Show all projects
```

## Examples

```bash
# Find sessions about authentication
/edge-fork "authentication hooks implementation"

# Find sessions about refactoring
/edge-fork "refactoring database queries performance"

# Search all projects for performance work
/edge-fork --all-projects "performance optimization"

# Build the index (first time or refresh)
/edge-fork --index

# Get fork command for a specific session
/edge-fork 5ce9f4a1
```

## Auto-Suggest

At session start, if you have an objective set, Smart Forking automatically suggests
related sessions. This appears as "RELATED SESSIONS" in the session start output.

## How It Works

1. **Session Discovery**: Finds sessions in `~/.claude/projects/<project>/`
2. **Summary Extraction**: Extracts first 5 user messages + detected objective
3. **Embedding Generation**: Uses LM Studio's embedding API
4. **Similarity Search**: Cosine similarity for vector matching
5. **Fork Command**: Outputs `claude --resume <id> --fork-session`

## Storage

```
.claude/
  embeddings/
    index.json      # Session metadata
    vectors.npy     # NumPy embedding array
    config.json     # LM Studio URL config
```

## Configuration

Set LM Studio URL via environment variable:
```bash
export LMSTUDIO_URL="http://192.168.254.68:1234"
```

Or it will use the default: `http://192.168.254.68:1234`

## Troubleshooting

**LM Studio not connecting:**
- Ensure LM Studio is running
- Check that an embedding model is loaded (nomic-embed-text-v1.5)
- Verify the URL with: `curl http://192.168.254.68:1234/v1/models`

**No sessions found:**
- Sessions are in `~/.claude/projects/<project-hash>/`
- The directory name is based on your project path

**Index is empty:**
- Run `/edge-fork --index` to build the index
- Ensure LM Studio is available during indexing
