"""
extract_specs.py
Extracts computer hardware specifications from Japanese/English product description strings.

Usage:
    import pandas as pd
    from extract_specs import extract_specs

    df = pd.DataFrame({"combined": [item1_text, item2_text, ...]})
    result = extract_specs(df, text_column="combined")
    print(result)
"""

import re
import pandas as pd
from typing import Optional


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _search(pattern: str, text: str, flags: int = re.IGNORECASE) -> Optional[str]:
    """Return first captured group or None."""
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def _normalize_half(text: str) -> str:
    """Convert full-width digits/letters to half-width for easier parsing."""
    result = []
    for ch in text:
        cp = ord(ch)
        if 0xFF01 <= cp <= 0xFF5E:
            result.append(chr(cp - 0xFEE0))
        elif cp == 0x3000:
            result.append(' ')
        else:
            result.append(ch)
    return ''.join(result)


# ---------------------------------------------------------------------------
# Individual field extractors
# ---------------------------------------------------------------------------

def _extract_brand(text: str) -> Optional[str]:
    """Extract manufacturer brand."""
    patterns = [
        r'メーカー[名]?\s*[：:]\s*([\w\s]+?)(?:\n|　|　|,|型番)',
        r'(Lenovo|Dell|HP|ASUS|Acer|Toshiba|Fujitsu|Panasonic|NEC|Sony|Microsoft|Apple|MSI|Samsung)',
    ]
    for p in patterns:
        v = _search(p, text, re.IGNORECASE)
        if v:
            return v.strip()
    return None


def _extract_model(text: str) -> Optional[str]:
    """Extract model name/number."""
    patterns = [
        r'型番\s*[：:]\s*([\w\s\-]+?)(?:\n|　|CPU|メモリ|OS)',
        r'(ThinkPad\s+[\w\-]+)',
        r'(IdeaPad\s+[\w\-]+)',
        r'(Latitude\s+[\w\-]+)',
        r'(Inspiron\s+[\w\-]+)',
    ]
    for p in patterns:
        v = _search(p, text, re.IGNORECASE)
        if v:
            return v.strip()
    return None


def _extract_os(text: str) -> Optional[str]:
    """Extract operating system."""
    patterns = [
        r'OS\s*[：:]\s*(Windows\s*\d+\s*(?:Pro|Home|Professional)?\s*(?:64bit|32bit)?)',
        r'(Windows\s*1[01]\s*(?:Pro|Home|Professional)?\s*(?:64bit|32bit)?)',
        r'OS\s+(Windows\s*\d+)',
    ]
    for p in patterns:
        v = _search(p, text, re.IGNORECASE)
        if v:
            return v.strip()
    return None


def _extract_cpu(text: str) -> Optional[str]:
    """Extract full CPU description."""
    patterns = [
        r'CPU[製品名]*\s*[：:]\s*(intel\s+Core\s+[^\n\r,。]{3,60})',
        r'CPU\s+([\w\s\-]+?(?:GHz|MHz)[^\n,。]{0,30})',
        r'(Core\s+[i][3579][-\s]\d{4,5}[A-Z]*(?:\s*[\d.]+GHz)?)',
        r'(インテル\s+Core\s+[^\n,。]{5,40})',
    ]
    for p in patterns:
        v = _search(p, text, re.IGNORECASE)
        if v:
            return v.strip()
    return None


