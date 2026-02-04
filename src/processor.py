import pandas as pd

def process_results(json_data):
    """
    Parses Rakuten JSON response into a list of dictionaries.
    """
    if not json_data or 'Items' not in json_data:
        return []

    processed_list = []
    for item_wrapper in json_data['Items']:
        item = item_wrapper['Item']
        processed_list.append({
            "Name": item.get("itemName"),
            "Price (¥)": item.get("itemPrice"),
            "Shop": item.get("shopName"),
            "URL": item.get("itemUrl"),
            "Image": item.get("mediumImageUrls")[0].get("imageUrl") if item.get("mediumImageUrls") else None,
            "Description": item.get("itemCaption")[:100] + "..." # Truncated
        })
    
    return processed_list