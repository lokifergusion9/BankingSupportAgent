from langchain.tools import tool
from bankingsupportagent.rag.retriever import retrieve, format_docs

@tool
def search_policies(query:str) -> str:
    """Search SecureBank's official policy documents: cards, accounts, deposits, charges, fraud, disputes, and complaints.
    Use this for questions about rules, fees, limits, timelines or procedures. Cite the source in your answer.
    
    
    Args:
        query: A short specific search question, e.g. 'replacement' card fee
    """

    return format_docs(retrieve(query))