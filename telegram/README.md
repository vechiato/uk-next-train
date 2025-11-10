# Telegram Train Notification

This directory contains scripts to monitor UK train status and send Telegram alerts when criteria are met.

## Files
- `notify_train.py`: Checks train status and sends Telegram alerts based on configured criteria
- `config.json`: Configure multiple trips with days, time ranges, and notification criteria
- `config.json.example`: Configure example trips with days, time ranges, and notification criteria
- `setup_cron.sh`: Adds a cron job to run the notification script every 5 minutes
- `README.md`: This file

## Configuration

The `config.json` supports multiple trip configurations:

```json
{
  "telegram_token": "YOUR_BOT_TOKEN",
  "telegram_chat_id": "YOUR_CHAT_ID", 
  "trips": [
    {
      "name": "Morning Commute",
      "from": "BCE",
      "to": "WAT", 
      "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
      "time_start": "07:00",
      "time_end": "09:30",
      "criteria": {
        "notify_cancelled": true,
        "notify_delayed": true,
        "delay_threshold_minutes": 5
      }
    }
  ]
}
```

### Trip Configuration Options:
- `name`: Descriptive name for the trip
- `from`/`to`: Station codes (e.g., "BCE", "WAT")
- `days`: Array of days when monitoring is active (case-insensitive)
- `time_start`/`time_end`: Time range in HH:MM format (24-hour)
- `criteria`: Notification rules
  - `notify_cancelled`: Alert for cancelled trains
  - `notify_delayed`: Alert for delayed trains  
  - `notify_platform`: Alert when platform is assigned and train is on time
  - `delay_threshold_minutes`: Minimum delay to trigger alert

## Notification Logic

The script uses smart notification rules to avoid spam:

1. **Platform Assignment**: Notifies when a train is on time AND has a platform assigned (useful to know when to head to the platform)
2. **Delays**: Notifies when delays exceed the threshold
3. **Cancellations**: Notifies for cancelled trains
4. **Change Detection**: Only sends notifications when something changes (golden rule)
   - Won't send duplicate notifications for the same train status
   - Will notify again if delay increases (e.g., 10min → 15min delay)
   - Will notify if platform changes or other details update

Each trip maintains state in `.notification_state.json` to track what was last notified.

## Setup
1. Create a Telegram bot via @BotFather and get your bot token
2. Get your chat ID (message @userinfobot on Telegram)
3. Edit `config.json` with your details and trip configurations
4. Run `chmod +x setup_cron.sh && ./setup_cron.sh` to add the cron job

## Examples

### Weekday Commute Only
Monitor weekday morning and evening commutes with different delay thresholds.

### Weekend Monitoring  
Monitor weekend trips but only for cancellations, not delays.

### Multiple Routes
Configure different from/to combinations for various journeys.

## Notes
- Uses public Huxley2 API (no credentials required)
- Completely independent of your xbar plugin
- Logs output to `cron.log` in the same directory
- Smart duplicate detection prevents notification spam
- State file (`.notification_state.json`) tracks last notifications
- Only notifies when something meaningful changes
