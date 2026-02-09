import streamlit as st
import pandas as pd
from src.rakuten_api import fetch_rakuten_items
from src.processor import process_results
# from src.pckoboscrape import KoboScraperService
import mojimoji

from src.cleanzentohan import clean_japanese_specs
# from src.aiprocess import extract_specs
from time import sleep
from datetime import datetime


datetime = datetime.now().strftime("%Y-%m-%^d %H:%M")


st.set_page_config(page_title="Rakuten Used PC Finder", layout="wide")

st.title("💻 Rakuten Used Computer Finder")
st.markdown("Find the best deals on used PCs via the Rakuten API.")

# Sidebar Filters
with st.sidebar:
    st.header("Search Filters")
    query = st.text_input("Search Keyword (e.g., MacBook, ThinkPad)", value="Laptop")
    search_button = st.button("Search Rakuten")

# Main Logic

# scraper = KoboScraperService()
# if st.button("Scrape PC Kobo"):
#     df = scraper.fetch_items("ThinkPad", total_pages=3)
#     st.dataframe(df)

if search_button:
    with st.spinner("Fetching listings..."):
        raw_data = fetch_rakuten_items(query)

        results_list = []

        final_df=pd.DataFrame

        print(raw_data)
        
        items = raw_data

        items["combined"] = items["itemName"] + items["itemCaption"]

        items["combined"] = items["combined"].apply(mojimoji.zen_to_han)

        # 2. Convert the list of dicts into a new "Specs" DataFrame

        # 3. Merge side-by-side
        # We use axis=1 to add columns, and reset_index to ensure rows align perfectly
        final_df = items


        try:
            final_df.to_csv(f"rakutenapidata_{query}{datetime}.csv", index = False)
            
            # Display summary
            st.success(f"Found {len(final_df)} items matching your criteria.")
            
            # Display items in a grid
            for i in range(0, 20, 3):
                cols = st.columns(3)
                for j in range(3):
                    if i + j < len(final_df):
                        item = final_df[i+j]
                        with cols[j]:
                            if item['Image']:
                                st.image(item['Image'], width="stretch")
                            st.subheader(f"¥{item['Price (¥)']:,.0f}")
                            st.write(item['Name'][:50] + "...")
                            st.link_button("View on Rakuten", item['URL'])
        except Exception as e:
            st.error(f"Unexpected Error: {e}")
