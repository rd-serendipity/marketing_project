import asyncio
import functools

import os
import uuid
from langchain.output_parsers.openai_functions import JsonOutputFunctionsParser
from langchain.agents import create_openai_tools_agent, AgentExecutor
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import END, StateGraph
from langchain_core.output_parsers import StrOutputParser

from colorama import Fore
from prompt_agents.prompt import Prompts
from models import LLM
from state import AgentState
from tools.web import research
from dotenv import load_dotenv

load_dotenv()

os.environ['LANGCHAIN_PROJECT'] = 'MARKETING_PROJECT'

TAVILY_TOOL = TavilySearchResults(max_results=6)
MODEL = LLM('groq', 'llama-3.1-70b-versatile').get_llm()

REQUIREMENTS_NAME = 'requirements'
SUMMARY_NAME = 'summarizer'
INPUT_NAME = 'inputer'
ROUTE_OPTIONS = [INPUT_NAME, SUMMARY_NAME]

WEBSITE_DATA_AGENT = 'website_data_agent'
CONSULTANT = 'consultant_agent'  # one with internet access
BRAND_TUNER = 'brand_tuner_agent'
QUALITY_CHECKER = 'quality_checker_agent'
FORMATTER = 'formater_node_agent'
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


# input node 
def input_node(state: AgentState):
    # if state['next_requirements'] == '':
    #     details = input('Give some details about your brand:\n')
    # else:
    details = input(f"{Fore.CYAN}{state['message_requirements'][-1].content}{Fore.RESET}:\n")
    return {'message_requirements': [HumanMessage(content=details, name = INPUT_NAME)]}

