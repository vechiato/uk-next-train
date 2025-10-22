#!/usr/bin/env python3
import os
import sys
import json
import urllib.request
import argparse
from datetime import datetime, timedelta

# Global verbose flag
VERBOSE = False

def vprint(*args, **kwargs):
    """Print only in verbose mode"""
    if VERBOSE:
        print(*args, **kwargs)

def load_config(path):
    with open(path, 'r') as f:
        return json.load(f)

def send_telegram(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": message}).encode()
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = resp.read()
            vprint(f"✅ Telegram message sent successfully")
            return result
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return None

def is_time_in_range(current_time, start_time, end_time):
    """Check if current time is within the specified range"""
    start = datetime.strptime(start_time, '%H:%M').time()
    end = datetime.strptime(end_time, '%H:%M').time()
    current = datetime.strptime(current_time, '%H:%M').time()
    
    if start <= end:
        in_range = start <= current <= end
    else:  # Range crosses midnight
        in_range = current >= start or current <= end
    
    vprint(f"🕐 Time check: {current_time} in {start_time}-{end_time} = {in_range}")
    return in_range

def is_day_active(current_day, active_days):
    """Check if current day is in the active days list"""
    is_active = current_day.lower() in [day.lower() for day in active_days]
    vprint(f"📅 Day check: {current_day} in {active_days} = {is_active}")
    return is_active

def parse_delay_minutes(etd, std):
    """Parse delay in minutes from estimated vs scheduled time"""
    if etd == 'Delayed' or etd == 'On time':
        return 0
    
    try:
        etd_time = datetime.strptime(etd, '%H:%M')
        std_time = datetime.strptime(std, '%H:%M')
        
        # Handle next day times
        if etd_time < std_time:
            etd_time += timedelta(days=1)
            
        delay_minutes = (etd_time - std_time).total_seconds() / 60
        return int(delay_minutes)
    except:
        return 0

def check_trip(trip, config):
    """Check a specific trip configuration"""
    now = datetime.now()
    current_day = now.strftime('%A')  # Monday, Tuesday, etc.
    current_time = now.strftime('%H:%M')
    
    vprint(f"\n🚂 Checking trip: {trip['name']}")
    vprint(f"📍 Route: {trip['from']} → {trip['to']}")
    vprint(f"📅 Current: {current_day} {current_time}")
    
    # Check if today is an active day for this trip
    if not is_day_active(current_day, trip['days']):
        vprint(f"⏭️  Skipping - not an active day")
        return
    
    # Check if current time is within the monitoring window
    if not is_time_in_range(current_time, trip['time_start'], trip['time_end']):
        vprint(f"⏭️  Skipping - outside time window")
        return
    
    vprint(f"✅ Trip is active - checking trains...")
    
    # Fetch train data
    url = f"https://huxley2.azurewebsites.net/departures/{trip['from']}/to/{trip['to']}"
    vprint(f"🌐 API URL: {url}")
    
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            trains = data.get('trainServices', [])
            
            if not trains:
                vprint(f"📭 No trains found")
                return
            
            vprint(f"🚊 Found {len(trains)} trains:")
                
            # Check the next few trains for issues
            for i, train in enumerate(trains[:3]):  # Check first 3 trains
                train_time = train.get('std', 'Unknown')
                train_dest = train['destination'][0].get('locationName', trip['to']) if train.get('destination') else trip['to']
                etd = train.get('etd', train.get('std'))
                
                vprint(f"  {i+1}. {train_time} to {train_dest} - ETD: {etd}")
                
                issues = []
                
                # Check for cancellation
                if train.get('isCancelled') and trip['criteria'].get('notify_cancelled', True):
                    issues.append("CANCELLED")
                    vprint(f"    ❌ Train is cancelled")
                
                # Check for delays
                if trip['criteria'].get('notify_delayed', True) and not train.get('isCancelled'):
                    std = train.get('std')
                    
                    if etd == 'Delayed':
                        issues.append("DELAYED")
                        vprint(f"    ⏰ Train is delayed (unknown duration)")
                    elif etd != 'On time' and etd != std:
                        delay_mins = parse_delay_minutes(etd, std)
                        threshold = trip['criteria'].get('delay_threshold_minutes', 5)
                        
                        vprint(f"    ⏱️  Delay: {delay_mins}min (threshold: {threshold}min)")
                        
                        if delay_mins >= threshold:
                            issues.append(f"DELAYED {delay_mins}min")
                            vprint(f"    ⚠️  Exceeds threshold!")
                
                # Send notification if issues found
                if issues:
                    from_name = data.get('locationName', trip['from'])
                    
                    issue_text = " & ".join(issues)
                    
                    message = f"🚨 {trip['name']}\n"
                    message += f"Train {train_time} {from_name} → {train_dest}\n"
                    message += f"Status: {issue_text}"
                    
                    if train.get('platform'):
                        message += f"\nPlatform: {train['platform']}"
                    
                    vprint(f"🚨 ALERT: {issue_text}")
                    vprint(f"📱 Sending message: {message}")
                    
                    send_telegram(config['telegram_token'], config['telegram_chat_id'], message)
                    print(f"Alert sent for {trip['name']}: {issue_text}")
                    break  # Only alert for the first problematic train
                else:
                    vprint(f"    ✅ No issues")
                    
    except Exception as e:
        print(f"❌ Train API error for {trip['name']}: {e}")

def main():
    global VERBOSE
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Monitor UK trains and send Telegram notifications')
    parser.add_argument('-v', '--verbose', action='store_true', 
                       help='Enable verbose output for testing and debugging')
    args = parser.parse_args()
    
    VERBOSE = args.verbose
    
    if VERBOSE:
        print(f"🚂 UK Train Monitor - Verbose Mode")
        print(f"⏰ Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    
    try:
        config = load_config(config_path)
        vprint(f"📋 Loaded config with {len(config.get('trips', []))} trips")
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        sys.exit(1)
    
    # Process each trip configuration
    active_trips = 0
    for i, trip in enumerate(config.get('trips', [])):
        vprint(f"\n--- Trip {i+1}/{len(config['trips'])} ---")
        check_trip(trip, config)
        
        # Count active trips for summary
        now = datetime.now()
        current_day = now.strftime('%A')
        current_time = now.strftime('%H:%M')
        if (is_day_active(current_day, trip['days']) and 
            is_time_in_range(current_time, trip['time_start'], trip['time_end'])):
            active_trips += 1
    
    if VERBOSE:
        print(f"\n📊 Summary: {active_trips}/{len(config.get('trips', []))} trips currently active")
        print(f"✅ Monitoring complete")

if __name__ == '__main__':
    main()
