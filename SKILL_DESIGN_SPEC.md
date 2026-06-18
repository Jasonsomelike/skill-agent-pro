# Agent Skill Plugin Plus：Skill 设计规范

## 1. 适用范围

本文档适用于 `Agent Skill Plugin Plus` 1.5.0 及以上版本，用于设计以下来源的 Skill：

1. 插件包内置 Skill；
2. 服务端外部目录 Skill；
3. zip 安装包 Skill；
4. Dify Agent 节点中的 `custom_skills` YAML Skill。

推荐优先使用服务端外部目录：

```text
/opt/dify-agent-skills/<skill_directory>/SKILL.md
```

这样新增或更新 Skill 后，只需重新运行 Agent，不需要重新打包插件。

---

## 2. 运行与命中机制

### 2.1 加载顺序

插件按以下顺序加载：

```text
1. 插件内置 skills/
2. external_skills_dir
3. storage 中安装的 Skill 包
4. custom_skills YAML
```

所有 Skill 通过 `name` 注册。Skill 名称必须全局唯一，不要依赖同名覆盖行为。

### 2.2 Trigger 规则匹配

插件首先使用 `triggers` 进行快速匹配：

- 忽略英文大小写；
- 使用子串匹配；
- 除 `*` 外，其他正则特殊字符会被转义；
- `*` 表示任意字符通配；
- 只要命中一个 trigger，Skill 就会进入候选列表。

评分规则：

| 命中 trigger 数量 | 分数 |
|---|---:|
| 1 | 0.50 |
| 2 | 0.70 |
| 3 | 0.80 |
| 4 及以上 | 从 0.85 递增，最高 1.00 |

候选 Skill 先按分数降序排列；分数相同时，再按 `priority` 降序排列。

最终最多激活 Agent 节点中 `max_active_skills` 指定的数量，默认是 3。

### 2.3 语义兜底匹配

当没有任何 trigger 命中，且 `semantic_skill_matching` 开启时，插件使用 Agent 节点选择的模型进行一次语义路由。路由输入包含当前 query 与 `history_turns` 范围内的最近会话，因此“就填入111”“按刚才那个格式导出”等追问可以继承上一轮任务意图。

语义路由只读取以下元数据：

```text
name
description
category
triggers
priority
source
```

语义路由不会读取 `SKILL.md` 正文。因此：

- `description` 必须准确描述 Skill 的领域、任务类型和适用边界；
- 不要只写“帮助用户解决问题”“通用助手”；
- 应写出用户可能使用的概念、任务和场景；
- 语义置信度低于 0.55 时不会激活。

一旦 Skill 被 trigger 或语义路由激活，`SKILL.md` 正文才会注入主模型上下文。

### 2.4 推荐策略

一个合格的 Skill 应同时具备：

1. 高精度 trigger：覆盖领域核心术语；
2. 高质量 description：覆盖未列出的同义词和长尾表达；
3. 清晰正文：规定激活后的处理流程和输出要求。

不要试图穷举所有 trigger。Trigger 负责高频、明确场景，description 负责语义兜底。

---

## 3. 目录结构

### 3.1 服务端外部 Skill

```text
/opt/dify-agent-skills/
└── network_teacher/
    ├── SKILL.md
    └── config.yaml
```

约束：

- 每个 Skill 必须放在独立的一级子目录中；
- 文件名必须严格为大写 `SKILL.md`；
- 插件不会递归发现更深层的 Skill 根目录；
- 以下结构不会被识别：

```text
/opt/dify-agent-skills/SKILL.md
/opt/dify-agent-skills/group/network_teacher/SKILL.md
/opt/dify-agent-skills/network_teacher/skill.md
```

### 3.2 允许的外部根目录

插件只允许读取：

```text
/opt/dify-agent-skills
/app/external-skills
```

以及它们的子目录。其他路径会被拒绝。

### 3.3 文件编码

所有文本文件必须使用：

```text
UTF-8，无 BOM
```

不要使用 GBK、ANSI 或系统默认编码。编码错误会导致整个 Skill 加载失败。

---

## 4. SKILL.md 标准格式

