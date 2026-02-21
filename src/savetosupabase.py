import os
from supabase import create_client, Client

# Initialize Supabase Client
# url: str = os.environ.get("")
# key: str = os.environ.get("SUPABASE_KEY")


# if "SUPABASE_URL" in st.secrets:
#     SUPABASE_URL = st.secrets["SUPABASE_URL"]

# if "SUPABASE_KEY" in st.secrets:
#     SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

# supabase: Client = create_client(url, key)

def save_to_supabase(data_list):
    """
    data_list: A list of dictionaries (from your Polars/Scraper output)
    """
    try:
        # .insert() handles multiple rows at once
        response = supabase.table("listings").insert(data_list).execute()
        return response
    except Exception as e:
        print(f"Database Error: {e}")