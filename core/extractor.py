from openai import OpenAI
import instructor
from llm_cosmos.schema.models import KnowledgeGraph
import os
class SemanticExtractor: # https://dashscope.aliyuncs.com/compatible-mode/v1
    def __init__(self, model_name: str = "llama3", base_url: str = "http://localhost:11434/v1", temperature: float = 0.3):
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
        You are a knowledge graph extractor.
        Analyze the concept "{topic}" deeply.
        Identify the top {max_concepts} most important relationships or sub-concepts related to "{topic}".
        Return them as a set of Subject -> Relation -> Object triples.
        Ensure 'subject' is usually "{topic}" or a closely related concept.
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

    def get_embedding(self, text: str, model: str = "qwen3-embedding:0.6b") -> list[float]:
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
