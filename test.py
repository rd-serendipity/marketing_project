import asyncio
import functools

import operator
import os
from typing import Annotated, TypedDict
import uuid
from langchain.output_parsers.openai_functions import JsonOutputFunctionsParser
from langchain.agents import create_openai_tools_agent, AgentExecutor
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.messages import HumanMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import END, StateGraph
from langchain_core.output_parsers import StrOutputParser

from prompt_agents.prompt import Prompts
from models import LLM
from state import AgentState
from tools.web import research
from dotenv import load_dotenv

load_dotenv()

class State(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    next: str

llm = LLM('groq', 'llama-3.1-70b-versatile').get_llm()

# creating a requirement agent

system_prompt = ''
guided_json = {
    'type': 'object',
    'properties': {
        'feedback': {
            'type': 'string',
            'description': 'The next role to be called or FINISH if have enough information'
        }
    }
}

prompt = ChatPromptTemplate.from_messages(
    [
        ('system', system_prompt),
        ('human', 'My name is john')
    ]
)



chain = prompt | llm | JsonOutputFunctionsParser()
