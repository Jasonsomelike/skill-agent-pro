# Agent Skill Plugin Plus 技术状态文档

> 更新时间：2026-06-18
> 文档用途：记录当前插件的实现进度、服务器登录方式、部署位置、已完成能力与剩余待办。
> 注意：生产服务器凭据不存放在仓库中。部署时请通过密码管理器、SSH Agent 或环境变量提供。

## 1. 项目概况

- 本地工作目录：`E:\vibecoding\skill-create`
- 当前本地插件版本：`1.5.0`
- 当前插件名称：`agent-skill-plugin-plus`
- 插件类型：`agent strategy plugin`
- `manifest.yaml` 当前只声明了 `agent_strategies`，没有把 `tool`、`model`、`endpoint`、`datasource` 等能力混写进同一个包。

当前关键文件：

- `manifest.yaml`
- `provider/agent_skill.yaml`
- `strategies/skill_agent.yaml`
- `strategies/skill_agent.py`
- `skills/runtime_workspace.py`
- `SKILL_DESIGN_SPEC.md`

当前仓库是脏工作区，存在未提交改动与新增文件，这意味着本地状态是“持续开发中”的快照，不等于一个干净发布分支。

## 2. 当前已完成的点

### 2.1 插件打包与安装问题已修复

已解决此前上传失败问题：

```text
agent_strategy and tool, model, endpoint, trigger, or datasource cannot be provided at the same time
```

处理结果：

- 插件被固定为纯 `agent strategy` 类型；
- `manifest.yaml` 不再混入 `tool` 能力；
- 可以正常打包为 `.difypkg` 并在 Dify 中升级安装。

### 2.2 Pydantic 参数模型问题已修复

已处理此前运行时报错：

```text
SkillAgentParams is not fully defined
```

处理方式：

- 在 `strategies/skill_agent.py` 中对 `SkillAgentParams` 执行了 `model_rebuild(...)`；
- 显式补齐了 `AgentModelConfig`、`ToolEntity`、`List`、`Optional`、`Any` 等类型命名空间；
- Agent 节点运行时不再因为 Pydantic 模型未重建而失败。

### 2.3 已支持 Dify 工具调用

目标之一是让该 Agent Strategy 像 Dify 自带 Agent 策略一样可调用 Dify 工具，这一能力已经打通。

当前行为：

- Agent 节点的 `tools` 参数会进入策略；
- 插件会把 Dify 已选择工具转换为模型可调用的工具定义；
- 主循环里支持模型发起工具调用，并把结果继续喂回推理链路；
- 因此该策略已经不是“只读 skill 指令”，而是“Skill + Dify Tools”的混合执行模式。

### 2.4 已支持上传 Skill 包并在运行前安装

已支持通过 Agent 节点的 `skill_packages` 参数上传 zip 技能包。

当前能力：

- 每次运行前可安装 zip 包中的一个或多个 Skill；
- 安装来源使用 Dify 插件 storage；
- 安装后可被本次运行加载进 Skill Registry；
- 已提供一组内部 `skill_*` 工具用于访问已安装 Skill 包内容。

当前内置的内部工具包括：

- `skill_list_installed`
- `skill_get_metadata`
- `skill_list_files`
- `skill_read_file`
- `skill_run_command`

说明：

- `skill_run_command` 默认关闭；
- 只有开启 `allow_skill_commands` 后，才允许在“已安装 skill 包目录”中执行白名单命令；
- 这还不是“任意上下文直接运行脚本”，只是“受限地运行已安装 skill 包里的命令”。

### 2.5 已支持服务端外部 Skills 目录

已实现“插件继续读取包内置 skills，同时额外读取服务端外部目录”的能力。

当前加载顺序：

1. 插件内置 `skills/`
2. `external_skills_dir` 指向的外部目录
3. Dify storage 中安装的 skill 包
4. Agent 节点 `custom_skills` YAML

默认外部目录：

```text
/opt/dify-agent-skills
```

当前限制：

- 只允许读取 `/opt/dify-agent-skills`、`/app/external-skills` 及其子目录；
- 外部技能目录必须是一层一级子目录；
- Skill 文件名必须严格为 `SKILL.md`；
- 新增技能后只需往服务器目录增加 `<skill_name>/SKILL.md`，然后重新运行 Agent，不需要重新打包上传插件。

### 2.6 已加入原生会话记忆能力

该 Agent Strategy 之前没有记忆能力，现在已经接入了 Dify 原生历史消息。

当前实现：

