"""
Main entry point for fetching Bybit Open Interest data.
"""

from datetime import datetime, timezone
from fetcher import BybitOIFetcher, save_to_csv


def main():
    """Main execution function."""
    
    # Configuration
    SYMBOL = "BTCUSDT"
    INTERVAL = "1h"  # Options: 5min, 15min, 30min, 1h, 4h, 1d
    CATEGORY = "linear"  # Options: linear, inverse, option
    OUTPUT_DIR = "data"
    
    # Date range (UTC)
    SINCE = datetime(2026, 1, 1, tzinfo=timezone.utc)
    UNTIL = datetime(2026, 1, 3, tzinfo=timezone.utc)
    
    # Initialize fetcher with retry settings
    fetcher = BybitOIFetcher(
        max_retries=3,
        base_delay=1.0,
        rate_limit_delay=0.1
    )
    
    # Fetch data
    df_oi = fetcher.fetch_open_interest(
        symbol=SYMBOL,
        interval=INTERVAL,
        category=CATEGORY,
        since=SINCE,
        until=UNTIL,
        max_requests=500
    )
    
    # Save results
    if not df_oi.empty:
        print("\n" + "=" * 60)
        print("VERIFICATION")
        print("=" * 60)
        print(f"Symbol:      {SYMBOL}")
        print(f"Interval:    {INTERVAL}")
        print(f"Category:    {CATEGORY}")
        print(f"Requested:   {SINCE.strftime('%Y-%m-%d %H:%M')} → {UNTIL.strftime('%Y-%m-%d %H:%M')}")
        print(f"Actual:      {df_oi['timestamp'].iloc[0].strftime('%Y-%m-%d %H:%M')} → {df_oi['timestamp'].iloc[-1].strftime('%Y-%m-%d %H:%M')}")
        print(f"Total bars:  {len(df_oi)}")
        print(f"OI range:    {df_oi['oi_total'].min():.2f} → {df_oi['oi_total'].max():.2f}")
        print("=" * 60 + "\n")
        
        print(df_oi.head(10))
        print("...")
        print(df_oi.tail(10))
        
        # Save to CSV
        save_to_csv(df_oi, SYMBOL, INTERVAL, OUTPUT_DIR)
    else:
        print("\nNo data to process")


if __name__ == "__main__":
    main()