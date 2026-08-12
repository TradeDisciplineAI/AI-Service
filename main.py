import os
import json
import logging
from dotenv import load_dotenv

# 1. LOAD THE KEYS FIRST!
load_dotenv()

# 2. NOW WE CAN IMPORT THE AGENT!
from agent2_graph import agent2_app

# Setup production logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def main():
    print("=========================================")
    print("🤖 Agent 2: News & Sentiment Analyzer")
    print("=========================================")
    
    if not os.getenv("GOOGLE_API_KEY"):
        logger.error("GOOGLE_API_KEY missing in .env file. Exiting.")
        return

    ticker = input("\nEnter a stock ticker (e.g., RELIANCE, AAPL): ").upper()
    inputs = {"ticker": ticker}
    
    print("\n[Processing...] Fetching data and analyzing. Please wait.\n")
    
    try:
        result = agent2_app.invoke(inputs)
        final_report_dict = result.get("final_analysis_json")
        
        print("================ OUTPUT FOR AGENT 3 ================")
        print(json.dumps(final_report_dict, indent=4))
        print("====================================================")
        print("✅ Analysis Complete!")
        
    except Exception as e:
        logger.error(f"Workflow failed: {e}")

if __name__ == "__main__":
    main()