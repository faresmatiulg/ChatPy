from flask import Flask, request, jsonify
from flask_cors import CORS
import pusher

app = Flask(__name__)
CORS(app)

pusher_client = pusher.Pusher(
  app_id='2064483',
  key='ebff80d16de6cdb1443e',
  secret='b1ae5b9b7f6a2365b73c',
  cluster='us2',
  ssl=True
)

@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.get_json()
    message = data.get('message')
    senderId = data.get('senderId')
    pusher_client.trigger('my-channel', 'my-event', {'message': message, 'senderId': senderId})
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    app.run(debug=True)
