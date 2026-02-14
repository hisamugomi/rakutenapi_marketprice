import requests
import streamlit as st
import time
import json
import csv
import pandas as pd
import os

# Rakuten API Endpoint

def process_rakuten_json(json_data):
    """
    Converts raw Rakuten JSON response into a flat Pandas DataFrame.
    """
    if "Items" not in json_data:
        return pd.DataFrame()

    # Unpack the nested 'Item' dictionary for each entry
    items_list = [item["Item"] for item in json_data["Items"]]
    
    # Convert to DataFrame
    df = pd.DataFrame(items_list)
    
    # Select only the columns we actually need for our model
    columns_to_keep = [
        'itemName', 'itemPrice', 'itemUrl', 'itemCaption', 
        'genreId', 'shopName', 'itemCode'
    ]
    
    # Filter only if the columns exist (safety check)
    existing_cols = [c for c in columns_to_keep if c in df.columns]
    return df[existing_cols]

# --- How to collect multiple pages into one big DataFrame ---

# all_dfs = [] # A list to hold small dataframes from each page

# for page_num in range(1, 4):  # Fetch 3 pages
#     raw_json = fetch_rakuten_items("中古 パソコン", page=page_num)
#     if raw_json:
#         page_df = process_rakuten_json(raw_json)
#         all_dfs.append(page_df)


API_URL = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"

def fetch_rakuten_items(keyword, total_pages = 30):
    """
    Fetches used computer items from Rakuten Ichiba API.
    """
    TIMEOUT = 10
    allitems = []

    for page in range(1, total_pages + 1):
        params = {
            # "applicationId": st.secrets["RAKUTEN_APP_ID"],
            "applicationId": os.environ.get("RAKUTEN_APP_ID"),
            "format": "json",
            "keyword": keyword,
            "page": page,
            "usedFlag": 1,        # 1 focuses specifically on USED items
            "genreId": 100026,    # Genre ID for 'Computers & Peripherals'
            "hits": 30,           # Items per page (max 30)
            "sort": "-itemPrice", # Sort by descending price (adjustable)
        }

        # params = {
        #     "applicationId": st.secrets["RAKUTEN_APP_ID"],
        #     "format": "json",
        #     "keyword": "Lenovo L590 -トナー -互換", # Note the negative keywords to block toner/compatibles
        #     "genreId": 100026,                  # Try 110101 for Laptops or 213313 for Used specifically

        #     "usedFlag": 1,
        #     "hits": 30,
        #     "sort": "+itemPrice", 
        # }

        
        # Include affiliate ID if it exists in secrets
        
        params["affiliateId"] = os.environ.get("RAKUTEN_AFFILIATE_ID")


        # if "RAKUTEN_AFFILIATE_ID" in st.secrets:
        #     params["affiliateId"] = st.secrets["RAKUTEN_AFFILIATE_ID"]

        try:
            response = requests.get(API_URL, params=params, timeout=TIMEOUT)
            response.raise_for_status()
            rawjson = response.json()

            if "error" in rawjson:
                st.error(f"API Error: {rawjson['error_description']}")
                return None

            if "Items" in rawjson and len(rawjson["Items"]) > 0:
        # 2. Extract and flatten
                page_df = process_rakuten_json(rawjson)
                
                # 3. Add to our collection
                allitems.append(page_df)
                print(f"✅ Scraped page {page}: {len(page_df)} items added.")
            else:
                print("🏁 No more items found or API limit reached.")
                break

        
            time.sleep(3)


        except requests.exceptions.Timeout:
            st.error("The request timed out. Rakuten's servers might be slow.")
        except requests.exceptions.HTTPError as e:
            st.error(f"HTTP Error: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            st.error(f"Unexpected Error: {e}")


    # 4. Combine all pages at once (The "Senior" move)
        if allitems:
            all_items_df = pd.concat(allitems, ignore_index=True)
        else:
            all_items_df = pd.DataFrame()

    return all_items_df