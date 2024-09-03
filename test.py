import asyncio
import functools

import operator
import os
from typing import Annotated, TypedDict
import uuid
from langchain.output_parsers.openai_functions import JsonOutputFunctionsParser
from langchain.agents import create_openai_tools_agent, AgentExecutor
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.messages import HumanMessage, BaseMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import END, StateGraph
from langchain_core.output_parsers import StrOutputParser

from prompt_agents.prompt import Prompts
from models import LLM
from state import AgentState
from tools.web import research
from dotenv import load_dotenv

load_dotenv()

REQUIREMENTS_NAME = 'requirements'
SUMMARY_NAME = 'summarizer'
INPUT_NAME = 'input'
ROUTE_OPTIONS = [INPUT_NAME, SUMMARY_NAME]

class AgentState(TypedDict):
    message_requirements: Annotated[list[BaseMessage], operator.add]
    next_requirements: str
    final_requirements: str


MODEL = LLM('groq', 'llama-3.1-70b-versatile').get_llm()


def input_node(state: AgentState):
    if state['next_requirements'] == '':
        details = input('Give some details about yourself:\n')
    else:
        details = input(f"{state['message_requirements'][-1].content}:\n")
    return {'message_requirements': [HumanMessage(content=details, name = INPUT_NAME)]}

# creating a requirement agent

system_prompt = '''
You are an LLM tasked with gathering specific information about a user. Your goal is to collect the following details: user's name, father's name, hobby, gender, and nationality. 
Previous conversation: {message_requirements}.

If the user provides all the necessary details, return the following JSON structure:
json


  "next_requirements": "SUMMARY",
  "question": "nothing more to ask"

If the information provided by the user is incomplete or you need further clarification, return:
json


  "next_requirements": "MORE_INPUT",
  "question": "Please provide [specific detail(s) needed]"

If the user's last message indicates that they wish to quit or stop, or if they do not want to provide more information, return:
json


  "next_requirements": "SUMMARY",
  "question": "user denied to give full information"

Use the context from Previous conversation to evaluate the completeness of the information provided and respond accordingly.
'''



guided_json = {
    'name': 'router_fn',
    'description': 'Select the next step, ask user more questions or move to summary.',
    'parameters': {
        'type': 'object',
        'properties': {
            'next_requirements': {
                'type': 'string',
                'enum': [ROUTE_OPTIONS],
                'description': "The input has to be called or the summarizer"
            },
            'question': {
                'type': 'str',
                'description': 'The question to be asked to the user.'
            }
        },
        'required': ['next_requirements', 'question'],
    }
}

requirements_llm = LLM('groq', 'llama-3.1-70b-versatile').get_llm_binded_function([guided_json], {'name': 'router_fn'})


prompt = ChatPromptTemplate.from_messages(
    [
        ('system', system_prompt)
    ]
)

# bind the MODEL _
requirements_chain = prompt | requirements_llm | JsonOutputFunctionsParser()


def requirements_node(state: AgentState):
    result = requirements_chain.invoke(state)
    return {
        'message_requirement': [AIMessage(content=result['question'], name= REQUIREMENTS_NAME)],
        'next_requirements' : result['next_requirements']
        }


prompt = 'Summarize the whole detatils of the user by refering \nmessages: {message_requirement}'
prompt_template = ChatPromptTemplate.from_template(prompt)

def summary(state: AgentState):
    chain = prompt_template | MODEL | StrOutputParser()
    result = chain.invoke(state)
    return {'final_requirements': result}


workflow = StateGraph(AgentState)
workflow.add_node(INPUT_NAME, input_node)
workflow.add_node(REQUIREMENTS_NAME, requirements_node)
workflow.add_node(SUMMARY_NAME, summary)
workflow.set_entry_point(INPUT_NAME)
workflow.add_edge(INPUT_NAME, REQUIREMENTS_NAME)

workflow.add_conditional_edges(
    REQUIREMENTS_NAME, 
    lambda x: x['next_requirements'],
    {
        'SUMMARY': SUMMARY_NAME,
        'MORE_INPUT': INPUT_NAME
    }
)

workflow.add_edge(SUMMARY_NAME, END)



req_app = workflow.compile()

initial_state = AgentState(
    message_requirement=[],
    next_requirements='',
    final_requirements=''
)

for output in req_app.stream(initial_state):
    for node_name, output_value in output.items():
        print("---")
        print(f"Output from node '{node_name}':")
        print(output_value)
    print("\n---\n")