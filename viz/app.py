import streamlit as st
import networkx as nx
from pyvis.network import Network
import tempfile
import os
import sys
import json
import math
import io
import csv
from datetime import datetime, timezone
from urllib.parse import quote

# Add project root to path to ensure imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from core.extractor import SemanticExtractor
from core.graph_engine import GraphEngine
from schema.models import KnowledgeGraph, Triple

def cosine_similarity(v1, v2):
    if not v1 or not v2: return 0.0
    dot_product = sum(a*b for a, b in zip(v1, v2))
    magnitude1 = math.sqrt(sum(a*a for a in v1))
    magnitude2 = math.sqrt(sum(b*b for b in v2))
    if magnitude1 == 0 or magnitude2 == 0: return 0.0
    return dot_product / (magnitude1 * magnitude2)

def clone_model(model, **updates):
    if hasattr(model, "model_copy"):
        return model.model_copy(update=updates)
    return model.copy(update=updates)

def normalize_entity(text: str) -> str:
    return " ".join((text or "").strip().split())

def maybe_merge_entity(
    entity: str,
    embedding_cache: dict[str, list[float]],
    existing_entities: list[str],
    extractor: SemanticExtractor,
    embedding_model: str,
    enabled: bool,
    threshold: float,
    compare_limit: int,
):
    entity_norm = normalize_entity(entity)
    if not enabled or not entity_norm:
        return entity_norm, False

    if entity_norm in embedding_cache:
        entity_emb = embedding_cache[entity_norm]
    else:
        entity_emb = extractor.get_embedding(entity_norm, model=embedding_model)
        embedding_cache[entity_norm] = entity_emb

    if not entity_emb:
        return entity_norm, False

    best_match = None
    best_sim = -1.0
    candidates = existing_entities[-compare_limit:] if compare_limit > 0 else existing_entities
    for cand in candidates:
        if cand == entity_norm:
            return entity_norm, False
        cand_emb = embedding_cache.get(cand)
        if not cand_emb:
            continue
        sim = cosine_similarity(entity_emb, cand_emb)
        if sim > best_sim:
            best_sim = sim
            best_match = cand

    if best_match is not None and best_sim >= threshold:
        return best_match, True

    return entity_norm, False

def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()

def safe_iri(text: str, base: str = "urn:llm-cosmos:"):
    t = normalize_entity(text)
    if not t:
        return f"<{base}empty>"
    return f"<{base}{quote(t.replace(' ', '_'), safe=':_-')}>"

def to_turtle_rdfs_subclass(graph: nx.DiGraph):
    lines = [
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "",
    ]
    for u, v, data in graph.edges(data=True):
        rel = (data.get("title") or "").strip().lower()
        if rel != "is_a":
            continue
        lines.append(f"{safe_iri(u)} rdfs:subClassOf {safe_iri(v)} .")
    return "\n".join(lines) + "\n"

def parse_iso_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except Exception:
        return None

def compute_revenue_metrics(contracts: list[dict]):
    today = datetime.now(timezone.utc).date()
    active_arr = 0.0
    pipeline_expected_arr = 0.0
    active_logos = set()
    churned_arr = 0.0

    for row in contracts or []:
        status = (row.get("status") or "").strip().lower()
        customer = (row.get("customer") or "").strip()
        acv = float(row.get("acv_usd") or 0.0)
        prob = float(row.get("probability") or 0.0)
        start_d = parse_iso_date((row.get("start_date") or "").strip())
        end_d = parse_iso_date((row.get("end_date") or "").strip())

        in_range = True
        if start_d and today < start_d:
            in_range = False
        if end_d and today > end_d:
            in_range = False

        if status == "active":
            if in_range:
                active_arr += acv
                if customer:
                    active_logos.add(customer)
        elif status == "pipeline":
            pipeline_expected_arr += acv * max(0.0, min(1.0, prob))
        elif status == "churned":
            churned_arr += acv

    return {
        "active_arr": active_arr,
        "active_mrr": active_arr / 12.0,
        "active_customers": len(active_logos),
        "pipeline_expected_arr": pipeline_expected_arr,
        "churned_arr": churned_arr,
    }

