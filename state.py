from typing import Annotated, Sequence, TypedDict
from langchain_core.messages import BaseMessage
import operator

class AgentState(TypedDict):
    message_requirements: Annotated[list[BaseMessage], operator.add]
    next_requirements: str
    input_data: str

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
    final_output: str
    next: str