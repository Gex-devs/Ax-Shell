if [ "$(playerctl -p spotify status 2>/dev/null | tr -d '[:space:]')" == "Playing" ] || \
   [ "$(playerctl -p spotify status 2>/dev/null | tr -d '[:space:]')" == "Paused" ]; then
    # Launch Glava in full-screen mode
    glava --verbose --desktop &
    sleep 0.2  # Ensure Glava initializes properly

    # Get the Glava window ID
    # GLAVA_WIN=$(xdotool search --onlyvisible --class "glava" | head -n 1)
    $GLAVA_WIN="Glava"

    # Make Glava fullscreen
    # if [[ -n "$GLAVA_WIN" ]]; then
        # hyprctl dispatch fullscreen "$GLAVA_WIN" 1
    # fi

    #Focus window 
    hyprctl dispatch focuswindow "title:$GLAVA_WIN"
    hyprctl dispatch movetoworkspace 1
    sleep 0.1
    hyprctl dispatch focuswindow "title:$GLAVA_WIN"
    hyprctl dispatch fullscreen 

    # Lock screen with music theme
    hyprlock --config ~/.config/hypr/hyprlock_music.conf -v

else
    # If music is not playing, just lock normally
    hyprlock -v
fi

sleep 0.1 
pkill glava
