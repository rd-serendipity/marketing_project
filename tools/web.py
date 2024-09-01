import asyncio
import json
import sys

import aiohttp
from bs4 import BeautifulSoup
from langchain.tools import tool
from pydantic import BaseModel, Field

# PARSING HTML
def parse_html(html_content: str) -> str:
    soup = BeautifulSoup(html_content, 'html.parser')
    for tag in ["nav", "footer", "aside", "script", "style", "img", "header"]:
        for match in soup.find_all(tag):
            match.decompose()

    text_content = soup.get_text()
    text_content = ' '.join(text_content.split())
    return text_content[:8000]

# FETCHING WEBPAGES
async def get_webpage_content(url: str) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            html_content = await response.text()

    text_content = parse_html(html_content)
    print(f'URL: {url} - getched successfully.')
    return text_content


# Tool Creation
class ResearchInput(BaseModel):
    research_urls: list[str] = Field(description='Must be valid list of URLs.')


@tool('research', args_schema=ResearchInput)
async def research(research_urls: list[str]) -> str:
    '''Get content of provided URLs for research purpose'''
    tasks = [asyncio.create_task(get_webpage_content(url)) for url in research_urls]
    contents = await asyncio.gather(*tasks, return_exceptions=True)
    return json.dumps(contents)
