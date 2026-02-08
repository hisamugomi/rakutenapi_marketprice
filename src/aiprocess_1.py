import polars as pl
from typing import Optional
from pydantic import BaseModel, Field
import streamlit as st
from langchain_ollama import ChatOllama
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import time

# ===== 1. OPTIMIZED SCHEMA (Simpler = Faster) =====
class LaptopSpecs(BaseModel):
    """Simplified schema - fewer fields = faster extraction"""
    brand: Optional[str] = Field(default=None, description="Manufacturer: Dell, Apple, Lenovo, etc.")
    cpu: Optional[str] = Field(default=None, description="CPU model: Core i5-8250U, Ryzen 5, etc.")
    ram_gb: Optional[int] = Field(default=None, description="RAM in GB as integer")
    storage_gb: Optional[int] = Field(default=None, description="Storage in GB as integer")
    storage_type: Optional[str] = Field(default=None, description="SSD, HDD, or eMMC")


# ===== 2. OPTIMIZED LLM CONFIGURATION =====
# Key changes:
# - num_ctx reduced to 1024 (default 2048) - faster processing
# - num_thread set to 4 (your i5-8250U has 4 cores, 8 threads)
# - temperature=0 for deterministic output
llm = ChatOllama(
    model="schroneko/gemma-2-2b-jpn-it:latest",
    temperature=0,
    num_ctx=1024,  # CRITICAL: Reduced context window = 2x faster
    num_thread=4,  # Match your CPU cores for optimal performance
    num_gpu=0,     # T480 doesn't have dedicated GPU
)

structured_llm = llm.with_structured_output(LaptopSpecs)


# ===== 3. PARALLEL BATCH PROCESSING =====
def extract_specs_parallel(names_batch: list[str], max_retries: int = 2) -> list[dict]:
    """
    Extract specs with retry logic and error handling
    
    Args:
        names_batch: List of product names
        max_retries: Number of retry attempts on failure
    
    Returns:
        List of extracted specs as dicts
    """
    for attempt in range(max_retries):
        try:
            # Batch processing with structured output
            results = structured_llm.batch(names_batch)
            return [item.model_dump() for item in results]
        
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"⚠️  Retry {attempt + 1}/{max_retries} due to: {e}")
                time.sleep(1)  # Brief pause before retry
            else:
                print(f"❌ Failed after {max_retries} attempts: {e}")
                # Return empty dicts for failed batch
                return [{} for _ in names_batch]


# ===== 4. MAIN PROCESSING FUNCTION (OPTIMIZED) =====
def extract_specs_process(
    input_csv: str,
    output_csv: str = "rakuten_enriched_fast.csv",
    batch_size: int = 3,  # REDUCED from 5 - better for 2B model
    max_workers: int = 2,  # Parallel batches (conservative for your RAM)
    sample_size: Optional[int] = None  # For testing: set to 50
):
    """
    Process CSV with parallel batch extraction
    
    Performance Tips:
    - batch_size=3: Optimal for Gemma 2B on your hardware
    - max_workers=2: Prevents RAM overflow (each worker ~4GB)
    - sample_size: Use 50-100 for testing before full run
    
    Args:
        input_csv: Path to input CSV
        output_csv: Path to save results
        batch_size: Items per LLM call (lower = more stable)
        max_workers: Parallel threads (2-3 recommended)
        sample_size: Limit rows for testing (None = process all)
    """
    
    # 1. Load data (Polars is already fast)
    print(f"📂 Loading {input_csv}...")
    df = pl.read_csv(input_csv)
    
    # Optional: Sample for testing
    if sample_size:
        df = df.head(sample_size)
        print(f"🧪 Testing with {sample_size} samples")
    
    print(f"📊 Processing {len(df)} items...")
    
    # 2. Extract product names
    names = df["combined"].to_list()
    
    # 3. Create batches
    batches = [
        names[i:i + batch_size] 
        for i in range(0, len(names), batch_size)
    ]
    
    print(f"🔢 Created {len(batches)} batches (size={batch_size})")
    
    # 4. Parallel processing with progress bar
    all_specs = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all batches
        futures = {
            executor.submit(extract_specs_parallel, batch): batch 
            for batch in batches
        }
        
        # Process results with progress bar
        with tqdm(total=len(batches), desc="🤖 Extracting specs") as pbar:
            for future in as_completed(futures):
                try:
                    batch_results = future.result()
                    all_specs.extend(batch_results)
                except Exception as e:
                    print(f"❌ Batch failed: {e}")
                    # Add empty dicts for failed batch
                    batch = futures[future]
                    all_specs.extend([{} for _ in batch])
                
                pbar.update(1)
    
    # 5. Merge results back to DataFrame
    print("🔗 Merging results...")
    specs_df = pl.from_dicts(all_specs)
    
    # Ensure specs_df has same length as original df
    if len(specs_df) != len(df):
        print(f"⚠️  Warning: Length mismatch! df={len(df)}, specs={len(specs_df)}")
    
    final_df = pl.concat([df, specs_df], how="horizontal")
    
    # 6. Save results
    final_df.write_csv(output_csv)
    print(f"✅ Done! Saved to {output_csv}")
    
    # 7. Show sample results
    print("\n📋 Sample extracted specs:")
    print(final_df.select(["itemName", "brand", "cpu", "ram_gb", "storage_gb"]).head(5))
    
    return final_df


