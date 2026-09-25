import flask

app = flask.Flask(__name__)


@app.route("/health")
def health() -> str:
    return "ok"


def serve() -> None:
    app.run(debug=True)
