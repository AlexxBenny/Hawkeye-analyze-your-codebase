# 🦅 Using Hawkeye with Antigravity — Integration Guide

Antigravity is a Gemini-based AI coding agent that runs as a VS Code extension. Hawkeye exposes 12 architectural intelligence tools via MCP (Model Context Protocol). Once connected, Antigravity queries Hawkeye **before editing any Python file** to understand dependencies, blast radius, complexity, and cycle risks.

---

## Step 1: Install Hawkeye with MCP Support

```bash
pip install "hawkeye-analyzer[mcp]"
```

Verify:
```bash
hawkeye --version         # Should show 0.6.2+
hawkeye-mcp --help        # Should show MCP server options
where.exe hawkeye-mcp     # Windows: should show path to .exe
```

> [!IMPORTANT]
> Hawkeye must be installed in an environment that's on your system PATH, so the `hawkeye-mcp` command is accessible from any directory.

---

## Step 2: Configure MCP in Antigravity

Antigravity has its own MCP configuration file, separate from the Gemini CLI.

**Config file location:**
```
C:\Users\<username>\.gemini\antigravity\mcp_config.json
```

**How to find it:** Open Antigravity Settings → scroll to "INSTALLED MCP SERVERS" → click **"Open MCP Config"**

**Write this config:**

```json
{
  "mcpServers": {
    "hawkeye": {
      "command": "hawkeye-mcp",
      "args": []
    }
  }
}
```

> [!NOTE]
> **No `--project` needed.** The `args: []` means the server starts idle. Antigravity calls `hawkeye_analyze(project_path)` dynamically with whatever workspace is active. This works for **any** Python project without config changes.
>
> If you want to pin a specific project for faster startup, use `"args": ["--project", "D:/path/to/project"]` instead — but this locks the server to one project.

---

## Step 3: Activate

After editing the config, click **"Refresh"** in the MCP servers panel (next to "INSTALLED MCP SERVERS"). If Hawkeye doesn't appear, restart Antigravity.

Hawkeye will appear in the "INSTALLED MCP SERVERS" list with 12 tools available.

---

## Step 4: Verify the Connection

Ask Antigravity:

```
"What Hawkeye tools do you have?"
```

You should see all 12 `hawkeye_*` tools listed. You can also test with:

```
"Analyze this project with Hawkeye"
```

---

## Step 5: Add Hawkeye Rules to System Prompt (Optional but Recommended)

To make Antigravity **automatically** use Hawkeye before every edit, add this to the global `~/.gemini/GEMINI.md`:

```markdown
## Architectural Awareness (Hawkeye)

When working on a Python project, use the Hawkeye MCP tools for architectural intelligence.

### Before Editing Any Python File
1. Call hawkeye_analyze(project_path) once at the start of the session if not already analyzed
2. Call hawkeye_file_context(file_path) before editing any Python file to understand:
   - How many modules depend on this file (blast radius)
   - The file's health status and risk classification
   - Whether it's involved in import cycles
   - Its complexity metrics (CC, Cog)

### Editing Rules Based on Context
- If risk is "hub" or "fragile": make minimal, surgical changes only
- If health is "critical": do NOT add complexity — suggest refactoring instead
- If health is "elevated" and arch_role is "core": complexity is structural — normal edits are safe
- If insights include "extreme_cyclomatic": suggest decomposition before adding more logic
- If dependent_count is high (≥5): be extra careful with interface changes

### Before Refactoring
- Before renaming or changing a class/function interface: call hawkeye_impact(file, symbol)
- Before multi-file edits: call hawkeye_context(files)

### After Editing
- After adding new import statements: call hawkeye_cycles() to verify no circular dependencies
```

---

## How It Works Internally

### Data Flow

```
┌─────────────────────┐
│   Antigravity (You) │  ← VS Code extension
│  Calls MCP tools:   │
│  hawkeye_analyze()  │
│  hawkeye_file_ctx() │
└─────────┬───────────┘
          │ stdio (JSON-RPC)
          ▼
┌─────────────────────┐
│   hawkeye-mcp       │  ← Spawned as child process by Antigravity
│   (mcp.py)          │
│                     │
│   _engine (global)  │  ← Singleton HawkeyeEngine in RAM
└─────────┬───────────┘
          │ calls internally
          ▼
┌─────────────────────┐
│   HawkeyeEngine     │  ← 9-step analysis pipeline
│   (engine.py)       │
│   Reads .py files   │
│   Parses AST        │
│   Builds graph      │
│   Computes metrics  │
└─────────────────────┘
```

