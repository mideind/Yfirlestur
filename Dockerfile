FROM ubuntu:latest
WORKDIR /usr/share/nginx/yfirlestur.is
COPY . .
RUN apt-get update
RUN apt-get install -y python3-pip postgresql-server-dev-all
RUN pip install -r requirements.txt
ENV DEBUG=True
ENV DEBUG_BIND_IP=0.0.0.0
EXPOSE 5002
CMD ./start.sh
