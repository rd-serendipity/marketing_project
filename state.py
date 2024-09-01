from typing import Annotated, Sequence, TypedDict
from langchain_core.messages import BaseMessage
import operator

class AgentState(TypedDict):
    input: str
    website_links: list[str]
    requirements_completed: bool  # Fixed typo here

    website_data: Annotated[Sequence[BaseMessage], operator.add]
    brand_tuner: Annotated[Sequence[BaseMessage], operator.add]
    consultant: Annotated[Sequence[BaseMessage], operator.add]
    quality_checker: Annotated[Sequence[BaseMessage], operator.add]

    last_brand_tuner: str
    last_consultant: str
    last_quality_checker: str
    feedback: str
    OPTIONS: list[str]
    MEMBERS: list[str]
    next: str