### Where Is Data Stored?

**All data lives in RAM only.** There is no database, no cache file, no `.hawkeye/` directory.

| Data | Storage | Lifetime |
|------|---------|----------|
| Dependency graph | RAM (`engine._graph`) | Dies when Antigravity closes |
| Module metrics | RAM (`engine._module_metrics`) | Dies when Antigravity closes |
| Cycle report | RAM (`engine._cycle_report`) | Dies when Antigravity closes |
| Symbol registry | RAM (`engine._symbol_registry`) | Dies when Antigravity closes |
| File hashes | RAM (`engine._file_hashes`) | Dies when Antigravity closes |
| Multi-project cache | RAM (`_analyzed_projects` dict) | Dies when Antigravity closes |

**Nothing persists between sessions.** Each restart re-analyzes from scratch (~5 seconds for 300 modules).

---

## Workflow — What Happens on Every Edit

```
You: "Fix the bug in engine.py"

Step 1: Is the project analyzed?
  NO  → hawkeye_analyze("D:/project")  → ~5 seconds, builds graph in RAM
  YES → skip (cached from earlier in this session)

Step 2: hawkeye_file_context("engine.py")  → <10ms RAM lookup
  Returns: dependencies, dependents, blast radius, CC, Cog,
           health, insights, risk profile, cycle status

Step 3: Antigravity reads the context
  "engine.py has 8 dependents, CC=45, risk=hub"
  → Makes surgical, minimal changes
  → Avoids breaking the 8 modules that import from it

Step 4 (if new imports added): hawkeye_cycles()
  Verify no circular dependencies introduced
```

### Before Refactoring a Symbol

```
User: "Rename BrainCore to CognitiveCore"

Antigravity calls:
  hawkeye_impact("brain/core.py", symbol="BrainCore")

Returns:
  direct_users: 3
  direct_modules: ["main", "merlin", "test_brain"]
  transitive_users: 5

Antigravity now knows exactly which 3 files need updating.
```

### Before Multi-File Edits

```
User: "Refactor merlin.py, main.py, and mission_orchestrator.py"

Antigravity calls:
  hawkeye_context(["merlin.py", "main.py", "mission_orchestrator.py"])

Returns:
  shared_dependencies: 26
  combined_blast_radius: 10

Antigravity: "These 3 files share 26 dependencies —
those are the fragile points I must not break."
```

---

## The 12 Available Tools

| Tool | What Antigravity Uses It For |
|------|------------------------------|
| `hawkeye_analyze(path)` | Initial project scan (called once per session) |
| **`hawkeye_file_context(file)`** | **Before editing ANY file** — the primary tool |
| `hawkeye_context(files)` | Before editing 2+ related files together |
| `hawkeye_impact(file, symbol)` | Before renaming/refactoring a class or function |
| `hawkeye_symbols(file)` | Understanding what a module exports |
| `hawkeye_find(pattern)` | Discovering module names by search |
| `hawkeye_cycles()` | After creating new imports — verify no cycles |
| `hawkeye_metrics(sort_by)` | Finding the riskiest modules in the project |
| `hawkeye_path(source, target)` | Understanding how two modules are connected |
| `hawkeye_hotspots(limit, days)` | Rank files by complexity × git churn — the real risk |
| `hawkeye_graph(max_depth)` | Structural overview — top hubs, edge count, density |

---

## Quick Setup Checklist

- [ ] `pip install "hawkeye-analyzer[mcp]"` — install Hawkeye
- [ ] Open Antigravity Settings → "Open MCP Config" → paste the config
- [ ] Click "Refresh" or restart Antigravity
- [ ] Verify: ask "What Hawkeye tools do you have?"
- [ ] (Optional) Add Hawkeye rules to `~/.gemini/GEMINI.md`
- [ ] Test: open a Python project and ask "What's the architectural context for [some_file].py?"

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `hawkeye-mcp` not found | Ensure Hawkeye is installed in a PATH-accessible environment. Run `where.exe hawkeye-mcp` to check |
| "No MCP Servers" in UI | Click "Open MCP Config", paste the config JSON, click "Refresh" |
| MCP tools not showing after config | Restart Antigravity (close and reopen VS Code) |
| Wrong project analyzed | Antigravity calls `hawkeye_analyze()` with the workspace path automatically |
| Slow first query (~5s) | Normal — this is the one-time analysis. All subsequent queries are <10ms |
| UTF-8 errors on Windows | Hawkeye auto-handles this via stdout reconfiguration |