- `strategies/skill_agent.yaml` 中声明了 `features: history-messages`
- 新增参数 `history_turns`，默认值为 `10`
- 运行时通过 `_prepare_history_messages(...)` 把最近若干轮历史消息注入模型上下文

当前效果：

- Agent 能看到最近的 Dify 会话历史；
- 调试模式下会输出类似 `Memory: loaded X turn(s), Y message(s).`

### 2.7 已加入语义技能匹配兜底

当前命中策略已经不是纯触发词匹配。

现有机制：

1. 先执行 `triggers` 规则匹配；
2. 若没有任何 trigger 命中，且 `semantic_skill_matching = true`，则调用所选模型做一次语义路由；
3. 路由置信度低于 `0.55` 时不会激活；
4. 最多激活 `max_active_skills` 个技能。

当前语义路由读取的主要元数据包括：

- `name`
- `description`
- `category`
- `triggers`
- `priority`
- `source`

### 2.8 已修复“你有什么 skills”场景下的空列表表述问题

此前模型可能只检查“安装包技能”，然后错误回答“没有任何 skills”。

现在的处理：

- 系统提示中会注入完整 Skill Inventory；
- 包含内置、外部、已安装、以及运行时注册的技能来源；
- 当用户询问“有哪些技能”时，要求模型从该 Inventory 回答，而不是说技能为空。

### 2.9 已补充 Skill 设计规范文档

已新增：

- `SKILL_DESIGN_SPEC.md`

该文档已覆盖：

- Skill 加载顺序
- Trigger 匹配规则
- 语义兜底机制
- `SKILL.md` / `config.yaml` 规范
- 外部目录结构约束
- 测试方法
- 发布检查表

它已经可以作为后续设计新 Skill 的基线规范。

## 3. 当前服务器与部署信息

### 3.1 登录信息

- 服务器地址：`103.236.97.248`
- SSH 端口：`54867`
- 用户名：`root`
- 密码：不写入仓库，请从安全凭据存储读取

Linux / macOS / OpenSSH 直接登录：

```bash
ssh root@103.236.97.248 -p 54867
```

Windows 下可用 PowerShell 自带 `ssh`，或使用 PuTTY 的 `plink.exe`：

```powershell
"D:\Program Files\plink.exe" -P 54867 root@103.236.97.248
```

已知主机指纹：

```text
SHA256:8h23c4MCUC6rV0Yuxeatq5ZuPDtryFD8aSHli3ycC3s
```

说明：

- 之前排查过 SSH 公钥与密码登录问题；
- 当前实际可用端口是 `54867`，不是默认 `22`；
- 当前部署环境支持密码登录；推荐迁移到 SSH 密钥并关闭 root 密码直登。

### 3.2 服务器上的 Dify 位置

- Dify 部署目录：`/opt/dify`
- 外部 Skill 目录：`/opt/dify-agent-skills`
- 需要挂载外部 Skill 的服务：`plugin_daemon`

建议的 volume 挂载：

```yaml
volumes:
  - /opt/dify-agent-skills:/opt/dify-agent-skills:ro
```

### 3.3 当前已知的 Dify 插件租户与插件标识

当前安装信息（2026-06-18 升级后）：

- 租户 ID：`b91f2ed2-e431-4b0a-afeb-0633d3a715f5`
- 已安装插件：`local/agent-skill-plugin-plus:1.5.0@e9e6ee6ccd4eb04a01eb388709aac6bb17450deff0a86f91a76a7795a2892689`

服务端当前部署版本是 `1.5.0`，插件运行实例已正常启动。

## 4. 当前推荐的部署 / 升级方式

### 4.1 本地打包

需要在插件目录的父目录执行：

```powershell
cd E:\vibecoding
C:\Users\ASUS\.local\bin\dify.exe plugin package ./skill-create
```

### 4.2 上传到服务器

可使用 `pscp.exe` 上传生成的 `.difypkg`：

```powershell
"D:\Program Files\pscp.exe" -P 54867 .\agent-skill-plugin-plus-<version>.difypkg root@103.236.97.248:/opt/dify/
```

### 4.3 进入容器并执行升级

已知可行流程：

1. 把宿主机 `.difypkg` 复制进 `dify-api-1` 容器；
2. 在容器内调用 Dify 官方 `PluginInstaller` 升级插件；
3. 按租户 ID 对现有插件执行 `upgrade_plugin(...)`；
4. 等待任务完成后清理临时包文件。

这套流程之前已经成功用于从旧版本升级到 `1.3.0`、`1.4.0`。

## 5. 当前未完成的点

以下是现在还没有真正做完、也是下一阶段最关键的工作。

### 5.1 通用运行时工作区脚本执行已部署

