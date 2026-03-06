"""
Realistic Rakuten API rows for unit tests.

Schema matches the full DataFrame that extract_specs() receives:
  raw columns from fetch_rakuten_items() +
  combined / scraped_at / is_active / search_query added by scraper.py

Each entry has:
  "row"      - the input dict (one DataFrame row)
  "expected" - verified against the actual extractor output
               (run: uv run python -m pytest tests/ -v to confirm)

All expected values were verified by running the real extractor functions.
Notes on regex behaviour are inline where non-obvious.
"""
from __future__ import annotations

SCRAPED_AT = "2026-02-21T10:00:00+09:00"

ROWS = [
    # ── 1. L580 i7-8550U — JP CPU format, full spec block ────────────────────
    {
        "row": {
            "itemCode":     "pcshop:l580-i7-001",
            "itemName":     "Lenovo ThinkPad L580 Core i7-8550U 8GB SSD256GB Win11",
            "itemCaption": (
                "メーカー名 Lenovo 型番 ThinkPad L580 "
                "CPU インテル® Core™ i7-8550U プロセッサー (1.80GHz〜4.00GHz) "
                "液晶 15.6型 フルHD IPS液晶 "
                "メモリ 8GB  M.2 SSD 256GB "
                "OS Windows 11 Pro 64bit "
                "Webカメラ HD 720p  Bluetooth 4.1 "
                "USB3.0 ×2  USB Type-C x2 "
                "重さ：2.0kg  保証期間1年間"
            ),
            "itemPrice":    32800,
            "itemUrl":      "https://item.rakuten.co.jp/pcshop/l580-i7-001",
            "genreId":      "100040",
            "shopName":     "PCショップA",
            "is_active":    True,
            "scraped_at":   SCRAPED_AT,
            "search_query": "L580 -lenovo",
        },
        "expected": {
            "brand":  "Lenovo",
            "cpu":    "インテル® Core™ i7-8550U プロセッサー (1.80GHz〜4.00GHz)",
            "memory": "8GB",
            "ssd":    "256GB",
            "hdd":    None,
            "os":     "Windows 11 Pro 64bit",
        },
    },

    # ── 2. L580 i5-8250U — EN CPU format, NVMe 512GB, 16GB ───────────────────
    # Note: "メモリ 16GB" (no 容量) is required for regex to match.
    {
        "row": {
            "itemCode":     "recpc:l580-i5-002",
            "itemName":     "ThinkPad L580 Core i5 8250U 16GB NVMe SSD512GB Windows11 Pro",
            "itemCaption": (
                "型番：Lenovo ThinkPad L580 "
                "CPU：第8世代 Core i5-8250U 1.6GHz 4コア8スレッド "
                "メモリ 16GB  爆速NVMe式 SSD 512GB(新品換装済) "
                "ディスプレイ：15.6インチ 1366 x 768 "
                "OS Windows 11 Pro 64bit  テンキー  Bluetooth搭載 "
                "USB3.0 x2  USB Type-C接続口 x2個 "
                "重さ：2.0kg"
            ),
            "itemPrice":    38500,
            "itemUrl":      "https://item.rakuten.co.jp/recpc/l580-i5-002",
            "genreId":      "100040",
            "shopName":     "リサイクルPC館",
            "is_active":    True,
            "scraped_at":   SCRAPED_AT,
            "search_query": "L580 -lenovo",
        },
        "expected": {
            "brand":  "Lenovo",
            "cpu":    "Core i5 8250U",
            "memory": "16GB",
            "ssd":    "512GB",
            "hdd":    None,
            # itemName has "Windows11 Pro" (no space) — regex matches it first
            "os":     "Windows11 Pro",
        },
    },

    # ── 3. L590 i5-8265U — DDR4 prefix memory format ─────────────────────────
    {
        "row": {
            "itemCode":     "ecopc:l590-i5-003",
            "itemName":     "Lenovo ThinkPad L590 Core i5-8265U 8GB SSD256GB WPS Office Win11",
            "itemCaption": (
                "型番Lenovo ThinkPad L590  CPU第8世代 Core i5 "
                "画面15.6インチワイド (1,366x768)  RAMDDR4 8GB  SSD256GB "
                "OS Windows 11 Pro 64bit  WPS Office 2 "
                "USB 3.0x2  USB 3.1 Type-Cx2  テンキー "
                "保証期間：30日間  光学ドライブ非搭載"
            ),
            "itemPrice":    28800,
            "itemUrl":      "https://item.rakuten.co.jp/ecopc/l590-i5-003",
            "genreId":      "100040",
            "shopName":     "エコPCショップ",
            "is_active":    True,
            "scraped_at":   SCRAPED_AT,
            "search_query": "L590 -lenovo",
        },
        "expected": {
            "brand":  "Lenovo",
            "memory": "8GB",
            "ssd":    "256GB",
            "hdd":    None,
            "os":     "Windows 11 Pro 64bit",
        },
    },

    # ── 4. L390 13.3" — compact form factor, メモリ prefix ────────────────────
    {
        "row": {
            "itemCode":     "usedpc:l390-i7-004",
            "itemName":     "ThinkPad L390 Core i7 8550U 8GB SSD512GB 13.3型 Win11 Pro",
            "itemCaption": (
                "メーカー：Lenovo シリーズ：ThinkPad L390 "
                "CPU：インテル Core i7 プロセッサー 8550U (1.80GHz〜4.00GHz) "
                "メモリ 8GB  M.2 SSD 512GB "
                "ディスプレイ 13.3インチ FHD IPS "
                "OS Windows 11 Pro 64bit "
                "Bluetooth 4.1  Webカメラ搭載 "
                "重さ：1.49kg  保証1年間"
            ),
            "itemPrice":    34900,
            "itemUrl":      "https://item.rakuten.co.jp/usedpc/l390-i7-004",
            "genreId":      "100040",
            "shopName":     "中古PC専門店",
            "is_active":    True,
            "scraped_at":   SCRAPED_AT,
            "search_query": "L390 -lenovo",
        },
        "expected": {
            "brand":  "Lenovo",
            "memory": "8GB",
            "ssd":    "512GB",
            "hdd":    None,
            "os":     "Windows 11 Pro 64bit",
        },
    },

    # ── 5. Dell Latitude 5300 i5-8265U — 13" compact Dell ────────────────────
    {
        "row": {
            "itemCode":     "junkpc:lat5300-005",
            "itemName":     "Dell Latitude 5300 Core i5-8265U 8GB SSD256GB 13.3型 Win11",
            "itemCaption": (
                "メーカー Dell  型番 Latitude 5300 "
                "CPU intel Core i5-8265U 1.60GHz (最大3.90GHz) "
                "液晶 13.3型ワイド フルHD (1920×1080) "
                "メモリ 8GB  SSD：256GB "
                "OS Windows11 Pro 64bit "
                "Bluetooth 5.0  Webカメラ：HD 720p "
                "USB3.0 ×2  USB Type-C ×1 "
                "重さ：1.36kg"
            ),
            "itemPrice":    22800,
            "itemUrl":      "https://item.rakuten.co.jp/junkpc/lat5300-005",
            "genreId":      "100040",
            "shopName":     "ジャンクPC堂",
            "is_active":    True,
            "scraped_at":   SCRAPED_AT,
            "search_query": "Latitude 5300 -dell",
        },
        "expected": {
            "brand":  "Dell",
            "memory": "8GB",
            "ssd":    "256GB",
            "hdd":    None,
            "os":     "Windows11 Pro 64bit",
        },
    },

    # ── 6. Dell Latitude 5400 i5-8365U — 16GB, 容量（SSD）pattern ────────────
    # Note: "容量（SSD）512GB" matches _RE_SSD2; "メモリ 16GB" for memory.
    {
        "row": {
            "itemCode":     "pcland:lat5400-006",
            "itemName":     "Dell Latitude 5400 Core i5-8365U 16GB SSD512GB 14型 FHD Win11",
            "itemCaption": (
                "型番 Dell Latitude 5400 "
                "CPU Core i5-8365U 1.60GHz Quad-Core "
                "メモリ 16GB  容量（SSD）512GB "
                "液晶 14.0インチ フルHD (1920×1080) IPS "
                "OS Windows 11 Pro 64bit "
                "USB 3.1 Type-C×1  USB3.0×2 "
                "Bluetooth 5.0  HDカメラ搭載 "
                "重さ 1.58kg  保証期間90日"
            ),
            "itemPrice":    39800,
            "itemUrl":      "https://item.rakuten.co.jp/pcland/lat5400-006",
            "genreId":      "100040",
            "shopName":     "PCランド",
            "is_active":    True,
            "scraped_at":   SCRAPED_AT,
            "search_query": "Latitude 5400 -dell",
        },
        "expected": {
            "brand":  "Dell",
            "memory": "16GB",
            "ssd":    "512GB",
            "hdd":    None,
            "os":     "Windows 11 Pro 64bit",
        },
    },

    # ── 7. Dell Latitude 5490 i7-8650U — Intel® EN format ────────────────────
    {
        "row": {
            "itemCode":     "netshop:lat5490-007",
            "itemName":     "Dell Latitude 5490 Core i7-8650U 8GB SSD256GB 14インチ Win11 Pro",
            "itemCaption": (
                "メーカー名：Dell  品番：Latitude 5490 "
                "CPU：Intel® Core™ i7-8650U (1.90GHz, 最大4.20GHz) "
                "メモリ 8GB (8GB×1) DDR4  SSD 256GB (M.2 NVMe) "
                "ディスプレイ 14.0型 (1920×1080) FHD "
                "OS：Windows 11 Pro 64bit "
                "Bluetooth 4.2  Webカメラ：720p "
                "USB3.1 Type-C×1  USB3.0×2 "
                "重さ：1.63kg"
            ),
            "itemPrice":    31500,
            "itemUrl":      "https://item.rakuten.co.jp/netshop/lat5490-007",
            "genreId":      "100040",
            "shopName":     "ネットPC",
            "is_active":    True,
            "scraped_at":   SCRAPED_AT,
            "search_query": "Latitude 5490 -dell",
        },
        "expected": {
            "brand":  "Dell",
            "memory": "8GB",
            "ssd":    "256GB",
            "hdd":    None,
            "os":     "Windows 11 Pro 64bit",
        },
    },

    # ── 8. Dell Latitude 5490 i5-8250U — HDD ONLY (no SSD) ───────────────────
    # Older listing with spinning hard drive — verifies ssd=None, hdd is captured.
    {
        "row": {
            "itemCode":     "oldpc:lat5490-hdd-008",
            "itemName":     "Dell Latitude 5490 Core i5-8250U 8GB HDD500GB 14型 Win10",
            "itemCaption": (
                "メーカー：Dell  型番：Latitude 5490 "
                "CPU：Core i5-8250U 1.60GHz 4コア8スレッド "
                "メモリ 8GB  HDD 500GB "
                "液晶：14.0型 FHD (1920×1080) "
                "OS Windows 10 Pro 64bit "
                "Bluetooth 4.2  Webカメラ搭載 "
                "USB3.0×2  USB Type-C×1 "
                "重さ：1.63kg  保証なし"
            ),
            "itemPrice":    12800,
            "itemUrl":      "https://item.rakuten.co.jp/oldpc/lat5490-hdd-008",
            "genreId":      "100040",
            "shopName":     "オールドPC",
            "is_active":    True,
            "scraped_at":   SCRAPED_AT,
            "search_query": "Latitude 5490 -dell",
        },
        "expected": {
            "brand":  "Dell",
            "memory": "8GB",
            "ssd":    None,       # ← no SSD in this listing
            "hdd":    "500GB",    # ← HDD only
            "os":     "Windows 10 Pro 64bit",
        },
    },

    # ── 9. Dell Latitude 5500 — dual storage: SSD + HDD ─────────────────────
    {
        "row": {
            "itemCode":     "greenpc:lat5500-009",
            "itemName":     "Dell Latitude 5500 Core i5-8265U 8GB SSD256GB HDD1TB 15.6型 Win11",
            "itemCaption": (
                "型番：Dell Latitude 5500 "
                "CPU：Core i5-8265U 1.60GHz 4コア "
                "メモリ：8GB  SSD：256GB  HDD：1TB "
                "液晶：15.6型ワイド FHD (1920×1080) "
                "OS：Windows 11 Pro 64bit "
                "Bluetooth 5.0  Webカメラ：720p HD "
                "USB3.0×2  USB3.1 Type-C×1 "
                "重さ：1.95kg  保証：3ヶ月"
            ),
            "itemPrice":    26800,
            "itemUrl":      "https://item.rakuten.co.jp/greenpc/lat5500-009",
            "genreId":      "100040",
            "shopName":     "グリーンPC",
            "is_active":    True,
            "scraped_at":   SCRAPED_AT,
            "search_query": "Latitude 5500 -dell",
        },
        "expected": {
            "brand":  "Dell",
            "memory": "8GB",
            "ssd":    "256GB",
            "hdd":    "1TB",
            "os":     "Windows 11 Pro 64bit",
        },
    },

    # ── 10. Dell Latitude 5590 i7-8850H — 6-core JP format ───────────────────
    # Note: CPU regex stops at closing ')'; text outside parens is not captured.
    {
        "row": {
            "itemCode":     "maxpc:lat5590-010",
            "itemName":     "Dell Latitude 5590 Core i7-8850H 16GB SSD512GB 15.6型 Win11 Pro",
            "itemCaption": (
                "メーカー名 Dell  型番 Latitude 5590 "
                "CPU インテル® Core™ i7-8850H プロセッサー (2.60GHz〜4.30GHz) 6コア12スレッド "
                "メモリ 16GB (8GB×2) DDR4  M.2 SSD 512GB (NVMe) "
                "ディスプレイ 15.6型 フルHD IPS (1920×1080) "
                "OS Windows 11 Pro 64bit "
                "Bluetooth 4.2  Webカメラ：HD 720p "
                "USB3.0×3  USB3.1 Type-C×1 "
                "重さ：1.98kg  保証1年間"
            ),
            "itemPrice":    49800,
            "itemUrl":      "https://item.rakuten.co.jp/maxpc/lat5590-010",
            "genreId":      "100040",
            "shopName":     "マックスPC",
            "is_active":    True,
            "scraped_at":   SCRAPED_AT,
            "search_query": "Latitude 5590 -dell",
        },
        "expected": {
            "brand":  "Dell",
            # Regex stops at ')' — "6コア12スレッド" after paren is not captured
            "cpu":    "インテル® Core™ i7-8850H プロセッサー (2.60GHz〜4.30GHz)",
            "memory": "16GB",
            "ssd":    "512GB",
            "hdd":    None,
            "os":     "Windows 11 Pro 64bit",
        },
    },
]