```markdown
---
name: network-teacher
description: 面向计算机网络学习和考试复习，解释网络协议、分层模型、路由、子网和传输层机制，并提供分步骤推导与易错点总结。
triggers:
  - 计算机网络
  - TCP
  - UDP
  - OSI
  - 七层模型
  - 子网划分
  - 路由协议
  - 网络协议
priority: 10
category: education
---

# 计算机网络教学 Skill

## 适用任务

- 解释计算机网络概念；
- 辅助课程学习与考试复习；
- 分步骤解决子网、路由和协议分析问题；
- 总结考点、易错点和典型题型。

## 处理流程

1. 先用通俗语言解释核心概念；
2. 再给出专业定义和标准术语；
3. 涉及计算时逐步展示推导；
4. 涉及考试复习时总结考点和易错点；
5. 必要时给出一个典型例题。

## 输出要求

- 使用清晰的小标题；
- 不跳过关键推导步骤；
- 区分通俗解释与专业定义；
- 不确定的信息应明确说明。

## 边界

- 不负责真实网络设备的未授权操作；
- 不编造抓包结果、设备配置或实验数据。
```

---

## 5. Frontmatter 字段规范

### 5.1 `name`

状态：必填。

推荐格式：

```text
小写英文 kebab-case
```

示例：

```yaml
name: network-teacher
name: contract-reviewer
name: sql-performance-helper
```

要求：

- 全局唯一；
- 保持稳定，不随显示名称变化；
- 不使用空格、中文、路径分隔符；
- `enabled_skills` 参数按该字段精确筛选。

虽然代码会在缺失时回退到目录名，但正式 Skill 不应依赖此行为。

### 5.2 `description`

状态：必填。

这是语义路由最重要的字段。应包含：

```text
领域 + 能处理的任务 + 典型对象/概念 + 适用场景 + 必要边界
```

推荐：

```yaml
description: 面向计算机网络学习和考试复习，解释网络协议、OSI/TCP-IP 分层、路由、子网和传输层机制，并提供分步骤推导与易错点总结。
```

不推荐：

```yaml
description: 一个有用的网络助手。
description: 帮助用户完成各种任务。
```

### 5.3 `triggers`

状态：强烈推荐。

Trigger 应覆盖：

- 核心专有名词；
- 常见中文名称；
- 常见英文名称及缩写；
- 高频任务表达；
- 容易被用户直接输入的概念。

示例：

```yaml
triggers:
  - OSI
  - 七层模型
  - 开放式系统互联
  - TCP
  - 三次握手
  - 子网划分
```

设计原则：

- 优先使用区分度高的短语；
- 同时包含中英文和常见缩写；
- 避免过宽触发词；
- 不要只写单字或常见虚词；
- 通配符仅用于明确模式。

不推荐：

```yaml
triggers:
  - 系统
  - 问题
  - 帮助
  - 数据
```

这些词会造成大量误激活。

通配符示例：

```yaml
triggers:
  - "*握手"
  - "HTTP*状态码"
```

谨慎使用 `*`，它可能扩大匹配范围。

### 5.4 `priority`

状态：可选，默认 0。

用途：仅在 trigger 匹配分数相同时决定顺序。

建议区间：

| 优先级 | 用途 |
|---:|---|
| 0 | 普通 Skill |
| 5 | 较具体的领域 Skill |
| 10 | 主要领域 Skill |
| 20 以上 | 必须压过同类 Skill 的特殊规则 |

`priority` 不会让一个完全不相关的 Skill 自动命中。

### 5.5 `category`

状态：可选，但推荐。

示例：

```yaml
category: education
category: development
category: legal
category: data-analysis
```

Category 会提供给语义路由，有助于区分相邻领域。

### 5.6 `allowed_tools`

状态：可选。

当前版本会读取该字段，但尚未使用它强制限制 Dify 工具调用。因此：

- 可以作为文档声明；
- 不可把它当作安全边界；
- 真正的工具权限仍由 Dify Agent 节点的工具配置控制。

---

## 6. config.yaml 规范

`config.yaml` 是可选文件，用于把元数据与正文分离。

示例：

```yaml
name: network-teacher
description: 面向计算机网络学习和考试复习，解释协议、分层、路由和子网问题。
triggers:
  - 计算机网络
  - OSI
  - TCP
priority: 10
category: education
```

合并规则：

```text
config.yaml 中的同名字段覆盖 SKILL.md frontmatter
```

建议选择一种维护方式：

1. 只使用 `SKILL.md` frontmatter；或
2. 把完整元数据统一放进 `config.yaml`。

不要在两个文件中维护不同版本的 triggers，否则容易出现“看起来改了，但实际被 config.yaml 覆盖”的问题。

---

## 7. SKILL.md 正文设计

正文是 Skill 激活后注入模型的行为说明。建议包含以下章节。

### 7.1 适用任务

明确 Skill 负责什么：

```markdown
## 适用任务

- 解释协议工作原理；
- 解决课程计算题；
- 生成复习提纲；
- 分析典型易错点。
```

### 7.2 处理流程

使用可执行步骤，而不是抽象口号：

