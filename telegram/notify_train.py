#!/usr/bin/env python3
import os
import sys
import json
import urllib.request
import argparse
import hashlib
from datetime import datetime, timedelta

# Global verbose flag
VERBOSE = False

# State file to track last notifications
STATE_FILE = os.path.join(os.path.dirname(__file__), '.notification_state.json')

def vprint(*args, **kwargs):
    """Print only in verbose mode"""
    if VERBOSE:
        print(*args, **kwargs)

def load_config(path):
    with open(path, 'r') as f:
        return json.load(f)

def load_state():
    """Load the last notification state"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
                vprint(f"📂 Loaded state with {len(state)} trip states")
                return state
        except:
            vprint(f"⚠️  Could not load state file, starting fresh")
            return {}
    vprint(f"📂 No state file found, starting fresh")
    return {}

def save_state(state):
    """Save the current notification state"""
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
        vprint(f"💾 State saved successfully")
    except Exception as e:
        print(f"⚠️  Could not save state: {e}")

def get_train_signature(trip_name, train):
    """Create a unique signature for a train's current state"""
    # Include key identifying and state information
    components = [
        trip_name,
        train.get('std', ''),  # Scheduled time
        train.get('etd', ''),  # Estimated time
        str(train.get('isCancelled', False)),
        train.get('platform', 'unknown')
    ]
    signature = '|'.join(components)
    return hashlib.md5(signature.encode()).hexdigest()

def should_notify_train(trip_name, train, last_state):
    """
    Determine if we should notify about this train.
    Returns: (should_notify, reason)
    """
    std = train.get('std', '')
    
    # Check if we have previous notification for this specific train time
    if last_state and last_state.get('train_time') == std:
        # Same train - check if signature changed
        current_signature = get_train_signature(trip_name, train)
        last_signature = last_state.get('signature')
        
        if current_signature == last_signature:
            return False, "duplicate"  # No change
        else:
            return True, "changed"  # Something changed
    elif last_state and last_state.get('train_time'):
        # Different train time
        # Check if last notification was recent (within 15 minutes)
        # to avoid spamming when trains pass and new ones appear
        last_time_str = last_state.get('timestamp', '')
        if last_time_str:
            try:
                from datetime import datetime
                last_time = datetime.strptime(last_time_str, '%Y-%m-%d %H:%M:%S')
                now = datetime.now()
                time_diff = (now - last_time).total_seconds() / 60  # minutes
                
                # If last notification was less than 10 minutes ago, be cautious
                # Only notify if it's for an earlier train (user might want to catch it)
                if time_diff < 10:
                    last_train_time = last_state.get('train_time', '')
                    if std > last_train_time:
                        # New train is later - probably don't need to notify yet
                        return False, "too_soon"
            except:
                pass
        
        return True, "new_train"
    else:
        # No previous state - first notification
        return True, "first_notification"


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

