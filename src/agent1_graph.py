import logging
import json
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

from src.models import Agent1State
from src.tools.yfinance_tool import fetch_market_data

logger = logging.getLogger(__name__)

llm = ChatGoogleGenerativeAI(model="gemini-flash-latest", temperature=0.1)

def gather_market_node(state: Agent1State):
    ticker = state["ticker"]
    
    # Tool now returns a dictionary
    data_dict = fetch_market_data(ticker)
    
    return {"market_data": data_dict} # Save the dict to the state

def analyze_market_node(state: Agent1State):
    ticker = state["ticker"]
    
    # Extract the dictionary from state
    market_dict = state.get('market_data', {})
    
    # If the tool failed, skip AI analysis
    if "error" in market_dict:
        return {"final_scan_json": {"error": market_dict["error"]}}

    system_prompt = f"""You are Agent 1, the Market Scanner.
    Analyze this 5-minute intraday price action and volume for {ticker}.
    1. Determine if the stock is experiencing a 'Breakout', a 'Reversal', or 'Consolidating'.
    2. Identify if there is a massive surge in Volume.
    3. Estimate the nearest Key Support and Resistance price levels based on the highs and lows.
    
    [RECENT CANDLES]
    {market_dict.get('text_for_ai')}
    """
    
    # We ask the AI ONLY for the boolean flags (True/False)
    schema_prompt = f"""
    Return ONLY a valid JSON object matching this format:
    {{
        "breakout_detected": true,
        "volume_surge": true,
        "reversal_detected": false,
        "trend_direction": "UP",
        "key_support_level": 0.00,
        "key_resistance_level": 0.00,
        "summary": "Short explanation."
    }}
    """
    
    response = llm.invoke([
        HumanMessage(content=system_prompt),
        HumanMessage(content=schema_prompt)
    ])
    
    content = response.content
    if isinstance(content, list):
        content = "".join([c["text"] if isinstance(c, dict) and "text" in c else str(c) for c in content])
    
    try:
        raw_text = str(content).strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:-3].strip()
        elif raw_text.startswith("```"):
            raw_text = raw_text[3:-3].strip()
            
        ai_json = json.loads(raw_text)
        
        # FINAL ASSEMBLY: Combine the Python market data with the AI's boolean flags
        final_dict = {
            "symbol": market_dict["symbol"],
            "exchange": "NSE",
            "current_price": market_dict["current_price"],
            "timestamp": market_dict["timestamp"],
            "breakout_detected": ai_json.get("breakout_detected", False),
            "volume_surge": ai_json.get("volume_surge", False),
            "reversal_detected": ai_json.get("reversal_detected", False),
            "trend_direction": ai_json.get("trend_direction", "UNKNOWN"),
            "key_support_level": ai_json.get("key_support_level", 0.0),
            "key_resistance_level": ai_json.get("key_resistance_level", 0.0),
            "summary": ai_json.get("summary", ""),
            "ohlcv_candles": market_dict["ohlcv_candles"]
        }
        
    except Exception as e:
        logger.error(f"Failed to parse Agent 1 JSON: {e}")
        final_dict = {"error": "Failed to generate JSON"}
        
    return {"final_scan_json": final_dict}

# Build the Workflow
workflow = StateGraph(Agent1State)
workflow.add_node("gather_market", gather_market_node)
workflow.add_node("analyze_market", analyze_market_node)

workflow.set_entry_point("gather_market")
workflow.add_edge("gather_market", "analyze_market")
workflow.add_edge("analyze_market", END)

agent1_app = workflow.compile()