# ===== 5. STREAMLIT INTEGRATION (OPTIONAL) =====
def streamlit_ui():
    """
    Streamlit UI for interactive extraction
    """
    st.title("🤖 Laptop Specs Extractor")
    st.markdown("### Optimized for T480 (i5-8250U, 32GB RAM)")
    
    uploaded_file = st.file_uploader("Upload CSV", type=['csv'])
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        batch_size = st.slider("Batch Size", 1, 5, 3, help="Items per LLM call")
    
    with col2:
        max_workers = st.slider("Parallel Workers", 1, 4, 2, help="More = faster but more RAM")
    
    with col3:
        sample_size = st.number_input("Sample Size (0=all)", 0, 10000, 0, step=50)
    
    if uploaded_file and st.button("🚀 Start Extraction", type="primary"):
        
        with st.spinner("Processing..."):
            # Save uploaded file temporarily
            temp_path = f"/tmp/{uploaded_file.name}"
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            # Run extraction
            try:
                result_df = extract_specs_process(
                    input_csv=temp_path,
                    batch_size=batch_size,
                    max_workers=max_workers,
                    sample_size=sample_size if sample_size > 0 else None
                )
                
                st.success("✅ Extraction complete!")
                st.dataframe(result_df.head(20))
                
                # Download button
                csv_data = result_df.write_csv()
                st.download_button(
                    "📥 Download Results",
                    csv_data,
                    "extracted_specs.csv",
                    "text/csv"
                )
                
            except Exception as e:
                st.error(f"❌ Error: {e}")


# ===== 6. COMMAND-LINE EXECUTION =====
if __name__ == "__main__":
    
    # Option A: Test with 50 samples first
    print("🧪 Running TEST MODE (50 samples)...")
    extract_specs_process(
        input_csv="/home/hisamu/Downloads/Coding/Python/streamlitdir/rakuten_used_computer_finder/rakutenapidata_L3902026-02-08 21:10.csv",
        output_csv="rakuten_test_results.csv",
        batch_size=3,
        max_workers=2
        # sample_size=50  # TEST FIRST!
    )
    
    # Option B: Full processing (uncomment after testing)
    # print("🚀 Running FULL MODE...")
    # extract_specs_process(
    #     input_csv="/home/hisamu/Downloads/Coding/Python/streamlitdir/rakuten_used_computer_finder/rakutenapidata_T4902026-02-07 16:27.csv",
    #     output_csv="rakuten_enriched_fast.csv",
    #     batch_size=3,
    #     max_workers=2,
    #     sample_size=None
    # )