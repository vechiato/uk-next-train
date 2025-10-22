#!/bin/bash
# UK Train Monitor - Cron Setup Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONITOR_SCRIPT="$SCRIPT_DIR/notify_train.py"
CONFIG_FILE="$SCRIPT_DIR/config.json"

echo "🚂 UK Train Monitor - Cron Setup"
echo "================================="

# Check if script exists
if [ ! -f "$MONITOR_SCRIPT" ]; then
    echo "❌ Error: train_monitor.py not found in $SCRIPT_DIR"
    exit 1
fi

# Make script executable
chmod +x "$MONITOR_SCRIPT"
echo "✅ Made train_monitor.py executable"

# Check if config exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "⚠️  Configuration file not found. Creating from example..."
    if [ -f "${CONFIG_FILE}.example" ]; then
        cp "${CONFIG_FILE}.example" "$CONFIG_FILE"
        echo "📝 Created $CONFIG_FILE from example"
        echo "⚠️  Please edit $CONFIG_FILE with your Telegram credentials!"
        echo ""
        echo "You need to:"
        echo "1. Create a Telegram bot (@BotFather)"
        echo "2. Get your chat ID"
        echo "3. Edit the config file with these values"
        echo ""
        exit 1
    else
        echo "❌ Error: No example config found"
        exit 1
    fi
fi

# # Test configuration
# echo "🧪 Testing configuration..."
# if python3 "$MONITOR_SCRIPT" --config "$CONFIG_FILE" --test; then
#     echo "✅ Configuration test successful!"
# else
#     echo "❌ Configuration test failed. Please check your Telegram credentials."
#     exit 1
# fi

echo ""
echo "📋 Cron Job Options:"
echo "==================="
echo ""
echo "1. Every 5 minutes during commute hours (7-10 AM, 5-8 PM):"
echo "   */5 7-9,17-19 * * 1-5 $MONITOR_SCRIPT --config $CONFIG_FILE"
echo ""
echo "2. Every 10 minutes during commute hours:"
echo "   */10 7-9,17-19 * * 1-5 $MONITOR_SCRIPT --config $CONFIG_FILE"
echo ""
echo "3. Every 5 minutes all day (weekdays only):"
echo "   */5 * * * 1-5 $MONITOR_SCRIPT --config $CONFIG_FILE"
echo ""
echo "4. Every 2 minutes during peak times:"
echo "   */2 8-9,18-19 * * 1-5 $MONITOR_SCRIPT --config $CONFIG_FILE"
echo ""

read -p "Select option (1-4) or press Enter to skip cron setup: " choice

case $choice in
    1)
        CRON_ENTRY="*/5 7-9,17-19 * * 1-5 $MONITOR_SCRIPT --config $CONFIG_FILE"
        ;;
    2)
        CRON_ENTRY="*/10 7-9,17-19 * * 1-5 $MONITOR_SCRIPT --config $CONFIG_FILE"
        ;;
    3)
        CRON_ENTRY="*/5 * * * 1-5 $MONITOR_SCRIPT --config $CONFIG_FILE"
        ;;
    4)
        CRON_ENTRY="*/2 8-9,18-19 * * 1-5 $MONITOR_SCRIPT --config $CONFIG_FILE"
        ;;
    "")
        echo "⏭️  Skipping cron setup"
        echo ""
        echo "To set up manually, add this to your crontab (crontab -e):"
        echo "*/5 7-9,17-19 * * 1-5 $MONITOR_SCRIPT --config $CONFIG_FILE"
        exit 0
        ;;
    *)
        echo "❌ Invalid option"
        exit 1
        ;;
esac

echo ""
echo "📅 Adding cron job..."

# Add to crontab
(crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -

if [ $? -eq 0 ]; then
    echo "✅ Cron job added successfully!"
    echo ""
    echo "Current crontab:"
    crontab -l | grep train_monitor
else
    echo "❌ Failed to add cron job"
    echo "You can add it manually with: crontab -e"
    echo "Add this line: $CRON_ENTRY"
fi

# Setup cron job for train notification
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/notify_train.py"
LOGFILE="$SCRIPT_DIR/cron.log"

# Example: run every 5 minutes
CRON="*/5 * * * * $PYTHON_SCRIPT >> $LOGFILE 2>&1"

# Add to user's crontab
(crontab -l 2>/dev/null; echo "$CRON") | crontab -
echo "Cron job added. Check $LOGFILE for output."

echo ""
echo "🎉 Setup complete!"
echo ""
echo "📊 To monitor logs:"
echo "   tail -f /var/log/cron.log"
echo "   (or check system logs for cron output)"
echo ""
echo "🧪 To test manually:"
echo "   $MONITOR_SCRIPT --config $CONFIG_FILE"
echo ""
echo "⚙️  To test configuration:"
echo "   $MONITOR_SCRIPT --config $CONFIG_FILE --test"