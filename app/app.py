import base64
import glob
import json
import logging
import os
import tempfile

import cv2

from flask import (
    Flask,
    jsonify,
    abort,
    make_response,
    request,
    send_file,
)
from fuzzywuzzy import process

from face.face_detection import select_face, select_face_update
from face.face_swap import face_swap
from utils.helpers import download_with_user_agent


NOT_FOUND = "Not found"
BAD_REQUEST = "Bad request"

app = Flask(__name__)

####################################################
# Load constants once
####################################################
if os.getenv("ENVIRONMENT", "") == "container":
    people_path = "/people/*.jpg"
    lookup_file = "/models/lookup.json"
else:
    people_path = "../people/*.jpg"
    lookup_file = "../models/lookup.json"
PEOPLE = [os.path.basename(person) for person in glob.glob(people_path)]
logging.basicConfig(level=logging.INFO)


@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({"error": NOT_FOUND}), 404)


@app.errorhandler(400)
def bad_request(error):
    return make_response(jsonify({"error": BAD_REQUEST}), 400)


@app.route("/status")
def get_health():
    return "Health Check OK", 200


@app.route("/image/<id>", methods=["GET"])
def image(id):
    id_decoded = base64.b64decode(bytes(id, "utf-8")).decode("utf-8")
    print(id_decoded)
    return send_file(id_decoded, mimetype="image/jpeg", attachment_filename="test.jpg")


@app.route("/swap", methods=["POST"])
def swap():

    if not request.form:
        abort(400)
    if not request.form["text"]:
        abort(400)

    logging.info(request.form)
    request_text = request.form["text"]
    request_text = request_text.replace("\xa0", " ")
    src_url = request_text.split(" ")[0]
    src_user = request_text.split(" ")[1]

    warp_2d = False
    correct_color = False

    if warp_2d in request_text.split(" "):
        warp_2d = True

    if correct_color in request_text.split(" "):
        correct_color = True

    logging.info(src_user)

    file_name = src_user.split("|")[1].replace(">", "").replace(".", " ").title() + ".jpg"

    logging.info(file_name)
    if os.path.isfile("../people/" + file_name):
        best_match = file_name
    else:  # Fuzzy match names
        best_match, _ = process.extractOne(src_user, PEOPLE)

    # Need to use a helper to download the images to fake a browser (some websites block straight downloads)
    with tempfile.NamedTemporaryFile(suffix=".jpg") as temp_url_source:
        download_with_user_agent(src_url, temp_url_source)
        url_image = cv2.imread(temp_url_source.name)

        person_image = cv2.imread("../people/" + best_match)

        src_img = person_image
        dst_img = url_image

        src_points, src_shape, src_face = select_face(src_img)  # Select src face
        dest_faces = select_face_update(dst_img)  # Select dst face

        if src_points is None:
            logging.info("Detect 0 Face !!!")
            abort(400)

        for face in dest_faces:
            dst_points, dst_shape, dst_face = face
            dst_img = face_swap(src_face, dst_face, src_points, dst_points, dst_shape, dst_img, warp_2d, correct_color)

        tmp_file = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        cv2.imwrite(tmp_file.name, dst_img)

        tmp_file_encoded = base64.b64encode(tmp_file.name.encode("utf-8")).decode("utf-8")

        json_return = jsonify(
            {
                "response_type": "in_channel",
                "attachments": [{"image_url": f"https://gary-robot.herokuapp.com/image/{tmp_file_encoded}"}],
            }
        )
        logging.info(tmp_file_encoded)

        return (
            json_return,
            200,
        )
    return make_response(jsonify({"error": BAD_REQUEST}), 400)


if __name__ == "__main__":
    app.run(debug=True)
