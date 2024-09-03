from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mistralai import ChatMistralAI
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

class LLM:
    def __init__(self, api_services, model_name):
        if api_services == 'groq':
            llm = ChatGroq(model = model_name)
        elif api_services == 'google':
            llm = ChatGoogleGenerativeAI(model= model_name)
        elif api_services == 'anthropic':
            llm = ChatAnthropic(model_name=model_name)
        elif api_services == 'mistral':
            llm = ChatMistralAI(model_name=model_name)
        elif api_services == 'openai': 
            llm = ChatOpenAI(model=model_name)
        else:
            print('API SERVICE NOT SUPPORTED')

        self.llm = llm
        self.api_services = api_services
    
    def get_llm(self):
        return self.llm
    
    def get_llm_binded_function(self, lst_tools: list, tool_name_dict: dict):
        if self.api_services in ['groq', 'anthropic', 'openai']:
            return self.llm.bind(functions=lst_tools, function_call=tool_name_dict)
        elif self.api_services in ['google']:
            print('Not Suppoted in Google!!')


    