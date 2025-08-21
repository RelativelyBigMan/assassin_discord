#!/bin/bash

#check if user exists
if id "assassin" &>/dev/null; then
    echo "User 'assassin' exists"
else
    useradd -m assassin && chown -R assassin /app
fi

exec su -s /bin/bash assassin -c "python3 bot.py"