```markdown
## 处理流程

1. 判断问题属于概念解释、计算题还是考试复习；
2. 概念题先通俗解释，再给专业定义；
3. 计算题逐步列公式和中间结果；
4. 最后总结结论、考点和易错点。
```

### 7.3 输出要求

规定输出结构、语言和详细程度：

```markdown
## 输出要求

- 默认使用中文；
- 先给结论，再展开解释；
- 计算过程不得省略关键步骤；
- 对比内容优先使用表格。
```

### 7.4 工具策略

如果 Skill 可能使用 Dify 工具，说明何时使用，而不是假设工具一定存在：

```markdown
## 工具策略

- 需要查询实时标准时，可使用已配置的搜索工具；
- 没有可用工具时，基于已有知识回答并说明时效限制；
- 不得声称已调用实际不存在的工具。
```

### 7.5 边界与拒绝条件

明确哪些任务不属于该 Skill：

```markdown
## 边界

- 不执行未授权网络扫描；
- 不编造真实设备或抓包结果；
- 与计算机网络无关的问题交给通用 Agent 处理。
```

---

## 8. 内容质量要求

### 8.1 指令应可执行

不推荐：

```text
请专业、准确、高质量地回答。
```

推荐：

```text
先给出一句话结论，再解释术语；涉及计算时列出输入、公式、中间结果和最终答案。
```

### 8.2 避免重复通用 Agent 指令

Skill 应只描述领域增量，不要重复：

```text
你是一个乐于助人的助手。
认真理解用户需求。
保持礼貌。
```

### 8.3 控制正文长度

Skill 正文会直接占用模型上下文。建议：

- 单个 Skill 正文控制在 500 至 2500 中文字；
- 避免粘贴整本规范、教材或 API 文档；
- 把规则压缩成步骤、表格和检查表；
- 只保留会改变模型行为的内容。

### 8.4 避免相互冲突

最多可能同时激活多个 Skill。每个 Skill 应：

- 只约束自身领域；
- 避免声明“忽略其他所有指令”；
- 避免无条件规定全局输出格式；
- 对跨领域任务允许其他 Skill 补充。

---

## 9. 参考文件和脚本

Skill 目录可以包含：

```text
references/
scripts/
templates/
assets/
```

但当前版本需要区分来源能力：

### 外部目录 Skill

外部 Skill 当前主要作为“指令 Skill”使用：

- `SKILL.md` 和 `config.yaml` 会被加载；
- 其他文件不会自动注入上下文；
- 外部目录脚本不会自动执行；
- 不应在正文中假设模型一定能读取 `references/`。

### storage 安装包 Skill

zip 安装包可通过内部 `skill_*` 动作读取文件，并在显式开启命令执行后运行白名单命令。

插件 1.5.0 还提供每次调用独立的运行时工作区：

- `runtime_write_file` / `runtime_read_file` / `runtime_list_files` 用于工作区文件操作；
- 开启 `allow_runtime_execution` 后，可使用 `runtime_run_python` 与 `runtime_run_command`；
- 最终交付文件应调用 `runtime_export_file`，或由 `auto_export_files` 自动作为 Blob 附件返回；
- DOCX、XLSX、PPTX、PDF 任务应生成真实文件，不要只输出示例脚本；
- 运行时执行不是操作系统级沙箱，生产环境必须配置最小命令白名单、超时和文件大小限制。

任何脚本执行都应：

- 默认关闭；
- 使用最小权限；
- 不写入系统目录；
- 不保存明文密钥；
- 不执行来源不可信的代码。

---

## 10. 自定义 YAML Skill

Dify Agent 节点中的 `custom_skills` 支持：

```yaml
- name: translation-helper
  description: 处理中文与英文之间的翻译、术语统一和语气调整，适用于文档、邮件和技术内容。
  triggers:
    - 翻译
    - translate
    - 中译英
    - 英译中
  priority: 5
  category: language
  instructions: |
    # 翻译助手

    1. 识别源语言和目标语言；
    2. 保留专有名词和格式；
    3. 默认给出自然译文；
    4. 有歧义时列出备选译法。
```

`instructions` 等价于文件型 Skill 的正文。

自定义 YAML 适合临时试验；稳定 Skill 应迁移到外部目录并纳入版本管理。

---

## 11. 标准设计流程

### 第一步：定义领域边界

回答：

```text
该 Skill 负责什么？
不负责什么？
什么问题应激活？
什么相似问题不应激活？
```

### 第二步：编写 description

先写一段能让不了解正文的路由模型正确分类的描述。

### 第三步：设计 triggers

至少覆盖：

```text
2 至 5 个核心概念
2 至 5 个常见任务表达
常见中英文名称和缩写
```

