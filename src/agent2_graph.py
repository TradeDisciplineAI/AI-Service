import logging
import json
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
import concurrent.futures

from src.models import Agent2State
from src.tools.news_api_tool import fetch_financial_news
from src.tools.reddit_tool import fetch_reddit_sentiment
from src.tools.twitter_tool import fetch_twitter_sentiment

logger = logging.getLogger(__name__)

# We use the standard LLM directly
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.1,max_retries=6)

def gather_data_node(state: Agent2State):
    ticker = state["ticker"]
    
    # Run all 3 internet scrapers at the exact same time in parallel!
    with concurrent.futures.ThreadPoolExecutor() as executor:
        news_future = executor.submit(fetch_financial_news, ticker)
        reddit_future = executor.submit(fetch_reddit_sentiment, ticker)
        twitter_future = executor.submit(fetch_twitter_sentiment, ticker)
        
        news = news_future.result()
        reddit = reddit_future.result()
        twitter = twitter_future.result()
    
    return {
        "news_data": news,
        "reddit_data": reddit,
        "twitter_data": twitter
    }

def analyze_node(state: Agent2State):
    ticker = state["ticker"]
    logger.info(f"Analyzing gathered data for {ticker}...")
    
    # OPTIMIZATION: Ensure we don't pass massive walls of text that slow the AI down
    news_str = str(state.get('news_data'))[:5000] # Limit to 5000 characters
    reddit_str = str(state.get('reddit_data'))[:5000]
    twitter_str = str(state.get('twitter_data'))[:5000]
    
    system_prompt = f"""You are Agent 2, the News & Sentiment Analyzer.
    Analyze the following real-time data for {ticker}. 
    Calculate the overall sentiment and conviction score.
    Also, extract the 3 most important news headlines or social media posts.
    
    [NEWS DATA]
    {news_str}
    
    [REDDIT DATA]
    {reddit_str}
    
    [TWITTER DATA]
    {twitter_str}
    """
    
    # OPTIMIZATION: Use Native JSON Mode instead of manual string hacking!
    schema_prompt = f"""
    Return ONLY a valid JSON object matching this exact format:
    {{
        "ticker": "{ticker}",
        "overall_sentiment": "Bullish",
        "conviction_score": 8,
        "summary": "Short 2 sentence summary here.",
        "top_headlines": [
            {{
                "title": "Headline 1",
                "description": "Short explanation of the headline."
            }}
        ]
    }}
    """
    
    import time
    
    response = None
    for attempt in range(6): # Try up to 6 times
        try:
            response = llm.invoke([
                HumanMessage(content=system_prompt),
                HumanMessage(content=schema_prompt)
            ])
            break # Success! Break out of the loop
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                logger.warning(f"Agent 2: Google Rate Limit hit! Waiting 65 seconds before retry (Attempt {attempt+1}/6)...")
                time.sleep(65) # Force the program to wait 65 seconds
                if attempt == 5: 
                    raise e # Give up after 6 failed tries
            else:
                raise e # If it's a different error, throw it immediately
    
    # YOUR ORIGINAL FIX: Safely convert the output to a string whether it's a list or not
    content = response.content
    if isinstance(content, list):
        # Join list blocks into a single string
        content = "".join([c["text"] if isinstance(c, dict) and "text" in c else str(c) for c in content])
    
    try:
        # Some versions of langchain still wrap native JSON in markdown blocks, 
        # but the inner content is guaranteed to be clean JSON.
        raw_text = str(content).strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:-3].strip()
        elif raw_text.startswith("```"):
            raw_text = raw_text[3:-3].strip()
            
        final_dict = json.loads(raw_text)
    except Exception as e:
        logger.error(f"Failed to parse JSON: {e}")
        final_dict = {"error": "Failed to generate JSON", "raw_output": str(content)}
        
    return {"final_analysis_json": final_dict}

workflow = StateGraph(Agent2State)
workflow.add_node("gather_data", gather_data_node)
workflow.add_node("analyze", analyze_node)

workflow.set_entry_point("gather_data")
workflow.add_edge("gather_data", "analyze")
workflow.add_edge("analyze", END)

agent2_app = workflow.compile()