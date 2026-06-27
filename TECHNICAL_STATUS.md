# Agent Skill Plugin Plus 技术状态文档

> 更新时间：2026-06-19
> 文档用途：记录当前插件、外部 skills、Dify chatflow、服务器部署状态，以及当前剩余阻塞点。
> 注意：生产服务器凭据不存放在仓库中。部署时请通过密码管理器、SSH Agent、密钥文件或环境变量提供。

## 1. 当前总览

- 本地工作目录：`E:\vibecoding\skill-create`
- 当前本地插件版本：`1.5.4`
- 当前插件名称：`agent-skill-plugin-plus`
- 插件类型：`agent strategy plugin`
- 当前阶段结论：
  - 代码、skills、chatflow、部署产物和线上应用切换均已完成
  - Dify 应用已切换到最新 published workflow，切换后的全量线上冒烟已通过
  - 已验证版本已同步到 GitHub 发布分支，当前仅剩创建并合并 Pull Request

当前关键文件与目录：

- `manifest.yaml`
- `provider/agent_skill.yaml`
- `strategies/skill_agent.yaml`
- `strategies/skill_agent.py`
- `skills/`
- `examples/external-skills/`
- `scripts/build_jw_skill_chatflow.py`
- `chatflows/JW-SkillAgent-Pro-1.5.4.yml`
- `tests/`

说明：

- 当前仓库是持续开发中的工作区，不是干净发布分支
- 仓库中存在用户自己的未提交改动，处理时应避免覆盖无关更改

## 2. 已完成能力

### 2.1 插件打包与安装链路已稳定

此前出现过：

```text
agent_strategy and tool, model, endpoint, trigger, or datasource cannot be provided at the same time
```

现在已修复：

- 插件被固定为纯 `agent strategy` 类型
- `manifest.yaml` 不再混入 `tool`、`model`、`endpoint` 等异类能力
- 已可正常打包为 `.difypkg`
- 已可在 Dify 中成功升级安装

### 2.2 Agent 已支持 Skill + Dify Tools 混合执行

当前策略不再只是“读技能提示词”，而是已支持完整工具调用链路：

- Agent 节点中选择的 Dify tools 会进入策略
- 插件会把已选工具转换为模型可调用定义
- 主循环支持模型发起 tool call，并把工具结果继续送回推理上下文
- 因此当前策略已经是“Skill 路由 + Dify Tools 调用”的混合执行模式

### 2.3 外部 Skills、安装包 Skills、运行时 Skills 已打通

当前支持的 Skill 来源：

1. 插件内置 `skills/`
2. 服务端外部目录 `external_skills_dir`
3. Dify storage 中安装的 skill 包
4. Agent 节点 `custom_skills` YAML

默认服务端外部目录：

```text
/opt/dify-agent-skills
```

当前服务端外部 skills 已上传并生效，服务器上共有 11 个 external skills。

### 2.4 原生会话历史与百炼持久化记忆已接入

已完成两层记忆能力：

- Dify 原生会话历史消息注入
- 百炼持久化记忆工具接入

已经修复过的关键问题：

```text
DocumentPromptMessageContent is not JSON serializable
```

当前结论：

- live smoke 中不再出现该序列化报错
- 记忆工具的 `user_id` 已统一改为真正的 `sys.user_id` 变量选择器
- 跨轮次、跨会话记忆读写在 smoke 中已观察到正常行为

### 2.5 技能匹配已支持触发词 + 语义兜底 + 连续上下文

当前技能命中机制：

1. 先走 `triggers` 规则匹配
2. 未命中时走语义匹配
3. 语义匹配时会结合最近历史消息与当前 query 联合判断
4. 低于阈值时不激活
5. 最多激活 `max_active_skills` 个技能

当前已验证技能路由相关行为：

- 问候类请求会命中专门问候 skill
- 学习建议类请求会进入学习教练类 skill
- 网络概念解释、题目分析、题目生成等可分别落到相应 skills

### 2.6 运行时工作区与文件导出能力已完成

本地已实现并通过测试的运行时能力包括：

