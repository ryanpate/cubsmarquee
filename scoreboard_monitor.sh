#!/bin/bash
# Cubs Scoreboard Monitor Script
# Provides easy commands to manage the scoreboard service

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SERVICE_NAME="cubs-scoreboard.service"

show_menu() {
    echo "================================="
    echo "  Cubs Scoreboard Manager v1.0"
    echo "================================="
    echo "1. Check Status"
    echo "2. Start Scoreboard"
    echo "3. Stop Scoreboard"
    echo "4. Restart Scoreboard"
    echo "5. View Live Logs"
    echo "6. View Error Logs"
    echo "7. Clear Old Logs"
    echo "8. Enable Auto-Start"
    echo "9. Disable Auto-Start"
    echo "10. Test Display (5 seconds)"
    echo "0. Exit"
    echo "================================="
}

check_status() {
    echo -e "${YELLOW}Checking scoreboard status...${NC}"
    sudo systemctl status $SERVICE_NAME --no-pager
    
    # Also check if the python process is running
    if pgrep -f "main.py" > /dev/null; then
        echo -e "${GREEN}✓ Scoreboard process is running${NC}"
    else
        echo -e "${RED}✗ Scoreboard process is not running${NC}"
    fi
}

start_scoreboard() {
    echo -e "${YELLOW}Starting scoreboard...${NC}"
    sudo systemctl start $SERVICE_NAME
    sleep 2
    check_status
}

stop_scoreboard() {
    echo -e "${YELLOW}Stopping scoreboard...${NC}"
    sudo systemctl stop $SERVICE_NAME
    # Also kill any orphaned processes
    sudo pkill -f "main.py"
    echo -e "${GREEN}Scoreboard stopped${NC}"
}

restart_scoreboard() {
    echo -e "${YELLOW}Restarting scoreboard...${NC}"
    sudo systemctl restart $SERVICE_NAME
    sleep 2
    check_status
}

view_logs() {
    echo -e "${YELLOW}Showing live logs (Ctrl+C to exit)...${NC}"
    sudo journalctl -u $SERVICE_NAME -f
}

view_error_logs() {
    echo -e "${YELLOW}Showing recent errors...${NC}"
    LOG_DIR="/home/pi/scoreboard_logs"
    if [ -d "$LOG_DIR" ]; then
        # Show last 50 lines of the most recent error log
        LATEST_ERROR_LOG=$(ls -t $LOG_DIR/scoreboard_error_*.log 2>/dev/null | head -1)
        if [ -n "$LATEST_ERROR_LOG" ]; then
            echo "From: $LATEST_ERROR_LOG"
            tail -50 "$LATEST_ERROR_LOG"
        else
            echo "No error logs found"
        fi
    else
        echo "Log directory not found"
    fi
}

clear_old_logs() {
    echo -e "${YELLOW}Clearing logs older than 7 days...${NC}"
    LOG_DIR="/home/pi/scoreboard_logs"
    if [ -d "$LOG_DIR" ]; then
        find "$LOG_DIR" -name "*.log" -mtime +7 -delete
        echo -e "${GREEN}Old logs cleared${NC}"
    else
        echo "Log directory not found"
    fi
}

enable_autostart() {
    echo -e "${YELLOW}Enabling auto-start at boot...${NC}"
    sudo systemctl enable $SERVICE_NAME
    echo -e "${GREEN}Auto-start enabled${NC}"
}

disable_autostart() {
    echo -e "${YELLOW}Disabling auto-start at boot...${NC}"
    sudo systemctl disable $SERVICE_NAME
    echo -e "${GREEN}Auto-start disabled${NC}"
}

test_display() {
    echo -e "${YELLOW}Running display test for 5 seconds...${NC}"
    # Create a simple test script
    cat > /tmp/test_display.py << 'EOF'
import time
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics

options = RGBMatrixOptions()
options.rows = 48
options.cols = 96
options.chain_length = 1
options.parallel = 1
options.hardware_mapping = 'regular'

matrix = RGBMatrix(options=options)
canvas = matrix.CreateFrameCanvas()

# Draw test pattern
for x in range(96):
    for y in range(48):
        if (x + y) % 2 == 0:
            canvas.SetPixel(x, y, 255, 0, 0)
        else:
            canvas.SetPixel(x, y, 0, 0, 255)

font = graphics.Font()
font.LoadFont("/home/pi/scoreboard_refactored/fonts/7x13B.bdf")
color = graphics.Color(255, 255, 255)
graphics.DrawText(canvas, font, 10, 25, color, "TEST OK")

canvas = matrix.SwapOnVSync(canvas)
time.sleep(5)
canvas.Clear()
matrix.SwapOnVSync(canvas)
print("Display test completed")
EOF
    
    sudo python3 /tmp/test_display.py
    rm /tmp/test_display.py
}

# Main loop
while true; do
    show_menu
    read -p "Select option: " choice
    
    case $choice in
        1) check_status ;;
        2) start_scoreboard ;;
        3) stop_scoreboard ;;
        4) restart_scoreboard ;;
        5) view_logs ;;
        6) view_error_logs ;;
        7) clear_old_logs ;;
        8) enable_autostart ;;
        9) disable_autostart ;;
        10) test_display ;;
        0) echo "Exiting..."; exit 0 ;;
        *) echo -e "${RED}Invalid option${NC}" ;;
    esac
    
    echo ""
    read -p "Press Enter to continue..."
    clear
done