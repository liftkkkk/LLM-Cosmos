## LLM-Cosmos（企业知识图谱 / 领域本体快速构建）

LLM-Cosmos 是一个面向业务团队与数据团队的“本体与知识图谱生成工作台”：从少量种子概念出发，自动扩展严格的 `is_a`（子类）层级关系，生成可视化的领域本体结构；同时内置质量控制、人审闭环、版本化交付与可量化评测，帮助组织把“知识资产”从一次性文本产出，升级为可持续迭代、可审计、可复用的结构化资产。

## 适用场景

- 客服/售后：快速搭建产品故障树、部件层级与问题分类体系，支撑检索与分流
- 企业检索/问答（RAG）：构建领域词表与概念层级，提升召回、减少同义词噪声
- 数据治理：统一指标口径、实体命名与分类树，降低跨团队沟通成本
- 风控/合规：建立规则对象与风险分类本体，形成审计可追溯的资产包
- 研究与投研：行业概念图谱、产业链层级结构的快速成型与持续迭代

## 端到端工作流（从想法到可交付资产）

1. 输入：选择种子概念与扩展策略（深度、宽度、预算）
2. 生成：调用 OpenAI Compatible 接口抽取严格 `is_a` 三元组并增量构图
3. 质量：embedding 相似度剪枝、同义合并、冲突治理与自动消环
4. 人审：对关系进行 accept/编辑，并可“一键按审阅结果重建”
5. 交付：导出 JSON/CSV/GraphML/Turtle，并生成 revision 包用于复现与审计
6. 评测：上传 gold triples，自动计算 precision/recall/F1，量化改进空间

![图谱视图](docs/b01.jpeg)

## 核心能力

- 严格 `is_a` 三元组抽取（subject -> is_a -> object），支持 `confidence` 与 `description`
- Embedding 相似度剪枝与同义合并（控制扩展相关性，减少同义节点）
- 预算控制（最大节点数、最大 LLM 调用数），避免扩展失控
- 人工审阅闭环（accept/编辑）并可按审阅结果重建图
- 冲突治理（多父节点治理、自动消环：移除最低 confidence 边）
- 导出与对接：JSON、CSV、GraphML、Turtle（RDFS subClassOf）
- 评测与复盘：对齐 gold triples，输出 TP/FP/FN 与 precision/recall/F1
- 版本与审计：revision.json 打包图/设置/指标/人审/业务数据；审计日志可导出

## 商业价值（把“知识”变成可运营资产）

- 从 0 到 1：用“种子概念 + 约束抽取”在短周期内形成可用的领域本体雏形
- 从 1 到 N：用版本化与审计把知识沉淀为可复用资产，跨项目可迁移、可回滚
- 可量化增长：用评测指标把“好不好”变成“可对比”，支持迭代与上线门禁
- 降本增效：减少人工梳理与反复对齐成本，让专家精力聚焦在审核与口径决策

## 数据与安全（默认不做多余事情）

- 本地运行：应用与可视化在本机/内网启动，数据流向由你掌控
- 可替换模型：对接任意 OpenAI Compatible 服务（公有云/私有化网关/本地模型）
- 可审计交付：revision 与审计日志让每次变更可追溯、可复现、可评审

## 环境要求

- Python 3.10+（建议 3.11/3.12）
- 需要可用的 OpenAI Compatible 接口（默认：DashScope compatible-mode）
- 如使用默认 DashScope：需要环境变量 `DASHSCOPE_API_KEY`

## 安装

```bash
python -m pip install -r requirements.txt
```

## 启动

推荐直接启动 Streamlit（可视化工作台）：

```bash
python -m streamlit run viz/app.py
```

或使用入口：

```bash
python main.py
```

访问地址（通常为 8501；若端口被占用会自动递增）：

- http://localhost:8501

## 配置（在页面左侧 Settings）

- Model Name：默认 `qwen3-max`
- Base URL：默认 `https://dashscope.aliyuncs.com/compatible-mode/v1`
- Embedding Model：默认 `text-embedding-v4`
- Similarity Threshold：embedding 剪枝阈值
- Min Triple Confidence：过滤低置信度边（缺失 confidence 的边不拦截）
- Recursion Depth / Max Concepts / Max Width：控制扩展策略
- Max Total Nodes / Max LLM Calls：预算（避免爆炸式扩展）
- Merge Similar Entities：开启 embedding 合并（阈值与对比窗口可调）
- Human Review Mode：开启人审表格与“按审阅结果重建”
- Enforce Single Parent：单父治理（保留最高 confidence 父边）

## 评测（Benchmark）

上传 gold triples CSV（列名支持 `subject,relation,object` 或 `Subject,Relation,Object`），会计算：

- TP/FP/FN
- precision / recall / F1

## 版本化交付（Revisions & Audit）

- Download Revision JSON：导出 revision.json（包含图/设置/指标/人审/业务数据）
- Upload Revision JSON + Restore：上传并复现同一状态
- Download Audit Log as CSV：导出审计日志

## 常见问题

- 抽取/embedding 报鉴权或 401：
  - 使用默认 DashScope 时，需要设置环境变量 `DASHSCOPE_API_KEY`
- 页面提示 “Ensure Ollama is running!”：
  - 当前默认不是 Ollama，本项目走 OpenAI compatible 接口；请以页面配置为准

## 交付物示例（给客户/内部协作的“可复现资产包”）

- revision.json：包含图结构、参数设置、评测指标、人审结果与业务数据，支持上传后一键复现
- Audit Log CSV：记录关键操作与变更，便于审计与协作评审
- 图谱导出：用于导入下游系统（图数据库、三元组存储、数据平台或 RAG 流程）

## 与企业系统对接（常见落地方向）

- 作为统一概念层：为数据仓库指标、主数据与业务词表提供“可追溯的分类树”
- 作为检索增强：将本体层级用于 query 扩展、实体规范化、同义合并与召回分层
- 作为质量门禁：以评测指标与审计包作为上线准入与版本回归基线
