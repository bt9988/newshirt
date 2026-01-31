#!/usr/bin/env python3
"""
Shirt Trends Monitor
--------------------
A production-ready script to monitor Google Trends for rising "shirt" related queries.
It filters out specific colors, materials, and brands, then alerts via Telegram.

Usage:
    python3 shirt_trends_monitor.py

Requirements:
    pip install pytrends requests pandas

Environment Variables:
    TELEGRAM_BOT_TOKEN  : Your Telegram Bot Token
    TELEGRAM_CHANNEL_ID : Your Target Channel ID (e.g., @QuietWhaleChannel)
"""

import os
import sys
import json
import time
import logging
from datetime import datetime
from typing import List, Dict, Set, Optional

import requests
import pandas as pd
from pytrends.request import TrendReq

# --- Configuration ---
SEEN_FILE = 'seen_trends.json'
KEYWORD = 'shirt'
TIMEFRAME = 'now 4-H'  # Last 4 hours to catch immediate trends
GEO = 'US'             # Default to US, change to '' for worldwide

# Filter Rules
EXCLUDED_COLORS = {
    'white', 'black', 'red', 'blue', 'green', 'yellow',
    'pink', 'purple', 'brown', 'grey', 'gray', 'orange'
}

EXCLUDED_MATERIALS = {
    'linen', 'denim', 'cotton', 'silk', 'wool'
}

EXCLUDED_BRANDS = {
    'supreme', 'bape', 'hardy', 'custom', 'nike', 'adidas', 'armour', 'under', 'emotions', 'punisher', 'social', 'karl', 'spiderman', 'chanel', 
}

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class TrendMonitor:
    def __init__(self):
        self.bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        self.channel_id = os.environ.get('TELEGRAM_CHANNEL_ID')
        
        # Validate Env Vars
        if not self.bot_token or not self.channel_id:
            logger.error("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHANNEL_ID env vars.")
            sys.exit(1)

        self.pytrends = TrendReq(hl='en-US', tz=360)
        self.seen_phrases = self._load_seen_phrases()

    def _load_seen_phrases(self) -> Set[str]:
        """Loads previously alerted phrases to prevent duplicates."""
        if not os.path.exists(SEEN_FILE):
            return set()
        try:
            with open(SEEN_FILE, 'r') as f:
                data = json.load(f)
                return set(data)
        except (json.JSONDecodeError, IOError):
            logger.warning("Could not read seen_trends.json. Starting fresh.")
            return set()

    def _save_seen_phrases(self):
        """Persists seen phrases to disk."""
        try:
            with open(SEEN_FILE, 'w') as f:
                json.dump(list(self.seen_phrases), f)
        except IOError as e:
            logger.error(f"Failed to save seen phrases: {e}")

    def is_valid_phrase(self, phrase: str) -> bool:
        """
        Applies filtering logic:
        1. Must contain 'shirt'
        2. Must NOT contain excluded colors, materials, or brands.
        """
        lower_phrase = phrase.lower()
        
        # 1. Base keyword check
        if 'shirt' not in lower_phrase:
            return False

        # 2. Exclusion checks
        # Helper to check if any word in a set exists as a substring in the phrase
        def contains_excluded(excluded_set: Set[str]) -> bool:
            for item in excluded_set:
                # We use word boundary check logic simply by checking inclusion
                # For stricter matching, regex could be used, but simple inclusion is safer for "redshirt"
                if item in lower_phrase:
                    return True
            return False

        if contains_excluded(EXCLUDED_COLORS):
            logger.debug(f"Filtered (Color): {phrase}")
            return False

        if contains_excluded(EXCLUDED_MATERIALS):
            logger.debug(f"Filtered (Material): {phrase}")
            return False

        if contains_excluded(EXCLUDED_BRANDS):
            logger.debug(f"Filtered (Brand): {phrase}")
            return False

        return True

    def fetch_rising_queries(self) -> List[Dict]:
        """
        Queries Google Trends for 'related queries' to the keyword 'shirt'.
        Returns a list of dictionaries containing the query and value.
        """
        try:
            self.pytrends.build_payload([KEYWORD], cat=0, timeframe=TIMEFRAME, geo=GEO)
            related = self.pytrends.related_queries()
            
            if not related or KEYWORD not in related:
                logger.warning("Empty response from Google Trends API.")
                return []

            # 'rising' contains queries with significant recent growth
            rising_df = related[KEYWORD]['rising']
            
            if rising_df is None or rising_df.empty:
                logger.info("No rising trends found currently.")
                return []

            # Convert DataFrame to list of dicts for easier processing
            return rising_df.to_dict('records')

        except Exception as e:
            logger.error(f"API Error fetching trends: {e}")
            return []

    def send_telegram_alert(self, phrase: str, growth_value):
        """Sends a formatted message to the configured Telegram channel."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        growth_str = "BREAKOUT" if str(growth_value).lower() == 'breakout' else f"+{growth_value}%"
        
        message = (
            f"👕 <b>NEW TREND DETECTED</b>\n\n"
            f"Phrase: <b>{phrase.title()}</b>\n"
            f"Growth: {growth_str}\n"
            f"Status: RISING\n"
            f"Time: {timestamp}"
        )

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.channel_id,
            "text": message,
            "parse_mode": "HTML"
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code != 200:
                logger.error(f"Telegram Send Failed: {resp.text}")
            else:
                logger.info(f"Alert sent for: {phrase}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Connection error sending Telegram alert: {e}")

    def run(self):
        """Main execution flow."""
        logger.info("Starting trend scan...")
        
        potential_trends = self.fetch_rising_queries()
        
        new_trends_found = 0
        
        for item in potential_trends:
            query = item['query']
            value = item['value']  # Growth % or 'Breakout'

            # 1. Check if already processed
            if query in self.seen_phrases:
                continue

            # 2. Check filters (Colors, Materials, Brands)
            if self.is_valid_phrase(query):
                # 3. Alert
                self.send_telegram_alert(query, value)
                
                # 4. Mark as seen
                self.seen_phrases.add(query)
                new_trends_found += 1
            else:
                # Optional: Add invalid phrases to seen to skip re-processing logic next time?
                # No, because a phrase might become valid if we change logic later. 
                # For now, we only persist alerted ones to avoid spam.
                pass

        if new_trends_found > 0:
            self._save_seen_phrases()
            logger.info(f"Scan complete. {new_trends_found} new alerts sent.")
        else:
            logger.info("Scan complete. No new valid trends found.")

if __name__ == "__main__":
    try:
        monitor = TrendMonitor()
        monitor.run()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}")
        sys.exit(1)
