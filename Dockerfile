FROM sitespeedio/sitespeed.io:22.0.0

RUN apt-get update && apt-get upgrade -y
RUN apt-get install -y python3-pip
RUN pip3 install --upgrade 'requests==2.20.0'
RUN pip3 install --upgrade 'pytz'

COPY launch.sh /
COPY minio_tests_reader.py /
COPY results_processing.py /
COPY util.py /

ENTRYPOINT ["/launch.sh"]