def check_trip(trip, config, state):
    """Check a specific trip configuration"""
    now = datetime.now()
    current_day = now.strftime('%A')  # Monday, Tuesday, etc.
    current_time = now.strftime('%H:%M')
    
    trip_name = trip['name']
    
    vprint(f"\n🚂 Checking trip: {trip_name}")
    vprint(f"📍 Route: {trip['from']} → {trip['to']}")
    vprint(f"📅 Current: {current_day} {current_time}")
    
    # Check if today is an active day for this trip
    if not is_day_active(current_day, trip['days']):
        vprint(f"⏭️  Skipping - not an active day")
        return state
    
    # Check if current time is within the monitoring window
    if not is_time_in_range(current_time, trip['time_start'], trip['time_end']):
        vprint(f"⏭️  Skipping - outside time window")
        return state
    
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
                return state
            
            vprint(f"🚊 Found {len(trains)} trains:")
                
            # Get last notification state for this trip
            last_state = state.get(trip_name, {})
            last_signature = last_state.get('signature')
            last_train_time = last_state.get('train_time')
            last_notified = last_state.get('timestamp')
            
            if last_notified:
                vprint(f"📌 Last notification: {last_notified} for {last_train_time} train")
            else:
                vprint(f"📌 No previous notification for this trip")
                
            # Check the next few trains for notification-worthy conditions
            for i, train in enumerate(trains[:3]):  # Check first 3 trains
                train_time = train.get('std', 'Unknown')
                train_dest = train['destination'][0].get('locationName', trip['to']) if train.get('destination') else trip['to']
                etd = train.get('etd', train.get('std'))
                platform = train.get('platform')
                is_cancelled = train.get('isCancelled', False)
                
                vprint(f"  {i+1}. {train_time} to {train_dest} - ETD: {etd} - Platform: {platform or 'TBC'}")
                
                # Determine if we should notify
                should_notify = False
                notification_reason = None
                
                # Rule 1: Train is cancelled or delayed
                if is_cancelled:
                    should_notify = True
                    notification_reason = "CANCELLED"
                    vprint(f"    ❌ Train is cancelled")
                    
                elif etd != 'On time' and etd != train.get('std'):
                    std = train.get('std')
                    delay_mins = parse_delay_minutes(etd, std)
                    threshold = trip['criteria'].get('delay_threshold_minutes', 5)
                    
                    vprint(f"    ⏱️  Delay: {delay_mins}min (threshold: {threshold}min)")
                    
                    if delay_mins >= threshold:
                        should_notify = True
                        notification_reason = f"DELAYED {delay_mins}min"
                        vprint(f"    ⚠️  Exceeds threshold!")
                
                # Rule 2: Train is on time with platform defined
                elif platform and trip['criteria'].get('notify_platform', True):
                    should_notify = True
                    notification_reason = f"ON TIME - Platform {platform}"
                    vprint(f"    🎯 On time with platform assigned")
                
                # Golden Rule: Check if this notification would be a duplicate
                if should_notify:
                    should_notify_result, reason = should_notify_train(trip_name, train, last_state)
                    
                    if not should_notify_result:
                        if reason == "duplicate":
                            vprint(f"    🔄 Duplicate notification detected - skipping")
                            vprint(f"       Train time: {train_time}, Last notified: {last_train_time}")
                            current_sig = get_train_signature(trip_name, train)
                            vprint(f"       Last: {last_signature}")
                            vprint(f"       Now:  {current_sig}")
                        elif reason == "too_soon":
                            vprint(f"    ⏱️  Too soon since last notification - skipping")
                            vprint(f"       This train: {train_time}, Last notified: {last_train_time}")
                        should_notify = False
                    else:
                        vprint(f"    ✨ Notification approved - {reason}")
                        if reason == "changed":
                            current_sig = get_train_signature(trip_name, train)
                            vprint(f"       Old signature: {last_signature}")
                            vprint(f"       New signature: {current_sig}")
                        elif reason == "new_train":
                            vprint(f"       Different train time: {train_time} (was {last_train_time})")
                        elif reason == "first_notification":
                            vprint(f"       First notification for this trip")
                
                # Send notification if conditions met
                if should_notify:
                    from_name = data.get('locationName', trip['from'])
                    
                    message = f"🚂 {trip_name}\n"
                    message += f"Train {train_time} {from_name} → {train_dest}\n"
                    
                    if is_cancelled:
                        message += f"Status: ❌ CANCELLED"
                    elif "DELAYED" in notification_reason:
                        delay_mins = parse_delay_minutes(etd, std)
                        message += f"Status: ⏰ DELAYED {delay_mins} minutes\n"
                        message += f"Expected: {etd}"
                    else:
                        message += f"Status: ✅ ON TIME"
                    
                    if platform:
                        message += f"\nPlatform: {platform}"
                    
                    vprint(f"🚨 ALERT: {notification_reason}")
                    vprint(f"📱 Sending message:\n{message}")
                    
                    send_telegram(config['telegram_token'], config['telegram_chat_id'], message)
                    print(f"Alert sent for {trip_name}: {notification_reason}")
                    
                    # Update state with new signature, timestamp, and train time
                    current_signature = get_train_signature(trip_name, train)
                    state[trip_name] = {
                        'signature': current_signature,
                        'train_time': train_time,
                        'timestamp': now.strftime('%Y-%m-%d %H:%M:%S'),
                        'reason': notification_reason
                    }
                    
                    break  # Only alert for the first relevant train
                else:
                    vprint(f"    ⏭️  No notification needed")
                    
    except Exception as e:
        print(f"❌ Train API error for {trip_name}: {e}")
    
    return state

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
    
    # Load notification state
    state = load_state()
    
    # Process each trip configuration
    active_trips = 0
    for i, trip in enumerate(config.get('trips', [])):
        vprint(f"\n--- Trip {i+1}/{len(config['trips'])} ---")
        state = check_trip(trip, config, state)
        
        # Count active trips for summary
        now = datetime.now()
        current_day = now.strftime('%A')
        current_time = now.strftime('%H:%M')
        if (is_day_active(current_day, trip['days']) and 
            is_time_in_range(current_time, trip['time_start'], trip['time_end'])):
            active_trips += 1
    
    # Save updated state
    save_state(state)
    
    if VERBOSE:
        print(f"\n📊 Summary: {active_trips}/{len(config.get('trips', []))} trips currently active")
        print(f"✅ Monitoring complete")

if __name__ == '__main__':
    main()
