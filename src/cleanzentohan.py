import jaconv
import re

def clean_japanese_specs(text):
    # 1. Convert Full-width to Half-width (１６ -> 16, ｉ７ -> i7)
    # kana=False keeps Katakana as is, but converts numbers and letters
    text = jaconv.z2h(text, kana=False, digit=True, ascii=True)
    
    # 2. Lowercase for consistency
    text = text.lower()

    # 3. Replace common Japanese units with English counterparts
    replacements = {
        r'ギガ': 'gb',
        
        r'テラ': 'tb',
        r'インチ': 'inch',
        r'コア': 'core',
        r'スレッド': 'thread',
        r'世代': 'gen',
    }
    
    for jp_unit, en_unit in replacements.items():
        text = re.sub(jp_unit, en_unit, text)
        
    # 4. Clean up weird spacing (Optional but recommended)
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

# --- Test with your sample data ---
# sample = "画面サイズ：15.6インチメモリ：8/16G/32GSSD：128GB~2048GB"
# cleaned = clean_japanese_specs(sample)
# print(f"Original: {sample}")
# print(f"Cleaned : {cleaned}")
# Result: 画面サイズ:15.6inchメモリ:8/16g/32gssd:128gb~2048gbr