# requirements node 
guided_json = {
    'name': 'router_fn',
    'description': 'Select the next step, ask user more questions or move to summary.',
    'parameters': {
        'type': 'object',
        'properties': {
            'next_requirements': {
                'type': 'string',
                'enum': [ROUTE_OPTIONS],
                'description': "The inputer has to be called or the summarizer"
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


prompt = ChatPromptTemplate.from_template(Prompts.get_requirement_prompt())
requirements_chain = prompt | requirements_llm | JsonOutputFunctionsParser()


def requirements_node(state: AgentState):
    result = requirements_chain.invoke(state)
    return {
        'message_requirements': [AIMessage(content=result['question'], name= REQUIREMENTS_NAME)],
        'next_requirements' : result['next_requirements']
        }

prompt_template = ChatPromptTemplate.from_template(Prompts.get_summarize_requirements())

def summary(state: AgentState):
    chain = prompt_template | MODEL | StrOutputParser()
    result = chain.invoke(state)
    return {'input_data': result}


# creating agents
website_data_agent = create_agent(MODEL, [research], Prompts.get_website_data())
website_data_node = functools.partial(
    async_agent_node, agent=website_data_agent, name=WEBSITE_DATA_AGENT
)

consultant_agent = create_agent(MODEL, [TAVILY_TOOL], Prompts.get_consultant_prompt())

def consultant_agent_node(state, agent, name):
    result = agent.invoke(state)
    # print('\n\nlast_consutant: ', state['last_consultant'])
    # state['last_consultant'] = result['output']
    # print('\n\nafter updatelast_consutant: ', state['last_consultant'])
    return {
        'consultant': [HumanMessage(content=result['output'], name=name)],
        'last_consultant': result['output']    
        }

consultant_node = functools.partial(
    consultant_agent_node, agent=consultant_agent, name=CONSULTANT
)

brand_tuner_agent = create_agent(MODEL, [TAVILY_TOOL], Prompts.get_brand_tuner_prompt())


def brand_tuner_agent_node(state, agent, name):
    result = agent.invoke(state)
    # state['last_brand_tuner'] = result['output']
    return {
        'brand_tuner': [HumanMessage(content=result['output'], name=name)],
        'last_brand_tuner': result['output']
        }

brand_tuner_node = functools.partial(
    brand_tuner_agent_node, agent = brand_tuner_agent, name=BRAND_TUNER
)

# QUALITY CHECK NODE

router_function_def = {
    "name": "route",
    "description": "Select the next role or finish based on the findings and give feedback",
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

QUALITY_CHECKER_MODEL = LLM('groq', 'llama-3.1-70b-versatile').get_llm_binded_function([router_function_def], {'name': 'route'})

quality_check_chain = (
    quality_check_template
    | QUALITY_CHECKER_MODEL
    | JsonOutputFunctionsParser()
)

def quality_check_node_func(state: AgentState, agent, name):
    # for k, v in state.items():
    #     print(k, ':', v, '\n****************\n')
    result = agent.invoke(state)

    # print('RESULT\n\n\n****************************')
    # print(result)
    # print('*****************************')

    # print('*********************************')
    # print(result)
    # print('*********************************')
    # state['feedback'] = result['output'].get('feedback', '')
    # state['next'] = result['output'].get('next', 'FINISH')
    return {
        'quality_checker': [HumanMessage(content=str(result), name=name)],
        'last_quality_checker': result,
        'feedback': result['feedback'],
        'next': result['next']
        }

quality_check_node = functools.partial(
    quality_check_node_func, agent=quality_check_chain, name=QUALITY_CHECKER
)

formatter_template = ChatPromptTemplate.from_messages(
    [
        ('system', Prompts.get_formater_prompt())
    ]
)

formatter_chain = formatter_template | MODEL | StrOutputParser()
def formatter_node(state):
    result = formatter_chain.invoke(state)
    return {
        'final_output': result
    }

# def save_file_node(state: AgentState):
#     markdown_content = str(state["final_output"])
#     name = state['website_links'][0]
#     filename = f"./{uuid.uuid1()}.md"
#     with open(filename, "w", encoding="utf-8") as file:
#         file.write(markdown_content)
#     return {
#         'final_output': f'Saved final output to {filename}'
#     }

def save_file_node(state: AgentState):
    output_dir = "output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    markdown_content = str(state["final_output"])
    name = state['website_links'][0]
    filename = os.path.join(output_dir, f"{uuid.uuid1()}.md")
    
    with open(filename, "w", encoding="utf-8") as file:
        file.write(markdown_content)
    
    return {
        'final_output': f'Saved final output to {filename}'
    }

workflow = StateGraph(AgentState)
workflow.add_node(INPUT_NAME, input_node)
workflow.add_node(REQUIREMENTS_NAME, requirements_node)
workflow.add_node(SUMMARY_NAME, summary)
workflow.add_node(WEBSITE_DATA_AGENT, website_data_node)
workflow.add_node(CONSULTANT, consultant_node)
workflow.add_node(BRAND_TUNER, brand_tuner_node)
workflow.add_node(QUALITY_CHECKER, quality_check_node)
workflow.add_node(FORMATTER, formatter_node)
workflow.add_node(SAVE_FILE_NODE, save_file_node)

workflow.set_entry_point(REQUIREMENTS_NAME)
workflow.add_edge(INPUT_NAME, REQUIREMENTS_NAME)

workflow.add_conditional_edges(
    REQUIREMENTS_NAME, 
    lambda x: x['next_requirements'],
    {
        'SUMMARY': SUMMARY_NAME,
        'MORE_INPUT': INPUT_NAME
    }
)

workflow.add_edge(SUMMARY_NAME, WEBSITE_DATA_AGENT)
workflow.add_edge(WEBSITE_DATA_AGENT, CONSULTANT)
workflow.add_edge(CONSULTANT, BRAND_TUNER)
workflow.add_edge(BRAND_TUNER, QUALITY_CHECKER)

conditional_map = {name: name for name in MEMBERS}
conditional_map['FINISH'] = FORMATTER

workflow.add_conditional_edges(
    QUALITY_CHECKER,
    lambda x: x['next'],
    conditional_map
)

workflow.add_edge(FORMATTER, SAVE_FILE_NODE)
workflow.add_edge(SAVE_FILE_NODE, END)

# workflow.set_config(recursion_limit = 50)
graph = workflow.compile()


async def run_research_graph(initial_data):
    initial_state = AgentState(
        website_links=initial_data["website_links"],
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
        MEMBERS= ['consultant_agent', 'brand_tuner_agent'],
        final_output="",
        message_requirements=[],
        next_requirements='',
        input_data=''
    )
        
    async for output in graph.astream(initial_state):
        for node_name, output_value in output.items():
            print("---")
            print(f"Output from node '{node_name}':")
            print(output_value)
        print("\n---\n")


# data_input = '''Brand Name: The Souled Store

# Brand Identity: A trendy and vibrant brand that caters to the youth, focusing on pop culture-inspired merchandise and apparel. The brand emphasizes creativity, self-expression, and a fun, casual lifestyle.

# Key Products/Services:

# Graphic T-shirts
# Hoodies and sweatshirts
# Shorts and joggers
# Accessories (e.g., bags, caps, phone cases)
# Footwear
# Merchandise related to movies, TV shows, and sports teams'''

website_links = ['https://www.thesouledstore.com']
initial_data = {
    "website_links": website_links
}
asyncio.run(run_research_graph(initial_data))