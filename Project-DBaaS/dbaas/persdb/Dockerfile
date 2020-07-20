FROM base:latest
WORKDIR /app
COPY . /app
EXPOSE 8500
CMD ["/bin/sh","-c","cd /app && ([ ! -f persistent.db ] && python database.py); python db-service.py"]
