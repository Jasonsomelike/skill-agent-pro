# Skill Agent Pro

## Overview

Skill Agent Pro is an intelligent agent strategy plugin for the Dify platform that dynamically activates specialized skills based on user queries. Inspired by Claude Code Skills and OpenAI Agents Codex Tool concepts.

## ✨ Core Features

| Feature | Description |
|---------|-------------|
| 🎯 **Multi-Skill Architecture** | Load and manage multiple specialized skills |
| 🔍 **Smart Matching** | Automatically activate relevant skills based on keywords |
| 🛠️ **Tool Integration** | Seamlessly integrates with Dify's built-in tools |
| 🧪 **Runtime Workspace** | Execute controlled scripts in an isolated per-run workspace |
| 📎 **File Delivery** | Return generated DOCX, XLSX, PPTX, PDF, and other files as attachments |
| 📝 **Easy Creation** | Support SKILL.md files and YAML configuration |
| 🔄 **Streaming Responses** | Real-time streaming output with debug logging |

## 🧰 Built-in Skills

### 1. Code Helper

Assists with programming and code-related tasks:

- 📖 **Code Explanation** - Break down complex logic
- 🔧 **Refactoring** - Apply SOLID principles
- 🐛 **Debugging** - Analyze errors and provide fixes
- ⚡ **Optimization** - Identify bottlenecks

**Triggers:** `explain code`, `refactor`, `optimize`, `code review`, `debug`, `fix bug`, `code`

---

### 2. Documentation Helper

Creates comprehensive documentation:

- 📄 **README Generation** - Complete project docs
- 🌐 **API Documentation** - Endpoints, parameters, examples
- 💬 **Code Comments** - Multi-format docstrings
- ✍️ **Technical Writing** - Clear, structured content

**Triggers:** `document`, `readme`, `api docs`, `docstring`, `jsdoc`

---

### 3. Testing Helper

Generates tests and improves coverage:

- 🧪 **Unit Tests** - AAA pattern, edge cases
- 🔗 **Integration Tests** - Component interaction testing
- 🎭 **Mocking & Stubbing** - Dependency isolation
- 📊 **Coverage Analysis** - Identify untested paths

**Triggers:** `test`, `unit test`, `integration test`, `mock`, `coverage`, `pytest`, `jest`

---

## ⚙️ Configuration Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `model` | model-selector | ✅ | - | LLM model to use |
| `tools` | array[tools] | ❌ | - | External tools available |
| `query` | string | ✅ | - | User query to process |
| `enabled_skills` | string | ❌ | "all" | Comma-separated skill names |
| `custom_skills` | string | ❌ | - | YAML-formatted custom skills |
| `skill_packages` | files | ❌ | - | Zip package(s) containing `SKILL.md`; installed before the run |
| `external_skills_dir` | string | ❌ | `/opt/dify-agent-skills` | Read-only server directory containing skill folders |
| `debug_mode` | boolean | ❌ | false | Enable debug logging |
| `max_active_skills` | number | ✅ | 3 | Maximum matched skills to inject |
| `semantic_skill_matching` | boolean | ❌ | true | Use the selected model and recent conversation context as a semantic fallback when no trigger matches |
| `history_turns` | number | ✅ | 10 | Number of recent native Dify conversation turns included in context |
| `allow_skill_commands` | boolean | ❌ | false | Allow installed skills to execute whitelisted commands |
| `allowed_commands` | string | ❌ | python,python3,node,npm,npx,bun,sh,bash | Command allowlist for installed skill scripts |
| `allow_runtime_execution` | boolean | ❌ | false | Allow Python and allowlisted commands in a temporary per-run workspace |
| `runtime_allowed_commands` | string | ❌ | python,python3,node,npm,npx,bun,sh,bash | Command allowlist for the runtime workspace |
| `runtime_command_timeout` | number | ✅ | 60 | Maximum seconds for one runtime command |
| `runtime_max_file_mb` | number | ✅ | 20 | Maximum size of one workspace file written or exported |
| `auto_export_files` | boolean | ❌ | true | Automatically attach common deliverable files left in the workspace |
| `maximum_iterations` | number | ✅ | 10 | Max tool call iterations |

## Runtime Workspace and File Attachments

Each agent invocation receives a fresh temporary workspace. The model can write and inspect files, and—when `allow_runtime_execution` is enabled—run Python or allowlisted commands there. Runtime execution is disabled by default because generated code has the permissions of the plugin process.

The built-in runtime tools are:

- `runtime_write_file`, `runtime_read_file`, `runtime_list_files`
- `runtime_run_python`, `runtime_run_command`
- `runtime_export_file`

Generated deliverables are returned through Dify Blob messages. Common DOCX, XLSX, PPTX, PDF, CSV, text, archive, and image files are also auto-exported when `auto_export_files` is enabled.

## Installable Skill Packages

This fork adds persistent zip-based skill package management while preserving Dify tool calling.

Upload zip files directly in the strategy's `skill_packages` parameter; they are installed before that run. Dify only allows one plugin capability family per package, so this package is published as an Agent Strategy plugin rather than a mixed Agent Strategy + Tool plugin.

Each zip can contain one or more skill folders. A valid skill folder must include `SKILL.md`; optional `references/`, `scripts/`, or other files are preserved and can be inspected by the agent through internal `skill_*` tools.

Script execution is disabled by default. Enable `allow_skill_commands` and configure `allowed_commands` only for trusted skill packages.

## External Server Skills

The strategy also loads skills from `/opt/dify-agent-skills` by default. Mount the host directory into the Dify plugin daemon as read-only:

```yaml
volumes:
  - /opt/dify-agent-skills:/opt/dify-agent-skills:ro
```

Each skill must use this structure:

```text
/opt/dify-agent-skills/
└── my_skill/
    ├── SKILL.md
    └── config.yaml
```

Only `/opt/dify-agent-skills`, `/app/external-skills`, and their subdirectories are accepted. The plugin reads existing directories and never creates them.

## 📦 Custom Skills

Define custom skills using YAML format in Dify interface:

```yaml
- name: translation-helper
  description: Helps translate text between languages
  triggers:
    - translate
    - translation
  priority: 5
  category: language
  instructions: |
    # Translation Helper
    
    When translating:
    1. Identify source and target languages
    2. Provide accurate translations
    3. Explain nuances or alternatives
```

## 🚀 Getting Started

1. Install the plugin in your Dify workspace
2. Create a new Agent application
3. Select **"Skill-based Agent"** as the agent strategy
4. Configure model and tools
5. Start chatting - skills activate automatically!

## 📚 Documentation

- [Skill Design Specification](./SKILL_DESIGN_SPEC.md) - Schema, routing, writing, testing, and publishing rules
- [Development Guide](./DEVELOPMENT.md) - Installation, debugging, project structure
- [Privacy Policy](./PRIVACY.md) - Data handling explanation

---

# License

MIT License

# Contributing

Contributions are welcome! Please see [Development Guide](DEVELOPMENT.md) for details.
