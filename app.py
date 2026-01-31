from flask import Flask, request, abort
from linebot.v3.exceptions import InvalidSignatureError
from handlers.line_webhook import handler 

app = Flask(__name__)

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"

if __name__ == "__main__":
    app.run(port=5000, debug=True)
