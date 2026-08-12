import logging
import json
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

from models import Agent2State
from tools.news_api_tool import fetch_financial_news
from tools.reddit_tool import fetch_reddit_sentiment
from tools.twitter_tool import fetch_twitter_sentiment

logger = logging.getLogger(__name__)

# We use the standard LLM directly (no with_structured_output)
# Use "gemini-1.5-flash" here again, it was probably failing because of the structured output bug!
llm = ChatGoogleGenerativeAI(model="gemini-flash-latest", temperature=0.1)

def gather_data_node(state: Agent2State):
    ticker = state["ticker"]
    
    news = fetch_financial_news(ticker)
    reddit = fetch_reddit_sentiment(ticker)
    twitter = fetch_twitter_sentiment(ticker)
    
    return {
        "news_data": news,
        "reddit_data": reddit,
        "twitter_data": twitter
    }

def analyze_node(state: Agent2State):
    ticker = state["ticker"]
    logger.info(f"Analyzing gathered data for {ticker}...")
    
    system_prompt = f"""You are Agent 2, the News & Sentiment Analyzer.
    Analyze the following real-time data for {ticker}. 
    Calculate the overall sentiment and conviction score.
    Also, extract the 3 most important news headlines or social media posts.
    
    YOU MUST OUTPUT ONLY VALID JSON WITH NO MARKDOWN FORMATTING OR BACKTICKS.
    Format your response EXACTLY like this example:
    {{
        "ticker": "{ticker}",
        "overall_sentiment": "Bullish",
        "conviction_score": 8,
        "summary": "Short 2 sentence summary here.",
        "top_headlines": ["Headline 1", "Headline 2", "Headline 3"]
    }}
    
    [NEWS DATA]
    {state.get('news_data')}
    
    [REDDIT DATA]
    {state.get('reddit_data')}
    
    [TWITTER DATA]
    {state.get('twitter_data')}
    """
    
    response = llm.invoke([HumanMessage(content=system_prompt)])
    
    # NEW FIX: Safely convert the output to a string whether it's a list or not
    content = response.content
    if isinstance(content, list):
        # Join list blocks into a single string
        content = "".join([c["text"] if isinstance(c, dict) and "text" in c else str(c) for c in content])
        
    raw_text = str(content).replace('```json', '').replace('```', '').strip()
    
    try:
        final_dict = json.loads(raw_text)
    except Exception as e:
        logger.error(f"Failed to parse JSON: {e}")
        final_dict = {"error": "Failed to generate JSON", "raw_output": raw_text}
        
    return {"final_analysis_json": final_dict}

workflow = StateGraph(Agent2State)
workflow.add_node("gather_data", gather_data_node)
workflow.add_node("analyze", analyze_node)

workflow.set_entry_point("gather_data")
workflow.add_edge("gather_data", "analyze")
workflow.add_edge("analyze", END)

agent2_app = workflow.compile()