# Skill Agent Pro

## 概述

Skill Agent Pro 是一个智能代理策略插件，能够根据用户查询自动匹配和激活专业技能。灵感来源于 Claude Code Skills 和 OpenAI Agents Codex Tool 概念。

## ✨ 核心功能

| 功能 | 描述 |
|-----|------|
| 🎯 **多技能架构** | 同时加载和管理多个专业技能 |
| 🔍 **智能匹配** | 基于关键词自动激活相关技能 |
| 🛠️ **工具集成** | 与 Dify 内置工具生态系统无缝集成 |
| 🧪 **运行时工作区** | 在每次调用的独立临时工作区中受控执行脚本 |
| 📎 **文件交付** | 把生成的 DOCX、XLSX、PPTX、PDF 等真实文件作为附件返回 |
| 📝 **简易创建** | 支持 SKILL.md 文件和 YAML 配置两种方式 |
| 🔄 **流式响应** | 实时流式输出，支持调试日志 |

## 🧰 内置技能

### 1. 代码助手 (Code Helper)

协助编程和代码相关任务：

- 📖 **代码解释** - 将复杂逻辑分解为易懂的步骤
- 🔧 **重构** - 应用 SOLID 原则，改进代码结构
- 🐛 **调试** - 分析错误并提供修复方案
- ⚡ **优化** - 识别瓶颈，提升性能

**触发词：** `explain code`, `refactor`, `optimize`, `code review`, `debug`, `fix bug`, `code`

---

### 2. 文档助手 (Documentation Helper)

为代码和项目创建全面的文档：

- 📄 **README 生成** - 完整的项目文档
- 🌐 **API 文档** - 端点、参数、示例
- 💬 **代码注释** - 多种格式的文档字符串
- ✍️ **技术写作** - 清晰、结构化的内容

**触发词：** `document`, `readme`, `api docs`, `docstring`, `jsdoc`

---

### 3. 测试助手 (Testing Helper)

生成测试并提高代码覆盖率：

- 🧪 **单元测试** - AAA 模式、边界情况
- 🔗 **集成测试** - 组件交互测试
- 🎭 **模拟与存根** - 依赖隔离
- 📊 **覆盖率分析** - 识别未测试的路径

**触发词：** `test`, `unit test`, `integration test`, `mock`, `coverage`, `pytest`, `jest`

---

## ⚙️ 配置参数

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|-----|------|-----|-------|------|
| `model` | model-selector | ✅ | - | 使用的 LLM 模型 |
| `tools` | array[tools] | ❌ | - | 可用的外部工具 |
| `query` | string | ✅ | - | 用户查询 |
| `enabled_skills` | string | ❌ | "all" | 逗号分隔的技能名称或 "all" |
| `custom_skills` | string | ❌ | - | YAML 格式的自定义技能 |
| `external_skills_dir` | string | ❌ | `/opt/dify-agent-skills` | 服务端只读外部技能目录 |
| `semantic_skill_matching` | boolean | ❌ | true | 触发词未命中时结合最近会话上下文进行语义匹配 |
| `history_turns` | number | ✅ | 10 | 加入模型上下文的最近 Dify 原生会话轮数，0 表示关闭 |
| `allow_skill_commands` | boolean | ❌ | false | 允许已安装 Skill 包执行白名单命令 |
| `allowed_commands` | string | ❌ | python,python3,node,npm,npx,bun,sh,bash | 已安装 Skill 包命令白名单 |
| `allow_runtime_execution` | boolean | ❌ | false | 允许在每次运行的临时工作区中执行 Python 和白名单命令 |
| `runtime_allowed_commands` | string | ❌ | python,python3,node,npm,npx,bun,sh,bash | 运行时工作区命令白名单 |
| `runtime_command_timeout` | number | ✅ | 60 | 单次运行时命令最大执行秒数 |
| `runtime_max_file_mb` | number | ✅ | 20 | 单个工作区写入或导出文件的最大 MB |
| `auto_export_files` | boolean | ❌ | true | 自动把工作区中的常见交付文件作为附件返回 |
| `debug_mode` | boolean | ❌ | false | 启用调试日志 |
| `maximum_iterations` | number | ✅ | 10 | 最大工具调用迭代次数 |

## 🧪 运行时工作区与附件返回

每次 Agent 调用都会创建一个全新的临时工作区。模型可以在其中写入、读取和列出文件；开启 `allow_runtime_execution` 后，还可以执行 Python 或白名单命令。执行能力默认关闭，因为生成代码会继承插件进程的系统权限。

内置运行时工具包括：

- `runtime_write_file`、`runtime_read_file`、`runtime_list_files`
- `runtime_run_python`、`runtime_run_command`
- `runtime_export_file`

最终文件通过 Dify Blob 消息作为真实附件返回。开启 `auto_export_files` 时，DOCX、XLSX、PPTX、PDF、CSV、文本、压缩包和常见图片等交付文件也会自动导出。

## 📂 服务端外部技能目录

策略默认额外读取 `/opt/dify-agent-skills`。请把宿主机目录只读挂载到 Dify 的插件运行服务：

```yaml
volumes:
  - /opt/dify-agent-skills:/opt/dify-agent-skills:ro
```

技能目录结构必须为：

```text
/opt/dify-agent-skills/
└── my_skill/
    ├── SKILL.md
    └── config.yaml
```

插件仅允许读取 `/opt/dify-agent-skills`、`/app/external-skills` 及其子目录，不会自动创建目录。新增技能后只需重新运行 Agent，无需重新打包插件。

## 📦 自定义技能

在 Dify 界面中使用 YAML 格式定义自定义技能：

```yaml
- name: translation-helper
  description: 帮助在不同语言之间翻译文本
  triggers:
    - translate
    - 翻译
  priority: 5
  category: language
  instructions: |
    # 翻译助手
    
    翻译时：
    1. 识别源语言和目标语言
    2. 提供准确的翻译
    3. 解释细微差别或替代方案
```

## 🚀 快速开始

1. 在 Dify 工作区安装插件
2. 创建新的 Agent 应用
3. 选择 **"Skill-based Agent"** 作为代理策略
4. 配置模型和工具
5. 开始对话 - 技能会自动激活！

## 📚 更多文档

- [Skill 设计规范](../SKILL_DESIGN_SPEC.md) - 字段、命中机制、正文写法、测试与发布检查表
- [开发指南](./DEVELOPMENT.md) - 安装、调试、项目结构
- [隐私政策](./PRIVACY.md) - 数据处理说明
