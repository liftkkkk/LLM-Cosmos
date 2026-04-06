import networkx as nx
from schema.models import KnowledgeGraph

class GraphEngine:
    def __init__(self):
        self.graph = nx.DiGraph()
        self._canonical_by_norm: dict[str, str] = {}

    def _normalize_entity(self, text: str) -> str:
        return " ".join((text or "").strip().split())

    def _canonicalize_entity(self, text: str) -> str:
        norm = self._normalize_entity(text)
        if not norm:
            return norm
        if norm in self._canonical_by_norm:
            return self._canonical_by_norm[norm]
        self._canonical_by_norm[norm] = norm
        return norm

    def add_knowledge(self, kg: KnowledgeGraph):
        """
        Integrates a KnowledgeGraph object into the NetworkX graph.
        """
        for triple in kg.triples:
            if triple.relation is None:
                continue
            if triple.relation.strip().lower() != "is_a":
                continue
            subject = self._canonicalize_entity(triple.subject)
            object_ = self._canonicalize_entity(triple.object)
            if not subject or not object_:
                continue
            # Add nodes if they don't exist
            if not self.graph.has_node(subject):
                self.graph.add_node(subject, label=subject, title=subject)
            
            if not self.graph.has_node(object_):
                self.graph.add_node(object_, label=object_, title=object_)
            
            # Add edge with attributes
            # Using add_edge overwrites existing edges between same nodes if not careful with MultiDiGraph
            # But for DiGraph it updates attributes. We might want to append relations if multiple exist.
            # For simplicity, we just add/update.
            self.graph.add_edge(
                subject, 
                object_, 
                title=triple.relation.strip().lower(),
                label=triple.relation.strip().lower(),
                description=triple.description,
                confidence=triple.confidence,
                source_topic=getattr(triple, "source_topic", None),
            )

    def get_stats(self):
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges()
        }

    def clear(self):
        self.graph.clear()
        self._canonical_by_norm.clear()