def build_revision(seed: str, settings: dict, metrics: dict, review_items: list, graph: nx.DiGraph, business: dict):
    graph_data = nx.node_link_data(graph)
    return {
        "kind": "llm_cosmos_revision",
        "created_at": utc_now_iso(),
        "seed": seed,
        "settings": settings,
        "metrics": metrics,
        "review_items": review_items,
        "graph": graph_data,
        "business": business,
        "stats": {"nodes": graph.number_of_nodes(), "edges": graph.number_of_edges()},
    }

def restore_revision(payload: dict):
    graph_data = payload.get("graph") or {}
    g = nx.node_link_graph(graph_data, directed=True, multigraph=False)
    st.session_state.graph_engine.clear()
    st.session_state.graph_engine.graph = nx.DiGraph(g)
    st.session_state.current_seed = payload.get("seed") or ""
    st.session_state.metrics = payload.get("metrics") or st.session_state.metrics
    st.session_state.review_items = payload.get("review_items") or []
    st.session_state.review_map = {}
    business = payload.get("business") or {}
    st.session_state.company_profile = business.get("company_profile") or st.session_state.company_profile
    st.session_state.contracts = business.get("contracts") or []

def log_event(action: str, details: dict | None = None):
    st.session_state.audit_log.append(
        {"ts": utc_now_iso(), "action": action, "details": details or {}}
    )

def valuation_from_arr(arr_usd: float, multiple: float):
    return arr_usd * multiple

def format_money(n: float | None):
    if n is None:
        return None
    abs_n = abs(n)
    if abs_n >= 1_000_000_000:
        return f"${n/1_000_000_000:.2f}B"
    if abs_n >= 1_000_000:
        return f"${n/1_000_000:.2f}M"
    if abs_n >= 1_000:
        return f"${n/1_000:.2f}K"
    return f"${n:.2f}"

def parse_gold_triples_csv(bytes_data: bytes):
    text = bytes_data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    triples = set()
    for row in reader:
        s = normalize_entity((row.get("subject") or row.get("Subject") or "").strip())
        r = (row.get("relation") or row.get("Relation") or "is_a").strip().lower()
        o = normalize_entity((row.get("object") or row.get("Object") or "").strip())
        if not s or not o:
            continue
        triples.add((s, r, o))
    return triples

st.set_page_config(page_title="LLM-Cosmos", layout="wide")

st.title("🌌 LLM-Cosmos: Knowledge Graph Explorer")

# Sidebar settings
with st.sidebar:
    st.header("Settings")
    model_name = st.text_input("Model Name", value="qwen3-max")
    base_url = st.text_input("Base URL", value="https://dashscope.aliyuncs.com/compatible-mode/v1")
    embedding_model = st.text_input("Embedding Model", value="text-embedding-v4")
    similarity_threshold = st.slider("Similarity Threshold", 0.0, 1.0, 0.4)
    min_confidence = st.slider("Min Triple Confidence", 0.0, 1.0, 0.0)
    depth = st.slider("Recursion Depth", 1, 10, 4)
    max_concepts = st.slider("Max Concepts per Node", 1, 10, 5)
    max_width = st.slider("Max Width per Layer", 5, 50, 10)
    temperature = st.slider("Temperature (Creativity)", 0.0, 1.0, 0.3)
    max_total_nodes = st.slider("Max Total Nodes (Budget)", 50, 2000, 400)
    max_api_calls = st.slider("Max LLM Calls (Budget)", 10, 500, 120)
    enable_merge = st.checkbox("Merge Similar Entities (Embedding)", value=False)
    merge_threshold = st.slider("Merge Threshold", 0.0, 1.0, 0.92)
    merge_compare_limit = st.slider("Merge Compare Limit", 10, 1000, 200)
    enable_human_review = st.checkbox("Human Review Mode", value=False)
    enforce_single_parent = st.checkbox("Enforce Single Parent (Resolve Conflicts)", value=False)
    if st.button("Clear Graph"):
        if "graph_engine" in st.session_state:
            st.session_state.graph_engine.clear()
            st.session_state.pop("review_items", None)
            st.session_state.pop("review_map", None)
            st.rerun()

# Initialize session state
if "graph_engine" not in st.session_state:
    st.session_state.graph_engine = GraphEngine()
if "audit_log" not in st.session_state:
    st.session_state.audit_log = []
