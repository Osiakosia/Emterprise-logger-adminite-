# APP_NAME = "ccTalk Recycler Logger/Controller"
# VERSION = "1.1.0-enterprise"
@app.route("/meta.json")
def meta():
    with open("commands.json", "r") as f:
        commands = json.load(f)
    with open("events.json", "r") as f:
        events = json.load(f)

    return jsonify({
        "commands": commands,
        "events": events,
        "devices": {
            "2": "Coin acceptor",
            "3": "Hopper 1",
            "4": "Hopper 2",
            "5": "Hopper 3",
            "40": "Recycler",
            "80": "Dongle"
        }
    })