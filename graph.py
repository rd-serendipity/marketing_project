import asyncio
import functools
import operator
import uuid
from typing import Annotated, TypedDict, Sequence
import os
from langchain.output_parsers.openai_functions import JsonOutputFunctionsParser
from langchain.agents import create_openai_tools_agent, AgentExecutor
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph

from prompt_agents.prompt import Prompts
from llm import LLM
from state import AgentState
from tools.web import research
from dotenv import load_dotenv

load_dotenv()

os.environ['LANGCHAIN_PROJECT'] = 'MARKETING_PROJECT'

TAVILY_TOOL = TavilySearchResults(max_results=6)
MODEL = LLM('groq', 'llama-3.1-70b-versatile').get_llm()

WEBSITE_DATA_AGENT = 'website_data_agent'
CONSULTANT = 'consultant_agent'  # one with internet access
BRAND_TUNER = 'brand_tuner_agent'
QUALITY_CHECKER = 'quality_checker_agent'
SAVE_FILE_NODE = 'save_file_agent'

MEMBERS = [CONSULTANT, BRAND_TUNER]
OPTIONS = MEMBERS + ['FINISH']

def create_agent(llm, tools, system_prompt):
    prompt = ChatPromptTemplate.from_messages(
        [
            ('system', system_prompt),
            MessagesPlaceholder(variable_name='agent_scratchpad')
        ]
    )
    agent = create_openai_tools_agent(llm=llm, tools=tools, prompt=prompt)
    executor = AgentExecutor(agent=agent, tools=tools)
    return executor

async def async_agent_node(state: AgentState, agent, name):
    result = await agent.ainvoke(state)
    return {'website_data': [HumanMessage(content=result['output'], name=name)]}

# creating agents
website_data_agent = create_agent(MODEL, [research], Prompts.get_website_data())
website_data_node = functools.partial(
    async_agent_node, agent=website_data_agent, name=WEBSITE_DATA_AGENT
)

consultant_agent = create_agent(MODEL, [TAVILY_TOOL], Prompts.get_consultant_prompt())

def consultant_agent_node(state, agent, name):
    result = agent.invoke(state)
    state['last_consultant'] = result['output']
    return {'consultant': [HumanMessage(content=result['output'], name=name)]}

consultant_node = functools.partial(
    consultant_agent_node, agent=consultant_agent, name=CONSULTANT
)

brand_tuner_agent = create_agent(MODEL, [TAVILY_TOOL], Prompts.get_brand_tuner_prompt())

def brand_tuner_agent_node(state, agent, name):
    result = agent.invoke(state)
    state['last_brand_tuner'] = result['output']
    return {'brand_tuner': [HumanMessage(content=result['output'], name=name)]}

brand_tuner_node = functools.partial(
    brand_tuner_agent_node, agent = brand_tuner_agent, name=BRAND_TUNER
)

# QUALITY CHECK NODE

router_function_def = {
    "name": "route",
    "description": "Select the next role or finish based on the findings.",
    "parameters": {
        "type": "object",
        "properties": {
            "next": {
                "type": "string",
                "enum": OPTIONS,
                "description": "The next role to be called or FINISH if the process is complete."
            },
            "feedback": {
                "type": "string",
                "description": "Feedback on the current state or reason for the selection."
            }
        },
        "required": ["next", "feedback"]
    }
}

quality_check_template = ChatPromptTemplate.from_messages([
    ('system', Prompts.get_quality_check_prompt()),
    (
        'system',
        'Given the conversation above, who should act next?'
        ' Or should we FINISH? Select one of: {options}',
    )]
).partial(options=', '.join(OPTIONS), members=', '.join(MEMBERS))

quality_check_chain = (
    quality_check_template
    | MODEL.bind(functions=[router_function_def], function_call={'name': 'route'})
    | JsonOutputFunctionsParser()
)

def quality_check_node_func(state: AgentState, agent, name):
    for s in state:
        print(s)
    result = agent.invoke(state)
    print('*********************************')
    print(result)
    print('*********************************')
    state['feedback'] = result['output'].get('feedback', '')
    state['next'] = result['output'].get('next', 'FINISH')
    return {'quality_checker': HumanMessage(content=str(result['output']), name=name)}

quality_check_node = functools.partial(
    quality_check_node_func, agent=quality_check_chain, name=QUALITY_CHECKER
)

workflow = StateGraph(AgentState)
workflow.add_node(WEBSITE_DATA_AGENT, website_data_node)
workflow.add_node(CONSULTANT, consultant_node)
workflow.add_node(BRAND_TUNER, brand_tuner_node)
workflow.add_node(QUALITY_CHECKER, quality_check_node)

workflow.set_entry_point(WEBSITE_DATA_AGENT)
workflow.add_edge(WEBSITE_DATA_AGENT, CONSULTANT)
workflow.add_edge(CONSULTANT, BRAND_TUNER)
workflow.add_edge(BRAND_TUNER, QUALITY_CHECKER)

conditional_map = {name: name for name in MEMBERS}
conditional_map['FINISH'] = END

workflow.add_conditional_edges(
    QUALITY_CHECKER,
    lambda x: x['next'],
    conditional_map
)

graph = workflow.compile()

async def run_research_graph(input):
    initial_state = AgentState(
        input=[HumanMessage(content=input["input"])],
        website_links=input["website_links"],
        requirements_completed=False,
        website_data=[],
        brand_tuner=[],
        consultant=[],
        quality_checker=[],
        last_brand_tuner="",
        last_consultant="",
        last_quality_checker="",
        feedback="",
        next="",
        OPTIONS= ['consultant_agent', 'brand_tuner_agent', 'FINISH'],
        MEMBERS= ['consultant_agent', 'brand_tuner_agent']
    )
    async for output in graph.astream(initial_state):
        for node_name, output_value in output.items():
            print("---")
            print(f"Output from node '{node_name}':")
            print(output_value)
        print("\n---\n")

website_links = ['https://www.apple.com/', 'https://www.apple.com/iphone/']
test_input = {
    "input": "My brand name is apple find strategies to find boost sales.",
    "website_links": website_links
}
asyncio.run(run_research_graph(test_input))