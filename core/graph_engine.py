import networkx as nx
from schema.models import KnowledgeGraph

class GraphEngine:
    def __init__(self):
        self.graph = nx.DiGraph()

    def add_knowledge(self, kg: KnowledgeGraph):
        """
        Integrates a KnowledgeGraph object into the NetworkX graph.
        """
        for triple in kg.triples:
            if triple.relation is None:
                continue
            if triple.relation.strip().lower() != "is_a":
                continue
            # Add nodes if they don't exist
            if not self.graph.has_node(triple.subject):
                self.graph.add_node(triple.subject, label=triple.subject, title=triple.subject)
            
            if not self.graph.has_node(triple.object):
                self.graph.add_node(triple.object, label=triple.object, title=triple.object)
            
            # Add edge with attributes
            # Using add_edge overwrites existing edges between same nodes if not careful with MultiDiGraph
            # But for DiGraph it updates attributes. We might want to append relations if multiple exist.
            # For simplicity, we just add/update.
            self.graph.add_edge(
                triple.subject, 
                triple.object, 
                title=triple.relation.strip().lower(),
                label=triple.relation.strip().lower(),
                description=triple.description
            )

    def get_stats(self):
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges()
        }

    def clear(self):
        self.graph.clear()
