import polars as pl
import pandas as pd
from typing import Optional
from pydantic import BaseModel, Field
# from langchain_google_genai import ChatGoogleGenerativeAI
import streamlit as st

from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# 1. Initialize the Model
# 'llama3.2' is a great balance of speed and intelligence for local machines.

# 2. Define a Prompt Template
# This acts as the "Instruction Set" for your AI.

# 3. Create the Chain (The Pipeline)
# The '|' symbol "pipes" data from one stage to the next.


# # 1. Define the Schema (The "Desired Columns")
class LaptopSpecs(BaseModel):
    brand: Optional[str] = Field(description="The manufacturer, e.g., Dell, Apple, Lenovo")
    cpu: Optional[str] = Field(description="The CPU model, e.g., Core i5-1030NG7, Ryzen 5 5600U")
    ram_gb: Optional[int] = Field(description="RAM size in GB as an integer, e.g., 16")
    storage_gb: Optional[int] = Field(description="Storage size in GB as an integer, e.g., 512")
    storage_type: Optional[str] = Field(description="SSD, HDD, or eMMC")
    screen_size_inch: Optional[float] = Field(description="Screen size in inches, e.g., 15.6")
    weight: Optional[float] = Field(description="How heavy the laptop is, e.g., 500")
    
    
# # 2. Initialize Gemini via LangChain
# llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0, google_api_key=st.secrets["GOOGLE_API_KEY"]) # This line fixes the error)
# structured_llm = llm.with_structured_output(LaptopSpecs)

llm = ChatOllama(
    model="schroneko/gemma-2-2b-jpn-it:latest",
    temperature=0,
    # base_url="http://localhost:11434" # Defaults to this; change if using Docker network
)
structured_llm = llm.with_structured_output(LaptopSpecs)



# # 3. Extraction Function
def extract_specs(names_list):
    try:
        # We pass the cleaned text directly to the model
        result = structured_llm.batch(names_list)
        return [item.model_dump() for item in result]
    except Exception as e:
        print(f"Error extracting: {e}")
        return {}

# chain = prompt | llm | StrOutputParser()


# # 4. Running it on your DataFrame
# # Let's say your CSV has a column 'itemName_clean'
def extractspecsprocess():

    df = pl.read_csv("/home/hisamu/Downloads/Coding/Python/streamlitdir/rakuten_used_computer_finder/rakutenapidata_T4902026-02-07 16:27.csv")
    print(df.head())

    batch_size = 5
    names = df["itemName"].to_list()
    all_specs = []

    for i in range(0, len(names), batch_size):
        batch = names[i : i + batch_size]
        batch_results = extract_specs(batch)
        all_specs.extend(batch_results)

    # 4. Merge back and save
    specs_df = pl.from_dicts(all_specs)
    final_df = pl.concat([df, specs_df], how="horizontal")

    final_df.write_csv("rakuten_enriched_fast.csv")
    print("✅ Done!")



extractspecsprocess()