import streamlit as st
import networkx as nx
from pyvis.network import Network
import tempfile
import os
import sys
import json
import math

# Add project root to path to ensure imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from llm_cosmos.core.extractor import SemanticExtractor
from llm_cosmos.core.graph_engine import GraphEngine

def cosine_similarity(v1, v2):
    if not v1 or not v2: return 0.0
    dot_product = sum(a*b for a, b in zip(v1, v2))
    magnitude1 = math.sqrt(sum(a*a for a in v1))
    magnitude2 = math.sqrt(sum(b*b for b in v2))
    if magnitude1 == 0 or magnitude2 == 0: return 0.0
    return dot_product / (magnitude1 * magnitude2)

st.set_page_config(page_title="LLM-Cosmos", layout="wide")

st.title("🌌 LLM-Cosmos: Knowledge Graph Explorer")

# Sidebar settings
with st.sidebar:
    st.header("Settings")
    model_name = st.text_input("Model Name", value="gemma3:1b")
    base_url = st.text_input("Base URL", value="http://localhost:11434/v1")
    embedding_model = st.text_input("Embedding Model", value="qwen3-embedding:0.6b")
    similarity_threshold = st.slider("Similarity Threshold", 0.0, 1.0, 0.4)
    depth = st.slider("Recursion Depth", 1, 10, 4)
    max_concepts = st.slider("Max Concepts per Node", 1, 10, 5)
    max_width = st.slider("Max Width per Layer", 5, 50, 10)
    temperature = st.slider("Temperature (Creativity)", 0.0, 1.0, 0.3)
    
    if st.button("Clear Graph"):
        if "graph_engine" in st.session_state:
            st.session_state.graph_engine.clear()
            st.rerun()

# Initialize session state
if "graph_engine" not in st.session_state:
    st.session_state.graph_engine = GraphEngine()

col1, col2 = st.columns([3, 1])

with col1:
    seed_concept = st.text_input("Enter a concept to explore:", "Artificial Intelligence")

with col2:
    st.write("") # Spacer
    st.write("")
    if st.button("🚀 Explore Cosmos", type="primary"):
        st.session_state.current_seed = seed_concept
        extractor = SemanticExtractor(model_name=model_name, base_url=base_url, temperature=temperature)
        
        # Get root embedding
        with st.spinner(f"Calculating embedding for root node '{seed_concept}'..."):
            root_embedding = extractor.get_embedding(seed_concept, model=embedding_model)
        
        if not root_embedding:
            st.error(f"Failed to get embedding for seed concept: {seed_concept}. Check if model '{embedding_model}' is available.")
            st.stop()
            
        embedding_cache = {seed_concept: root_embedding}
        st.session_state.similarity_data = [{"node": seed_concept, "similarity": 1.0}]
        
        # Progress bar
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Breadth-first search style expansion
        current_layer = [seed_concept]
        visited = set()
        
        total_steps = depth
        
        # BFS Traversal
        for d in range(depth):
            # Deduplicate current layer to avoid redundant processing
            current_layer = list(dict.fromkeys(current_layer))
            
            # Apply width limit
            if len(current_layer) > max_width:
                st.warning(f"Depth {d+1}: Limiting processing to first {max_width} nodes (out of {len(current_layer)})")
                concepts_to_process = current_layer[:max_width]
            else:
                concepts_to_process = current_layer

            status_text.text(f"Exploring depth {d+1}/{depth} - Processing {len(concepts_to_process)} concepts...")
            progress_bar.progress(d / depth)
            
            next_layer = []
            
            for i, topic in enumerate(concepts_to_process):
                if topic in visited:
                    continue
                visited.add(topic)
                
                status_text.text(f"Extracting knowledge for: {topic}")
                try:
                    kg = extractor.extract_related_concepts(topic, max_concepts=max_concepts)
                    st.session_state.graph_engine.add_knowledge(kg)
                    
                    # Collect objects for next layer
                    for triple in kg.triples:
                        if triple.object not in visited:
                            # Calculate similarity to prune unrelated concepts
                            if triple.object in embedding_cache:
                                obj_embedding = embedding_cache[triple.object]
                            else:
                                obj_embedding = extractor.get_embedding(triple.object, model=embedding_model)
                                embedding_cache[triple.object] = obj_embedding
                            
                            sim = cosine_similarity(root_embedding, obj_embedding)
                            
                            # Record similarity
                            st.session_state.similarity_data.append({
                                "node": triple.object,
                                "similarity": sim
                            })
                            
                            if sim >= similarity_threshold:
                                next_layer.append(triple.object)
                            else:
                                # Optional: log or visualize pruned nodes
                                print(f"Pruned '{triple.object}' (similarity: {sim:.2f} < {similarity_threshold})")
                except Exception as e:
                    st.error(f"Error processing {topic}: {e}")
            
            if not next_layer:
                break
                
            current_layer = next_layer
            
        progress_bar.progress(1.0)
        status_text.success("Exploration Complete!")

# Visualisation
st.subheader("Interactive Knowledge Graph")
graph = st.session_state.graph_engine.graph

if graph.number_of_nodes() > 0:
    # Highlight seed node
    if "current_seed" in st.session_state:
        seed = st.session_state.current_seed
        for node in graph.nodes:
            if node == seed:
                graph.nodes[node]['color'] = '#ff4b4b' # Red color
                graph.nodes[node]['size'] = 30
            else:
                graph.nodes[node].pop('color', None)
                graph.nodes[node].pop('size', None)

    # Pyvis configuration
    nt = Network(height="600px", width="100%", bgcolor="#222222", font_color="white", directed=True)
    nt.from_nx(graph)
    
    # Physics options for better stability and layout
    nt.force_atlas_2based()
    
    # Save and display
    try:
        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
            path = tmp.name
        
        nt.save_graph(path)
        
        with open(path, 'r', encoding='utf-8') as f:
            html_content = f.read()
            
        st.components.v1.html(html_content, height=600)
        
        # Cleanup
        os.unlink(path)
        
    except Exception as e:
        st.error(f"Error visualizing graph: {e}")
        
    # Stats
    stats = st.session_state.graph_engine.get_stats()
    st.info(f"**Graph Statistics:** {stats['nodes']} Nodes | {stats['edges']} Edges")

    # Download JSON
    graph_data = nx.node_link_data(graph)
    json_str = json.dumps(graph_data, indent=2, ensure_ascii=False)
    st.download_button(
        label="Download Graph as JSON",
        data=json_str,
        file_name="knowledge_graph.json",
        mime="application/json"
    )

    # Download Similarity Data
    if "similarity_data" in st.session_state:
        sim_json = json.dumps(st.session_state.similarity_data, indent=2, ensure_ascii=False)
        st.download_button(
            label="Download Similarity Data as JSON",
            data=sim_json,
            file_name="similarity_scores.json",
            mime="application/json"
        )
    
    # Data Table
    if st.checkbox("Show Raw Triples"):
        triples_data = []
        for u, v, data in graph.edges(data=True):
            triples_data.append({
                "Subject": u,
                "Relation": data.get("title", ""),
                "Object": v,
                "Description": data.get("description", "")
            })
        st.dataframe(triples_data)

else:
    st.info("Enter a concept and click 'Explore Cosmos' to generate the graph. Ensure Ollama is running!")
