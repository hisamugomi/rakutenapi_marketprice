import re
from typing import Dict, Optional

class SpecExtractor:
    """Extract computer specs from text using regex"""
    
    # CPU patterns
    CPU_PATTERNS = [
        r'(core\s*i[3579][-\s]*\d{4,5}[a-z]*)',
        r'(core\s*i[3579])',  # Generic Core iN
        r'(ryzen\s*[3579]\s*\d{4}[a-z]*)',
        r'(ryzen\s*[3579])',   # Generic Ryzen N
        r'(celeron|pentium|atom)[\s-]*\w*',
        r'(m1|m2|m3)[\s]*(pro|max|ultra)?',
        r'(xeon)[\s-]*\w*'
    ]
    
    # Memory patterns
    MEMORY_PATTERNS = [
        r'(\d+)\s*gb[\s]*(ram|メモリ|memory)',
        r'(ram|メモリ|memory)[\s:：]*(\d+)\s*gb',
        r'[\s-](\d+)\s*gb'  # Generic GB mismatch
    ]
    
    # Storage patterns
    STORAGE_PATTERNS = [
        r'(ssd|hdd)[\s:：]*(\d+)\s*(gb|tb)',
        r'(\d+)\s*(gb|tb)[\s]*(ssd|hdd)'
    ]
    
    # Brand keywords
    BRANDS = {
        'dell': 'Dell',
        'デル': 'Dell',
        'lenovo': 'Lenovo',
        'レノボ': 'Lenovo',
        'hp': 'HP',
        'asus': 'ASUS',
        'acer': 'Acer',
        'fujitsu': 'Fujitsu',
        '富士通': 'Fujitsu',
        'nec': 'NEC',
        'panasonic': 'Panasonic',
        'パナソニック': 'Panasonic',
        'dynabook': 'Dynabook',
        'vaio': 'VAIO',
        'apple': 'Apple',
        'macbook': 'Apple',
        'mac': 'Apple',
        'thinkpad': 'Lenovo',
        'latitude': 'Dell',
        'inspiron': 'Dell',
        'elitebook': 'HP',
        'probook': 'HP',
        'surface': 'Microsoft'
    }
    
    # Condition keywords (Order matters for priority)
    CONDITIONS = {
        '美品': 'Excellent',
        'ランクa': 'Excellent',
        'ランクb': 'Good',
        '動作確認済': 'Good',
        '新品ssd': None, # Ignore "New SSD" as condition
        '新品': 'New',
        '未使用': 'Unused',
        '中古': 'Used',
        'ランクc': 'Fair',
        'ジャンク': 'Junk',
        '傷あり': 'Fair',
    }
    
    def extract(self, text: str) -> Dict:
        """Extract all specs from text"""
        if not text:
             return {
                'cpu': None, 'cpu_generation': None, 'memory_gb': None,
                'storage_type': None, 'storage_gb': None, 'brand': None,
                'condition': None, 'screen_size': None
            }
        
        text_lower = text.lower()
        
        specs = {
            'cpu': self._extract_cpu(text_lower),
            'cpu_generation': None,
            'memory_gb': self._extract_memory(text_lower),
            'storage_type': None,
            'storage_gb': None,
            'brand': self._extract_brand(text_lower),
            'condition': self._extract_condition(text_lower),
            'screen_size': self._extract_screen_size(text_lower)
        }
        
        # Extract storage
        storage = self._extract_storage(text_lower)
        if storage:
            specs['storage_type'] = storage['type']
            specs['storage_gb'] = storage['size']
        
        # Extract CPU generation
        if specs['cpu']:
            specs['cpu_generation'] = self._extract_cpu_generation(specs['cpu'])
        
        return specs
    
    def _extract_cpu(self, text: str) -> Optional[str]:
        """Extract CPU model"""
        for pattern in self.CPU_PATTERNS:
            match = re.search(pattern, text)
            if match:
                return match.group(0).strip().upper()
        return None
    
    def _extract_cpu_generation(self, cpu: str) -> Optional[int]:
        """Extract CPU generation (e.g., 8 from i5-8250U)"""
        if not cpu: return None
        
        match = re.search(r'i[3579][-\s]*(\d)', cpu, re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        # Ryzen generation
        match = re.search(r'ryzen\s*[3579]\s*(\d)', cpu, re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        return None
    
    def _extract_memory(self, text: str) -> Optional[int]:
        """Extract RAM size in GB"""
        for pattern in self.MEMORY_PATTERNS:
            matches = re.finditer(pattern, text)
            for match in matches:
                # Find the group that has the digit
                val = None
                for g in match.groups():
                    if g and g.isdigit():
                        val = int(g)
                        break
                
                # Heuristic: RAM is usually <= 128GB
                # Storage is usually >= 120GB (except old ones, but loose filter helps)
                if val and 0 < val <= 128:
                    return val
        return None
    
    def _extract_storage(self, text: str) -> Optional[Dict]:
        """Extract storage type and size"""
        for pattern in self.STORAGE_PATTERNS:
            match = re.search(pattern, text)
            if match:
                groups = match.groups()
                
                # Find type (SSD/HDD)
                storage_type = next((g.upper() for g in groups if g and g.lower() in ['ssd', 'hdd']), None)
                
                # Find size
                size = None
                unit = None
                for g in groups:
                    if g and g.isdigit():
                        size = int(g)
                    elif g and g.lower() in ['gb', 'tb']:
                        unit = g.lower()
                
                if storage_type and size and unit:
                    # Convert TB to GB
                    if unit == 'tb':
                        size *= 1024
                    
                    return {'type': storage_type, 'size': size}
        
        return None
    
    def _extract_brand(self, text: str) -> Optional[str]:
        """Extract brand"""
        for keyword, brand in self.BRANDS.items():
            if keyword in text:
                return brand
        return None
    
    def _extract_condition(self, text: str) -> Optional[str]:
        """Extract condition"""
        for keyword, condition in self.CONDITIONS.items():
            if keyword in text:
                if condition is None:
                    continue
                return condition
        return None
    
    def _extract_screen_size(self, text: str) -> Optional[float]:
        """Extract screen size in inches"""
        match = re.search(r'(\d+\.?\d*)\s*(インチ|inch|")', text)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None
