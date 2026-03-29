from openai import OpenAI
import instructor
from schema.models import KnowledgeGraph
import os
class SemanticExtractor: # https://dashscope.aliyuncs.com/compatible-mode/v1; text-embedding-v4; qwen3-max
    def __init__(self, model_name: str = "qwen3-max", base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1", temperature: float = 0.3):
        self.model_name = model_name
        self.temperature = temperature
        # Initialize OpenAI client pointing to Ollama
        self.client = instructor.from_openai(
            OpenAI(
                base_url=base_url,
                api_key=os.getenv('DASHSCOPE_API_KEY'),  # Required but ignored by Ollama
            ),
            mode=instructor.Mode.JSON
        )

    def extract_related_concepts(self, topic: str, max_concepts: int = 10) -> KnowledgeGraph:
        """
        Extracts direct relationships and sub-concepts for a given topic.
        """
        prompt = f"""
        You are an enterprise ontology designer.
        Treat "{topic}" as the current root class (concept) in an enterprise ontology.
        Your ONLY task is to list its first-level subclasses (direct child classes) in key business sub-areas.
        Every triple MUST represent a pure "X is a {topic}" subclass-of relationship that can be written strictly as "X is a kind of {topic}".
        For every triple you output:
        - Subject: a direct subclass of "{topic}" (a more specific class).
        - Relation: exactly the string "is_a" (lowercase, with underscore).
        - Object: exactly "{topic}".
        Do NOT output any other relation phrases or types (such as "depends on", "related to", "part of", "is a type of", "includes examples such as", etc.).
        If a candidate relationship cannot be expressed as a strict is-a (subclass-of) relation to "{topic}", omit it.
        Return ONLY ontology edges as Subject -> Relation -> Object triples that satisfy these rules.
        """
        
        try:
            resp = self.client.chat.completions.create(
                model=self.model_name,
                response_model=KnowledgeGraph,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that outputs knowledge graphs in JSON format. You MUST return valid JSON data adhering to the schema, NOT the schema definition itself."},
                    {"role": "user", "content": prompt}
                ]
            )
            # Programmatically enforce the limit
            if resp.triples and len(resp.triples) > max_concepts:
                resp.triples = resp.triples[:max_concepts]
            return resp
        except Exception as e:
            print(f"Error extracting concepts for {topic}: {e}")
            return KnowledgeGraph(triples=[])

    def get_embedding(self, text: str, model: str = "text-embedding-v4") -> list[float]:
        """
        Get embedding for a given text using Ollama.
        """
        try:
            # Using the raw OpenAI client from instructor
            response = self.client.embeddings.create(
                model=model,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"Error getting embedding for {text}: {e}")
            return []
