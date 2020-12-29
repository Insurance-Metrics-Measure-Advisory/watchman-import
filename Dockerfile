FROM rackspacedot/python37


#RUN pip install fastapi
#RUN pip install uvicorn

WORKDIR /
ADD . /
RUN pip install -r requirements.txt
RUN pip install pymongo
RUN python -m spacy download en_core_web_md

EXPOSE 8000
CMD ["uvicorn","watchmen.main:app","--host", "0.0.0.0", "--port", "80"]