- 独立临时工作区
- `runtime_write_file`
- `runtime_read_file`
- `runtime_list_files`
- `runtime_run_python`
- `runtime_run_command`
- `runtime_export_file`
- `auto_export_files`

当前行为：

- 可生成真实 DOCX、XLSX、PPTX、PDF 等文件
- 可通过 Blob / 附件方式返回给前端
- 已包含命令白名单、超时、输出截断、相对路径约束等基础安全控制

### 2.7 知识库引用展示已优化

针对知识库回答场景，已完成以下优化：

- 回复中保留精确 `document_name`
- 标注更明确的页码信息
- 优先使用来源整页图片，而不是只展示插图
- 支持在回答中给出更清晰的来源指向，便于用户自己回看原文

当前 smoke 中已验证：

- 引用结果里能保留精确文件名
- 能看到页码信息
- 能看到整页图 URL

### 2.8 学习路线已改为 Mermaid

此前路线图使用纯文本，现已改为 Mermaid 代码块输出。

已验证结论：

- 前端可以正常渲染 Mermaid
- 浏览器侧验证结果显示已生成 SVG
- 未出现把原始代码块直接裸露给用户的情况

### 2.9 Besti 公文格式 Word 生成已补强

已完成：

- 严格按 Besti 公文格式约束生成 Word
- 表格默认作为附件放置
- 图片默认作为附件放置
- 允许显式指定放入正文
- 自动生成附件列表
- 优化签名、日期、分页、图片段落，修复图片被裁切问题

已完成的可视化验证：

- 样例 DOCX 已导出为 PDF
- 已逐页渲染为 PNG 检查版式
- 当前样例的正文、附件表格、附件图片分页表现正常

### 2.10 新工具与新 Skills 已进入最终 DSL

最终 chatflow DSL 中已包含以下 9 个工具：

- `getKonwledgeBase`
- `list_memory`
- `add_memory`
- `update_memory`
- `anspire_search`
- `anspire_crawl`
- `text2image`
- `bilibili_search`
- `bilibili_get_video_info`

新增和补充的外部 skills 已包括：

- `network-greeting`
- `network-learning-coach`
- `network-problem-solver`
- `network-question-analyzer`
- `network-question-generator`
- `network-scope-guide`
- `network-learning-media`
- `network-visual-explainer`
- `besti-document-writer`

## 3. 测试与产物状态

### 3.1 本地测试状态

- 单元测试：14 个通过
- `ruff`：通过
- external skills quick validate：11 个通过
- chatflow DSL 最终校验：通过

### 3.2 关键产物

最终 chatflow DSL：

- `E:\vibecoding\skill-create\chatflows\JW-SkillAgent-Pro-1.5.4.yml`

清爽插件包：

- `E:\vibecoding\skill-create\dist\agent-skill-plugin-plus-1.5.4-clean.difypkg`

live smoke 结果：

- `E:\vibecoding\skill-create\tmp\skill-agent-pro-1.5.4-live-smoke.json`
- `E:\vibecoding\skill-create\tmp\skill-agent-pro-1.5.4-tool-smoke.json`
- `E:\vibecoding\skill-create\tmp\skill-agent-pro-1.5.4-post-switch-smoke.json`

Besti 样例文档：

- `E:\vibecoding\skill-create\tmp\besti-sample-v154\Besti格式样例-1.5.4.docx`

## 4. 服务器与线上部署状态

### 4.1 登录与部署位置

- 服务器地址：`103.236.97.248`
- SSH 端口：`54867`
- 用户名：`root`
- Dify 部署目录：`/opt/dify`
- 外部 Skill 目录：`/opt/dify-agent-skills`

说明：

- 当前实际可用端口是 `54867`
- 建议优先使用 SSH 密钥而不是密码直登
- 生产凭据不应写入仓库

### 4.2 当前 Dify 相关标识

- tenant id：`b91f2ed2-e431-4b0a-afeb-0633d3a715f5`
- app id：`a7d68723-da54-45e3-a742-d746f4f852c7`
- 公开聊天地址：`https://dify.jasonsome.cn:22380/chat/qAwvMQu4ziP5PCai`