if "revisions" not in st.session_state:
    st.session_state.revisions = []
if "company_profile" not in st.session_state:
    st.session_state.company_profile = {
        "company_name": "",
        "segment": "enterprise",
        "pricing_model": "annual_subscription",
    }
if "contracts" not in st.session_state:
    st.session_state.contracts = []
if "metrics" not in st.session_state:
    st.session_state.metrics = {
        "llm_calls": 0,
        "embedding_calls": 0,
        "triples_total": 0,
        "triples_added": 0,
        "triples_filtered_by_confidence": 0,
        "nodes_pruned_by_similarity": 0,
        "entities_merged": 0,
    }
if "review_items" not in st.session_state:
    st.session_state.review_items = []
if "review_map" not in st.session_state:
    st.session_state.review_map = {}

col1, col2 = st.columns([3, 1])

with col1:
    seed_concept = st.text_input("Enter a concept to explore:", "Artificial Intelligence")

with col2:
    st.write("") # Spacer
    st.write("")
    if st.button("🚀 Explore Cosmos", type="primary"):
        # Start a fresh exploration each time
        st.session_state.graph_engine.clear()
        st.session_state.current_seed = seed_concept
        st.session_state.review_items = []
        st.session_state.review_map = {}
        st.session_state.metrics = {
            "llm_calls": 0,
            "embedding_calls": 0,
            "triples_total": 0,
            "triples_added": 0,
            "triples_filtered_by_confidence": 0,
            "nodes_pruned_by_similarity": 0,
            "entities_merged": 0,
        }
        settings_snapshot = {
            "model_name": model_name,
            "base_url": base_url,
            "embedding_model": embedding_model,
            "similarity_threshold": similarity_threshold,
            "min_confidence": min_confidence,
            "depth": depth,
            "max_concepts": max_concepts,
            "max_width": max_width,
            "temperature": temperature,
            "max_total_nodes": max_total_nodes,
            "max_api_calls": max_api_calls,
            "enable_merge": enable_merge,
            "merge_threshold": merge_threshold,
            "merge_compare_limit": merge_compare_limit,
            "enable_human_review": enable_human_review,
            "enforce_single_parent": enforce_single_parent,
        }
        log_event("explore_started", {"seed": seed_concept, "settings": settings_snapshot})
        extractor = SemanticExtractor(model_name=model_name, base_url=base_url, temperature=temperature)
        
        # Get root embedding
        with st.spinner(f"Calculating embedding for root node '{seed_concept}'..."):
            root_embedding = extractor.get_embedding(seed_concept, model=embedding_model)
            st.session_state.metrics["embedding_calls"] += 1
        
        if not root_embedding:
            st.error(f"Failed to get embedding for seed concept: {seed_concept}. Check if model '{embedding_model}' is available.")
            st.stop()
            
        embedding_cache = {seed_concept: root_embedding}
        st.session_state.similarity_data = [{"node": seed_concept, "similarity": 1.0}]
        existing_entities = [normalize_entity(seed_concept)]
        
        # Progress bar
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Breadth-first search style expansion
        current_layer = [seed_concept]
        visited = set()
        
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

                if st.session_state.graph_engine.graph.number_of_nodes() >= max_total_nodes:
                    status_text.warning(f"Budget reached: Max Total Nodes = {max_total_nodes}")
                    current_layer = []
                    break
                if st.session_state.metrics["llm_calls"] >= max_api_calls:
                    status_text.warning(f"Budget reached: Max LLM Calls = {max_api_calls}")
                    current_layer = []
                    break
                
                status_text.text(f"Extracting knowledge for: {topic}")
                try:
                    kg = extractor.extract_related_concepts(topic, max_concepts=max_concepts)
                    st.session_state.metrics["llm_calls"] += 1
                    st.session_state.metrics["triples_total"] += len(kg.triples or [])

                    filtered_triples = []
                    for triple in kg.triples or []:
                        conf = getattr(triple, "confidence", None)
                        if conf is not None and conf < min_confidence:
                            st.session_state.metrics["triples_filtered_by_confidence"] += 1
                            continue

                        subject_raw = triple.subject
                        object_raw = triple.object

                        subject, merged_s = maybe_merge_entity(
                            subject_raw,
                            embedding_cache=embedding_cache,
                            existing_entities=existing_entities,
                            extractor=extractor,
                            embedding_model=embedding_model,
                            enabled=enable_merge,
                            threshold=merge_threshold,
                            compare_limit=merge_compare_limit,
                        )
                        object_, merged_o = maybe_merge_entity(
                            object_raw,
                            embedding_cache=embedding_cache,
                            existing_entities=existing_entities,
                            extractor=extractor,
                            embedding_model=embedding_model,
                            enabled=enable_merge,
                            threshold=merge_threshold,
                            compare_limit=merge_compare_limit,
                        )
                        if merged_s:
                            st.session_state.metrics["entities_merged"] += 1
                        if merged_o:
                            st.session_state.metrics["entities_merged"] += 1

                        if subject and subject not in existing_entities:
                            existing_entities.append(subject)
                        if object_ and object_ not in existing_entities:
                            existing_entities.append(object_)

                        triple_with_provenance = clone_model(
                            triple,
                            subject=subject,
                            object=object_,
                            source_topic=topic,
                        )
                        filtered_triples.append(triple_with_provenance)

                        key = (subject, triple_with_provenance.relation.strip().lower(), object_)
                        existing = st.session_state.review_map.get(key)
                        if existing is None:
                            row = {
                                "accept": True,
                                "subject": subject,
                                "relation": triple_with_provenance.relation.strip().lower(),
                                "object": object_,
                                "confidence": getattr(triple_with_provenance, "confidence", None),
                                "description": getattr(triple_with_provenance, "description", None),
                                "source_topics": topic,
                            }
                            st.session_state.review_map[key] = row
                        else:
                            prev_sources = existing.get("source_topics") or ""
                            if topic not in prev_sources.split("; "):
                                existing["source_topics"] = (prev_sources + "; " + topic).strip("; ")
                            prev_conf = existing.get("confidence", None)
                            if prev_conf is None:
                                existing["confidence"] = getattr(triple_with_provenance, "confidence", None)
                            elif getattr(triple_with_provenance, "confidence", None) is not None:
                                existing["confidence"] = max(prev_conf, getattr(triple_with_provenance, "confidence", None))
                            if not existing.get("description") and getattr(triple_with_provenance, "description", None):
                                existing["description"] = getattr(triple_with_provenance, "description", None)

                    kg = KnowledgeGraph(triples=filtered_triples)
                    st.session_state.graph_engine.add_knowledge(kg)
                    st.session_state.metrics["triples_added"] += len(filtered_triples)
                    # print(kg.triples)
                    # Collect objects for next layer
                    for triple in kg.triples:
                        if triple.subject not in visited:
                            # Calculate similarity to prune unrelated concepts
                            if triple.object in embedding_cache:
                                obj_embedding = embedding_cache[triple.object]
                            else:
                                obj_embedding = extractor.get_embedding(triple.object, model=embedding_model)
                                embedding_cache[triple.object] = obj_embedding
                                st.session_state.metrics["embedding_calls"] += 1

                            if triple.subject in embedding_cache:
                                sub_embedding = embedding_cache[triple.subject]
                            else:
                                sub_embedding = extractor.get_embedding(triple.subject, model=embedding_model)
                                embedding_cache[triple.subject] = sub_embedding
                                st.session_state.metrics["embedding_calls"] += 1
                            
                            sim1 = cosine_similarity(root_embedding, obj_embedding)
                            sim2 = cosine_similarity(root_embedding, sub_embedding)
                            
                            # Record similarity
                            st.session_state.similarity_data.append({
                                "node": triple.object,
                                "similarity": sim1
                            })
                            st.session_state.similarity_data.append({
                                "node": triple.subject,
                                "similarity": sim2
                            })
                            sim = min(sim1, sim2)
                            if sim >= similarity_threshold:
                                next_layer.append(triple.subject)
                            else:
                                st.session_state.metrics["nodes_pruned_by_similarity"] += 1
                                # Optional: log or visualize pruned nodes
                                print(f"Pruned '{triple.subject}' (similarity: {sim:.2f} < {similarity_threshold})")
                except Exception as e:
                    st.error(f"Error processing {topic}: {e}")
            
            if not next_layer:
                break
                
            current_layer = next_layer
            
        progress_bar.progress(1.0)
        status_text.success("Exploration Complete!")
        st.session_state.review_items = list(st.session_state.review_map.values())
        log_event(
            "explore_completed",
            {
                "seed": seed_concept,
                "stats": st.session_state.graph_engine.get_stats(),
                "metrics": st.session_state.metrics,
            },
        )

