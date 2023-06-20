from time import sleep


from flask import Flask
from flask_restx import Api, Resource, Namespace

from src.phanos import profile_publisher

ns = Namespace("dummy")


class DummyDbAccess:
    @profile_publisher.profile
    def first_access(self):
        sleep(0.2)

    @profile_publisher.profile
    def second_access(self):
        self.first_access()
        sleep(0.3)


@ns.route("/one")
class DummyResource(Resource):
    access = DummyDbAccess()

    @profile_publisher.profile
    def get(self):
        self.access.first_access()
        self.access.second_access()
        return {"success": True}, 201


app = Flask(__name__)
api = Api(
    app,
    prefix="/api",
)
api.add_namespace(ns)