本地 1.5.0 已实现：

- 每次 Agent 调用创建独立临时工作区；
- `runtime_write_file`、`runtime_read_file`、`runtime_list_files`；
- `runtime_run_python` 与 `runtime_run_command`；
- 命令白名单、1～300 秒超时、输出截断与相对路径约束；
- 运行时执行默认关闭，需要显式开启 `allow_runtime_execution`。

安全说明：

- 该能力是进程级受控执行，不是容器或操作系统级强沙箱；
- 生产环境仍应使用最小命令白名单，并限制插件容器权限。

### 5.2 生成文件 Blob / 附件返回已部署

本地实现包括：

- `runtime_export_file` 显式导出；
- `auto_export_files` 自动扫描常见交付文件；
- 通过 `create_blob_message(...)` 返回真实文件；
- DOCX、XLSX、PPTX、PDF 等 MIME 类型识别；
- 单文件大小限制与最多自动导出 10 个文件；
- 新增 `python-docx`、`openpyxl`、`python-pptx`、`reportlab` 运行依赖。

### 5.3 技能语义匹配已支持连续上下文

本地 1.5.0 会在语义路由前读取最近历史消息，并把“最近会话 + 当前 query”联合送入 `_semantic_match_skills(...)`。主模型上下文和技能路由使用同一组 `history_turns` 范围。

### 5.4 内置 Skills 的语义元数据已加强

已改写 `docs-helper`、`code-helper`、`testing-helper` 的中英文描述和触发词，并为文档生成、文件导出、内容填充、代码执行与测试运行补充了明确行为指令。

### 5.5 1.5.0 已打包并部署

围绕“直接运行脚本 + 返回文件 + 上下文语义匹配增强”的改动，已形成本地 `1.5.0`，并完成打包：

```text
E:\vibecoding\agent-skill-plugin-plus-1.5.0.difypkg
```

该包已确认不包含 `TECHNICAL_STATUS.md`、测试目录、示例目录和未接线草稿文件，并已部署到服务器。升级任务状态为 `success`，插件守护进程日志显示运行实例 `ready`。

下一步：

- 在 Dify 工作流中做一次完整冒烟测试

建议最少验证以下场景：

1. 用户问“你有什么 skills”
2. 用户问“OSI 模型是什么”
3. 用户先说“帮我生成一个 docx”
4. 用户下一轮只说“就填入111”
5. Agent 能调用工具或脚本生成真实文件
6. 文件能作为附件/Blob 返回

## 6. 当前代码状态的补充说明

### 6.1 已接线文件

当前真正参与插件运行链路的关键文件：

- `manifest.yaml`
- `provider/agent_skill.yaml`
- `strategies/skill_agent.yaml`
- `strategies/skill_agent.py`
- `skills/`
- `skills/package_store.py`

### 6.2 当前本地存在但未接入 manifest 的草稿文件

本地还存在以下新增文件：

- `provider/skill_manager.py`
- `provider/skill_manager.yaml`
- `tools/skill_manager.py`
- `tools/skill_manager.yaml`

现状说明：

- 这些文件当前没有挂进 `manifest.yaml`
- 因此它们不是当前已部署插件的生效能力
- 可视为本地实验性草稿或后续扩展点

## 7. 建议的下一步执行顺序

建议按下面顺序继续推进：

1. [已完成] 在 `strategies/skill_agent.py` 中加入“运行时工作区”能力；
2. [已完成] 新增直接执行 Python / 脚本、写文件、列文件、导出文件的内部工具；
3. [已完成] 把技能语义路由改为“当前 query + 最近历史上下文”联合判断；
4. [已完成] 改造内置 skills 的中文描述、触发词和文档生成指令；
5. [已完成] 升级本地版本号到 `1.5.0`；
6. [已完成] 打包 `agent-skill-plugin-plus-1.5.0.difypkg`；
7. [已完成] 部署到生产服务器；
8. [待执行] 在 Dify 工作流中以“生成 docx 并返回附件”为核心用例做业务验收。

## 8. 结论

截至当前，插件已经完成了以下核心跨越：

- 从“纯 Skill 策略”升级为“Skill + Dify Tools”策略；
- 支持服务端外部 Skills 热加载；
- 支持上传 zip Skill 包并在运行前安装；
- 支持原生历史记忆；
- 支持 trigger + 语义兜底匹配；
- 已形成一份可复用的 Skill 设计规范。

1.5.0 已补齐并部署“受控运行时执行、真实文件附件返回、连续上下文技能路由”三条主链路。当前仅剩 Dify 工作流中的端到端业务验收。
