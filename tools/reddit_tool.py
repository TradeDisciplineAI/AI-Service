import praw
import os
import logging

logger = logging.getLogger(__name__)

def fetch_reddit_sentiment(ticker: str) -> str:
    logger.info(f"Fetching Reddit data for: {ticker}")
    
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        logger.warning("Reddit API credentials missing in .env file.")
        return "No Reddit data available (Missing API Key)."

    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent="TradingCopilot/1.0"
        )
        
        subreddit = reddit.subreddit("IndianStreetBets+IndiaInvestments+stocks")
        results = []
        
        for submission in subreddit.search(ticker, sort="new", time_filter="week", limit=5):
            results.append(f"Title: {submission.title}\nText: {submission.selftext[:100]}...\n")
            
        if not results:
            return f"No Reddit discussions found for {ticker}."
            
        return f"REDDIT DATA:\n" + "\n".join(results)
    except Exception as e:
        logger.error(f"Reddit PRAW Error: {e}")
        return "Error fetching Reddit data."