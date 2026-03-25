from pydantic import BaseModel, Field
from typing import List, Optional

class Triple(BaseModel):
    subject: str = Field(..., description="The subject entity of the relationship")
    relation: str = Field(..., description="The type of relationship connecting the subject and object")
    object: str = Field(..., description="The object entity of the relationship")
    description: Optional[str] = Field(None, description="A brief explanation of why this relationship exists")

class KnowledgeGraph(BaseModel):
    triples: List[Triple] = Field(..., description="List of knowledge triples extracted from the text")
