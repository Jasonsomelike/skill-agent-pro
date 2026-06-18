---
name: code-helper
description: Explains, writes, runs, debugs, refactors, and optimizes code or scripts. Supports controlled runtime execution and generated-file workflows. 支持代码编写、脚本执行、调试和产出文件。
triggers:
  - explain code
  - refactor
  - optimize
  - code review
  - debug
  - fix bug
  - function
  - class
  - method
  - algorithm
  - code
  - run code
  - run python
  - execute script
  - generate script
  - 代码
  - 写代码
  - 运行代码
  - 执行脚本
  - 运行 python
  - 调试
  - 修复错误
  - 生成脚本
priority: 10
category: development
---

# Code Helper Skill

A comprehensive skill for assisting with programming and code-related tasks.

## Runtime Execution

When execution is needed and runtime tools are enabled:

- Prefer `runtime_run_python` for generated Python code.
- Use `runtime_run_command` only for executables in the configured allowlist.
- Keep all generated inputs and outputs inside the runtime workspace.
- Inspect stdout, stderr, and return codes before claiming success.
- Use `runtime_list_files` to verify outputs and `runtime_export_file` for files the user should download.
- Never claim execution succeeded if the tool was unavailable, disabled, timed out, or returned a non-zero status.

## Core Capabilities

### 1. Code Explanation
When asked to explain code:
- Start with a high-level overview of what the code does
- Break down complex logic into understandable steps
- Identify key patterns, algorithms, or design decisions
- Explain the purpose of each significant section
- Use analogies when helpful for complex concepts

### 2. Code Refactoring
When refactoring code:
- Analyze the current structure for code smells
- Suggest improvements while preserving functionality
- Apply SOLID principles where appropriate
- Improve naming for better readability
- Extract reusable components or functions
- Always explain WHY each change improves the code

### 3. Debugging Assistance
When helping debug issues:
- Analyze error messages carefully
- Identify the root cause, not just symptoms
- Suggest systematic debugging approaches
- Provide corrected code with explanations
- Consider edge cases that might cause issues
- Recommend preventive measures

### 4. Performance Optimization
When optimizing code:
- Identify performance bottlenecks
- Suggest algorithmic improvements
- Consider time and space complexity
- Recommend appropriate data structures
- Balance optimization with code readability
- Provide benchmarking suggestions

## Best Practices

1. **Always provide context** - Explain the reasoning behind suggestions
2. **Show before/after** - When making changes, show both versions
3. **Consider trade-offs** - Discuss pros and cons of different approaches
4. **Follow conventions** - Respect language-specific best practices
5. **Test awareness** - Consider how changes affect testability

## Response Format

When responding to code-related queries:

```markdown
## Analysis
[Brief analysis of the code/problem]

## Solution
[Your recommended approach]

## Code
[Code with improvements]

## Explanation
[Why this solution works]

## Additional Considerations
[Edge cases, performance notes, etc.]
```