### 4.3 已安装插件版本

当前已安装插件：

```text
local/agent-skill-plugin-plus:1.5.4@debd5e0137308c5ce5a24bac962e86ecfd6e9dfe656a1e8aa7008f1f808c505e
```

当前结论：

- 插件安装任务已成功
- plugin daemon 日志已出现实例 ready
- 外部 skills 已上传到服务器

### 4.4 已发布 workflow

已知 workflow 状态：

- 当前线上实际运行的新 workflow：`08dfb052-a20e-4e15-bbb3-21880fffb1f0`
- 已下线的旧 workflow：`0d613718-d2e3-4e9d-8b98-116b06eb8072`
- 旧 published workflow：`39702c3f-8ed6-44a9-b9aa-2eb9ca72a0cf`
- draft workflow：`8e07a0b5-4305-4857-8270-02d96b293e5d`

## 5. 已解决的线上阻塞点

此前应用入口仍指向旧 workflow，现已解决。

### 5.1 根因确认

2026-06-19 线上数据库核查确认，app：

```text
a7d68723-da54-45e3-a742-d746f4f852c7
```

当时的 `apps.workflow_id` 确实仍为：

```text
0d613718-d2e3-4e9d-8b98-116b06eb8072
```

### 5.2 修复结果

已通过带旧值条件的数据库事务，将应用指针切换为：

```text
08dfb052-a20e-4e15-bbb3-21880fffb1f0
```

事务更新 1 行，回读结果与目标值一致。

### 5.3 切换后线上冒烟结果

新增可复用脚本：

- `scripts/live_smoke.py`

脚本仅从 `DIFY_API_KEY` 环境变量读取凭据，不在仓库中保存密钥。

切换后共执行 6 次 Service API 运行，全部满足：

- HTTP 状态均为 200
- workflow run 状态均为 `succeeded`
- 6 次运行的 `workflow_id` 均为 `08dfb052-a20e-4e15-bbb3-21880fffb1f0`
- 百炼持久化记忆可在全新会话中读回唯一验证暗号
- Bilibili 搜索返回真实视频结果和链接
- 文生图返回真实图片文件 URL
- Mermaid 路线图返回可渲染的 `mermaid` 代码块
- 知识库引用保留完整 PDF 文件名、页码和来源整页图
- plugin daemon 日志出现真实 `/dispatch/tool/invoke`
- 冒烟使用的临时 Service API Token 已删除，应用剩余 API Token 数量为 0

## 6. 仍需完成的事项

### 6.1 GitHub 发布状态

已完成：

- 已同步到 `E:\vibecoding\skill-agent-pro`
- GitHub 仓库：`Jasonsomelike/skill-agent-pro`
- 发布分支：`codex/release-1.5.4`
- 发布提交：`53330e4`（后续状态文档提交会追加在同一分支）
- 分支已成功推送到远端

仍需完成：

- 创建从 `codex/release-1.5.4` 到 `main` 的 Pull Request

当前本机 `gh` CLI 已安装，但尚未登录 GitHub；GitHub App 对该仓库创建 PR 返回 404。可登录 CLI 后创建：

```powershell
gh auth login
gh pr create --draft --base main --head codex/release-1.5.4 --title "[codex] Release Skill Agent Pro 1.5.4"
```

也可直接打开：

```text
https://github.com/Jasonsomelike/skill-agent-pro/pull/new/codex/release-1.5.4
```

## 7. 当前建议的执行顺序

1. 登录 GitHub CLI，或在浏览器打开预填 PR 页面
2. 创建 draft PR：`codex/release-1.5.4` → `main`
3. 等待 CI 通过后审阅并合并

## 8. 结论

截至 2026-06-19，`1.5.4` 本地代码、外部 skills、最终 chatflow DSL、插件安装、应用 workflow 切换和切换后线上冒烟均已完成。线上 6 次验证全部由最新 published workflow 执行成功，Bilibili、文生图、百炼持久化记忆、Mermaid 和知识库页图均已确认正常。代码已提交并推送到 `codex/release-1.5.4`，当前仅剩创建和合并 Pull Request。
