FROM ubuntu:latest
RUN apt update && apt install -y python3 python3-pip
WORKDIR /app
COPY . .
RUN pip3 install --break-system-packages -r requirements.txt 
ENTRYPOINT ["python3", "bot.py"]