Trigger 总数通常建议为 6 至 20 个。

### 第四步：编写处理流程

把专家经验转换为 3 至 8 个步骤。

### 第五步：定义输出和边界

说明结果如何组织，以及何时不应继续执行。

### 第六步：构造测试集

每个 Skill 至少准备：

```text
5 个应由 trigger 命中的问题
5 个应由语义路由命中的问题
5 个不应命中的相邻领域问题
2 个多 Skill 协同问题
```

---

## 12. 测试与验收

### 12.1 启用调试

Dify Agent 节点设置：

```text
Debug Mode: true
Enabled Skills: all
Semantic Skill Matching: true
Max Active Skills: 3
```

### 12.2 Trigger 命中测试

输入：

```text
OSI 模型是什么？
```

期望：

```text
Activated skills (trigger): network-teacher
```

### 12.3 语义兜底测试

输入中不使用任何已配置 trigger，但语义属于该领域：

```text
互联网通信为什么要采用分层架构？
```

期望：

```text
Activated skills (semantic): network-teacher
Semantic matches: network-teacher=...
```

### 12.4 负样本测试

输入：

```text
帮我写一份劳动合同解除通知。
```

`network-teacher` 不应激活。

### 12.5 清单测试

输入：

```text
你有哪些技能？
```

回答应列出完整 Registry，并标注内置、外部或安装来源，不应只检查 storage 安装包。

### 12.6 热更新测试

1. 修改 `/opt/dify-agent-skills/<skill>/SKILL.md`；
2. 不重新打包插件；
3. 重新运行 Agent；
4. 检查新规则是否生效。

---

## 13. 常见问题

### Skill 没有被加载

检查：

- 是否位于外部根目录的一级子目录；
- 文件名是否严格为 `SKILL.md`；
- 文件是否为 UTF-8；
- Docker volume 是否挂载到 `plugin_daemon`；
- `external_skills_dir` 是否正确；
- YAML 是否可以解析。

### Skill 已加载但 trigger 不命中

检查：

- 用户问题是否包含 trigger 子串；
- `config.yaml` 是否覆盖了 frontmatter 的 triggers；
- 是否使用了过于具体的表达；
- 中英文名称和缩写是否齐全。

### 语义路由没有命中

检查：

- `semantic_skill_matching` 是否开启；
- description 是否明确；
- Skill 是否被 `enabled_skills` 过滤；
- 模型是否能稳定输出 JSON；
- 该问题与 Skill 的相关性是否足够高。

### Skill 误命中

改进方式：

- 删除过宽 trigger；
- 使用更具体的短语；
- 收窄 description；
- 降低 priority 只能解决同分排序，不能阻止 trigger 命中；
- 拆分职责过宽的 Skill。

---

## 14. 发布检查表

提交新 Skill 前逐项确认：

- [ ] Skill 位于独立一级目录；
- [ ] 文件名为 `SKILL.md`；
- [ ] 文件编码为 UTF-8；
- [ ] `name` 使用唯一 kebab-case；
- [ ] `description` 清楚描述领域、任务和边界；
- [ ] triggers 包含中英文、缩写和高频表达；
- [ ] triggers 不包含过宽常用词；
- [ ] `priority` 设置合理；
- [ ] `category` 已填写；
- [ ] 正文包含适用任务、处理流程、输出要求和边界；
- [ ] 正文没有重复大量通用 Agent 指令；
- [ ] 正文长度合理；
- [ ] `config.yaml` 没有意外覆盖 frontmatter；
- [ ] trigger 正样本测试通过；
- [ ] 语义路由测试通过；
- [ ] 负样本没有误激活；
- [ ] 多 Skill 场景没有冲突；
- [ ] 不依赖未配置的工具；
- [ ] 不把 `allowed_tools` 当作强制安全边界；
- [ ] 外部 Skill 不假设引用文件或脚本会自动执行。

---

## 15. 最小模板

```markdown
---
name: my-skill
description: 清楚描述领域、可处理任务、典型概念、使用场景和边界。
triggers:
  - 核心术语
  - 常见缩写
  - 高频任务表达
priority: 5
category: domain-name
---

# My Skill

## 适用任务

- 任务一；
- 任务二。

## 处理流程

1. 判断任务类型；
2. 收集或检查必要信息；
3. 按领域规则处理；
4. 输出结论和必要说明。

## 输出要求

- 指定语言、结构和详细程度；
- 明确必须展示的过程；
- 明确不可编造的信息。

## 工具策略

- 说明何时使用已配置工具；
- 工具不可用时说明降级方式。

## 边界

- 说明不负责的任务；
- 说明需要拒绝或转交的情况。
```