# Visualisation
st.subheader("Interactive Knowledge Graph")
graph = st.session_state.graph_engine.graph

if graph.number_of_nodes() > 0:
    settings_snapshot = {
        "model_name": model_name,
        "base_url": base_url,
        "embedding_model": embedding_model,
        "similarity_threshold": similarity_threshold,
        "min_confidence": min_confidence,
        "depth": depth,
        "max_concepts": max_concepts,
        "max_width": max_width,
        "temperature": temperature,
        "max_total_nodes": max_total_nodes,
        "max_api_calls": max_api_calls,
        "enable_merge": enable_merge,
        "merge_threshold": merge_threshold,
        "merge_compare_limit": merge_compare_limit,
        "enable_human_review": enable_human_review,
        "enforce_single_parent": enforce_single_parent,
    }

    with st.expander("Quality & Budget Metrics", expanded=False):
        m = st.session_state.metrics
        confidences = []
        confidence_missing = 0
        for _, _, data in graph.edges(data=True):
            c = data.get("confidence", None)
            if c is None:
                confidence_missing += 1
            else:
                confidences.append(c)
        avg_conf = (sum(confidences) / len(confidences)) if confidences else None
        multi_parent_nodes = [n for n in graph.nodes if graph.in_degree(n) > 1]
        is_dag = nx.is_directed_acyclic_graph(graph)
        st.write(
            {
                "llm_calls": m.get("llm_calls", 0),
                "embedding_calls": m.get("embedding_calls", 0),
                "triples_total": m.get("triples_total", 0),
                "triples_added": m.get("triples_added", 0),
                "triples_filtered_by_confidence": m.get("triples_filtered_by_confidence", 0),
                "nodes_pruned_by_similarity": m.get("nodes_pruned_by_similarity", 0),
                "entities_merged": m.get("entities_merged", 0),
                "avg_confidence": avg_conf,
                "confidence_missing_edges": confidence_missing,
                "multi_parent_nodes": len(multi_parent_nodes),
                "is_dag": is_dag,
            }
        )

    with st.expander("Valuation Simulator (1e8 USD Target)", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            customers = st.number_input("Paying Customers", min_value=0, value=10, step=1)
            arpa_annual = st.number_input("ARPA / year (USD)", min_value=0.0, value=50_000.0, step=5_000.0)
        with c2:
            nrr = st.number_input("NRR (0.0-3.0)", min_value=0.0, max_value=3.0, value=1.2, step=0.05)
            yoy_growth = st.number_input("YoY Growth (0.0-5.0)", min_value=0.0, max_value=5.0, value=1.5, step=0.1)
        with c3:
            gross_margin = st.number_input("Gross Margin (0.0-1.0)", min_value=0.0, max_value=1.0, value=0.8, step=0.05)
            multiple = st.number_input("ARR Multiple", min_value=1.0, max_value=50.0, value=15.0, step=1.0)

        arr = float(customers) * float(arpa_annual)
        implied_valuation = valuation_from_arr(arr, float(multiple))
        rule40 = float(yoy_growth) + float(gross_margin)
        target_valuation = 100_000_000.0
        needed_arr = target_valuation / float(multiple) if multiple else None
        needed_customers = (needed_arr / float(arpa_annual)) if (needed_arr is not None and arpa_annual) else None

        st.write(
            {
                "ARR": format_money(arr),
                "Implied Valuation": format_money(implied_valuation),
                "Rule of 40 Proxy (growth+GM)": rule40,
                "Target Valuation": format_money(target_valuation),
                "ARR Needed For $100M": format_money(needed_arr) if needed_arr is not None else None,
                "Customers Needed (at ARPA)": int(needed_customers) if needed_customers is not None else None,
                "NRR": nrr,
            }
        )

    with st.expander("Revenue & Pipeline (Business Reality Check)", expanded=False):
        profile = st.session_state.company_profile
        p1, p2, p3 = st.columns(3)
        with p1:
            profile["company_name"] = st.text_input("Company Name", value=profile.get("company_name") or "")
        with p2:
            profile["segment"] = st.selectbox("Segment", options=["enterprise", "mid_market", "smb", "devtools"], index=["enterprise", "mid_market", "smb", "devtools"].index(profile.get("segment") or "enterprise"))
        with p3:
            profile["pricing_model"] = st.selectbox("Pricing Model", options=["annual_subscription", "usage_based", "hybrid"], index=["annual_subscription", "usage_based", "hybrid"].index(profile.get("pricing_model") or "annual_subscription"))

        default_contracts = st.session_state.contracts or [
            {"customer": "Customer A", "status": "active", "acv_usd": 50000.0, "probability": 1.0, "start_date": "", "end_date": "", "notes": ""},
            {"customer": "Customer B", "status": "pipeline", "acv_usd": 120000.0, "probability": 0.3, "start_date": "", "end_date": "", "notes": ""},
        ]
        edited_contracts = st.data_editor(
            default_contracts,
            use_container_width=True,
            num_rows="dynamic",
            key="contracts_editor",
            column_config={
                "status": st.column_config.SelectboxColumn("status", options=["active", "pipeline", "churned"]),
                "acv_usd": st.column_config.NumberColumn("acv_usd", min_value=0.0, step=1000.0),
                "probability": st.column_config.NumberColumn("probability", min_value=0.0, max_value=1.0, step=0.05),
            },
        )
        st.session_state.contracts = edited_contracts or []
        rev = compute_revenue_metrics(st.session_state.contracts)
        st.write(
            {
                "active_customers": rev["active_customers"],
                "active_arr": format_money(rev["active_arr"]),
                "active_mrr": format_money(rev["active_mrr"]),
                "pipeline_expected_arr": format_money(rev["pipeline_expected_arr"]),
                "churned_arr": format_money(rev["churned_arr"]),
            }
        )

        business_snapshot = {
            "company_profile": st.session_state.company_profile,
            "contracts": st.session_state.contracts,
            "computed": rev,
        }
        business_json = json.dumps(business_snapshot, ensure_ascii=False, indent=2)
        colb1, colb2 = st.columns([1, 1])
        with colb1:
            st.download_button(
                label="Download Business Snapshot JSON",
                data=business_json,
                file_name="business_snapshot.json",
                mime="application/json",
            )
        with colb2:
            upload_business = st.file_uploader("Upload Business Snapshot JSON", type=["json"], key="upload_business_snapshot")
            if upload_business is not None:
                try:
                    payload = json.loads(upload_business.getvalue().decode("utf-8"))
                    if st.button("Restore Business Snapshot"):
                        st.session_state.company_profile = payload.get("company_profile") or st.session_state.company_profile
                        st.session_state.contracts = payload.get("contracts") or []
                        log_event("business_restored", {"active_arr": compute_revenue_metrics(st.session_state.contracts)["active_arr"]})
                        st.rerun()
                except Exception as e:
                    st.error(f"Invalid business snapshot JSON: {e}")

    with st.expander("Human Review & Conflict Resolution", expanded=False):
        if enable_human_review:
            edited = st.data_editor(
                st.session_state.review_items,
                use_container_width=True,
                num_rows="dynamic",
                key="review_editor",
                column_config={
                    "accept": st.column_config.CheckboxColumn("accept"),
                    "confidence": st.column_config.NumberColumn("confidence", min_value=0.0, max_value=1.0, step=0.01),
                },
            )
            reviewed_csv = io.StringIO()
            reviewed_writer = csv.DictWriter(
                reviewed_csv,
                fieldnames=["accept", "subject", "relation", "object", "confidence", "description", "source_topics"],
            )
            reviewed_writer.writeheader()
            reviewed_writer.writerows(edited or [])
            st.download_button(
                label="Download Reviewed Triples as CSV",
                data=reviewed_csv.getvalue().encode("utf-8"),
                file_name="reviewed_triples.csv",
                mime="text/csv",
            )

            if st.button("Rebuild Graph from Reviewed Triples"):
                st.session_state.graph_engine.clear()
                accepted = []
                for row in edited or []:
                    if not row.get("accept", False):
                        continue
                    rel = (row.get("relation") or "").strip().lower()
                    if rel != "is_a":
                        continue
                    accepted.append(
                        Triple(
                            subject=normalize_entity(row.get("subject") or ""),
                            relation=rel,
                            object=normalize_entity(row.get("object") or ""),
                            description=row.get("description", None),
                            confidence=row.get("confidence", None),
                            source_topic=row.get("source_topics", None),
                        )
                    )
                st.session_state.graph_engine.add_knowledge(KnowledgeGraph(triples=accepted))
                st.session_state.review_items = edited or []
                log_event(
                    "review_rebuild",
                    {
                        "accepted": len(accepted),
                        "total": len(edited or []),
                        "stats": st.session_state.graph_engine.get_stats(),
                    },
                )
                st.rerun()

        if not nx.is_directed_acyclic_graph(graph):
            try:
                cycle_edges = nx.find_cycle(graph, orientation="original")
                st.warning({"cycle_example": cycle_edges})
            except Exception:
                st.warning("Graph has a cycle but failed to extract an example cycle.")

        multi_parent_nodes = [n for n in graph.nodes if graph.in_degree(n) > 1]
        if multi_parent_nodes:
            st.warning({"multi_parent_nodes_sample": multi_parent_nodes[:20], "count": len(multi_parent_nodes)})

        def resolve_single_parent_in_place(g: nx.DiGraph):
            to_remove = []
            for node in list(g.nodes):
                preds = list(g.predecessors(node))
                if len(preds) <= 1:
                    continue
                best_pred = None
                best_conf = -1.0
                for p in preds:
                    data = g.get_edge_data(p, node) or {}
                    c = data.get("confidence", None)
                    score = c if isinstance(c, (int, float)) else -1.0
                    if score > best_conf:
                        best_conf = score
                        best_pred = p
                for p in preds:
                    if p != best_pred:
                        to_remove.append((p, node))
            g.remove_edges_from(to_remove)

        if enforce_single_parent and st.button("Resolve Multi-Parent Conflicts (Keep Best Confidence)"):
            resolve_single_parent_in_place(graph)
            log_event("conflicts_resolved_single_parent", {"stats": st.session_state.graph_engine.get_stats()})
            st.rerun()

        def break_cycles_in_place(g: nx.DiGraph, max_steps: int = 2000):
            removed = 0
            for _ in range(max_steps):
                if nx.is_directed_acyclic_graph(g):
                    break
                cycle = nx.find_cycle(g, orientation="original")
                worst_edge = None
                worst_score = float("inf")
                for edge in cycle:
                    u, v = edge[0], edge[1]
                    data = g.get_edge_data(u, v) or {}
                    c = data.get("confidence", None)
                    score = c if isinstance(c, (int, float)) else -1.0
                    score = score if score >= 0 else 0.0
                    if score < worst_score:
                        worst_score = score
                        worst_edge = (u, v)
                if worst_edge is None:
                    break
                g.remove_edge(worst_edge[0], worst_edge[1])
                removed += 1
            return removed

        if st.button("Auto Break Cycles (Remove Lowest Confidence Edge)"):
            removed = break_cycles_in_place(graph)
            log_event("cycles_broken", {"removed_edges": removed, "stats": st.session_state.graph_engine.get_stats()})
            st.rerun()

    with st.expander("Benchmark (Gold Triples CSV)", expanded=False):
        gold_file = st.file_uploader("Upload gold triples CSV (columns: subject, relation, object)", type=["csv"])
        if gold_file is not None:
            try:
                gold = parse_gold_triples_csv(gold_file.getvalue())
                pred = set()
                for u, v, data in graph.edges(data=True):
                    r = (data.get("title") or "").strip().lower()
                    pred.add((normalize_entity(u), r, normalize_entity(v)))
                tp = len(pred & gold)
                fp = len(pred - gold)
                fn = len(gold - pred)
                precision = tp / (tp + fp) if (tp + fp) else None
                recall = tp / (tp + fn) if (tp + fn) else None
                f1 = (2 * precision * recall / (precision + recall)) if (precision is not None and recall is not None and (precision + recall)) else None
                st.write(
                    {
                        "gold_triples": len(gold),
                        "pred_triples": len(pred),
                        "tp": tp,
                        "fp": fp,
                        "fn": fn,
                        "precision": precision,
                        "recall": recall,
                        "f1": f1,
                    }
                )
            except Exception as e:
                st.error(f"Failed to evaluate: {e}")

    with st.expander("Revisions & Audit", expanded=False):
        seed = st.session_state.get("current_seed", "")
        business = {
            "company_profile": st.session_state.company_profile,
            "contracts": st.session_state.contracts,
        }
        revision = build_revision(
            seed=seed,
            settings=settings_snapshot,
            metrics=st.session_state.metrics,
            review_items=st.session_state.review_items,
            graph=graph,
            business=business,
        )
        revision_json = json.dumps(revision, ensure_ascii=False, indent=2)
        colr1, colr2 = st.columns([1, 1])
        with colr1:
            st.download_button(
                label="Download Revision JSON",
                data=revision_json,
                file_name="revision.json",
                mime="application/json",
            )
        with colr2:
            if st.button("Save Revision to Session"):
                st.session_state.revisions.append(revision)
                log_event("revision_saved", {"stats": revision.get("stats", {})})
                st.rerun()

        if st.session_state.revisions:
            st.write(
                [
                    {
                        "created_at": r.get("created_at"),
                        "seed": r.get("seed"),
                        "nodes": (r.get("stats") or {}).get("nodes"),
                        "edges": (r.get("stats") or {}).get("edges"),
                    }
                    for r in st.session_state.revisions[-10:]
                ]
            )

        uploaded = st.file_uploader("Upload Revision JSON", type=["json"])
        if uploaded is not None:
            try:
                uploaded_payload = json.loads(uploaded.getvalue().decode("utf-8"))
                if st.button("Restore Uploaded Revision"):
                    restore_revision(uploaded_payload)
                    log_event("revision_restored", {"stats": (uploaded_payload.get("stats") or {})})
                    st.rerun()
            except Exception as e:
                st.error(f"Invalid revision JSON: {e}")

        if st.session_state.audit_log:
            audit_csv = io.StringIO()
            audit_writer = csv.DictWriter(audit_csv, fieldnames=["ts", "action", "details"])
            audit_writer.writeheader()
            for item in st.session_state.audit_log:
                audit_writer.writerow(
                    {
                        "ts": item.get("ts"),
                        "action": item.get("action"),
                        "details": json.dumps(item.get("details") or {}, ensure_ascii=False),
                    }
                )
            st.download_button(
                label="Download Audit Log as CSV",
                data=audit_csv.getvalue().encode("utf-8"),
                file_name="audit_log.csv",
                mime="text/csv",
            )

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

    triple_rows = []
    for u, v, data in graph.edges(data=True):
        triple_rows.append(
            {
                "subject": u,
                "relation": data.get("title", ""),
                "object": v,
                "confidence": data.get("confidence", None),
                "description": data.get("description", ""),
                "source_topic": data.get("source_topic", None),
            }
        )
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["subject", "relation", "object", "confidence", "description", "source_topic"])
    writer.writeheader()
    writer.writerows(triple_rows)
    st.download_button(
        label="Download Triples as CSV",
        data=output.getvalue().encode("utf-8"),
        file_name="triples.csv",
        mime="text/csv",
    )

    turtle_str = to_turtle_rdfs_subclass(graph)
    st.download_button(
        label="Download Ontology as Turtle (RDFS)",
        data=turtle_str.encode("utf-8"),
        file_name="ontology.ttl",
        mime="text/turtle",
    )

    graphml_buf = io.StringIO()
    try:
        nx.write_graphml(graph, graphml_buf)
        st.download_button(
            label="Download Graph as GraphML",
            data=graphml_buf.getvalue().encode("utf-8"),
            file_name="knowledge_graph.graphml",
            mime="application/graphml+xml",
        )
    except Exception as e:
        st.warning(f"GraphML export failed: {e}")

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
                "Confidence": data.get("confidence", None),
                "Description": data.get("description", ""),
                "Source Topic": data.get("source_topic", None),
            })
        st.dataframe(triples_data)

else:
    st.info("Enter a concept and click 'Explore Cosmos' to generate the graph. Ensure Ollama is running!")
