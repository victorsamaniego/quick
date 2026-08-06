import os
import eventlet
# ¡MUY IMPORTANTE! Esto debe ir antes de importar Flask
eventlet.monkey_patch()

from app import app, socketio

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=False)