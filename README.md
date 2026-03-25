# LLM-Cosmos

LLM-Cosmos 是一个基于 LLM 的“概念扩散”知识图谱探索器：输入一个种子概念，程序会让模型输出结构化三元组（Subject → Relation → Object），并逐层扩展，最终在 Streamlit 中展示可交互的知识图谱。

## 功能

- 通过 OpenAI Compatible API 调用本地/远端模型，抽取知识三元组（使用 Instructor + Pydantic 进行结构化约束）
- 可选使用 Embedding + 余弦相似度对扩展节点进行剪枝（减少无关扩散）
- Streamlit + PyVis 交互式可视化，支持导出图谱 JSON 与相似度数据

## 目录结构

```text
llm_cosmos/
  core/
    extractor.py        # LLM 结构化抽取 + embedding
  schema/
    models.py           # Pydantic：Triple / KnowledgeGraph
  viz/
    app.py              # Streamlit 可视化入口
  main.py               # 启动 Streamlit
  requirements.txt
```

## 依赖

- Python 3.10+（建议）
- requirements.txt：
  - openai
  - instructor
  - pydantic
  - networkx
  - streamlit
  - pyvis

## 快速开始

1) 安装依赖

```bash
python -m pip install -r requirements.txt
```

2) 准备 OpenAI Compatible 服务（示例：Ollama）

- app 默认使用：
  - Base URL: `http://localhost:11434/v1`
  - Chat Model: `gemma3:1b`
  - Embedding Model: `qwen3-embedding:0.6b`

如果你使用 Ollama，请确保已拉取并启动对应模型，并开启 OpenAI compatible API。

3) 启动可视化

```bash
python main.py
```

或直接运行 Streamlit：

```bash
python -m streamlit run viz/app.py
```

启动后在浏览器打开 Streamlit 提示的地址即可。

## 配置说明

在页面左侧 Settings 中可调整：

- Model Name：用于抽取三元组的对话模型
- Base URL：OpenAI Compatible API 地址（例如 Ollama 的 `http://localhost:11434/v1`）
- Embedding Model：用于计算相似度的 embedding 模型
- Similarity Threshold：相似度阈值（越高越“保守”）
- Recursion Depth：扩展深度
- Max Concepts per Node：每个节点最多抽取多少条三元组
- Max Width per Layer：每层最多处理多少个概念（BFS 宽度限制）
- Temperature：抽取时的随机性

环境变量：

- `DASHSCOPE_API_KEY`：`openai.OpenAI` 客户端要求提供 `api_key` 字段时使用；在 Ollama 场景下通常不会真正校验该值。

## 输出

可视化页面支持导出：

- `knowledge_graph.json`：NetworkX Node-Link 格式的图数据
- `similarity_scores.json`：每个扩展节点相对种子概念的相似度记录

## 已知问题

- [viz/app.py](file:///c:/Users/z1881/Downloads/in-llm/llm_cosmos/viz/app.py) 引用了 `llm_cosmos.core.graph_engine.GraphEngine`，但当前仓库中未包含对应实现文件，因此直接运行可能会报 `ModuleNotFoundError`。如果你希望我补齐该模块实现并保证应用可跑通，可以继续告诉我你的预期功能（最小版：只负责维护 NetworkX 有向图、去重、统计与清空）。

