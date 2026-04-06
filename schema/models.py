from pydantic import BaseModel, Field
from typing import List, Optional
from typing import Annotated

class Triple(BaseModel):
    subject: str = Field(..., description="The subject entity of the relationship")
    relation: str = Field(..., description="The type of relationship connecting the subject and object")
    object: str = Field(..., description="The object entity of the relationship")
    description: Optional[str] = Field(None, description="A brief explanation of why this relationship exists")
    confidence: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = Field(
        None,
        description="Model-reported confidence score in [0, 1] for the triple correctness under the given relation constraints",
    )
    source_topic: Optional[str] = Field(
        None,
        description="The topic node from which this triple was extracted (provenance)",
    )

class KnowledgeGraph(BaseModel):
    triples: List[Triple] = Field(..., description="List of knowledge triples extracted from the text")
