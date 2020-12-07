# -*- coding: utf-8 -*-
import decorator
import flask
import json
import re
import requests
from stdnum import isbn as isbn_tool


app = flask.Flask(__name__)


@decorator.decorator
def enableCORS(func, *args, **kwargs):
    rv = func(*args, **kwargs)
    response = flask.make_response(rv)
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response


@app.route('/')
def index():
    return flask.render_template('index.html')


class LibrisObject:

    LIBRIS_API = {"libris_editions": "https://libris.kb.se/resource/bib/{}",
                  "libris_xl": "https://libris.kb.se/{}/data.jsonld"}

    def __init__(self, libris_id):
        self.libris_id = libris_id
        self.data = self.retrieve_libris_data()
        self.uri = self.extract_uri()
        self.librisxl_data = self.retrieve_librisxl_data()
        self.clean = self.process_libris_data()

    def delistify(self, somevalue):
        if isinstance(somevalue, list) and len(somevalue) == 1:
            while isinstance(somevalue, list):
                somevalue = somevalue[0]
        return somevalue

    def format_name(self, agent_dict):
        if agent_dict.get("familyName") and agent_dict.get("givenName"):
            full_name = "{} {}".format(agent_dict.get(
                "givenName"), agent_dict.get("familyName"))
        elif agent_dict.get("name"):
            full_name = agent_dict.get("name")
        return full_name

    def process_libris_data(self):
        clean = {}
        clean["libris_id"] = self.libris_id
        clean["libris_uri"] = self.uri
        clean["language"] = self.extract_language()
        clean["title"] = self.extract_title()
        clean["publication"] = self.extract_publication()
        clean["contributors"] = self.extract_contributors()
        clean["isbn"] = self.extract_isbn()
        clean["pages"] = self.extract_pages()
        return clean

    def extract_pages(self):
        required = ["s.", "s", "sidor",
                    "sid", "sid."]
        raw = self.librisxl_data[1]
        raw_extent = raw.get("extent")
        if raw_extent and raw_extent[0].get("label"):
            extent_labels = raw_extent[0]["label"]
            if len(extent_labels) != 1:
                return
            number_strings = re.findall(r"\d+", extent_labels[0])
            if (len(number_strings) == 1 and
                    any(x in extent_labels[0] for x in required)):
                return number_strings[0]

    def extract_isbn(self):
        isbns = []
        raw = self.librisxl_data[1].get("identifiedBy")
        if not raw:
            return
        raw_ids = [x for x in raw]
        for raw_id in raw_ids:
            if raw_id.get("@type").lower() == "isbn":
                raw_isbn = raw_id.get("value")
                isbn_type = isbn_tool.isbn_type(raw_isbn)
                if isbn_type:
                    formatted = isbn_tool.format(raw_isbn)
                    isbns.append(
                        {"type": isbn_type,
                         "value": formatted})
        return isbns

    def extract_uri(self):
        return self.data["@id"].split("/")[-1]

    def extract_contributors(self):
        contributors = []
        valid_roles = ["author", "illustrator", "translator", "editor"]
        raw = self.librisxl_data[1]
        contributor_data = raw.get("instanceOf").get("contribution")
        for raw_contributor in contributor_data:
            roles = raw_contributor.get("role")
            if not roles:
                if raw_contributor.get("@type") == "PrimaryContribution":
                    agent = raw_contributor.get("agent")
                    if agent.get("@id"):
                        person = agent.get("@id")
                    elif agent.get("@type") and agent.get("@type") == "Person":
                        person = self.format_name(agent)
                    contributors.append({"role": "author", "person": person})
            else:
                if not isinstance(roles, list):
                    roles = [roles]
                for role in roles:
                    person_role = role.get("@id").split("/")[-1]
                    if person_role in valid_roles:
                        agent = raw_contributor.get("agent")
                        if agent.get("@id"):
                            person = agent.get("@id")
                        elif (agent.get("@type") and
                              agent.get("@type") == "Person"):
                            person = self.format_name(agent)
                        contributors.append(
                            {"role": person_role, "person": person})
        return contributors

    def extract_title(self):
        raw = self.librisxl_data[1]
        has_subtitle = [x.get("subtitle") for x in raw.get(
            "hasTitle") if x.get("@type") == "Title"]
        has_main_title = [x.get("mainTitle") for x in raw.get(
            "hasTitle") if x.get("@type") == "Title"]
        return {"mainTitle": self.delistify(has_main_title),
                "subtitle": self.delistify(has_subtitle)}

    def extract_language(self):
        raw = self.librisxl_data[1]
        raw_language = raw.get("instanceOf").get("language")
        if raw_language:
            return raw_language[0].get("@id")

    def extract_publication(self):
        raw = self.librisxl_data[1]
        publication_data = [x for x in raw.get("publication") if
                            x.get("@type") == "PrimaryPublication"]
        if publication_data:
            publication = {}
            year = publication_data[0].get("year")
            place = publication_data[0].get("place")
            agent = publication_data[0].get("agent")
            if place:
                ort = [x.get("label") for x in place]
                if ort:
                    publication["place"] = self.delistify(ort)
            if agent:
                publisher = agent.get("label")
                if publisher:
                    publication["publisher"] = self.delistify(publisher)
            if year:
                publication["year"] = year
            return publication

    def retrieve_libris_data(self):
        headers = {'Accept': 'application/json'}
        url = self.LIBRIS_API["libris_editions"].format(self.libris_id)
        return json.loads(requests.get(url, headers=headers).text)

    def retrieve_librisxl_data(self):
        url = self.LIBRIS_API["libris_xl"].format(self.uri)
        return json.loads(requests.get(url).text).get("@graph")


@app.route('/api/<libris_id>')
@enableCORS
def api(libris_id):
    libris_object = LibrisObject(libris_id)
    return flask.jsonify(
        response=libris_object.clean,
    )
