
import pandas as pd
from typing import Optional
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
import streamlit as st

# 1. Define the Schema (The "Desired Columns")
class LaptopSpecs(BaseModel):
    brand: Optional[str] = Field(description="The manufacturer, e.g., Dell, Apple, Lenovo")
    cpu: Optional[str] = Field(description="The CPU model, e.g., Core i5-1030NG7, Ryzen 5 5600U")
    ram_gb: Optional[int] = Field(description="RAM size in GB as an integer, e.g., 16")
    storage_gb: Optional[int] = Field(description="Storage size in GB as an integer, e.g., 512")
    storage_type: Optional[str] = Field(description="SSD, HDD, or eMMC")
    screen_size_inch: Optional[float] = Field(description="Screen size in inches, e.g., 15.6")
    weight: Optional[float] = Field(description="How heavy the laptop is, e.g., 500")
    
    
# 2. Initialize Gemini via LangChain
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0, google_api_key=st.secrets["GOOGLE_API_KEY"]) # This line fixes the error)
structured_llm = llm.with_structured_output(LaptopSpecs)

# 3. Extraction Function
def extract_specs(text):
    try:
        # We pass the cleaned text directly to the model
        result = structured_llm.invoke(text)
        return result.dict()
    except Exception as e:
        print(f"Error extracting: {e}")
        return {}

# 4. Running it on your DataFrame
# Let's say your CSV has a column 'itemName_clean'
# df = pd.read_csv("rakuten_data.csv")
# specs_df = df['itemName_clean'].apply(extract_specs).apply(pd.Series)
# final_df = pd.concat([df, specs_df], axis=1)