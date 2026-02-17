import pandas as pd
import polars as pl
from src.rakuten_api import fetch_rakuten_items
# from src.processor import process_results
# from src.savetosupabase import save_to_supabase
# from src.pckoboscrape import KoboScraperService
import mojimoji
import os
# from src.cleanzentohan import clean_japanese_specs
# from src.aiprocess import extract_specs
from time import sleep
from datetime import datetime
import pytz
import supabase
from supabase import create_client
from src.extract_specs_1 import extract_specs


current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Add it to your Polars DataFrame
# 'pl.lit' stands for 'literal' (applies the same value to every row)
def run_scraper():
    # if "SUPABASE_URL" in st.secrets:

    url = os.environ.get("SUPABASE_URL")
    servicerole = os.environ.get("SERVICEROLE")    

    # if "SUPABASE_URL" in st.secrets:
    #     url = st.secrets["SUPABASE_URL"]

    # if "SUPABASE_KEY" in st.secrets:
    #     key = st.secrets["SUPABASE_KEY"]
    # if "servicerole" in st.secrets:
    #     servicerole = st.secrets["servicerole"]
    supabase: Client = create_client(url, servicerole)


    querys = [
        "L580 -lenovo", 
        "L590 -lenovo", 
        "L390 -lenovo", 
        # "L390", 
        # "L580", 
        # "L590"
        ]
    
    # 1. Get current time in JST (Japan Standard Time)
    jst = pytz.timezone('Asia/Tokyo')
    now_jst = datetime.now(jst).isoformat() # ISO format is best for Supabase

    for query in querys:
        # Fetch data using your existing function
        raw_data = fetch_rakuten_items(query) 
        
        if raw_data.empty:
            continue

        # 2. Data Cleaning & Metadata Addition
        # Clean Japanese text (Zen-to-Han) on the 'itemName' or a 'combined' column

        raw_data["combined"] = raw_data["itemName"] + raw_data["itemCaption"]

        raw_data["combined"] = raw_data["combined"].apply(mojimoji.zen_to_han)
        
        # Add the 'scraped_at' timestamp and 'is_active' flag
        raw_data["scraped_at"] = now_jst
        raw_data["is_active"] = True
        raw_data["search_query"] = query # Helps you filter in Streamlit later

        # 3. UPSERT to Supabase
        # .to_dict('records') converts the DataFrame into the JSON list Supabase needs
        # data_list = raw_data.to_dict(orient='records')
        
        raw_data_pl = pl.from_pandas(raw_data)
        extracteddata = extract_specs(raw_data_pl, text_col="combined", price_col="itemPrice", name_col="itemName")

        extracteddatapd = extracteddata.to_pandas()
        data_list = extracteddatapd.to_dict(orient='records')

        try:
            # We use 'itemCode' (Rakuten's unique ID) to prevent duplicates
            supabase.table("rakuten_table").insert(data_list).execute()

            print(f"Successfully synced {len(data_list)} items for: {query}")


        except Exception as e:
            print(f"Error saving to Supabase: {e}")

run_scraper()
