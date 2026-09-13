"""
Bybit Open Interest API fetcher with retry logic and error handling.
"""

import requests
import pandas as pd
import time
from typing import Optional, Dict, Any
from datetime import datetime, timezone


class BybitOIFetcher:
    """
    Fetches historical Open Interest data from Bybit V5 API.
    
    Supports: linear, inverse, option categories
    Intervals: 5min, 15min, 30min, 1h, 4h, 1d
    """
    
    BASE_URL = "https://api.bybit.com/v5/market/open-interest"
    
    def __init__(self, 
                 max_retries: int = 3,
                 base_delay: float = 1.0,
                 rate_limit_delay: float = 0.1):
        """
        Args:
            max_retries: Maximum retry attempts for failed requests
            base_delay: Base delay for exponential backoff (seconds)
            rate_limit_delay: Delay between requests to respect rate limits
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.rate_limit_delay = rate_limit_delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Bybit-OI-Fetcher/1.0'
        })
    
    def _make_request(self, params: Dict[str, Any]) -> Optional[Dict]:
        """
        Make HTTP request with retry logic and exponential backoff.
        
        Args:
            params: Query parameters
            
        Returns:
            JSON response or None if failed
        """
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(self.BASE_URL, params=params, timeout=30)
                response.raise_for_status()
                
                data = response.json()
                
                if data.get("retCode") != 0:
                    error_msg = data.get('retMsg', 'Unknown error')
                    print(f"API error (attempt {attempt + 1}/{self.max_retries}): {error_msg}")
                    
                    if attempt < self.max_retries - 1:
                        delay = self.base_delay * (2 ** attempt)
                        print(f"   Retrying in {delay:.1f}s...")
                        time.sleep(delay)
                        continue
                    return None
                
                return data
                
            except requests.exceptions.RequestException as e:
                print(f"Network error (attempt {attempt + 1}/{self.max_retries}): {e}")
                
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2 ** attempt)
                    print(f"   Retrying in {delay:.1f}s...")
                    time.sleep(delay)
                    continue
                return None
        
        return None
    
    def fetch_open_interest(self, 
                           symbol: str,
                           interval: str = "30min",
                           category: str = "linear",
                           since: Optional[datetime] = None,
                           until: Optional[datetime] = None,
                           max_requests: int = 500) -> pd.DataFrame:
        """
        Fetch historical Open Interest data with automatic pagination.
        
        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            interval: Time interval (5min, 15min, 30min, 1h, 4h, 1d)
            category: Contract category (linear, inverse, option)
            since: Start datetime (UTC). If None, fetches all available
            until: End datetime (UTC). If None, fetches until latest
            max_requests: Maximum number of API requests to make
            
        Returns:
            DataFrame with columns: timestamp, oi_total, oi_single
        """
        # Ensure timezone awareness
        if since and since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        if until and until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        
        params = {
            "category": category,
            "symbol": symbol.upper(),
            "intervalTime": interval,
            "limit": 200
        }
        
        all_data = []
        cursor = None
        request_count = 0
        
        print(f"Fetching {symbol.upper()} OI ({interval})...")
        if since:
            print(f"   From: {since.strftime('%Y-%m-%d %H:%M')}")
        if until:
            print(f"   Until: {until.strftime('%Y-%m-%d %H:%M')}")
        
        while request_count < max_requests:
            if cursor:
                params["cursor"] = cursor
            
            response_data = self._make_request(params)
            
            if response_data is None:
                print("Failed to fetch data after all retries")
                break
            
            result = response_data.get("result", {})
            items = result.get("list", [])
            
            if not items:
                break
            
            all_data.extend(items)
            cursor = result.get("nextPageCursor")
            request_count += 1
            
            # Early termination: check if oldest data is older than 'since'
            if since and items:
                oldest_ts = pd.to_datetime(int(items[-1]['timestamp']), unit='ms', utc=True)
                if oldest_ts < since:
                    print(f"   Reached data older than 'since' at request #{request_count}")
                    break
            
            if request_count % 10 == 0:
                print(f"   Loaded {len(all_data)} bars (request #{request_count})")
            
            if not cursor:
                break
            
            time.sleep(self.rate_limit_delay)
        else:
            print(f"Reached max requests limit ({max_requests})")
        
        if not all_data:
            print("o data received")
            return pd.DataFrame()
        
        # Process data
        df = pd.DataFrame(all_data)
        
        df['timestamp'] = pd.to_datetime(
            df['timestamp'].astype(int), 
            unit='ms', 
            utc=True
        )
        df['oi_total'] = df['openInterest'].astype(float)
        df['oi_single'] = df['singleOpenInterest'].astype(float)
        
        # Sort chronologically and remove duplicates
        df = df.sort_values('timestamp').drop_duplicates('timestamp').reset_index(drop=True)
        
        # Filter by date range
        if since:
            df = df[df['timestamp'] >= since]
        if until:
            df = df[df['timestamp'] <= until]
        
        # Reset index after filtering
        df = df.reset_index(drop=True)
        
        # Select final columns
        df_final = df[['timestamp', 'oi_total', 'oi_single']]
        
        # Summary
        if df_final.empty:
            print("No data in requested date range")
            return pd.DataFrame()
        
        start_dt = df_final['timestamp'].iloc[0].strftime('%Y-%m-%d %H:%M')
        end_dt = df_final['timestamp'].iloc[-1].strftime('%Y-%m-%d %H:%M')
        
        print(f"Load completed")
        print(f"   Total bars: {len(df_final)}")
        print(f"   Period: {start_dt} → {end_dt}")
        print(f"   API requests: {request_count}")
        
        return df_final


def save_to_csv(df: pd.DataFrame, 
                symbol: str, 
                interval: str, 
                output_dir: str = "data") -> Optional[str]:
    """
    Save DataFrame to CSV file with automatic naming.
    
    Args:
        df: DataFrame to save
        symbol: Trading pair symbol
        interval: Time interval
        output_dir: Output directory path
        
    Returns:
        Path to saved file or None if failed
    """
    if df.empty:
        print("Empty DataFrame, nothing to save")
        return None
    
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    start = df['timestamp'].iloc[0].strftime('%Y%m%d')
    end = df['timestamp'].iloc[-1].strftime('%Y%m%d')
    
    filename = f"{symbol.upper()}_oi_{interval}_{start}_to_{end}.csv"
    filepath = os.path.join(output_dir, filename)
    
    df.to_csv(filepath, index=False)
    
    print(f"Saved: {filepath}")
    print(f"   Size: {os.path.getsize(filepath) / 1024:.1f} KB")
    
    return filepath