def _extract_cpu_gen(text: str) -> Optional[str]:
    """Extract CPU generation number."""
    patterns = [
        r'第\s*(\d+)\s*世代',
        r'(\d+)(?:st|nd|rd|th)\s*[Gg]en(?:eration)?',
        r'Core\s+[i][3579][-\s](\d)[\d]{3}',  # e.g. i5-8250 → gen 8
        r'8\d{3}[UHQ]',   # 8xxx series → gen 8
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            if p == r'Core\s+[i][3579][-\s](\d)[\d]{3}':
                return m.group(1)
            if p == r'8\d{3}[UHQ]':
                return '8'
            return m.group(1)
    # Infer from CPU model number
    cpu_series = re.search(r'(\d{4,5})[UHQ]', text)
    if cpu_series:
        series_str = cpu_series.group(1)
        gen = series_str[0] if len(series_str) == 4 else series_str[:2]
        try:
            gen_num = int(gen)
            if 1 <= gen_num <= 14:
                return str(gen_num)
        except ValueError:
            pass
    return None


def _extract_memory(text: str) -> Optional[str]:
    """Extract RAM size (must be a realistic laptop memory value)."""
    patterns = [
        r'メモリ[容量]?\s*[：:（(]?\s*(\d+)\s*GB',
        r'(?:RAM|メモリ|MEM)\s*[：:\s]+(\d+)\s*GB',
        r'メモリ\s+(\d+)GB',
        r'(\d+)GB\s*(?:\(スロット|DDR[34]|RAM)',
        r'(?:memory|RAM)[：:\s]+(\d+)\s*GB',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            try:
                size = int(m.group(1))
                if size in (2, 4, 8, 16, 32, 64):   # valid laptop memory sizes
                    return f"{size}GB"
            except ValueError:
                pass
    return None


def _extract_storage(text: str) -> dict:
    """Extract SSD and HDD sizes. Returns dict with keys 'ssd' and 'hdd'."""
    result = {'ssd': None, 'hdd': None}

    # SSD patterns
    ssd_patterns = [
        r'(?:新品\s*)?(?:M\.2\s*)?SSD\s*[：:\s]*(\d+)\s*(GB|TB)',
        r'容量[（(]SSD[）)]?\s*[：:]\s*(\d+)\s*(GB|TB)',
        r'SSD[：:\s]+(\d+)\s*(GB|TB)',
        r'(\d+)\s*(GB|TB)\s*(?:新品\s*)?(?:M\.2\s*)?SSD',
        r'NVMe[式]?\s*SSD\s*(\d+)\s*(GB)',
    ]
    for p in ssd_patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            size, unit = m.group(1), m.group(2).upper()
            result['ssd'] = f"{size}{unit}"
            break

    # HDD patterns (if no SSD or separate HDD)
    hdd_patterns = [
        r'HDD\s*[：:\s]*(\d+)\s*(GB|TB)',
        r'(\d+)\s*(GB|TB)\s*HDD',
    ]
    for p in hdd_patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            size, unit = m.group(1), m.group(2).upper()
            result['hdd'] = f"{size}{unit}"
            break

    return result


def _extract_display_size(text: str) -> Optional[str]:
    """Extract screen size in inches."""
    patterns = [
        r'(?:ディスプレイ|液晶|画面)[^0-9]*(\d+(?:\.\d+)?)\s*(?:型|インチ|inch)',
        r'(\d+(?:\.\d+)?)\s*(?:型|インチ|inch)\s*(?:ワイド|液晶|IPS|TN|FHD|HD)',
        r'(\d+(?:\.\d+)?)\s*(?:型|インチ)',
        r'(\d+(?:\.\d+)?)["\"]?\s*(?:inch|インチ)',
        r'(\d+(?:\.\d+)?)-inch',
    ]
    for p in patterns:
        v = _search(p, text, re.IGNORECASE)
        if v:
            try:
                size = float(v)
                if 10 <= size <= 20:  # Sanity check for laptop screens
                    return f"{size}インチ"
            except ValueError:
                pass
    return None


def _extract_resolution(text: str) -> Optional[str]:
    """Extract screen resolution."""
    patterns = [
        r'(\d{3,4}[×x×]\d{3,4})',
        r'(1920\s*[×x]\s*1080)',
        r'(1366\s*[×x]\s*768)',
        r'(2560\s*[×x]\s*1440)',
        r'(フルHD|Full\s*HD|FHD)',
        r'(HD)',
    ]
    for p in patterns:
        v = _search(p, text, re.IGNORECASE)
        if v:
            return v.replace('×', 'x').replace('ｘ', 'x')
    return None


def _extract_weight(text: str) -> Optional[str]:
    """Extract device weight."""
    patterns = [
        r'重[さ量][：:\s]*(\d+(?:\.\d+)?)\s*kg',
        r'(\d+(?:\.\d+)?)\s*kg\s*(?:程度|前後|約)?',
        r'weight[：:\s]*(\d+(?:\.\d+)?)\s*kg',
    ]
    for p in patterns:
        v = _search(p, text, re.IGNORECASE)
        if v:
            try:
                w = float(v)
                if 0.5 <= w <= 5.0:  # Laptop weight sanity check
                    return f"{v}kg"
            except ValueError:
                pass
    return None


def _extract_optical_drive(text: str) -> Optional[str]:
    """Extract optical drive info."""
    if re.search(r'光学[ドド]ライブ[：:\s]*(?:な[しい]|非搭載|無し|なし)', text):
        return "なし"
    if re.search(r'光学[ドド]ライブ[：:\s]*(DVD|CD|Blu[-\s]?ray)', text, re.IGNORECASE):
        m = re.search(r'光学[ドド]ライブ[：:\s]*(DVD[^\n,。]{0,30})', text, re.IGNORECASE)
        return m.group(1).strip() if m else "搭載"
    if re.search(r'(DVD|光学)', text, re.IGNORECASE):
        if re.search(r'DVD.*?(?:非搭載|なし|無し)', text, re.IGNORECASE):
            return "なし"
        return "搭載"
    return None


def _extract_wireless(text: str) -> Optional[str]:
    """Extract wireless LAN / WiFi info."""
    patterns = [
        r'(802\.11\s*[a-z/]+)',
        r'(Wireless[-\s]AC\s*\d+)',
        r'(WiFi|Wi-Fi|無線LAN)\s*[：:\(（]?\s*([^\n,。)）]{3,40})',
        r'(ac/a/b/g/n)',
    ]
    for p in patterns:
        v = _search(p, text, re.IGNORECASE)
        if v:
            return v.strip()
    if re.search(r'(WiFi|Wi-Fi|無線LAN)', text, re.IGNORECASE):
        return "搭載"
    return None


def _extract_bluetooth(text: str) -> Optional[str]:
    """Extract Bluetooth version."""
    patterns = [
        r'Bluetooth\s+(\d+\.\d+)',
        r'Bluetooth\s+([\d.]+)',
    ]
    for p in patterns:
        v = _search(p, text, re.IGNORECASE)
        if v:
            return f"Bluetooth {v}"
    if re.search(r'Bluetooth', text, re.IGNORECASE):
        return "搭載"
    return None


def _extract_webcam(text: str) -> Optional[str]:
    """Extract webcam / web camera info."""
    patterns = [
        r'(?:Web)?[Cc]amera\s*[：:]\s*([\w\s]+p)',
        r'Webカメラ\s*[：:]\s*([\w\s]+)',
        r'(HD\s*720p)',
        r'(1080p)',
    ]
    for p in patterns:
        v = _search(p, text, re.IGNORECASE)
        if v:
            return v.strip()
    if re.search(r'(Webカメラ|webcam|カメラ搭載)', text, re.IGNORECASE):
        return "搭載"
    return None


def _extract_usb_ports(text: str) -> Optional[str]:
    """Extract USB port configuration."""
    ports = []
    m = re.search(r'USB\s*3\.0\s*[×x×]\s*(\d+)', text, re.IGNORECASE)
    if m:
        ports.append(f"USB3.0×{m.group(1)}")
    m = re.search(r'USB\s*3\.1\s*Type[-\s]?C\s*[×x×]?\s*(\d+)', text, re.IGNORECASE)
    if m:
        ports.append(f"USB3.1 Type-C×{m.group(1)}")
    elif re.search(r'USB\s*Type[-\s]?C', text, re.IGNORECASE):
        ports.append("USB Type-C搭載")
    return ", ".join(ports) if ports else None


def _extract_warranty(text: str) -> Optional[str]:
    """Extract warranty period."""
    patterns = [
        r'保証期間[：:\s]*(\d+年間?|\d+ヶ?月間?)',
        r'(\d+年間?)(?:の)?(?:動作)?保証',
        r'保証[：:\s]*(\d+日間)',
        r'(90日間?)',
        r'(30日間?)',
    ]
    for p in patterns:
        v = _search(p, text)
        if v:
            return v.strip()
    return None


def _extract_office(text: str) -> Optional[str]:
    """Extract bundled office software."""
    patterns = [
        r'(Microsoft\s*Office\s*\d{4})',
        r'(MS\s*Office\s*\d{4})',
        r'(Office\s*\d{4})',
        r'(WPS\s*Office\s*\d+)',
        r'(WPS\s*Office)',
        r'付属オフィスソフト[：:\s]*([^\n,。]{3,20})',
    ]
    for p in patterns:
        v = _search(p, text, re.IGNORECASE)
        if v and 'なし' not in v and '非' not in v:
            return v.strip()
    if re.search(r'オフィスソフト[：:\s]*な[しい]|Officeなし|Office\s*非搭載', text, re.IGNORECASE):
        return "なし"
    return None


def _extract_wireless(text: str) -> Optional[str]:
    """Extract wireless LAN / WiFi info."""
    patterns = [
        r'(802\.11\s*[a-z/]{2,8})',
        r'(Wireless[-\s]AC\s*\d+)',
        r'(ac/a/b/g/n)',
    ]
    for p in patterns:
        v = _search(p, text, re.IGNORECASE)
        if v:
            return v.strip()
    if re.search(r'(WiFi|Wi-Fi|無線LAN)', text, re.IGNORECASE):
        return "搭載"
    return None


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

def extract_specs(
    df: pd.DataFrame,
    text_column: str = "combined",
    price_column: Optional[str] = "itemPrice",
    name_column: Optional[str] = "itemName",
) -> pd.DataFrame:
    """
    Extract hardware specs from product description strings.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe containing product listings.
    text_column : str
        Column name holding the combined product description text.
    price_column : str, optional
        Column name holding the item price (numeric).
    name_column : str, optional
        Column name holding the item name/title.

    Returns
    -------
    pd.DataFrame
        New dataframe with one row per product and extracted spec columns:
        brand, model, os, cpu, cpu_gen, memory, ssd, hdd, display_size,
        resolution, weight, optical_drive, wireless, bluetooth, webcam,
        usb_ports, warranty, office, price.
    """
    records = []

    for _, row in df.iterrows():
        raw = str(row.get(text_column, ""))
        text = _normalize_half(raw)

        storage = _extract_storage(text)

        rec = {
            # ── Identity ──────────────────────────────────────────────────
            "item_name":     str(row.get(name_column, ""))[:120] if name_column else None,
            "price":         row.get(price_column) if price_column else None,
            # ── Manufacturer & OS ─────────────────────────────────────────
            "brand":         _extract_brand(text),
            "model":         _extract_model(text),
            "os":            _extract_os(text),
            # ── CPU ───────────────────────────────────────────────────────
            "cpu":           _extract_cpu(text),
            "cpu_gen":       _extract_cpu_gen(text),
            # ── Memory & Storage ─────────────────────────────────────────
            "memory":        _extract_memory(text),
            "ssd":           storage['ssd'],
            "hdd":           storage['hdd'],
            # ── Display ──────────────────────────────────────────────────
            "display_size":  _extract_display_size(text),
            "resolution":    _extract_resolution(text),
            # ── Physical ─────────────────────────────────────────────────
            "weight":        _extract_weight(text),
            # ── Connectivity ─────────────────────────────────────────────
            "wireless":      _extract_wireless(text),
            "bluetooth":     _extract_bluetooth(text),
            "webcam":        _extract_webcam(text),
            "usb_ports":     _extract_usb_ports(text),
            # ── Drive & Extras ───────────────────────────────────────────
            "optical_drive": _extract_optical_drive(text),
            "office":        _extract_office(text),
            "warranty":      _extract_warranty(text),
        }
        records.append(rec)

    result = pd.DataFrame(records)

    # Reorder columns for readability
    ordered_cols = [
        "item_name", "price",
        "brand", "model", "os",
        "cpu", "cpu_gen",
        "memory", "ssd", "hdd",
        "display_size", "resolution", "weight",
        "wireless", "bluetooth", "webcam", "usb_ports",
        "optical_drive", "office", "warranty",
    ]
    # Only keep columns that exist
    ordered_cols = [c for c in ordered_cols if c in result.columns]
    return result[ordered_cols]


# ---------------------------------------------------------------------------
# Demo / test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Build a small sample dataframe from the provided product data
    sample_data = [
        {
            "itemName": "フルHD 15.6型 Lenovo ThinkPad L580 Core i7 8550U M.2SSD256G メモリ8G",
            "itemPrice": 36800,
            "combined": (
                "Windows11 Pro 64bit導入済みで第8世代Core i7搭載！ "
                "メーカー名 Lenovo 型番 Thinkpad L580 "
                "CPU 4コア8スレッド インテル Core i7 プロセッサー 8550U (動作周波数 1.80GHz〜4.00GHz) "
                "液晶 15.6型 フルHD IPS液晶 (1,920×1,080ドット) "
                "メモリ 8GB ストレージ M.2 SSD 256GB "
                "Webカメラ HD 720p Bluetooth 4.1 "
                "USB3.0 ×2 USB Type-C x2 "
                "OS Windows 11 Pro 64bit 導入済み "
                "重さ：2.0kg"
            ),
        },
        {
            "itemName": "Lenovo ThinkPad L590 15.6インチ 第8世代 Core i5 メモリ16GB SSD 256GB Office付き",
            "itemPrice": 32800,
            "combined": (
                "型番Lenovo ThinkPad L590 CPU第8世代 Core i5 "
                "画面15.6インチワイド (1,366x768) RAMDDR4 16GB SSD256GB "
                "OS Windows 11 Pro 64bit OfficeWPS Office 2 "
                "USB 3.0x2 USB 3.1 Type-Cx2 HDMI 出力x1 "
                "保証期間：商品お届け後 30日間"
            ),
        },
        {
            "itemName": "ThinkPad L580 Core i5 8250U MEM:16GB SSD:512GB 一年保証",
            "itemPrice": 31980,
            "combined": (
                "メーカーLenovo シリーズThinkPad L580 "
                "メモリ容量16GB 容量（SSD）512GB(新品換装済) "
                "CPU intel Core i5 8250U 1.6(〜最大3.4)GHz "
                "ディスプレイ15.6型ワイド HD(1366×768) "
                "OSWindows11Pro 64bit 保証期間1年間 "
                "光学ドライブ非搭載 無線LAN Bluetooth "
                "重さ：2.0kg"
            ),
        },
        {
            "itemName": "ThinkPad L580 Core i3 8130U メモリ8GB SSD256GB WPS Office付き",
            "itemPrice": 25800,
            "combined": (
                "Lenovo ThinkPad L580 OS Windows11 64ビット "
                "プロセッサ 第8世代Core i3 Office WPS Office "
                "メモリ（RAM） 8GB SSD：256GB "
                "ディスプレイ 15.6インチ 解像度 HD TN液晶1366×768ドット "
                "無線LAN 対応 Bluetooth 搭載 保証：1年間有効"
            ),
        },
        {
            "itemName": "訳有 ThinkPad L580 Core i7-8550U 8GB SSD512GB Windows11",
            "itemPrice": 16489,
            "combined": (
                "型番：Lenovo ThinkPad L580 "
                "CPU：高性能 第8世代Core i7-8550U 1.8Ghz、4コア8スレッド "
                "ハードディスク：爆速NVMe式 SSD 512GB "
                "メモリ：8GB "
                "ディスプレイ：15.6インチ 1366 x 768 "
                "USB3.x接続口 x2個 USB Type-C接続口 x2個 "
                "Webカメラ搭載 Bluetooth搭載 "
                "OS Windows11 Pro 64bit "
                "一部キー入力不良 バッテリー不良"
            ),
        },
    ]

    df = pd.DataFrame(sample_data)
    result = extract_specs(df, text_column="combined", price_column="itemPrice", name_column="itemName")

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_colwidth", 40)

    print("=" * 100)
    print("EXTRACTED SPECS")
    print("=" * 100)
    print(result.to_string(index=False))
    print()

    # Show as transposed view for the first item
    print("=" * 60)
    print("FIRST ITEM — DETAILED VIEW")
    print("=" * 60)
    for col in result.columns:
        val = result.iloc[0][col]
        print(f"  {col:<20}: {val}")
